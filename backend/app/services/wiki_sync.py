"""Синхронизация Wiki.js → локальная БД + эмбеддинг чанков.

Логика:
1. list_pages() — все опубликованные страницы из вики.
2. Для каждой:
   - hash контента сверяем с локальным WikiPage.content_hash.
   - Если совпадает — пропуск.
   - Если изменился (или страница новая) — get_page, чанкинг,
     эмбеддинг, апсерт (старые чанки удаляются).
3. Страницы, которых больше нет в вики, удаляются из локальной БД
   (cascade сносит и их чанки).

После любой записи в БД сбрасываем кэш ретривала (см. wiki_retrieval).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass

from sqlalchemy import select, delete

from app.database import async_session
from app.models.wiki import WikiPage, WikiChunk
from app.services import wiki_service
from app.services import embedding_service

logger = logging.getLogger(__name__)


# Целимся в чанки ~500-700 символов с overlap ~50. Для markdown это ~100-150
# слов на чанк — хороший компромисс между точностью retrieval и контекстом.
CHUNK_TARGET = 600
CHUNK_OVERLAP = 60
CHUNK_MIN_REMAINING = 120


@dataclass
class SyncResult:
    total_pages: int
    pages_changed: int
    pages_unchanged: int
    pages_deleted: int
    chunks_indexed: int
    elapsed_seconds: float
    errors: list[str]


def _hash_content(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _chunk_markdown(text: str) -> list[str]:
    """Простой режущий-по-границам чанкер для markdown.

    Бьём по двойному переводу (параграфы) или одинарному переводу строки.
    Каждый чанк — до CHUNK_TARGET символов. Между соседними — overlap из
    последних CHUNK_OVERLAP символов, чтобы не терять смысл на стыках.
    """
    text = text.strip()
    if not text:
        return []
    # Сначала разбиваем по параграфам.
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks: list[str] = []
    buf = ""

    def flush():
        nonlocal buf
        if buf.strip():
            chunks.append(buf.strip())
        buf = ""

    for para in paragraphs:
        if not buf:
            buf = para
        elif len(buf) + 2 + len(para) <= CHUNK_TARGET:
            buf += "\n\n" + para
        else:
            flush()
            buf = para
        # Если буфер перерос — режем длинный параграф на куски.
        while len(buf) > CHUNK_TARGET:
            cut = buf.rfind("\n", 0, CHUNK_TARGET)
            if cut < CHUNK_TARGET - 200:
                cut = CHUNK_TARGET
            chunks.append(buf[:cut].strip())
            tail = buf[max(0, cut - CHUNK_OVERLAP):].strip()
            buf = tail
    flush()
    return [c for c in chunks if c]


async def _delete_stale_pages(active_wiki_ids: set[int]) -> int:
    """Удалить локальные WikiPage, которых нет в вики (например, удалили автора)."""
    async with async_session() as session:
        r = await session.execute(select(WikiPage.id, WikiPage.wiki_id))
        rows = r.all()
        stale_local_ids = [
            local_id for (local_id, wiki_id) in rows if wiki_id not in active_wiki_ids
        ]
        if not stale_local_ids:
            return 0
        await session.execute(delete(WikiPage).where(WikiPage.id.in_(stale_local_ids)))
        await session.commit()
        return len(stale_local_ids)


async def _upsert_page(meta, content_text: str, updated_at) -> tuple[bool, int]:
    """Создать/обновить страницу. Возвращает (changed, chunks_count)."""
    h = _hash_content(content_text)
    async with async_session() as session:
        r = await session.execute(select(WikiPage).where(WikiPage.wiki_id == meta.id))
        page = r.scalar_one_or_none()
        if page and page.content_hash == h:
            return False, 0  # без изменений

        if not page:
            page = WikiPage(
                wiki_id=meta.id,
                path=meta.path,
                title=meta.title,
                locale=meta.locale,
                content=content_text,
                content_hash=h,
                wiki_updated_at=updated_at,
            )
            session.add(page)
            await session.flush()
        else:
            page.path = meta.path
            page.title = meta.title
            page.locale = meta.locale
            page.content = content_text
            page.content_hash = h
            page.wiki_updated_at = updated_at
            # старые чанки сносим перед перезаливкой
            await session.execute(delete(WikiChunk).where(WikiChunk.page_id == page.id))

        # Чанкинг + эмбеддинги. Для каждого чанка в текст ещё пристёгиваем
        # title — это помогает retrieval (запрос «как создать прайс» легче
        # матчится с чанком, у которого в начале есть заголовок страницы).
        title_prefix = f"{meta.title}\n\n" if meta.title else ""
        chunks = _chunk_markdown(content_text)
        prepared = [title_prefix + c for c in chunks]

        if prepared:
            vectors = await asyncio.to_thread(embedding_service.embed_passages, prepared)
            for i, (text, vec) in enumerate(zip(prepared, vectors)):
                session.add(WikiChunk(
                    page_id=page.id,
                    chunk_index=i,
                    text=text,
                    embedding=embedding_service.encode_to_bytes(vec),
                ))

        await session.commit()
        return True, len(prepared)


async def sync_wiki(limit: int | None = None) -> SyncResult:
    """Однократный синк. Если limit задан — обработать только первые N страниц
    (полезно для smoke-теста).
    """
    if not wiki_service.is_configured():
        logger.info("Wiki.js не настроен, синк пропущен")
        return SyncResult(0, 0, 0, 0, 0, 0.0, ["wiki_not_configured"])

    started = time.time()
    errors: list[str] = []
    metas = await asyncio.to_thread(wiki_service.list_pages)
    if limit is not None:
        metas = metas[:limit]

    active_ids = {m.id for m in metas}
    deleted = await _delete_stale_pages(active_ids)

    pages_changed = 0
    pages_unchanged = 0
    chunks_indexed = 0
    for meta in metas:
        try:
            full = await asyncio.to_thread(wiki_service.get_page, meta.id)
            if full is None:
                errors.append(f"page {meta.id}: get_page returned None")
                continue
            changed, n_chunks = await _upsert_page(meta, full.content, full.updated_at)
            if changed:
                pages_changed += 1
                chunks_indexed += n_chunks
                logger.info(
                    f"Wiki sync: страница #{meta.id} '{meta.title[:40]}' "
                    f"обновлена, {n_chunks} чанков"
                )
            else:
                pages_unchanged += 1
        except Exception as e:
            logger.exception(f"Wiki sync: ошибка на странице {meta.id}: {e}")
            errors.append(f"page {meta.id}: {type(e).__name__}: {e}")

    # Инвалидация in-memory кэша эмбеддингов (если что-то поменялось)
    if pages_changed or deleted:
        from app.services import wiki_retrieval
        wiki_retrieval.invalidate_cache()

    res = SyncResult(
        total_pages=len(metas),
        pages_changed=pages_changed,
        pages_unchanged=pages_unchanged,
        pages_deleted=deleted,
        chunks_indexed=chunks_indexed,
        elapsed_seconds=round(time.time() - started, 2),
        errors=errors,
    )
    logger.info(
        f"Wiki sync завершён за {res.elapsed_seconds:.1f}с: "
        f"всего={res.total_pages}, обновлено={res.pages_changed}, "
        f"без изменений={res.pages_unchanged}, удалено={res.pages_deleted}, "
        f"чанков проиндексировано={res.chunks_indexed}, ошибок={len(res.errors)}"
    )
    return res


def schedule_wiki_sync(aps_scheduler, interval_minutes: int = 60, initial_delay_seconds: int = 60):
    """Поставить периодический синк в APScheduler.

    Initial run через initial_delay_seconds, далее каждые interval_minutes.
    """
    from datetime import datetime, timedelta

    if not wiki_service.is_configured():
        logger.info("Wiki.js не настроен — авто-синк не планируем")
        return

    # Первый запуск
    aps_scheduler.add_job(
        sync_wiki, "date",
        run_date=datetime.now() + timedelta(seconds=initial_delay_seconds),
        id="wiki_sync_initial", replace_existing=True,
    )
    # Регулярный
    aps_scheduler.add_job(
        sync_wiki, "interval",
        minutes=interval_minutes,
        id="wiki_sync_recurring", replace_existing=True,
    )
    logger.info(
        f"Wiki sync: запланирован первичный через {initial_delay_seconds}с "
        f"+ каждые {interval_minutes} мин"
    )

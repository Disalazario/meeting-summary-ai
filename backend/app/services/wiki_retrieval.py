"""Top-K поиск по wiki-чанкам через cosine similarity.

Все эмбеддинги (l2-нормализованные float32, dim=768) держим в RAM как одну
большую матрицу — для 176 страниц × ~5 чанков это ~1000 × 768 × 4 = 3 МБ.
Запрос: один embed + один matmul → миллисекунды.

Кеш загружается лениво при первом поиске и сбрасывается через
`invalidate_cache()` из wiki_sync после изменения данных.
"""
from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass

import numpy as np
from sqlalchemy import select

from app.database import async_session
from app.models.wiki import WikiPage, WikiChunk
from app.services import embedding_service

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    page_id: int
    page_title: str
    page_path: str
    chunk_text: str
    score: float


_cache_lock = threading.Lock()
_cache: dict | None = None  # {"matrix": np.ndarray, "meta": list[...]}


def invalidate_cache():
    global _cache
    with _cache_lock:
        _cache = None
    logger.info("Wiki retrieval: кэш сброшен")


async def _load_cache():
    """Поднять все чанки в матрицу N×768."""
    global _cache
    async with async_session() as session:
        r = await session.execute(
            select(
                WikiChunk.embedding, WikiChunk.text, WikiChunk.chunk_index,
                WikiPage.id, WikiPage.title, WikiPage.path,
            ).join(WikiPage, WikiChunk.page_id == WikiPage.id)
        )
        rows = r.all()

    if not rows:
        with _cache_lock:
            _cache = {"matrix": np.zeros((0, embedding_service.EMBED_DIM), dtype=np.float32),
                      "meta": []}
        return

    vectors = np.stack(
        [embedding_service.decode_from_bytes(row[0]) for row in rows]
    ).astype(np.float32, copy=False)

    meta = [
        {"page_id": row[3], "page_title": row[4], "page_path": row[5],
         "chunk_text": row[1], "chunk_index": row[2]}
        for row in rows
    ]
    with _cache_lock:
        _cache = {"matrix": vectors, "meta": meta}
    logger.info(f"Wiki retrieval: кэш загружен, чанков={vectors.shape[0]}")


async def search(query: str, k: int = 5, min_score: float = 0.6) -> list[RetrievedChunk]:
    """Top-K релевантных чанков по запросу.

    min_score обрезает шум — на multilingual-e5 cosine ниже 0.6 обычно
    значит «не связано» и лучше отдать пустой ответ, чем галлюцинации.
    """
    global _cache
    if _cache is None:
        await _load_cache()
    if _cache is None or _cache["matrix"].shape[0] == 0:
        return []

    q_vec = await asyncio.to_thread(embedding_service.embed_query, query)
    # Уже l2-normalized → cosine = dot
    scores = _cache["matrix"] @ q_vec  # shape (N,)
    if scores.size == 0:
        return []
    # top-K по убыванию
    top_idx = np.argsort(-scores)[:k]
    out: list[RetrievedChunk] = []
    for i in top_idx:
        score = float(scores[i])
        if score < min_score:
            continue
        m = _cache["meta"][int(i)]
        out.append(RetrievedChunk(
            page_id=m["page_id"],
            page_title=m["page_title"],
            page_path=m["page_path"],
            chunk_text=m["chunk_text"],
            score=score,
        ))
    return out


def format_context_block(chunks: list[RetrievedChunk]) -> str:
    """Сформировать блок «Контекст из документации» для подкладки в промпт.

    Если чанков нет — пустая строка (промпт-строитель не вставит блок).
    """
    if not chunks:
        return ""
    parts = []
    for i, ch in enumerate(chunks, 1):
        parts.append(
            f"[{i}] {ch.page_title} (/{ch.page_path}, score={ch.score:.2f}):\n{ch.chunk_text}"
        )
    return "\n\n".join(parts)


async def build_context_for(query: str, k: int = 5) -> str:
    """Удобная свёртка: получить top-K и сразу вернуть форматированный блок.

    Возвращает пустую строку, если вики не настроена или ничего не нашлось.
    """
    from app.services import wiki_service
    if not wiki_service.is_configured():
        return ""
    try:
        chunks = await search(query, k=k)
    except Exception as e:
        logger.warning(f"Wiki retrieval failed: {e}")
        return ""
    return format_context_block(chunks)

"""Глобальный поиск по встречам.

Скоуп — три источника, объединённых:
- meetings.title
- summaries.brief  + summaries.summary_text
- transcript_segments.text

Тип — LIKE (case-insensitive, простой). Для масштаба десятки-сотни встреч это
~30-100ms на запрос; FTS5 — следующий шаг, когда станет узким местом.

Фильтр доступа `scope`:
- 'all'  — все встречи (соответствует open-access политике Dashboard);
- 'mine' — только встречи, где пользователь owner ИЛИ его display_name
           встречался среди распознанных спикеров.

Ответ — список встреч с snippet и match_in для UI-подсветки.
"""
import re
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select, or_, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.summary import Summary
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.services.auth_service import get_current_user

router = APIRouter()


class SearchResultItem(BaseModel):
    meeting_id: int
    title: str
    date: datetime | None = None
    duration_seconds: float | None = None
    status: str
    matched_in: list[str]   # ['title', 'summary', 'transcript']
    snippet: str | None = None  # фрагмент с подсветкой match


class SearchResponse(BaseModel):
    query: str
    scope: str
    total: int
    items: list[SearchResultItem]


def _snippet_around(text: str, q: str, window: int = 80) -> str | None:
    """Вырезать ~2*window символов вокруг первого вхождения q (без учёта регистра)."""
    if not text or not q:
        return None
    idx = text.lower().find(q.lower())
    if idx < 0:
        return None
    start = max(0, idx - window)
    end = min(len(text), idx + len(q) + window)
    snippet = text[start:end].strip()
    if start > 0:
        snippet = "…" + snippet
    if end < len(text):
        snippet = snippet + "…"
    # схлопнем переводы строк в один пробел — иначе ломает layout в карточке
    return re.sub(r"\s+", " ", snippet)


@router.get("", response_model=SearchResponse)
async def global_search(
    q: str = Query("", min_length=0, max_length=200),
    scope: str = Query("all", pattern="^(all|mine)$"),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (q or "").strip()
    if not query:
        return SearchResponse(query="", scope=scope, total=0, items=[])

    like = f"%{query}%"

    # Базовый список meeting_id, где где-то встретилось.
    # Делаем три отдельных запроса и объединяем — на нашем масштабе быстрее, чем хитрый UNION.
    title_ids: set[int] = set()
    summary_ids: set[int] = set()
    transcript_ids: set[int] = set()

    r = await db.execute(
        select(Meeting.id).where(Meeting.title.ilike(like)).limit(200)
    )
    title_ids = {row[0] for row in r.all()}

    r = await db.execute(
        select(Summary.meeting_id).where(
            or_(Summary.brief.ilike(like), Summary.summary_text.ilike(like))
        ).limit(200)
    )
    summary_ids = {row[0] for row in r.all()}

    r = await db.execute(
        select(distinct(TranscriptSegment.meeting_id))
        .where(TranscriptSegment.text.ilike(like))
        .limit(200)
    )
    transcript_ids = {row[0] for row in r.all()}

    all_ids = title_ids | summary_ids | transcript_ids
    if not all_ids:
        return SearchResponse(query=query, scope=scope, total=0, items=[])

    # Фильтр scope: 'mine' — owner ИЛИ user.display_name среди спикеров встречи.
    if scope == "mine":
        mine_q = select(Meeting.id).where(Meeting.id.in_(all_ids)).where(
            or_(
                Meeting.owner_id == user.id,
                Meeting.id.in_(
                    select(distinct(TranscriptSegment.meeting_id)).where(
                        TranscriptSegment.speaker_label.ilike(user.display_name or user.username)
                    )
                ),
            )
        )
        r = await db.execute(mine_q)
        all_ids = {row[0] for row in r.all()}
        if not all_ids:
            return SearchResponse(query=query, scope=scope, total=0, items=[])

    # Загрузить встречи + краткий саммари для snippet (один сводный запрос).
    r = await db.execute(
        select(Meeting, Summary)
        .outerjoin(Summary, Summary.meeting_id == Meeting.id)
        .where(Meeting.id.in_(all_ids))
        .order_by(Meeting.date.desc().nullslast(), Meeting.created_at.desc())
        .limit(limit)
    )
    rows = r.all()

    items: list[SearchResultItem] = []
    for m, s in rows:
        matched_in: list[str] = []
        snippet: str | None = None
        if m.id in title_ids:
            matched_in.append("title")
        if m.id in summary_ids:
            matched_in.append("summary")
            if s:
                snippet = (
                    _snippet_around(s.brief or "", query)
                    or _snippet_around(s.summary_text or "", query)
                )
        if m.id in transcript_ids:
            matched_in.append("transcript")
            # snippet из транскрипта — отдельным запросом (берём ОДИН лучший сегмент).
            if not snippet:
                seg_r = await db.execute(
                    select(TranscriptSegment.text)
                    .where(
                        TranscriptSegment.meeting_id == m.id,
                        TranscriptSegment.text.ilike(like),
                    ).limit(1)
                )
                seg_row = seg_r.first()
                if seg_row:
                    snippet = _snippet_around(seg_row[0], query)

        items.append(SearchResultItem(
            meeting_id=m.id,
            title=m.title,
            date=m.date,
            duration_seconds=m.duration_seconds,
            status=m.status,
            matched_in=matched_in,
            snippet=snippet,
        ))

    return SearchResponse(query=query, scope=scope, total=len(items), items=items)

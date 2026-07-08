"""Wiki RAG: статус локального индекса + ручной запуск синхронизации.

Доступ для админов (роль 'admin'), потому что синк тяжёлый (qwen-уровень
тяжести по эмбеддингам) и потенциально может временно нагружать GPU.
"""
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, func

from app.database import get_db
from app.models.wiki import WikiPage, WikiChunk
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services import wiki_service, wiki_sync

logger = logging.getLogger(__name__)
router = APIRouter()


class WikiStatusResponse(BaseModel):
    configured: bool
    base_url: str
    total_pages: int
    total_chunks: int
    last_indexed_at: datetime | None = None
    last_sync_summary: str | None = None


class WikiSyncResultResponse(BaseModel):
    total_pages: int
    pages_changed: int
    pages_unchanged: int
    pages_deleted: int
    chunks_indexed: int
    elapsed_seconds: float
    errors: list[str]


_LAST_SYNC_SUMMARY: str | None = None


def _admin_only(user: User):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Только для администраторов")


@router.get("/status", response_model=WikiStatusResponse)
async def get_wiki_status(
    user: User = Depends(get_current_user),
    db=Depends(get_db),
):
    total_pages = (await db.execute(select(func.count(WikiPage.id)))).scalar() or 0
    total_chunks = (await db.execute(select(func.count(WikiChunk.id)))).scalar() or 0
    last = (
        await db.execute(select(func.max(WikiPage.indexed_at)))
    ).scalar()
    return WikiStatusResponse(
        configured=wiki_service.is_configured(),
        base_url=("[hidden]" if wiki_service.is_configured() else ""),
        total_pages=int(total_pages),
        total_chunks=int(total_chunks),
        last_indexed_at=last,
        last_sync_summary=_LAST_SYNC_SUMMARY,
    )


@router.post("/sync", response_model=WikiSyncResultResponse)
async def trigger_wiki_sync(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Запустить полную синхронизацию вики прямо сейчас (admin only)."""
    _admin_only(user)
    if not wiki_service.is_configured():
        raise HTTPException(status_code=400, detail="Wiki.js не настроен")
    logger.info(f"Manual wiki sync triggered by {user.username}")
    res = await wiki_sync.sync_wiki()
    global _LAST_SYNC_SUMMARY
    _LAST_SYNC_SUMMARY = (
        f"{datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC: "
        f"обновлено={res.pages_changed}, без изменений={res.pages_unchanged}, "
        f"удалено={res.pages_deleted}, чанков={res.chunks_indexed}, "
        f"за {res.elapsed_seconds:.1f}с"
    )
    return WikiSyncResultResponse(
        total_pages=res.total_pages,
        pages_changed=res.pages_changed,
        pages_unchanged=res.pages_unchanged,
        pages_deleted=res.pages_deleted,
        chunks_indexed=res.chunks_indexed,
        elapsed_seconds=res.elapsed_seconds,
        errors=res.errors,
    )

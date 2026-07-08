"""Заметки участников по встречам.

Каждый аутентифицированный пользователь может вести свои заметки по любой
встрече. Когда у автора встречи (owner) есть заметки — пайплайн обработки
после генерации саммари делает доп. LLM-проход и обогащает их контекстом
из транскрипта (enriched_content).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.meeting import Meeting
from app.models.note import MeetingNote
from app.models.user import User
from app.schemas.note import (
    MeetingNoteAuthor, MeetingNoteResponse, MeetingNoteUpdateRequest,
    MyMeetingNoteResponse,
)
from app.services.auth_service import get_current_user

router = APIRouter()


async def _ensure_meeting_exists(db: AsyncSession, meeting_id: int) -> Meeting:
    result = await db.execute(select(Meeting).where(Meeting.id == meeting_id))
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")
    return meeting


@router.get("/{meeting_id}/notes/me", response_model=MyMeetingNoteResponse)
async def get_my_note(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Получить мои заметки по этой встрече (или пустую заглушку)."""
    await _ensure_meeting_exists(db, meeting_id)
    result = await db.execute(
        select(MeetingNote).where(
            MeetingNote.meeting_id == meeting_id,
            MeetingNote.user_id == user.id,
        )
    )
    note = result.scalar_one_or_none()
    if note is None:
        return MyMeetingNoteResponse(content="", enriched_content=None,
                                     enriched_at=None, updated_at=None)
    return MyMeetingNoteResponse(
        content=note.content,
        enriched_content=note.enriched_content,
        enriched_at=note.enriched_at,
        updated_at=note.updated_at,
    )


@router.put("/{meeting_id}/notes/me", response_model=MyMeetingNoteResponse)
async def upsert_my_note(
    meeting_id: int,
    data: MeetingNoteUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Сохранить (создать или обновить) свои заметки по встрече."""
    await _ensure_meeting_exists(db, meeting_id)

    result = await db.execute(
        select(MeetingNote).where(
            MeetingNote.meeting_id == meeting_id,
            MeetingNote.user_id == user.id,
        )
    )
    note = result.scalar_one_or_none()

    if note is None:
        note = MeetingNote(
            meeting_id=meeting_id,
            user_id=user.id,
            content=data.content,
        )
        db.add(note)
    else:
        if note.content != data.content:
            # Меняется ручной текст → старое AI-обогащение устарело.
            note.content = data.content
            note.enriched_content = None
            note.enriched_at = None

    await db.commit()
    await db.refresh(note)
    return MyMeetingNoteResponse(
        content=note.content,
        enriched_content=note.enriched_content,
        enriched_at=note.enriched_at,
        updated_at=note.updated_at,
    )


@router.get("/{meeting_id}/notes", response_model=list[MeetingNoteResponse])
async def list_notes(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список всех заметок участников по встрече.

    Открытый доступ соответствует политике open access для встреч —
    любой аутентифицированный пользователь видит все заметки.
    """
    await _ensure_meeting_exists(db, meeting_id)
    result = await db.execute(
        select(MeetingNote)
        .options(selectinload(MeetingNote.user))
        .where(MeetingNote.meeting_id == meeting_id)
        .order_by(MeetingNote.updated_at.desc())
    )
    notes = list(result.scalars().all())
    return [
        MeetingNoteResponse(
            id=n.id,
            meeting_id=n.meeting_id,
            content=n.content,
            enriched_content=n.enriched_content,
            enriched_at=n.enriched_at,
            updated_at=n.updated_at,
            author=MeetingNoteAuthor(
                id=n.user.id,
                display_name=n.user.display_name or n.user.username,
            ),
        )
        for n in notes
        # Не показываем пустые «черновики», которые юзер открыл и закрыл
        if (n.content or "").strip()
    ]

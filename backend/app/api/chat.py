import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatMessageResponse, ChatResponse
from app.services.auth_service import get_current_user
from app.services.processing import _format_timestamp

router = APIRouter()


@router.post("/{meeting_id}/chat", response_model=ChatResponse)
async def send_message(
    meeting_id: int,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    # Build transcript text
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    segments = result.scalars().all()
    if not segments:
        raise HTTPException(status_code=400, detail="Расшифровка ещё не готова")

    lines = []
    for seg in segments:
        start = _format_timestamp(seg.start_time)
        end = _format_timestamp(seg.end_time)
        lines.append(f"[{start} - {end}] {seg.speaker_label}:\n{seg.text}\n")
    transcript_text = "\n".join(lines)

    # Load chat history
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.meeting_id == meeting_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at)
    )
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]

    # Call LLM
    from app.services.llm_service import LLMService
    llm = LLMService()
    # Wiki RAG — берём релевантные фрагменты по тексту вопроса пользователя.
    try:
        from app.services.wiki_retrieval import build_context_for
        llm.wiki_context = await build_context_for(data.message, k=5)
    except Exception:
        llm.wiki_context = ""
    response = await asyncio.to_thread(llm.chat, transcript_text, history, data.message)

    # Save messages
    db.add(ChatMessage(
        meeting_id=meeting_id, user_id=user.id, role="user", content=data.message,
    ))
    db.add(ChatMessage(
        meeting_id=meeting_id, user_id=user.id, role="assistant", content=response,
    ))
    await db.commit()

    return ChatResponse(response=response)


@router.get("/{meeting_id}/chat/history", response_model=list[ChatMessageResponse])
async def get_chat_history(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.meeting_id == meeting_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


async def _check_meeting(db: AsyncSession, meeting_id: int, user_id: int):
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")
    return meeting

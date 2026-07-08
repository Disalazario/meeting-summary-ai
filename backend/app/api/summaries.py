import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.summary import Summary
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.schemas.summary import SummaryResponse
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/{meeting_id}/summary", response_model=SummaryResponse)
async def get_summary(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    result = await db.execute(
        select(Summary).where(Summary.meeting_id == meeting_id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="Саммари ещё не готово")

    # Parse key_decisions from JSON string
    key_decisions = []
    if summary.key_decisions:
        try:
            key_decisions = json.loads(summary.key_decisions)
        except json.JSONDecodeError:
            key_decisions = []

    # Parse topics from JSON string
    topics = None
    if summary.topics:
        try:
            topics = json.loads(summary.topics)
        except json.JSONDecodeError:
            topics = None

    return SummaryResponse(
        id=summary.id,
        summary_text=summary.summary_text,
        brief=summary.brief,
        key_decisions=key_decisions,
        topics=topics,
    )


@router.post("/{meeting_id}/summary/regenerate", response_model=SummaryResponse)
async def regenerate_summary(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    # Get transcript
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    segments = result.scalars().all()
    if not segments:
        raise HTTPException(status_code=400, detail="Нет расшифровки для перегенерации")

    # Build transcript text
    from app.services.processing import _format_timestamp
    lines = []
    for seg in segments:
        start = _format_timestamp(seg.start_time)
        end = _format_timestamp(seg.end_time)
        lines.append(f"[{start} - {end}] {seg.speaker_label}:\n{seg.text}\n")
    transcript_text = "\n".join(lines)

    # Regenerate
    from app.services.llm_service import LLMService
    llm = LLMService()
    summary_result = await asyncio.to_thread(llm.generate_summary, transcript_text)

    # Update or create summary
    result = await db.execute(select(Summary).where(Summary.meeting_id == meeting_id))
    summary = result.scalar_one_or_none()
    if summary:
        summary.summary_text = summary_result.summary
        summary.brief = summary_result.brief
        summary.key_decisions = json.dumps(summary_result.key_decisions, ensure_ascii=False)
        await db.commit()
    else:
        summary = Summary(
            meeting_id=meeting_id,
            summary_text=summary_result.summary,
            brief=summary_result.brief,
            key_decisions=json.dumps(summary_result.key_decisions, ensure_ascii=False),
        )
        db.add(summary)
        await db.commit()
        await db.refresh(summary)

    key_decisions = summary_result.key_decisions

    return SummaryResponse(
        id=summary.id,
        summary_text=summary.summary_text,
        brief=summary.brief,
        key_decisions=key_decisions,
    )


async def _check_meeting(db: AsyncSession, meeting_id: int, user_id: int):
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")
    return meeting

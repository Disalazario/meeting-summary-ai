from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.schemas.transcript import TranscriptSegmentResponse, SpeakerRenameRequest
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/{meeting_id}/transcript", response_model=list[TranscriptSegmentResponse])
async def get_transcript(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Check ownership
    meeting = await _check_meeting(db, meeting_id, user.id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Совещание не найдено")

    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    return result.scalars().all()


@router.patch("/{meeting_id}/speakers")
async def rename_speakers(
    meeting_id: int,
    data: SpeakerRenameRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meeting = await _check_meeting(db, meeting_id, user.id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Совещание не найдено")

    result = await db.execute(
        select(TranscriptSegment).where(TranscriptSegment.meeting_id == meeting_id)
    )
    segments = result.scalars().all()

    updated = 0
    for seg in segments:
        if seg.speaker_label in data.speakers:
            seg.speaker_label = data.speakers[seg.speaker_label]
            updated += 1

    await db.commit()
    return {"updated": updated}


async def _check_meeting(db: AsyncSession, meeting_id: int, user_id: int):
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    return result.scalar_one_or_none()

"""Голосовые профили: enrollment, статус, удаление.

POST /api/users/{user_id}/voice/enroll — загрузить аудио (10–60 сек),
    извлечь embedding и сохранить как profile.
GET  /api/users/{user_id}/voice         — есть ли profile + дата обновления.
DELETE /api/users/{user_id}/voice       — удалить profile.

Пользователь может управлять только своим профилем. Админ — любым.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.models.voice_profile import VoiceProfile
from app.schemas.voice_profile import VoiceProfileStatus
from app.services.audio_service import preprocess_audio
from app.services.auth_service import get_current_user
from app.services.speaker_embedding import get_extractor, serialize

logger = logging.getLogger(__name__)
router = APIRouter()

# Ограничения для записи enrollment
MAX_ENROLL_SIZE_MB = 20
MIN_DURATION_SEC = 5.0
MAX_DURATION_SEC = 90.0


def _check_owner_or_admin(target_user_id: int, current: User):
    if current.id == target_user_id or current.role == "admin":
        return
    raise HTTPException(403, "Можно управлять только своим голосовым профилем")


async def _load_user(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(404, "Пользователь не найден")
    return user


@router.get("/{user_id}/voice", response_model=VoiceProfileStatus)
async def get_voice_status(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _check_owner_or_admin(user_id, current)
    await _load_user(db, user_id)
    result = await db.execute(
        select(VoiceProfile).where(VoiceProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        return VoiceProfileStatus(enrolled=False)
    return VoiceProfileStatus(
        enrolled=True,
        sample_count=profile.sample_count,
        updated_at=profile.updated_at,
    )


@router.post("/{user_id}/voice/enroll", response_model=VoiceProfileStatus)
async def enroll_voice(
    user_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _check_owner_or_admin(user_id, current)
    user = await _load_user(db, user_id)

    # Validate size
    max_bytes = MAX_ENROLL_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(400, f"Файл слишком большой (макс {MAX_ENROLL_SIZE_MB} МБ)")
    if not content:
        raise HTTPException(400, "Пустой файл")

    # Сохранить во временную папку и конвертировать в WAV 16kHz mono
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        ext = Path(file.filename or "audio.webm").suffix or ".webm"
        src = tmpdir_path / f"src{ext}"
        src.write_bytes(content)

        try:
            wav_path, duration = await preprocess_audio(src)
        except RuntimeError as e:
            logger.error(f"ffmpeg failed during enroll for user {user_id}: {e}")
            raise HTTPException(400, "Не удалось декодировать аудио")

        if duration < MIN_DURATION_SEC:
            raise HTTPException(
                400, f"Запись слишком короткая (нужно ≥{int(MIN_DURATION_SEC)} сек)"
            )
        if duration > MAX_DURATION_SEC:
            logger.info(f"Enroll {user.username}: запись {duration:.1f}с обрезается до {MAX_DURATION_SEC}с")

        # Извлечь embedding (синхронно, тяжёлая операция → thread)
        try:
            extractor = get_extractor()
            embedding = await asyncio.to_thread(
                extractor.extract_segment, wav_path, 0.0, min(duration, MAX_DURATION_SEC)
            )
        except Exception as e:
            logger.exception(f"Embedding extraction failed for user {user_id}: {e}")
            raise HTTPException(500, "Ошибка извлечения голосового отпечатка")

    # Upsert profile
    result = await db.execute(
        select(VoiceProfile).where(VoiceProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    blob = serialize(embedding)
    if profile is None:
        profile = VoiceProfile(user_id=user_id, embedding=blob, sample_count=1)
        db.add(profile)
    else:
        profile.embedding = blob
        profile.sample_count = 1  # явный re-enroll начинает счёт заново
    await db.commit()
    await db.refresh(profile)

    logger.info(f"Голосовой профиль сохранён: user={user.username} ({len(embedding)}-dim)")
    return VoiceProfileStatus(
        enrolled=True,
        sample_count=profile.sample_count,
        updated_at=profile.updated_at,
    )


@router.delete("/{user_id}/voice", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voice(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current: User = Depends(get_current_user),
):
    _check_owner_or_admin(user_id, current)
    await _load_user(db, user_id)
    result = await db.execute(
        select(VoiceProfile).where(VoiceProfile.user_id == user_id)
    )
    profile = result.scalar_one_or_none()
    if profile is not None:
        await db.delete(profile)
        await db.commit()

import asyncio
import shutil
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import FileResponse
from sqlalchemy import select, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.meeting import Meeting
from app.models.transcript import TranscriptSegment
from app.models.user import User
from app.schemas.meeting import MeetingResponse, MeetingListItem
from app.services.auth_service import get_current_user
from app.services.audio_service import validate_audio_extension

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def upload_meeting(
    file: UploadFile = File(...),
    title: str = Form(...),
    date: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Validate extension
    if not file.filename or not validate_audio_extension(file.filename):
        raise HTTPException(
            status_code=400,
            detail="Неподдерживаемый формат файла. Допустимые: mp3, mp4, wav, ogg, opus, webm, m4a, mkv, aac, flac",
        )

    # Validate size
    max_size = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    content = await file.read()
    if len(content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"Файл слишком большой. Максимум: {settings.MAX_UPLOAD_SIZE_MB}MB",
        )

    # Parse date
    meeting_date = None
    if date:
        try:
            meeting_date = datetime.fromisoformat(date)
        except ValueError:
            meeting_date = datetime.utcnow()

    # Create meeting record
    ext = Path(file.filename).suffix
    meeting = Meeting(
        title=title,
        date=meeting_date or datetime.utcnow(),
        status="uploaded",
        audio_path="",  # will be set after save
        owner_id=user.id,
    )
    db.add(meeting)
    await db.flush()
    await db.refresh(meeting)

    # Save file
    meeting_dir = settings.UPLOAD_DIR / str(meeting.id)
    meeting_dir.mkdir(parents=True, exist_ok=True)
    file_path = meeting_dir / f"original{ext}"
    file_path.write_bytes(content)

    meeting.audio_path = str(file_path)
    await db.flush()

    # Поставить в очередь обработки (последовательная — Whisper+Ollama делят GPU).
    # Запись бота параллельная, обработка — нет.
    from app.services.processing import enqueue_meeting_processing
    await enqueue_meeting_processing(meeting.id)

    size_mb = len(content) / 1024 / 1024
    logger.info(
        f"Совещание {meeting.id} загружено: '{title}', файл={file.filename} ({size_mb:.1f} MB), "
        f"пользователь={user.username}, обработка запущена"
    )
    return meeting


async def _meetings_user_participated_in(db: AsyncSession, display_name: str) -> set[int]:
    """ID встреч, где `display_name` есть среди распознанных спикеров.

    Сравнение case-insensitive по trimmed display_name.
    """
    target = display_name.strip().lower()
    if not target:
        return set()
    result = await db.execute(
        select(distinct(TranscriptSegment.meeting_id), TranscriptSegment.speaker_label)
    )
    ids: set[int] = set()
    for mid, label in result.all():
        if label and label.strip().lower() == target:
            ids.add(mid)
    return ids


async def _attach_user_context(
    db: AsyncSession, meetings: list[Meeting], current_user: User,
) -> list[dict]:
    """Дополнить каждое совещание полями owner_name / is_owner / participated."""
    if not meetings:
        return []

    owner_ids = {m.owner_id for m in meetings}
    owners_result = await db.execute(select(User).where(User.id.in_(owner_ids)))
    owner_map = {u.id: u.display_name for u in owners_result.scalars()}

    participated_ids = await _meetings_user_participated_in(db, current_user.display_name)

    out = []
    for m in meetings:
        d = {
            "id": m.id, "title": m.title, "date": m.date, "status": m.status,
            "error_message": m.error_message,
            "processing_progress": m.processing_progress,
            "processing_eta_seconds": m.processing_eta_seconds,
            "duration_seconds": m.duration_seconds,
            "source": m.source, "meeting_url": m.meeting_url,
            "owner_id": m.owner_id, "created_at": m.created_at,
            "owner_name": owner_map.get(m.owner_id),
            "is_owner": m.owner_id == current_user.id,
            "participated": m.id in participated_ids,
        }
        out.append(d)
    return out


@router.get("", response_model=list[MeetingListItem])
async def list_meetings(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Все совещания (open access). Опциональный поиск по названию (substring, case-insensitive)."""
    stmt = select(Meeting).order_by(Meeting.date.desc())
    if search:
        s = f"%{search.strip()}%"
        stmt = stmt.where(Meeting.title.ilike(s))
    result = await db.execute(stmt)
    meetings = list(result.scalars().all())
    return await _attach_user_context(db, meetings, user)


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meeting = await _get_meeting(db, meeting_id)
    ctx = await _attach_user_context(db, [meeting], user)
    return ctx[0]


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить совещание — разрешено только владельцу или админу."""
    meeting = await _get_meeting(db, meeting_id)
    if meeting.owner_id != user.id and user.role != "admin":
        raise HTTPException(403, "Удалять совещание может только его владелец или администратор")

    # Delete files
    meeting_dir = settings.UPLOAD_DIR / str(meeting.id)
    if meeting_dir.exists():
        shutil.rmtree(meeting_dir)

    await db.delete(meeting)
    await db.commit()


async def _ensure_opus_for_meeting(meeting_id: int, source_wav: Path) -> Path | None:
    """Создать (если ещё нет) сжатую Opus-копию аудио в каталоге встречи.

    Opus 32 kbps mono ≈ в 10–15 раз меньше WAV при качестве, неотличимом
    от оригинала для голоса. Используется для быстрого скачивания через
    домашний upload-канал.
    """
    audio_dir = settings.UPLOAD_DIR / str(meeting_id)
    opus_path = (audio_dir / "audio.opus").resolve()
    upload_root = settings.UPLOAD_DIR.resolve()
    if not str(opus_path).startswith(str(upload_root)):
        return None

    if opus_path.exists() and opus_path.stat().st_size > 0:
        # Если кешированный opus новее источника — берём кеш
        try:
            if opus_path.stat().st_mtime >= source_wav.stat().st_mtime:
                return opus_path
        except FileNotFoundError:
            return opus_path

    logger.info(f"[meeting:{meeting_id}] Кодирование audio.opus из {source_wav.name}...")
    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-y", "-i", str(source_wav),
        "-vn",
        "-c:a", "libopus", "-b:a", "32k", "-ac", "1", "-application", "voip",
        "-f", "ogg", str(opus_path),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        logger.error(f"[meeting:{meeting_id}] ffmpeg opus encode failed: {stderr.decode()[:300]}")
        return None
    size_mb = opus_path.stat().st_size / 1024 / 1024
    src_mb = source_wav.stat().st_size / 1024 / 1024
    logger.info(
        f"[meeting:{meeting_id}] audio.opus готов: {size_mb:.1f} МБ (источник: {src_mb:.1f} МБ, "
        f"сжатие в {src_mb/size_mb:.1f}×)"
    )
    return opus_path


@router.get("/{meeting_id}/audio")
async def download_audio(
    meeting_id: int,
    format: str = "opus",   # opus (по умолчанию, в ~10× меньше) | wav (оригинал)
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Скачать аудиозапись совещания.

    По умолчанию отдаётся Opus 32 kbps mono (≈ в 10× меньше WAV) — это
    критично для скачивания через домашний upload-канал.
    Чтобы получить оригинальный WAV, передайте ?format=wav.
    """
    meeting = await _get_meeting(db, meeting_id)
    if not meeting.audio_path:
        raise HTTPException(status_code=404, detail="Аудиозапись не найдена")

    upload_root = settings.UPLOAD_DIR.resolve()

    # Найти WAV-источник
    source = Path(meeting.audio_path).resolve()
    if not str(source).startswith(str(upload_root)):
        logger.warning(f"Path traversal attempt: audio_path={meeting.audio_path}")
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    if not source.exists():
        audio_dir = settings.UPLOAD_DIR / str(meeting_id)
        for name in ("audio.wav", "recorded.wav"):
            candidate = (audio_dir / name).resolve()
            if str(candidate).startswith(str(upload_root)) and candidate.exists():
                source = candidate
                break
    if not source.exists():
        raise HTTPException(status_code=404, detail="Файл аудиозаписи не найден")

    safe_title = (meeting.title or f"meeting_{meeting_id}")[:50].replace("/", "_")

    if format == "wav":
        return FileResponse(
            path=str(source),
            filename=f"{safe_title}_{meeting_id}.wav",
            media_type="audio/wav",
        )

    # Opus (по умолчанию) — кешируем сжатую версию рядом
    opus = await _ensure_opus_for_meeting(meeting_id, source)
    if opus is None or not opus.exists():
        # Fallback на WAV если не удалось перекодировать
        logger.warning(f"[meeting:{meeting_id}] Opus недоступен, fallback на WAV")
        return FileResponse(
            path=str(source),
            filename=f"{safe_title}_{meeting_id}.wav",
            media_type="audio/wav",
        )
    return FileResponse(
        path=str(opus),
        filename=f"{safe_title}_{meeting_id}.opus",
        media_type="audio/ogg",
    )


async def _get_meeting(db: AsyncSession, meeting_id: int) -> Meeting:
    """Любой аутентифицированный пользователь может прочитать любое совещание.

    Owner-only действия (удаление) проверяются отдельно в endpoint'ах.
    """
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")
    return meeting


# Backwards-compat alias — старое имя оставлено как обёртка без owner-фильтра.
# Часть API-модулей всё ещё вызывает _get_user_meeting; они теперь тоже
# получают встречу без проверки владельца.
async def _get_user_meeting(db: AsyncSession, meeting_id: int, user_id: int) -> Meeting:
    return await _get_meeting(db, meeting_id)

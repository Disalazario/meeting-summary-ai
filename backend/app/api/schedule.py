import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.scheduled_meeting import ScheduledMeeting
from app.models.telegram_group import TelegramGroup
from app.models.user import User
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


# Ссылка вида https://telemost.yandex.ru/j/12345678901234567890
_TELEMOST_URL_RE = re.compile(r"^https?://telemost\.yandex\.(ru|com)/j/\d{6,20}$")
_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")  # HH:MM 00:00..23:59


class ScheduleCreateRequest(BaseModel):
    title: str
    meeting_url: str

    # Одноразовая: задать scheduled_at (ISO datetime). Recurrence = 'none'.
    # Еженедельная: recurrence = 'weekly' + recurrence_day (0..6) + recurrence_time ("HH:MM") +
    #               timezone (default 'Europe/Moscow'). scheduled_at не используется.
    recurrence: str = "none"
    scheduled_at: str | None = None
    recurrence_day: int | None = None
    recurrence_time: str | None = None
    timezone: str = "Europe/Moscow"

    telegram_group_id: int | None = None

    @field_validator("recurrence")
    @classmethod
    def _check_recurrence(cls, v: str) -> str:
        if v not in ("none", "weekly"):
            raise ValueError("recurrence должен быть 'none' или 'weekly'")
        return v


class ScheduleUpdateRequest(BaseModel):
    """Частичное обновление расписания (например, тоггл активности)."""
    is_active: bool | None = None
    title: str | None = None


class ScheduleResponse(BaseModel):
    id: int
    title: str
    scheduled_at: datetime | None = None
    meeting_url: str | None = None
    status: str
    error_message: str | None = None
    recurrence: str = "none"
    recurrence_day: int | None = None
    recurrence_time: str | None = None
    timezone: str = "Europe/Moscow"
    is_active: bool = True
    next_run_at: datetime | None = None
    telegram_group_id: int | None = None
    telegram_group_name: str | None = None
    meeting_id: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


async def _enrich_response(
    sm: ScheduledMeeting,
    db: AsyncSession,
    scheduler,
) -> ScheduleResponse:
    tg_name = None
    if sm.telegram_group_id:
        r = await db.execute(
            select(TelegramGroup).where(TelegramGroup.id == sm.telegram_group_id)
        )
        group = r.scalar_one_or_none()
        if group:
            tg_name = group.name
    next_run = scheduler.get_next_run(sm.id) if scheduler else None
    return ScheduleResponse(
        id=sm.id,
        title=sm.title,
        scheduled_at=sm.scheduled_at,
        meeting_url=sm.meeting_url,
        status=sm.status,
        error_message=sm.error_message,
        recurrence=sm.recurrence or "none",
        recurrence_day=sm.recurrence_day,
        recurrence_time=sm.recurrence_time,
        timezone=sm.timezone or "Europe/Moscow",
        is_active=bool(sm.is_active),
        next_run_at=next_run,
        telegram_group_id=sm.telegram_group_id,
        telegram_group_name=tg_name,
        meeting_id=sm.meeting_id,
        created_at=sm.created_at,
    )


def _schedule_job(scheduler, bot_manager, sm: ScheduledMeeting):
    """Создать APScheduler job для записи. Без побочных эффектов на БД."""
    if (sm.recurrence or "none") == "weekly":
        if sm.recurrence_day is None or not sm.recurrence_time:
            raise ValueError(
                "Для weekly нужны recurrence_day (0..6) и recurrence_time (HH:MM)"
            )
        scheduler.schedule_recurring_weekly(
            sm.id,
            day_of_week=sm.recurrence_day,
            time_str=sm.recurrence_time,
            tz_name=sm.timezone or "Europe/Moscow",
            callback=bot_manager.start_scheduled,
        )
    else:
        if not sm.scheduled_at:
            raise ValueError("Для одноразовой встречи требуется scheduled_at")
        scheduler.schedule_meeting(
            sm.id, sm.scheduled_at,
            callback=bot_manager.start_scheduled,
        )


@router.post("", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_scheduled_meeting(
    body: ScheduleCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Запланировать встречу (одноразовую или еженедельную)."""
    if not _TELEMOST_URL_RE.match(body.meeting_url.strip()):
        raise HTTPException(
            status_code=400,
            detail="Невалидная ссылка на Телемост. Ожидается https://telemost.yandex.ru/j/...",
        )

    scheduled_at: datetime | None = None
    recurrence_day: int | None = None
    recurrence_time: str | None = None

    if body.recurrence == "none":
        if not body.scheduled_at:
            raise HTTPException(status_code=400, detail="Для одноразовой встречи укажите scheduled_at")
        try:
            scheduled_at = datetime.fromisoformat(body.scheduled_at)
        except ValueError:
            raise HTTPException(status_code=400, detail="Невалидный формат даты")
        if scheduled_at <= datetime.now():
            raise HTTPException(status_code=400, detail="Время должно быть в будущем")
    else:  # weekly
        if body.recurrence_day is None or not (0 <= body.recurrence_day <= 6):
            raise HTTPException(
                status_code=400,
                detail="recurrence_day должен быть числом 0..6 (Пн..Вс)",
            )
        recurrence_day = body.recurrence_day
        if not body.recurrence_time or not _TIME_RE.match(body.recurrence_time):
            raise HTTPException(
                status_code=400,
                detail="recurrence_time должен быть в формате HH:MM",
            )
        recurrence_time = body.recurrence_time

    tz_name = body.timezone or "Europe/Moscow"
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=400, detail=f"Неизвестная таймзона: {tz_name}")

    sm = ScheduledMeeting(
        title=body.title,
        scheduled_at=scheduled_at,
        meeting_url=body.meeting_url.strip(),
        recurrence=body.recurrence,
        recurrence_day=recurrence_day,
        recurrence_time=recurrence_time,
        timezone=tz_name,
        is_active=True,
        telegram_group_id=body.telegram_group_id,
        created_by=user.id,
    )
    db.add(sm)
    await db.commit()
    await db.refresh(sm)

    scheduler = request.app.state.scheduler
    bot_manager = request.app.state.bot_manager
    try:
        _schedule_job(scheduler, bot_manager, sm)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    logger.info(
        f"Встреча запланирована: id={sm.id}, recurrence={sm.recurrence}, "
        f"scheduled_at={scheduled_at}, day={recurrence_day}, time={recurrence_time}, tz={tz_name}"
    )

    return await _enrich_response(sm, db, scheduler)


@router.get("", response_model=list[ScheduleResponse])
async def list_scheduled_meetings(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список запланированных встреч пользователя."""
    result = await db.execute(
        select(ScheduledMeeting)
        .where(ScheduledMeeting.created_by == user.id)
        .order_by(ScheduledMeeting.scheduled_at.desc().nullslast(), ScheduledMeeting.created_at.desc())
    )
    meetings = result.scalars().all()
    scheduler = request.app.state.scheduler
    return [await _enrich_response(sm, db, scheduler) for sm in meetings]


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_scheduled_meeting(
    schedule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Детали запланированной встречи."""
    result = await db.execute(
        select(ScheduledMeeting).where(
            ScheduledMeeting.id == schedule_id,
            ScheduledMeeting.created_by == user.id,
        )
    )
    sm = result.scalar_one_or_none()
    if not sm:
        raise HTTPException(status_code=404, detail="Запланированная встреча не найдена")
    return await _enrich_response(sm, db, request.app.state.scheduler)


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_scheduled_meeting(
    schedule_id: int,
    body: ScheduleUpdateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Частичное обновление. Сейчас поддерживается:
    - is_active: для рекуррентных — пауза/возобновление job в APScheduler.
    - title: переименование.
    """
    result = await db.execute(
        select(ScheduledMeeting).where(
            ScheduledMeeting.id == schedule_id,
            ScheduledMeeting.created_by == user.id,
        )
    )
    sm = result.scalar_one_or_none()
    if not sm:
        raise HTTPException(status_code=404, detail="Запланированная встреча не найдена")

    scheduler = request.app.state.scheduler
    bot_manager = request.app.state.bot_manager

    if body.title is not None:
        sm.title = body.title

    if body.is_active is not None and bool(body.is_active) != bool(sm.is_active):
        sm.is_active = bool(body.is_active)
        if (sm.recurrence or "none") == "weekly":
            if sm.is_active:
                try:
                    _schedule_job(scheduler, bot_manager, sm)
                except ValueError as e:
                    raise HTTPException(status_code=400, detail=str(e))
            else:
                scheduler.cancel_meeting(sm.id)

    await db.commit()
    await db.refresh(sm)
    return await _enrich_response(sm, db, scheduler)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_scheduled_meeting(
    schedule_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отменить (для одноразовой) или удалить (для рекуррентной)."""
    result = await db.execute(
        select(ScheduledMeeting).where(
            ScheduledMeeting.id == schedule_id,
            ScheduledMeeting.created_by == user.id,
        )
    )
    sm = result.scalar_one_or_none()
    if not sm:
        raise HTTPException(status_code=404, detail="Запланированная встреча не найдена")

    is_recurring = (sm.recurrence or "none") != "none"

    if not is_recurring and sm.status not in ("pending",):
        raise HTTPException(status_code=400, detail="Можно отменить только ожидающие одноразовые встречи")

    sm.status = "cancelled"
    sm.is_active = False
    await db.commit()

    scheduler = request.app.state.scheduler
    scheduler.cancel_meeting(schedule_id)

    logger.info(f"Встреча {schedule_id} отменена (recurrence={sm.recurrence})")

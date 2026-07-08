import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.models.user import User
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()

TELEMOST_URL_REGEX = re.compile(r'^https?://telemost\.yandex\.(ru|com)/j/\d{6,20}$')


class BotJoinRequest(BaseModel):
    meeting_url: str
    title: str
    telegram_group_id: int | None = None


class BotQuickRequest(BaseModel):
    title: str
    telegram_group_id: int | None = None


class BotJoinResponse(BaseModel):
    meeting_id: int
    status: str


class BotQuickResponse(BaseModel):
    meeting_id: int
    meeting_url: str
    status: str


@router.post("/join", response_model=BotJoinResponse)
async def bot_join(
    body: BotJoinRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Подключить бота к существующей встрече."""
    if not TELEMOST_URL_REGEX.match(body.meeting_url):
        raise HTTPException(status_code=400, detail="Невалидная ссылка на Телемост")

    bot_manager = request.app.state.bot_manager
    try:
        meeting_id = await bot_manager.start_by_link(
            user_id=user.id,
            meeting_url=body.meeting_url,
            title=body.title,
            telegram_group_id=body.telegram_group_id,
        )
        logger.info(f"Бот подключён к {body.meeting_url}, meeting_id={meeting_id}")
        return BotJoinResponse(meeting_id=meeting_id, status="recording")
    except RuntimeError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/capacity")
async def bot_capacity(request: Request, user: User = Depends(get_current_user)):
    """Сколько ботов сейчас пишут параллельно и сколько встреч ждут обработки."""
    from app.services.processing import get_queue_size
    bot_manager = request.app.state.bot_manager
    return {
        "active": len(bot_manager._active),
        "max_parallel": bot_manager.max_parallel,
        "queue_size": get_queue_size(),
        "active_meeting_ids": list(bot_manager._active.keys()),
    }


@router.post("/quick", response_model=BotQuickResponse)
async def bot_quick(
    body: BotQuickRequest,
    request: Request,
    user: User = Depends(get_current_user),
):
    """DEPRECATED. Автоматическое создание встреч больше не поддерживается.

    Yandex 360 b2b-флоу требует интерактивной авторизации каждые ~3 месяца,
    что несовместимо с фоновым ботом. Создайте встречу в Телемост вручную
    и используйте POST /bot/join со ссылкой.
    """
    raise HTTPException(
        status_code=410,
        detail=(
            "Автоматическое создание встреч отключено. "
            "Создайте встречу в Telemost вручную и подключите бота по ссылке."
        ),
    )


@router.post("/stop/{meeting_id}")
async def bot_stop(
    meeting_id: int,
    request: Request,
    user: User = Depends(get_current_user),
):
    """Остановить запись."""
    bot_manager = request.app.state.bot_manager
    try:
        await bot_manager.stop_bot(meeting_id)
        return {"status": "stopped"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/active")
async def bot_active(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Список активных записей."""
    bot_manager = request.app.state.bot_manager
    return bot_manager.get_active_bots()

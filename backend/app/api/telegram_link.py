"""Привязка Telegram пользователю.

GET    /users/me/telegram          — есть ли привязка
POST   /users/me/telegram/link     — создать deeplink (10 мин TTL)
DELETE /users/me/telegram          — отвязать
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.telegram_link import create_token, deeplink
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)
router = APIRouter()


class TelegramStatus(BaseModel):
    linked: bool
    telegram_id: str | None = None


class TelegramLinkResponse(BaseModel):
    deeplink: str
    expires_in_seconds: int = 600


@router.get("/me/telegram", response_model=TelegramStatus)
async def get_my_telegram(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return TelegramStatus(linked=bool(user.telegram_id), telegram_id=user.telegram_id)


@router.post("/me/telegram/link", response_model=TelegramLinkResponse)
async def create_telegram_link(user: User = Depends(get_current_user)):
    """Создать одноразовый deeplink для привязки Telegram."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(400, "Telegram-бот не настроен")
    # Узнать username бота (через getMe)
    bot = TelegramService(settings.TELEGRAM_BOT_TOKEN)
    info = await bot.verify_bot()
    if not info or not info.get("username"):
        raise HTTPException(503, "Не удалось получить username бота")
    token = create_token(user.id)
    return TelegramLinkResponse(deeplink=deeplink(info["username"], token))


@router.delete("/me/telegram", status_code=204)
async def unlink_telegram(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if user.telegram_id:
        user.telegram_id = None
        await db.commit()
        logger.info(f"Telegram отвязан у user={user.username}")

"""Статусы внешних интеграций для UI настроек.

Пока — только read-only статус (configured / enabled / details). По мере
реализации каждой интеграции сюда же будут подключаться её эндпоинты
(webhook'и, OAuth-callback'и, ручной sync и т.п.).
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.models.user import User
from app.services.auth_service import get_current_user
from app.services import mango_service, amocrm_service

router = APIRouter()


class IntegrationStatusResponse(BaseModel):
    key: str           # стабильный машинный ключ ('mango' | 'amocrm')
    name: str          # человекочитаемое имя
    configured: bool   # есть ли ключи в .env
    enabled: bool      # реально ли подключено и работает
    details: str       # короткое сообщение для UI


@router.get("/status", response_model=list[IntegrationStatusResponse])
async def list_integration_statuses(user: User = Depends(get_current_user)):
    """Сводный статус всех настраиваемых интеграций."""
    items = [
        ("mango", mango_service.get_status()),
        ("amocrm", amocrm_service.get_status()),
    ]
    return [
        IntegrationStatusResponse(
            key=k,
            name=s.name,
            configured=s.configured,
            enabled=s.enabled,
            details=s.details,
        )
        for k, s in items
    ]

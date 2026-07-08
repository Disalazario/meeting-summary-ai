"""AmoCRM — пока заглушка под будущую интеграцию.

Когда дойдём до реализации:
- AmoCRM OAuth 2.0: refresh-token раз в день, access-token в RAM.
- API v4: задачи, контакты, сделки.
- Вероятный сценарий: после обработки встречи — создавать карточки задач
  в AmoCRM (аналог PlanFix-сценария, только с другим бэкендом).

Сейчас модуль содержит только функцию статуса для UI/админа.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.config import settings


@dataclass
class IntegrationStatus:
    name: str
    configured: bool
    enabled: bool
    details: str


def get_status() -> IntegrationStatus:
    has_domain = bool(settings.AMOCRM_DOMAIN)
    has_client = bool(settings.AMOCRM_CLIENT_ID and settings.AMOCRM_CLIENT_SECRET)
    configured = has_domain and has_client
    return IntegrationStatus(
        name="AmoCRM",
        configured=configured,
        enabled=False,
        details=(
            "Интеграция в разработке. Когда будет готова — задачи из встреч "
            "будут отправляться в AmoCRM наряду с PlanFix."
            if configured else
            "OAuth-приложение не настроено. Добавьте AMOCRM_DOMAIN, "
            "AMOCRM_CLIENT_ID, AMOCRM_CLIENT_SECRET в .env."
        ),
    )

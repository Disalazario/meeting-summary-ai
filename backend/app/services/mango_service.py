"""МангоТелеком VPBX — пока заглушка под будущую интеграцию.

Когда дойдём до реализации:
- VPBX API: HMAC-подписанный REST. История звонков /stats/, скачивание записи /recording/.
- Webhooks: события `call`/`recording` на наш endpoint (нужен MANGO_WEBHOOK_TOKEN).
- При получении завершённого звонка с записью — скачать mp3, создать Meeting
  с source='call_mango', положить в очередь обработки (тот же pipeline
  Whisper → diarize → summary → tasks).

Сейчас модуль содержит только функцию статуса для UI/админа, чтобы видеть,
прописаны ли ключи. Сами вызовы Манго не делаем.
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
    has_key = bool(settings.MANGO_VPBX_API_KEY)
    has_salt = bool(settings.MANGO_VPBX_API_SALT)
    configured = has_key and has_salt
    return IntegrationStatus(
        name="МангоТелеком",
        configured=configured,
        enabled=False,  # фактическая обработка ещё не реализована
        details=(
            "Интеграция в разработке. Когда будет готова — звонки из Манго "
            "будут автоматически попадать в очередь обработки."
            if configured else
            "Ключи не настроены. Добавьте MANGO_VPBX_API_KEY и MANGO_VPBX_API_SALT в .env."
        ),
    )

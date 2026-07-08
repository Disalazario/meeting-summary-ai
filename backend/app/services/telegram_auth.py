"""
Валидация initData от Telegram Mini App.
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qs

from app.config import settings


def validate_init_data(init_data: str, bot_token: str | None = None) -> dict | None:
    """
    Валидация initData от Telegram Mini App.
    Возвращает данные пользователя или None если невалидно.
    """
    if not init_data:
        return None

    token = bot_token or settings.TELEGRAM_BOT_TOKEN
    if not token:
        return None

    parsed = parse_qs(init_data, keep_blank_values=True)

    # Извлечь hash
    hash_value = parsed.pop('hash', [None])[0]
    if not hash_value:
        return None

    # Проверить auth_date (не старше 1 часа)
    auth_date = parsed.get('auth_date', [None])[0]
    if auth_date:
        try:
            if (time.time() - int(auth_date)) > 3600:
                return None
        except (ValueError, TypeError):
            return None

    # Собрать data_check_string (сортировка по ключам)
    data_check_pairs = []
    for key in sorted(parsed.keys()):
        data_check_pairs.append(f"{key}={parsed[key][0]}")
    data_check_string = "\n".join(data_check_pairs)

    # Создать secret key: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        b"WebAppData", token.encode(), hashlib.sha256
    ).digest()

    # Проверить подпись
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if calculated_hash != hash_value:
        return None

    # Вернуть данные пользователя
    user_data = parsed.get('user', [None])[0]
    if user_data:
        try:
            return json.loads(user_data)
        except json.JSONDecodeError:
            return None

    return None

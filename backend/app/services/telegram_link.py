"""Привязка Telegram-аккаунта пользователя к учётке через одноразовый deeplink.

Поток:
1. Пользователь в /settings нажимает «Привязать Telegram»
2. Backend генерирует одноразовый token и возвращает deeplink
   `https://t.me/<bot_username>?start=link_<token>`
3. Пользователь переходит, отправляется `/start link_<token>`
4. Bot-handler ловит, валидирует token → записывает chat_id в User.telegram_id
5. Бот отвечает «✓ привязано»

Токены — in-memory с TTL 10 мин, одноразовые. Для 4–7 человек этого хватит.
"""

import logging
import secrets
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_TOKEN_TTL_SEC = 600  # 10 минут
_PREFIX = "link_"


@dataclass
class _Entry:
    user_id: int
    expires_at: float


_tokens: dict[str, _Entry] = {}
_lock = threading.Lock()


def _gc():
    """Удалить просроченные токены."""
    now = time.time()
    expired = [t for t, e in _tokens.items() if e.expires_at < now]
    for t in expired:
        _tokens.pop(t, None)


def create_token(user_id: int) -> str:
    """Создать одноразовый токен для пользователя. Возвращает строку для deeplink."""
    with _lock:
        _gc()
        token = secrets.token_urlsafe(16)
        _tokens[token] = _Entry(user_id=user_id, expires_at=time.time() + _TOKEN_TTL_SEC)
    logger.info(f"Telegram-link token создан для user_id={user_id}, ttl={_TOKEN_TTL_SEC}s")
    return token


def consume_token(payload: str) -> int | None:
    """Проверить и потратить токен (одноразовый).

    Принимает либо чистый токен, либо строку `link_<token>` (как пришло из /start).
    Возвращает user_id, либо None если токена нет / просрочен.
    """
    token = payload[len(_PREFIX):] if payload.startswith(_PREFIX) else payload
    with _lock:
        _gc()
        entry = _tokens.pop(token, None)
    if entry is None:
        logger.info(f"Telegram-link token не найден или просрочен: {token[:8]}...")
        return None
    logger.info(f"Telegram-link token потрачен: user_id={entry.user_id}")
    return entry.user_id


def deeplink(bot_username: str, token: str) -> str:
    """Сформировать deeplink t.me/<bot>?start=link_<token>."""
    return f"https://t.me/{bot_username}?start={_PREFIX}{token}"

"""
Тест отправки сообщения в Telegram.

Запуск:
    cd backend
    python scripts/test_telegram.py <chat_id>
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings
from app.services.telegram_service import TelegramService


async def main():
    if not settings.TELEGRAM_BOT_TOKEN:
        print("TELEGRAM_BOT_TOKEN не задан в .env")
        return

    tg = TelegramService(settings.TELEGRAM_BOT_TOKEN)

    # Проверка бота
    info = await tg.verify_bot()
    if info:
        print(f"Бот: @{info.get('username')} ({info.get('first_name')})")
    else:
        print("Токен бота невалиден!")
        return

    if len(sys.argv) > 1:
        chat_id = sys.argv[1]
        ok = await tg.send_message(chat_id, "Тестовое сообщение от Meeting Summary Bot")
        print(f"Отправка в {chat_id}: {'OK' if ok else 'ОШИБКА'}")
    else:
        print("Для отправки тестового сообщения укажите chat_id:")
        print(f"  python scripts/test_telegram.py -100XXXXXXXXXX")


asyncio.run(main())

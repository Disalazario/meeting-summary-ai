"""
Отправка уведомлений в Telegram-группы.

Настройка:
1. Создать бота через @BotFather в Telegram
2. Получить токен бота
3. Добавить бота в группу
4. Получить chat_id группы
5. Сохранить в настройках приложения
"""

import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"

MAX_RETRIES = 3
RETRY_DELAYS = [2, 5, 10]


class TelegramService:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = TELEGRAM_API.format(token=bot_token)

    async def send_message(self, chat_id: str, text: str,
                           parse_mode: str = "HTML") -> bool:
        """Отправить сообщение в чат/группу с retry."""
        for attempt in range(MAX_RETRIES):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.post(
                        f"{self.base_url}/sendMessage",
                        json={
                            "chat_id": chat_id,
                            "text": text,
                            "parse_mode": parse_mode,
                            "disable_web_page_preview": False,
                        }
                    )
                    data = resp.json()
                    if not data.get("ok"):
                        logger.error(f"Telegram API error: {data}")
                        return False
                    logger.info(f"Сообщение отправлено в Telegram chat_id={chat_id}")
                    return True
            except Exception as e:
                delay = RETRY_DELAYS[attempt] if attempt < len(RETRY_DELAYS) else 10
                logger.warning(
                    f"Telegram send_message попытка {attempt+1}/{MAX_RETRIES} "
                    f"не удалась ({type(e).__name__}: {e}), "
                    f"повтор через {delay}с"
                )
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(delay)
        logger.error(f"Telegram: не удалось отправить в chat_id={chat_id} после {MAX_RETRIES} попыток")
        return False

    async def send_meeting_link(self, chat_id: str, title: str,
                                meeting_url: str) -> bool:
        """Отправить ссылку на совещание."""
        text = (
            f"<b>Совещание: {title}</b>\n"
            f"\n"
            f"Встреча начинается! Присоединяйтесь:\n"
            f'<a href="{meeting_url}">{meeting_url}</a>'
        )
        return await self.send_message(chat_id, text)

    async def send_meeting_ready(self, chat_id: str, title: str,
                                 app_url: str,
                                 miniapp_url: str | None = None) -> bool:
        """Уведомление что саммари готово, с кнопкой Mini App."""
        text = (
            f"<b>Совещание \"{title}\" обработано</b>\n"
            f"\n"
            f"Расшифровка и саммари готовы:\n"
            f'<a href="{app_url}">Открыть результат</a>'
        )

        if miniapp_url:
            return await self.send_message_with_webapp(
                chat_id, text, "Открыть в приложении", miniapp_url
            )
        return await self.send_message(chat_id, text)

    async def send_document(
        self, chat_id: str, file_bytes: bytes, filename: str,
        caption: str | None = None, mime_type: str = "application/pdf",
    ) -> bool:
        """Отправить файл (PDF и т.п.) в чат как документ."""
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                files = {"document": (filename, file_bytes, mime_type)}
                data: dict = {"chat_id": chat_id}
                if caption:
                    data["caption"] = caption
                    data["parse_mode"] = "HTML"
                resp = await client.post(
                    f"{self.base_url}/sendDocument",
                    data=data,
                    files=files,
                )
                payload = resp.json()
                if not payload.get("ok"):
                    logger.error(f"Telegram sendDocument error: {payload}")
                    return False
                logger.info(
                    f"Документ '{filename}' ({len(file_bytes)} байт) отправлен в chat_id={chat_id}"
                )
                return True
        except Exception as e:
            logger.error(f"Ошибка sendDocument: {type(e).__name__}: {e}")
            return False

    async def send_message_with_webapp(self, chat_id: str, text: str,
                                        button_text: str, webapp_url: str,
                                        parse_mode: str = "HTML") -> bool:
        """Отправить сообщение с кнопкой Web App."""
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": parse_mode,
                        "reply_markup": {
                            "inline_keyboard": [[{
                                "text": button_text,
                                "web_app": {"url": webapp_url},
                            }]],
                        },
                    },
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.error(f"Telegram API error: {data}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Ошибка отправки с Web App кнопкой: {e}")
            return False

    async def verify_bot(self) -> dict | None:
        """Проверить что токен бота валиден."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.get(f"{self.base_url}/getMe")
                data = resp.json()
                if data.get("ok"):
                    logger.info(f"Telegram бот верифицирован: @{data['result'].get('username')}")
                    return data.get("result")
                return None
            except Exception as e:
                logger.error(f"Ошибка верификации Telegram бота: {e}")
                return None

    async def set_commands(self) -> bool:
        """Зарегистрировать команды бота в Telegram."""
        commands = [
            {"command": "start", "description": "Приветствие и описание бота"},
            {"command": "create", "description": "Создать встречу: /create Название"},
            {"command": "join", "description": "Подключиться: /join ссылка"},
            {"command": "status", "description": "Статус текущей записи"},
            {"command": "meetings", "description": "Последние совещания"},
            {"command": "app", "description": "Открыть приложение"},
            {"command": "help", "description": "Список команд"},
        ]
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/setMyCommands",
                    json={"commands": commands},
                )
                data = resp.json()
                if data.get("ok"):
                    logger.info("Telegram команды зарегистрированы")
                    return True
                return False
            except Exception as e:
                logger.error(f"Ошибка регистрации команд: {e}")
                return False

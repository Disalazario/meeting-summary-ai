"""
Telegram Bot Handler — двусторонний Telegram-бот.

Получает команды от пользователей через long polling (getUpdates)
и выполняет действия через BotManager.

Команды:
  /start   — приветствие
  /help    — список команд
  /create  — создать встречу + запись
  /join    — подключить бота к существующей встрече
  /status  — статус текущей записи
  /meetings — последние 5 совещаний
"""

import asyncio
import logging
import re
from datetime import datetime

import httpx
from sqlalchemy import select, desc

from app.config import settings
from app.database import async_session
from app.models.meeting import Meeting
from app.models.telegram_group import TelegramGroup

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}"
TELEMOST_URL_RE = re.compile(r"https?://telemost\.yandex\.(ru|com)/j/\d{6,20}")


class TelegramBotHandler:
    def __init__(self, bot_token: str, bot_manager, telegram_service):
        self.bot_token = bot_token
        self.base_url = TELEGRAM_API.format(token=bot_token)
        self.bot_manager = bot_manager
        self.telegram = telegram_service
        self._offset = 0
        self._running = False
        self._task: asyncio.Task | None = None

        # Разрешённые чаты (пусто = все)
        self._allowed_chats: set[str] = set()
        if settings.TELEGRAM_ALLOWED_CHAT_IDS:
            self._allowed_chats = {
                cid.strip()
                for cid in settings.TELEGRAM_ALLOWED_CHAT_IDS.split(",")
                if cid.strip()
            }

        self._owner_id = settings.TELEGRAM_BOT_USER_ID

        # Ожидающие создания встречи (chat_id -> title)
        self._pending_create: dict[str, str] = {}

    def start(self):
        """Запустить polling в фоне."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._poll_loop())
        logger.info("Telegram Bot Handler: polling запущен")

    async def stop(self):
        """Остановить polling."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Telegram Bot Handler: polling остановлен")

    # ── Polling ──

    async def _poll_loop(self):
        """Основной цикл long polling с exponential backoff."""
        backoff = 5
        max_backoff = 300  # 5 мин макс — не спамить при недоступности
        consecutive_errors = 0
        while self._running:
            try:
                updates = await self._get_updates()
                backoff = 5  # сброс backoff при успехе
                consecutive_errors = 0
                for update in updates:
                    self._offset = update["update_id"] + 1
                    try:
                        await self._handle_update(update)
                    except Exception as e:
                        logger.error(f"Ошибка обработки update: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors <= 3:
                    logger.error(f"Telegram polling error: {e}")
                elif consecutive_errors == 4:
                    logger.error(f"Telegram polling error (подавляю повторы, backoff={backoff}с): {e}")
                # После 4-й ошибки логируем только каждые 50 попыток
                elif consecutive_errors % 50 == 0:
                    logger.warning(f"Telegram polling: {consecutive_errors} ошибок подряд, backoff={backoff}с")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, max_backoff)

    async def _get_updates(self) -> list[dict]:
        """Получить обновления от Telegram."""
        async with httpx.AsyncClient(timeout=35) as client:
            resp = await client.get(
                f"{self.base_url}/getUpdates",
                params={
                    "offset": self._offset,
                    "timeout": 30,
                    "allowed_updates": '["message","callback_query"]',
                },
            )
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
            return []

    async def _handle_update(self, update: dict):
        """Обработка одного обновления."""
        # Обработка callback_query (нажатие inline-кнопки)
        callback = update.get("callback_query")
        if callback:
            await self._handle_callback(callback)
            return

        message = update.get("message")
        if not message:
            return

        chat_id = str(message["chat"]["id"])
        text = (message.get("text") or "").strip()

        # Проверка авторизации
        if self._allowed_chats and chat_id not in self._allowed_chats:
            logger.warning(f"Telegram: неавторизованный чат {chat_id}")
            return

        if not text.startswith("/"):
            return

        # Парсинг команды (убираем @botname суффикс)
        parts = text.split(maxsplit=1)
        command = parts[0].lower().split("@")[0]
        args = parts[1] if len(parts) > 1 else ""

        logger.info(f"Telegram команда: {command} от chat_id={chat_id}")

        handlers = {
            "/start": self._cmd_start,
            "/help": self._cmd_help,
            "/create": self._cmd_create,
            "/new": self._cmd_create,
            "/join": self._cmd_join,
            "/status": self._cmd_status,
            "/meetings": self._cmd_meetings,
            "/list": self._cmd_meetings,
            "/app": self._cmd_app,
        }

        handler = handlers.get(command)
        if handler:
            await handler(chat_id, args)
        else:
            await self.telegram.send_message(
                chat_id,
                "Неизвестная команда. Используйте /help для списка команд.",
            )

    # ── Команды ──

    def _get_miniapp_url(self, path: str = "/") -> str:
        """Получить URL Mini App."""
        base = settings.MINI_APP_URL.rstrip("/")
        return f"{base}/miniapp{path}"

    async def _cmd_app(self, chat_id: str, args: str):
        """Открыть Mini App."""
        url = self._get_miniapp_url()
        if not settings.MINI_APP_URL:
            await self.telegram.send_message(
                chat_id, "Mini App не настроен. Задайте MINI_APP_URL в .env"
            )
            return
        await self._send_with_keyboard(
            chat_id,
            "Откройте приложение для просмотра совещаний:",
            [[{"text": "Открыть приложение", "web_app": {"url": url}}]],
        )

    async def _cmd_start(self, chat_id: str, args: str):
        # Привязка аккаунта: /start link_<token>
        if args and args.strip().startswith("link_"):
            await self._handle_link(chat_id, args.strip())
            return

        text = (
            "<b>Meeting Summary Bot</b>\n\n"
            "Я помогу записать и обработать ваше совещание "
            "в Яндекс Телемост.\n\n"
            "Что я умею:\n"
            "- Создать новую встречу с записью\n"
            "- Подключиться к существующей встрече\n"
            "- Показать статус записи\n"
            "- Показать список совещаний со ссылками\n\n"
            "Используйте /help для списка команд."
        )
        if settings.MINI_APP_URL:
            url = self._get_miniapp_url()
            await self._send_with_keyboard(
                chat_id, text,
                [[{"text": "Открыть приложение", "web_app": {"url": url}}]],
            )
        else:
            await self.telegram.send_message(chat_id, text)

    async def _handle_link(self, chat_id: str, payload: str):
        """Привязать Telegram-аккаунт пользователю по одноразовому токену."""
        from sqlalchemy import select
        from app.database import async_session
        from app.models.user import User
        from app.services.telegram_link import consume_token

        user_id = consume_token(payload)
        if user_id is None:
            await self.telegram.send_message(
                chat_id,
                "❌ Ссылка просрочена или уже использована.\n"
                "Откройте «Настройки» в приложении и сгенерируйте новую.",
            )
            return

        async with async_session() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None:
                await self.telegram.send_message(chat_id, "❌ Пользователь не найден")
                return

            # Проверить, не привязан ли этот chat_id уже к другому
            other_q = await session.execute(
                select(User).where(User.telegram_id == str(chat_id), User.id != user.id)
            )
            other = other_q.scalar_one_or_none()
            if other is not None:
                other.telegram_id = None

            user.telegram_id = str(chat_id)
            await session.commit()

        await self.telegram.send_message(
            chat_id,
            f"✅ Готово! Этот Telegram теперь привязан к «{user.display_name}».\n\n"
            "После каждого обработанного совещания, где вы участвовали, "
            "вы получите краткое саммари сюда.",
        )

    async def _cmd_help(self, chat_id: str, args: str):
        text = (
            "<b>Доступные команды:</b>\n\n"
            "/create &lt;название&gt; — Создать встречу и начать запись\n"
            "/join &lt;ссылка&gt; — Подключить бота к встрече\n"
            "/status — Статус текущей записи\n"
            "/meetings — Последние 5 совещаний\n"
            "/app — Открыть приложение\n"
            "/help — Список команд"
        )
        await self.telegram.send_message(chat_id, text)

    async def _cmd_create(self, chat_id: str, args: str):
        """DEPRECATED — автосоздание встреч отключено."""
        await self.telegram.send_message(
            chat_id,
            "ℹ️ Автоматическое создание встреч больше не поддерживается.\n\n"
            "Создайте встречу в <b>Telemost</b> вручную (через сайт или приложение), "
            "затем отправьте боту:\n\n"
            "<code>/join &lt;ссылка на встречу&gt;</code>\n\n"
            "Пример: /join https://telemost.yandex.ru/j/12345678901234567890",
        )

    async def _do_create_meeting(self, chat_id: str, title: str,
                                  telegram_group_id: int | None):
        """Создать встречу и отправить ссылку."""
        try:
            meeting_id, meeting_url = await self.bot_manager.start_quick(
                user_id=self._owner_id,
                title=title,
                telegram_group_id=telegram_group_id,
            )

            # Сохранить chat_id для уведомления после обработки
            await self._set_meeting_telegram_chat(meeting_id, chat_id)

            group_text = ""
            if telegram_group_id:
                group = await self.bot_manager._get_telegram_group(telegram_group_id)
                if group:
                    group_text = f"\nСсылка отправлена в группу <b>{group.name}</b>"

            text = (
                f"<b>Встреча создана!</b>\n\n"
                f"<b>{title}</b>\n\n"
                f"Ссылка для участников:\n"
                f'<a href="{meeting_url}">{meeting_url}</a>\n\n'
                f"Бот подключается к записи...{group_text}"
            )
            await self.telegram.send_message(chat_id, text)

        except RuntimeError as e:
            await self.telegram.send_message(chat_id, f"Ошибка: {e}")
        except Exception as e:
            logger.exception(f"Telegram /create error: {e}")
            await self.telegram.send_message(
                chat_id, "Произошла ошибка при создании встречи."
            )

    async def _cmd_join(self, chat_id: str, args: str):
        url = args.strip()
        if not url:
            await self.telegram.send_message(
                chat_id,
                "Укажите ссылку: /join https://telemost.yandex.ru/j/1234567890",
            )
            return

        # Извлечь URL из текста (на случай если прислали с текстом)
        match = TELEMOST_URL_RE.search(url)
        if not match:
            await self.telegram.send_message(
                chat_id,
                "Невалидная ссылка на Телемост.\n"
                "Формат: https://telemost.yandex.ru/j/НОМЕР",
            )
            return

        meeting_url = match.group(0)

        try:
            title = f"Встреча {datetime.now().strftime('%d.%m %H:%M')}"
            meeting_id = await self.bot_manager.start_by_link(
                user_id=self._owner_id,
                meeting_url=meeting_url,
                title=title,
            )

            await self._set_meeting_telegram_chat(meeting_id, chat_id)

            text = (
                f"<b>Бот подключается к встрече</b>\n\n"
                f'<a href="{meeting_url}">{meeting_url}</a>\n\n'
                f"Запись начнётся автоматически."
            )
            await self.telegram.send_message(chat_id, text)

        except RuntimeError as e:
            await self.telegram.send_message(chat_id, f"Ошибка: {e}")
        except Exception as e:
            logger.exception(f"Telegram /join error: {e}")
            await self.telegram.send_message(
                chat_id, "Произошла ошибка при подключении."
            )

    async def _cmd_status(self, chat_id: str, args: str):
        active = self.bot_manager.get_active_bots()
        if not active:
            await self.telegram.send_message(chat_id, "Нет активных записей.")
            return

        lines = ["<b>Активные записи:</b>\n"]
        for bot in active:
            started = datetime.fromisoformat(bot["started_at"])
            elapsed = int((datetime.utcnow() - started).total_seconds())
            mins = elapsed // 60
            secs = elapsed % 60
            lines.append(
                f"Совещание #{bot['meeting_id']} — "
                f"{mins}:{secs:02d}, "
                f"участников: {bot.get('participants', '?')}"
            )
        await self.telegram.send_message(chat_id, "\n".join(lines))

    async def _cmd_meetings(self, chat_id: str, args: str):
        async with async_session() as session:
            result = await session.execute(
                select(Meeting).order_by(desc(Meeting.created_at)).limit(5)
            )
            meetings = result.scalars().all()

        if not meetings:
            await self.telegram.send_message(chat_id, "Нет совещаний.")
            return

        STATUS_LABELS = {
            "uploaded": "Загружено",
            "waiting_bot": "Ожидание",
            "recording": "Запись",
            "processing": "Обработка",
            "transcribing": "Транскрибация",
            "diarizing": "Диаризация",
            "summarizing": "Саммари",
            "done": "Готово",
            "error": "Ошибка",
        }

        lines = ["<b>Последние совещания:</b>\n"]
        buttons = []
        for m in meetings:
            status = STATUS_LABELS.get(m.status, m.status)
            date_str = m.date.strftime("%d.%m.%Y") if m.date else ""
            line = f"<b>{m.title}</b> — {status}"
            if date_str:
                line += f" ({date_str})"
            lines.append(line)

            # Кнопка Mini App для каждого совещания (если done)
            if settings.MINI_APP_URL and m.status == "done":
                url = self._get_miniapp_url(f"/meeting/{m.id}")
                buttons.append([{
                    "text": f"📋 {m.title[:30]}",
                    "web_app": {"url": url},
                }])

        text = "\n".join(lines)

        if buttons:
            await self._send_with_keyboard(chat_id, text, buttons)
        else:
            await self.telegram.send_message(chat_id, text)

    # ── Callback (inline-кнопки) ──

    async def _handle_callback(self, callback: dict):
        """Обработка нажатия inline-кнопки."""
        callback_id = callback["id"]
        data = callback.get("data", "")
        message = callback.get("message", {})
        chat_id = str(message.get("chat", {}).get("id", ""))

        if not chat_id:
            await self._answer_callback(callback_id)
            return

        # Проверка авторизации
        if self._allowed_chats and chat_id not in self._allowed_chats:
            await self._answer_callback(callback_id)
            return

        logger.info(f"Telegram callback: {data} от chat_id={chat_id}")

        if data.startswith("create_group:"):
            await self._answer_callback(callback_id, "Создаю встречу...")
            group_value = data.split(":", 1)[1]
            title = self._pending_create.pop(chat_id, None)
            if not title:
                await self.telegram.send_message(
                    chat_id, "Сессия истекла. Повторите /create"
                )
                return

            telegram_group_id = int(group_value) if group_value != "none" else None
            await self._do_create_meeting(chat_id, title, telegram_group_id)
        else:
            await self._answer_callback(callback_id)

    # ── Telegram API helpers ──

    async def _send_with_keyboard(self, chat_id: str, text: str,
                                   inline_keyboard: list[list[dict]]) -> bool:
        """Отправить сообщение с inline-клавиатурой."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "HTML",
                        "reply_markup": {
                            "inline_keyboard": inline_keyboard,
                        },
                    },
                )
                data = resp.json()
                if not data.get("ok"):
                    logger.error(f"Telegram sendMessage error: {data}")
                    return False
                return True
            except Exception as e:
                logger.error(f"Ошибка отправки с клавиатурой: {e}")
                return False

    async def _answer_callback(self, callback_id: str, text: str = "") -> None:
        """Ответить на callback_query (убрать часики)."""
        async with httpx.AsyncClient(timeout=10) as client:
            try:
                await client.post(
                    f"{self.base_url}/answerCallbackQuery",
                    json={"callback_query_id": callback_id, "text": text},
                )
            except Exception:
                pass

    # ── DB helpers ──

    async def _get_telegram_groups(self) -> list:
        """Получить все Telegram-группы из БД."""
        async with async_session() as session:
            result = await session.execute(select(TelegramGroup))
            return result.scalars().all()

    async def _set_meeting_telegram_chat(self, meeting_id: int, chat_id: str):
        """Сохранить telegram_chat_id на meeting для уведомления после обработки."""
        async with async_session() as session:
            result = await session.execute(
                select(Meeting).where(Meeting.id == meeting_id)
            )
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.telegram_chat_id = chat_id
                await session.commit()

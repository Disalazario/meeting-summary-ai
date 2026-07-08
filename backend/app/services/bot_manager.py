"""
BotManager — оркестратор полного жизненного цикла бота.

Три режима запуска:
1. start_scheduled() — запланированная встреча (создание + Telegram + запись)
2. start_by_link() — подключение к существующей встрече по ссылке
3. start_quick() — создать встречу прямо сейчас + Telegram + запись
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.config import settings
from app.database import async_session
from app.models.meeting import Meeting
from app.models.scheduled_meeting import ScheduledMeeting
from app.models.telegram_group import TelegramGroup
from app.services.audio_capture import AudioCapture, ensure_pulseaudio_sink, sink_for_meeting
from app.services.telemost_auth import YandexAuth, TelemostMeetingCreator
from app.services.telemost_bot import TelemostBot
from app.services.telegram_service import TelegramService

logger = logging.getLogger(__name__)


@dataclass
class BotInstance:
    meeting_id: int
    session_id: int | None
    bot: TelemostBot
    capture: AudioCapture
    audio_path: str
    started_at: datetime


class BotManager:
    def __init__(self, telegram_service: TelegramService, yandex_auth: YandexAuth):
        self.telegram = telegram_service
        self.auth = yandex_auth
        self._active: dict[int, BotInstance] = {}
        # Семафор ограничивает число одновременных записей. Каждая занимает
        # ~1.5–2 ГБ RAM (Chromium+ffmpeg) и одно CPU-ядро. Дефолт 3 — настраивается
        # через .env параметр MAX_PARALLEL_BOTS.
        self._slots = asyncio.Semaphore(getattr(settings, "MAX_PARALLEL_BOTS", 3))
        # Лок только для атомарной проверки «не запускаем тот же meeting_id дважды»
        self._start_lock = asyncio.Lock()

    async def start_scheduled(self, scheduled_meeting_id: int):
        """
        Запуск запланированной встречи (вызывается APScheduler).

        Бот ПОДКЛЮЧАЕТСЯ к уже созданной встрече по сохранённой ссылке
        (sm.meeting_url) как гость, без авторизации Яндекс. Создание
        встреч автоматически не поддерживается — Yandex b2b-флоу
        непригоден к headless-автоматизации.

        Для рекуррентных (sm.recurrence != 'none') статус ScheduledMeeting
        НЕ меняется — запись остаётся pending и срабатывает по cron
        снова и снова. Каждое срабатывание создаёт отдельный Meeting,
        но `session_id` в BotInstance не проставляется, чтобы _finalize
        не выставлял 'completed' и не закрывал расписание.
        """
        logger.info(f"[scheduled:{scheduled_meeting_id}] Запуск запланированной встречи")
        async with self._start_lock:
            sm = await self._get_scheduled_meeting(scheduled_meeting_id)
            if not sm:
                logger.error(f"Запланированная встреча {scheduled_meeting_id} не найдена")
                return

            is_recurring = (sm.recurrence or "none") != "none"

            if is_recurring and not sm.is_active:
                logger.info(f"[scheduled:{sm.id}] Расписание приостановлено (is_active=False), пропускаем")
                return

            if not sm.meeting_url:
                logger.error(
                    f"[scheduled:{sm.id}] Нет meeting_url — нечего подключаться. "
                    "Запланированная встреча должна содержать ссылку на Телемост."
                )
                if not is_recurring:
                    await self._update_scheduled_status(
                        sm.id, "error",
                        "Не указана ссылка на встречу — бот не может подключиться",
                    )
                return

            if not is_recurring:
                await self._update_scheduled_status(sm.id, "starting")

            try:
                meeting_url = sm.meeting_url
                logger.info(
                    f"[scheduled:{sm.id}] Подключаюсь к {meeting_url} "
                    f"(recurrence={sm.recurrence})"
                )

                # Отправить ссылку в Telegram (если задана группа)
                telegram_chat_id = None
                if sm.telegram_group_id:
                    group = await self._get_telegram_group(sm.telegram_group_id)
                    if group:
                        telegram_chat_id = group.chat_id
                        await self.telegram.send_meeting_link(
                            group.chat_id, sm.title, meeting_url
                        )

                # Создать Meeting в БД
                meeting_id = await self._create_meeting(
                    title=sm.title,
                    owner_id=sm.created_by,
                    meeting_url=meeting_url,
                    telegram_chat_id=telegram_chat_id,
                )
                if not is_recurring:
                    await self._link_scheduled_to_meeting(sm.id, meeting_id)
                    await self._update_scheduled_status(sm.id, "active")

                # Бот заходит как гость — без авторизации Яндекс.
                # Для рекуррентных НЕ передаём session_id, чтобы _finalize не
                # выставил status=completed.
                session_id = None if is_recurring else sm.id
                await self._run_bot(meeting_id, meeting_url, session_id, use_auth=False)

            except Exception as e:
                logger.exception(f"[scheduled:{sm.id}] Ошибка: {e}")
                if not is_recurring:
                    await self._update_scheduled_status(sm.id, "error", str(e))

    @property
    def max_parallel(self) -> int:
        return getattr(settings, "MAX_PARALLEL_BOTS", 3)

    def _check_capacity(self) -> None:
        """Бросить RuntimeError если все слоты записи заняты."""
        if len(self._active) >= self.max_parallel:
            raise RuntimeError(
                f"Все слоты записи заняты ({len(self._active)}/{self.max_parallel} активн.). "
                "Дождитесь окончания одной встречи."
            )

    async def start_by_link(self, user_id: int, meeting_url: str,
                            title: str, telegram_group_id: int | None = None) -> int:
        """
        Подключение к существующей конференции по ссылке.
        Бот заходит как гость (без авторизации Яндекс).

        Параллельная запись поддерживается до MAX_PARALLEL_BOTS одновременно.
        """
        self._check_capacity()

        # Отправить ссылку в Telegram если указана группа
        telegram_chat_id = None
        if telegram_group_id:
            group = await self._get_telegram_group(telegram_group_id)
            if group:
                telegram_chat_id = group.chat_id
                await self.telegram.send_meeting_link(group.chat_id, title, meeting_url)

        meeting_id = await self._create_meeting(
            title=title, owner_id=user_id, meeting_url=meeting_url,
            telegram_chat_id=telegram_chat_id,
        )
        logger.info(f"[meeting:{meeting_id}] Подключение бота по ссылке: {meeting_url}")

        asyncio.create_task(
            self._run_bot(meeting_id, meeting_url, session_id=None, use_auth=False)
        )
        return meeting_id

    async def start_quick(self, user_id: int, title: str,
                          telegram_group_id: int | None = None) -> tuple[int, str]:
        """
        Быстрая встреча: создать конференцию + Telegram + записать.
        Возвращает (meeting_id, meeting_url).
        """
        self._check_capacity()

        # Создать конференцию
        creator = TelemostMeetingCreator(self.auth)
        meeting_url = await creator.create_meeting()
        logger.info(f"Быстрая встреча создана: {meeting_url}")

        # Telegram
        telegram_chat_id = None
        if telegram_group_id:
            group = await self._get_telegram_group(telegram_group_id)
            if group:
                telegram_chat_id = group.chat_id
                await self.telegram.send_meeting_link(
                    group.chat_id, title, meeting_url
                )

        # Создать Meeting
        meeting_id = await self._create_meeting(
            title=title, owner_id=user_id,
            meeting_url=meeting_url,
            telegram_chat_id=telegram_chat_id,
        )

        asyncio.create_task(
            self._run_bot(meeting_id, meeting_url, session_id=None, use_auth=True)
        )
        return meeting_id, meeting_url

    async def stop_bot(self, meeting_id: int):
        """Ручная остановка бота."""
        inst = self._active.get(meeting_id)
        if not inst:
            raise ValueError("Бот не найден")
        logger.info(f"[meeting:{meeting_id}] Ручная остановка бота")
        await self._finalize(inst)

    async def _run_bot(self, meeting_id: int, meeting_url: str,
                       session_id: int | None, use_auth: bool):
        """Основной цикл бота."""
        upload_dir = settings.UPLOAD_DIR / str(meeting_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        audio_path = str(upload_dir / "recorded.wav")

        cookies = self.auth.load_cookies() if use_auth and self.auth.is_authenticated else None
        headless = settings.BOT_HEADLESS

        # Per-meeting PulseAudio sink — иначе параллельные боты смикшируют аудио
        pulse_sink = sink_for_meeting(meeting_id)
        bot = TelemostBot(meeting_url, bot_name=settings.BOT_NAME, headless=headless, pulse_sink=pulse_sink)
        capture = AudioCapture(audio_path, sink_name=pulse_sink)

        inst = BotInstance(
            meeting_id=meeting_id,
            session_id=session_id,
            bot=bot,
            capture=capture,
            audio_path=audio_path,
            started_at=datetime.utcnow(),
        )
        self._active[meeting_id] = inst

        try:
            await self._update_meeting_status(meeting_id, "recording")

            # Per-meeting sink (создаём ДО запуска Chromium, иначе ему некуда лить аудио)
            logger.info(f"[meeting:{meeting_id}] Настройка PulseAudio sink {pulse_sink}...")
            ensure_pulseaudio_sink(pulse_sink)

            await bot.start(cookies=cookies)
            await bot.join_meeting()

            # Запуск аудио захвата:
            # 1. JS-based захват (перехват WebRTC remote streams) — для headless
            # 2. PulseAudio capture (fallback) — для headed режима
            js_capture_ok = await bot.start_js_audio_capture()
            if js_capture_ok:
                logger.info(f"[meeting:{meeting_id}] Используется JS аудио захват")
            else:
                logger.info(f"[meeting:{meeting_id}] JS захват не доступен, используем PulseAudio")

            # PulseAudio redirect + capture как fallback
            await bot.redirect_audio_to_sink()
            await capture.start()

            logger.info(f"[meeting:{meeting_id}] Запись началась (JS={js_capture_ok})")

            # Мониторинг (блокирующий до выхода)
            max_duration = settings.BOT_MAX_DURATION
            try:
                await asyncio.wait_for(
                    bot.monitor_participants(
                        check_interval=15,
                        alone_timeout=settings.BOT_ALONE_TIMEOUT,
                    ),
                    timeout=max_duration,
                )
            except asyncio.TimeoutError:
                logger.info(f"[meeting:{meeting_id}] Таймаут {max_duration}с, завершаем")

            await self._finalize(inst)

        except Exception as e:
            logger.exception(f"[meeting:{meeting_id}] Ошибка бота: {e}")
            await self._update_meeting_status(meeting_id, "error", str(e))
            await bot.leave()
            await capture.stop()
            await capture.cleanup()
            self._active.pop(meeting_id, None)

    async def _finalize(self, inst: BotInstance):
        """Завершение: стоп запись -> выход -> обработка."""
        logger.info(f"[meeting:{inst.meeting_id}] Финализация...")

        # 0. Собрать имена участников (пока бот ещё в конференции)
        participant_names = inst.bot.collected_participant_names
        if participant_names:
            logger.info(f"[meeting:{inst.meeting_id}] Участники Телемост: {participant_names}")
            await self._save_participant_names(inst.meeting_id, participant_names)
        else:
            logger.info(f"[meeting:{inst.meeting_id}] Имена участников не обнаружены")

        # 1. Остановить JS аудио захват (приоритет, всегда пробуем)
        js_audio_saved = False
        logger.info(f"[meeting:{inst.meeting_id}] Останавливаем JS аудио захват...")
        js_audio_saved = await inst.bot.stop_js_audio_capture(inst.audio_path)
        if js_audio_saved:
            logger.info(f"[meeting:{inst.meeting_id}] JS аудио сохранён: {inst.audio_path}")
        else:
            logger.info(f"[meeting:{inst.meeting_id}] JS аудио не доступен, используем PulseAudio")

        # 2. Остановить PulseAudio запись
        pulse_audio_path = await inst.capture.stop()

        # 3. Выход бота
        await inst.bot.leave()

        # 4. Выгрузить per-meeting sink (освобождаем PulseAudio ресурсы)
        await inst.capture.cleanup()

        self._active.pop(inst.meeting_id, None)

        if inst.session_id:
            await self._update_scheduled_status(inst.session_id, "completed")

        # Выбрать лучший аудио файл
        import subprocess

        audio_path = inst.audio_path

        # Если JS аудио не сохранён, используем PulseAudio запись
        if not js_audio_saved:
            audio_path = pulse_audio_path
            logger.info(f"[meeting:{inst.meeting_id}] Используем PulseAudio запись: {audio_path}")
        else:
            logger.info(f"[meeting:{inst.meeting_id}] Используем JS аудио: {audio_path}")

        audio_file = Path(audio_path)
        if not audio_file.exists():
            error_msg = "Аудиофайл не создан"
            logger.error(f"[meeting:{inst.meeting_id}] {error_msg}")
            await self._update_meeting_status(inst.meeting_id, "error", error_msg)
            return

        # Проверить уровень громкости
        try:
            vol_result = subprocess.run(
                ["ffmpeg", "-i", audio_path, "-af", "volumedetect", "-f", "null", "/dev/null"],
                capture_output=True, text=True, timeout=30,
            )
            for line in vol_result.stderr.split("\n"):
                if "mean_volume" in line or "max_volume" in line:
                    logger.info(f"[meeting:{inst.meeting_id}] Аудио: {line.strip()}")
        except Exception as e:
            logger.warning(f"[meeting:{inst.meeting_id}] Не удалось проверить громкость: {e}")

        # Обновить meeting и запустить обработку
        await self._update_meeting_audio(inst.meeting_id, audio_path)

        # Не запускаем обработку напрямую — кладём в очередь, воркер обработает.
        # Это гарантирует что Whisper+Ollama не будут конкурировать за GPU
        # когда параллельно идёт несколько записей.
        from app.services.processing import enqueue_meeting_processing
        await enqueue_meeting_processing(inst.meeting_id)

        logger.info(f"[meeting:{inst.meeting_id}] Бот завершил работу, обработка запущена")

    def get_active_bots(self) -> list[dict]:
        return [
            {
                "meeting_id": mid,
                "participants": inst.bot.participant_count,
                "started_at": inst.started_at.isoformat(),
            }
            for mid, inst in self._active.items()
        ]

    # ── DB helpers ──

    async def _get_scheduled_meeting(self, id: int) -> ScheduledMeeting | None:
        async with async_session() as session:
            result = await session.execute(
                select(ScheduledMeeting).where(ScheduledMeeting.id == id)
            )
            return result.scalar_one_or_none()

    async def _get_telegram_group(self, id: int) -> TelegramGroup | None:
        async with async_session() as session:
            result = await session.execute(
                select(TelegramGroup).where(TelegramGroup.id == id)
            )
            return result.scalar_one_or_none()

    async def _create_meeting(self, title: str, owner_id: int,
                              meeting_url: str | None = None,
                              telegram_chat_id: str | None = None) -> int:
        async with async_session() as session:
            meeting = Meeting(
                title=title,
                date=datetime.utcnow(),
                status="waiting_bot",
                audio_path="",
                owner_id=owner_id,
                source="bot",
                meeting_url=meeting_url,
                telegram_chat_id=telegram_chat_id,
            )
            session.add(meeting)
            await session.commit()
            await session.refresh(meeting)
            return meeting.id

    async def _update_meeting_status(self, id: int, status: str, error: str | None = None):
        async with async_session() as session:
            result = await session.execute(select(Meeting).where(Meeting.id == id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.status = status
                if error:
                    meeting.error_message = error
                await session.commit()

    async def _update_meeting_audio(self, id: int, path: str):
        async with async_session() as session:
            result = await session.execute(select(Meeting).where(Meeting.id == id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.audio_path = path
                meeting.status = "uploaded"
                await session.commit()

    async def _update_scheduled_status(self, id: int, status: str, error: str | None = None):
        async with async_session() as session:
            result = await session.execute(
                select(ScheduledMeeting).where(ScheduledMeeting.id == id)
            )
            sm = result.scalar_one_or_none()
            if sm:
                sm.status = status
                if error:
                    sm.error_message = error
                await session.commit()

    async def _save_participant_names(self, meeting_id: int, names: list[str]):
        import json
        async with async_session() as session:
            result = await session.execute(select(Meeting).where(Meeting.id == meeting_id))
            meeting = result.scalar_one_or_none()
            if meeting:
                meeting.participant_names = json.dumps(names, ensure_ascii=False)
                await session.commit()

    async def _link_scheduled_to_meeting(self, sm_id: int, meeting_id: int):
        async with async_session() as session:
            result = await session.execute(
                select(ScheduledMeeting).where(ScheduledMeeting.id == sm_id)
            )
            sm = result.scalar_one_or_none()
            if sm:
                sm.meeting_id = meeting_id
                await session.commit()

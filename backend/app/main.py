import logging
import logging.handlers
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select, text

from app.config import settings
from app.database import engine, Base, async_session

# ── Подавление повторяющихся warnings от библиотек ───────────────────
warnings.filterwarnings("ignore", message=".*backend.*parameter is not used by TorchCodec.*")
warnings.filterwarnings("ignore", message=".*TensorFloat-32.*TF32.*has been disabled.*")
warnings.filterwarnings("ignore", message=".*std\\(\\).*degrees of freedom.*")
warnings.filterwarnings("ignore", category=UserWarning, module="passlib")

# ── Logging ──────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FORMAT,
    datefmt=LOG_DATE_FORMAT,
    handlers=[
        logging.StreamHandler(),
        logging.handlers.RotatingFileHandler(
            LOG_DIR / "app.log",
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        ),
    ],
)

# Уменьшаем шум от библиотек
logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("speechbrain.utils.checkpoints").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Сервер запускается ===")

    # Create tables on startup (fallback if alembic not run)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Миграция: добавить новые колонки (если БД уже существует)
        # NOTE: column definitions are hardcoded constants, not user input.
        _MIGRATION_COLUMNS = (
            text("ALTER TABLE meetings ADD COLUMN meeting_url TEXT"),
            text("ALTER TABLE meetings ADD COLUMN telegram_chat_id TEXT"),
            text("ALTER TABLE meetings ADD COLUMN participant_names TEXT"),
            text("ALTER TABLE summaries ADD COLUMN topics TEXT"),
            text("ALTER TABLE tasks ADD COLUMN context TEXT"),
            text("ALTER TABLE planfix_sync_state ADD COLUMN task_count INTEGER NOT NULL DEFAULT 0"),
            text("ALTER TABLE scheduled_meetings ADD COLUMN meeting_url TEXT"),
        )
        for stmt in _MIGRATION_COLUMNS:
            try:
                await conn.execute(stmt)
                logger.info("Миграция: добавлена колонка")
            except Exception:
                pass  # колонка уже есть
    logger.info("БД инициализирована")

    # ── Phase 2: инициализация сервисов ──
    from app.services.telegram_service import TelegramService
    from app.services.telemost_auth import YandexAuth
    from app.services.bot_manager import BotManager
    from app.services.scheduler_service import SchedulerService
    from app.models.scheduled_meeting import ScheduledMeeting

    # Telegram
    telegram = TelegramService(settings.TELEGRAM_BOT_TOKEN)
    if settings.TELEGRAM_BOT_TOKEN:
        info = await telegram.verify_bot()
        if info:
            logger.info(f"Telegram бот: @{info.get('username')}")
            await telegram.set_commands()
        else:
            logger.warning("Telegram бот: токен невалиден или не задан")
    else:
        logger.info("Telegram бот: токен не задан, уведомления отключены")

    # Yandex Auth
    yandex_auth = YandexAuth()
    if yandex_auth.is_authenticated:
        logger.info("Яндекс авторизация: куки найдены")
    else:
        logger.info("Яндекс авторизация: не настроена (запустите scripts/setup_yandex_auth.py)")

    # Bot Manager
    bot_manager = BotManager(
        telegram_service=telegram,
        yandex_auth=yandex_auth,
    )

    # Очередь обработки (Whisper+Ollama последовательно)
    from app.services.processing import start_processing_worker, recover_stuck_meetings
    start_processing_worker()
    logger.info("Processing worker: запущен")
    # Подобрать зависшие встречи (uploaded / processing / etc) — переживут рестарт
    recovered = await recover_stuck_meetings()
    if recovered:
        logger.info(f"Recovery: {recovered} встреч поставлены в очередь после рестарта")

    # Scheduler
    scheduler = SchedulerService()
    scheduler.start()

    # PlanFix фоновая синхронизация справочников (раз в 15 мин + первый запуск через 30с)
    from app.services.planfix_sync import schedule_planfix_sync
    schedule_planfix_sync(scheduler.scheduler, interval_minutes=15)

    # Wiki.js RAG: первичный синк через 60с + ежечасный
    from app.services.wiki_sync import schedule_wiki_sync
    schedule_wiki_sync(scheduler.scheduler, interval_minutes=60, initial_delay_seconds=60)

    # Восстановить запланированные встречи из БД при старте.
    # One-off: status='pending'. Weekly: is_active=True (status может быть 'pending'
    # постоянно — это допустимо, см. ScheduledMeeting docstring).
    async with async_session() as session:
        result = await session.execute(
            select(ScheduledMeeting).where(
                ((ScheduledMeeting.recurrence == "none") & (ScheduledMeeting.status == "pending"))
                | ((ScheduledMeeting.recurrence != "none") & (ScheduledMeeting.is_active.is_(True)))
            )
        )
        pending = list(result.scalars().all())
        restored_one_off = 0
        restored_recurring = 0
        for sm in pending:
            try:
                if (sm.recurrence or "none") == "weekly":
                    scheduler.schedule_recurring_weekly(
                        sm.id,
                        day_of_week=sm.recurrence_day,
                        time_str=sm.recurrence_time,
                        tz_name=sm.timezone or "Europe/Moscow",
                        callback=bot_manager.start_scheduled,
                    )
                    restored_recurring += 1
                else:
                    if not sm.scheduled_at:
                        logger.warning(f"[scheduled:{sm.id}] one-off без scheduled_at — пропускаем")
                        continue
                    scheduler.schedule_meeting(
                        sm.id, sm.scheduled_at,
                        callback=bot_manager.start_scheduled,
                    )
                    restored_one_off += 1
            except Exception as e:
                logger.exception(f"[scheduled:{sm.id}] Не удалось восстановить job: {e}")
        if pending:
            logger.info(
                f"Recovery планировщика: восстановлено {restored_one_off} одноразовых "
                f"+ {restored_recurring} рекуррентных"
            )

    # Telegram Bot Handler (двусторонние команды)
    telegram_handler = None
    if settings.TELEGRAM_BOT_TOKEN:
        from app.services.telegram_bot_handler import TelegramBotHandler
        telegram_handler = TelegramBotHandler(
            bot_token=settings.TELEGRAM_BOT_TOKEN,
            bot_manager=bot_manager,
            telegram_service=telegram,
        )
        telegram_handler.start()
        logger.info("Telegram Bot Handler: запущен")

    app.state.telegram = telegram
    app.state.yandex_auth = yandex_auth
    app.state.bot_manager = bot_manager
    app.state.scheduler = scheduler
    app.state.telegram_handler = telegram_handler

    logger.info("=== Сервер готов ===")
    yield

    # Shutdown
    logger.info("=== Сервер останавливается ===")
    if telegram_handler:
        await telegram_handler.stop()
    scheduler.shutdown()
    for mid in list(bot_manager._active.keys()):
        try:
            await bot_manager.stop_bot(mid)
        except Exception:
            pass


app = FastAPI(title="Meeting Summary API", version="2.0.0", lifespan=lifespan)

# SECURITY: allow_origins=["*"] with allow_credentials=True is forbidden by
# the CORS spec and browsers will reject it.  When credentials are needed,
# origins must be explicit.  We read allowed origins from settings; if the
# list is empty we fall back to localhost dev origins (Vite) instead of "*"
# so a misconfigured production deploy is not open to every origin.
_DEV_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]
_cors_origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()] if settings.CORS_ORIGINS else []
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins or _DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from app.api.router import api_router  # noqa: E402

import time as _time  # noqa: E402
from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402
from starlette.requests import Request  # noqa: E402


class SlowRequestMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = _time.monotonic()
        response = await call_next(request)
        elapsed = _time.monotonic() - start
        if elapsed > 1.0:
            logger.warning(f"Slow request: {request.method} {request.url.path} — {elapsed:.1f}s")
        return response


app.add_middleware(SlowRequestMiddleware)
app.include_router(api_router, prefix="/api")

# Раздача Mini App (собранный frontend)
_miniapp_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "miniapp" / "dist"
if _miniapp_dist.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/miniapp", StaticFiles(directory=str(_miniapp_dist), html=True), name="miniapp")
    logger.info(f"Mini App раздаётся из {_miniapp_dist}")

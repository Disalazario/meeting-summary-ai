from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    SECRET_KEY: str = "change-me-in-production"
    HUGGINGFACE_TOKEN: str = ""
    DATABASE_URL: str = "sqlite+aiosqlite:///./app.db"

    # LLM (только Ollama — локальная модель)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5:7b"

    # JWT
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 24

    # Paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    UPLOAD_DIR: Path = Path(__file__).resolve().parent.parent / "uploads"

    # Limits
    MAX_UPLOAD_SIZE_MB: int = 500

    # Telegram
    TELEGRAM_BOT_TOKEN: str = ""

    # Bot
    BOT_HEADLESS: bool = True
    BOT_MAX_DURATION: int = 14400  # 4 часа
    BOT_ALONE_TIMEOUT: int = 60
    BOT_NAME: str = "Бот-секретарь"
    # Сколько ботов могут писать параллельно. Каждый ≈1.5–2 ГБ RAM + 1 CPU-ядро.
    # Обработка (Whisper+Ollama) всё равно идёт последовательно через очередь.
    MAX_PARALLEL_BOTS: int = 3

    # App URL (для ссылок в Telegram)
    APP_URL: str = "http://localhost:5173"

    # PlanFix
    PLANFIX_ACCOUNT: str = ""          # имя аккаунта (xxx.planfix.com)
    PLANFIX_API_TOKEN: str = ""        # Bearer-токен REST API v2
    PLANFIX_CACHE_TTL: int = 300       # кэш пользователей/проектов (сек)

    # CORS — comma-separated list of allowed origins (e.g. "http://localhost:5173,https://app.example.com")
    # Leave empty to fall back to localhost dev origins.
    CORS_ORIGINS: str = ""

    # Разрешить запуск с дефолтным SECRET_KEY (только локальная разработка).
    ALLOW_INSECURE_DEFAULTS: bool = False

    # Telegram Mini App
    MINI_APP_URL: str = ""

    # Telegram bot commands
    TELEGRAM_ALLOWED_CHAT_IDS: str = ""  # comma-separated, empty = allow all
    TELEGRAM_BOT_USER_ID: int = 1  # owner_id для встреч из Telegram

    # МангоТелеком (VPBX) — звонки будут попадать в очередь обработки.
    # Пока заглушка: только поля конфига, фактической интеграции нет.
    MANGO_VPBX_API_KEY: str = ""
    MANGO_VPBX_API_SALT: str = ""
    MANGO_WEBHOOK_TOKEN: str = ""

    # AmoCRM — будущая интеграция для отправки задач (как PlanFix).
    AMOCRM_DOMAIN: str = ""          # mycompany.amocrm.ru
    AMOCRM_CLIENT_ID: str = ""
    AMOCRM_CLIENT_SECRET: str = ""
    AMOCRM_REDIRECT_URI: str = ""

    # Wiki.js — RAG-индекс для обогащения саммари и чата контекстом продукта.
    # Пока только конфиг; реализация — отдельной задачей.
    WIKI_BASE_URL: str = ""          # https://wiki.example.com
    WIKI_API_TOKEN: str = ""

    model_config = {
        "env_file": str(Path(__file__).resolve().parent.parent.parent / ".env"),
        "env_file_encoding": "utf-8",
    }


settings = Settings()

# Ensure upload directory exists
settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# SECURITY: с дефолтным SECRET_KEY все JWT подделываются — не даём запуститься.
if settings.SECRET_KEY == "change-me-in-production" and not settings.ALLOW_INSECURE_DEFAULTS:
    raise RuntimeError(
        "SECRET_KEY is set to the default value — refusing to start. "
        "Generate one (`python -c \"import secrets; print(secrets.token_hex(32))\"`) "
        "and put it in .env, or set ALLOW_INSECURE_DEFAULTS=true for local development."
    )

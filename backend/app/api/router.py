from fastapi import APIRouter

from app.api import auth, users, meetings, transcripts, summaries, tasks, chat, export
from app.api import bot, schedule, telegram
from app.api import miniapp, planfix, voice_profile, telegram_link
from app.api import notes, integrations, wiki, search

api_router = APIRouter()


@api_router.get("/health", tags=["system"])
async def health_check():
    return {"status": "ok", "version": "2.0.0"}


# Phase 1
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(voice_profile.router, prefix="/users", tags=["voice"])
api_router.include_router(telegram_link.router, prefix="/users", tags=["telegram-link"])
api_router.include_router(meetings.router, prefix="/meetings", tags=["meetings"])
api_router.include_router(transcripts.router, prefix="/meetings", tags=["transcripts"])
api_router.include_router(summaries.router, prefix="/meetings", tags=["summaries"])
api_router.include_router(tasks.router, prefix="/meetings", tags=["tasks"])
api_router.include_router(chat.router, prefix="/meetings", tags=["chat"])
api_router.include_router(notes.router, prefix="/meetings", tags=["notes"])
api_router.include_router(export.router, prefix="/meetings", tags=["export"])

# Phase 2
api_router.include_router(bot.router, prefix="/bot", tags=["bot"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
api_router.include_router(telegram.router, prefix="/telegram", tags=["telegram"])

# PlanFix
api_router.include_router(planfix.router, tags=["planfix"])

# Mini App (Telegram Web App)
api_router.include_router(miniapp.router, prefix="/miniapp", tags=["miniapp"])

# Внешние интеграции (статус подключения МангоТелеком, AmoCRM и т.п.)
api_router.include_router(integrations.router, prefix="/integrations", tags=["integrations"])

# Wiki.js RAG — статус локального индекса + ручной sync
api_router.include_router(wiki.router, prefix="/wiki", tags=["wiki"])

# Глобальный поиск по встречам
api_router.include_router(search.router, prefix="/search", tags=["search"])

"""
API-роуты для Telegram Mini App.
Используют авторизацию через Telegram initData вместо JWT.
Показывают все совещания без фильтра по владельцу.
"""

import asyncio
import json
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.summary import Summary
from app.models.transcript import TranscriptSegment
from app.models.task import Task
from app.models.chat import ChatMessage
from app.models.user import User
from app.schemas.meeting import MeetingResponse, MeetingListItem
from app.schemas.task import PlanFixProjectItem, PlanFixUserItem
from app.services.auth_service import get_telegram_user

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_meeting(db: AsyncSession, meeting_id: int) -> Meeting:
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")
    return meeting


@router.get("/meetings", response_model=list[MeetingListItem])
async def list_meetings(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    result = await db.execute(
        select(Meeting)
        .where(Meeting.status.in_(["done", "processing", "transcribing", "diarizing", "summarizing", "uploaded"]))
        .order_by(Meeting.date.desc())
    )
    return result.scalars().all()


@router.get("/meetings/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    return await _get_meeting(db, meeting_id)


@router.get("/meetings/{meeting_id}/summary")
async def get_summary(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    result = await db.execute(
        select(Summary).where(Summary.meeting_id == meeting_id)
    )
    summary = result.scalar_one_or_none()
    if summary is None:
        raise HTTPException(status_code=404, detail="Саммари ещё не готово")

    key_decisions = []
    if summary.key_decisions:
        try:
            key_decisions = json.loads(summary.key_decisions)
        except (json.JSONDecodeError, TypeError):
            key_decisions = []

    return {
        "id": summary.id,
        "summary_text": summary.summary_text,
        "brief": summary.brief,
        "key_decisions": key_decisions,
    }


@router.get("/meetings/{meeting_id}/transcript")
async def get_transcript(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    return result.scalars().all()


@router.get("/meetings/{meeting_id}/tasks")
async def get_tasks(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    result = await db.execute(
        select(Task).where(Task.meeting_id == meeting_id)
    )
    return result.scalars().all()


@router.patch("/meetings/{meeting_id}/tasks/{task_id}")
async def toggle_task(
    meeting_id: int,
    task_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.meeting_id == meeting_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if "done" in body:
        task.done = body["done"]
    await db.commit()
    return task


@router.delete("/meetings/{meeting_id}/tasks/{task_id}", status_code=204)
async def delete_task_miniapp(
    meeting_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.meeting_id == meeting_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    await db.delete(task)
    await db.commit()


@router.get("/meetings/{meeting_id}/chat/history")
async def chat_history(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.meeting_id == meeting_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at)
    )
    return result.scalars().all()


@router.post("/meetings/{meeting_id}/chat")
async def chat(
    meeting_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    await _get_meeting(db, meeting_id)
    message = body.get("message", "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Пустое сообщение")

    from app.services.llm_service import LLMService

    # История чата
    history_result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.meeting_id == meeting_id, ChatMessage.user_id == user.id)
        .order_by(ChatMessage.created_at)
    )
    history = [
        {"role": msg.role, "content": msg.content}
        for msg in history_result.scalars().all()
    ]

    # Транскрипт для контекста
    transcript_result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    segments = transcript_result.scalars().all()
    transcript_text = "\n".join(
        f"{s.speaker_label}: {s.text}" for s in segments
    )

    # Обрезать транскрипт для чата (чтобы не перегружать LLM)
    max_context = 15000
    if len(transcript_text) > max_context:
        transcript_text = transcript_text[:max_context] + "\n... (обрезано)"

    llm = LLMService()
    response = await asyncio.to_thread(llm.chat, transcript_text, history, message)

    # Сохранить в БД
    db.add(ChatMessage(meeting_id=meeting_id, user_id=user.id, role="user", content=message))
    db.add(ChatMessage(meeting_id=meeting_id, user_id=user.id, role="assistant", content=response))
    await db.commit()

    return {"response": response}


# ── PlanFix integration ──

@router.get("/planfix/status")
async def planfix_status_miniapp(user: User = Depends(get_telegram_user)):
    from app.config import settings
    return {
        "configured": bool(settings.PLANFIX_ACCOUNT and settings.PLANFIX_API_TOKEN),
        "account": settings.PLANFIX_ACCOUNT or None,
    }


@router.get("/planfix/users", response_model=list[PlanFixUserItem])
async def planfix_users_miniapp(user: User = Depends(get_telegram_user)):
    from app.config import settings
    if not settings.PLANFIX_ACCOUNT or not settings.PLANFIX_API_TOKEN:
        raise HTTPException(400, "PlanFix не настроен")
    from app.services.planfix_service import get_planfix_service
    try:
        return await get_planfix_service().get_users()
    except httpx.TimeoutException:
        raise HTTPException(504, "PlanFix API не отвечает (таймаут)")
    except httpx.ConnectError:
        raise HTTPException(502, "PlanFix API недоступен")


@router.get("/planfix/projects", response_model=list[PlanFixProjectItem])
async def planfix_projects_miniapp(user: User = Depends(get_telegram_user)):
    from app.config import settings
    if not settings.PLANFIX_ACCOUNT or not settings.PLANFIX_API_TOKEN:
        raise HTTPException(400, "PlanFix не настроен")
    from app.services.planfix_service import get_planfix_service
    try:
        return await get_planfix_service().get_projects()
    except httpx.TimeoutException:
        raise HTTPException(504, "PlanFix API не отвечает (таймаут)")
    except httpx.ConnectError:
        raise HTTPException(502, "PlanFix API недоступен")


@router.post("/meetings/{meeting_id}/tasks/send-to-planfix")
async def send_tasks_to_planfix_miniapp(
    meeting_id: int,
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    from datetime import datetime, timezone
    from app.config import settings
    if not settings.PLANFIX_ACCOUNT or not settings.PLANFIX_API_TOKEN:
        raise HTTPException(400, "PlanFix не настроен")

    await _get_meeting(db, meeting_id)

    task_ids = body.get("task_ids", [])
    if not task_ids:
        raise HTTPException(400, "Не выбраны задачи")

    result = await db.execute(
        select(Task).where(Task.meeting_id == meeting_id, Task.id.in_(task_ids))
    )
    tasks = result.scalars().all()
    if not tasks:
        raise HTTPException(400, "Задачи не найдены")

    from app.services.planfix_service import get_planfix_service
    svc = get_planfix_service()

    project_id = body.get("project_id")
    assignee_ids = body.get("assignee_ids", {})
    creator_id = body.get("creator_id")
    global_deadline = body.get("deadline")
    results = []

    for task in tasks:
        if task.planfix_task_id:
            results.append({"task_id": task.id, "planfix_task_id": task.planfix_task_id, "success": True, "error": "Уже отправлена"})
            continue

        a_list = None
        tid = str(task.id)
        if tid in assignee_ids:
            a_list = [assignee_ids[tid]]  # "user:N" string

        try:
            pf = await svc.create_task(
                name=task.description,
                description=task.description,
                project_id=int(project_id) if project_id else None,
                assignee_ids=a_list,
                creator_id=creator_id,  # "user:N" string
                deadline=global_deadline or task.deadline,
            )
            pf_id = pf.get("id") or pf.get("task", {}).get("id")
            task.planfix_task_id = pf_id
            task.planfix_sent_at = datetime.now(timezone.utc).isoformat()
            results.append({"task_id": task.id, "planfix_task_id": pf_id, "success": True})
        except Exception as e:
            logger.error(f"Ошибка отправки задачи {task.id} в PlanFix: {e}")
            # SECURITY: Do not leak internal exception details to the client
            results.append({"task_id": task.id, "planfix_task_id": None, "success": False, "error": "Ошибка отправки в PlanFix"})

    await db.commit()
    return results


async def _build_pdf(db: AsyncSession, meeting_id: int):
    """Сгенерировать PDF для совещания. Возвращает (meeting, pdf_bytes)."""
    meeting = await _get_meeting(db, meeting_id)
    from app.services.pdf_service import generate_pdf

    summary_result = await db.execute(
        select(Summary).where(Summary.meeting_id == meeting_id)
    )
    summary = summary_result.scalar_one_or_none()
    transcript_result = await db.execute(
        select(TranscriptSegment)
        .where(TranscriptSegment.meeting_id == meeting_id)
        .order_by(TranscriptSegment.start_time)
    )
    segments = transcript_result.scalars().all()
    tasks_result = await db.execute(
        select(Task).where(Task.meeting_id == meeting_id)
    )
    tasks = tasks_result.scalars().all()

    pdf_bytes = generate_pdf(meeting, summary, segments, tasks)
    return meeting, pdf_bytes


@router.get("/meetings/{meeting_id}/export/pdf")
async def export_pdf(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    """Скачивание PDF напрямую (для веба).

    ⚠ В Telegram WebView (особенно iOS) обычное скачивание через blob
    может не работать — используйте POST /meetings/{id}/export/pdf/send,
    бот пришлёт PDF файлом в чат.
    """
    _, pdf_bytes = await _build_pdf(db, meeting_id)
    from fastapi.responses import Response
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="meeting_{meeting_id}.pdf"'},
    )


@router.post("/meetings/{meeting_id}/export/pdf/send")
async def send_pdf_to_chat(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_telegram_user),
):
    """Сгенерировать PDF и отправить файлом в чат с ботом — у пользователя
    он появится как обычный документ Telegram, скачиваемый штатно.

    Это рекомендованный способ для Mini App: blob+download в WebView нестабилен.
    """
    from app.config import settings
    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(503, "Telegram-бот не настроен")
    if not user.telegram_id:
        raise HTTPException(
            400,
            "У пользователя нет привязанного Telegram. Откройте Mini App из бота.",
        )

    meeting, pdf_bytes = await _build_pdf(db, meeting_id)

    from app.services.telegram_service import TelegramService
    bot = TelegramService(settings.TELEGRAM_BOT_TOKEN)
    safe_title = (meeting.title or f"meeting_{meeting_id}")[:60].replace("/", "_")
    ok = await bot.send_document(
        chat_id=user.telegram_id,
        file_bytes=pdf_bytes,
        filename=f"{safe_title}.pdf",
        caption=f"📄 PDF-отчёт совещания «{meeting.title}»",
    )
    if not ok:
        raise HTTPException(502, "Не удалось отправить файл через Telegram")
    return {"status": "sent", "size_bytes": len(pdf_bytes)}

"""PlanFix API endpoints — пользователи, проекты, отправка задач.

Списки users/projects читаются из локального кеша в БД (планфикс-API синхронизируется
фоном раз в 15 минут). UI больше не ждёт 45 секунд при открытии Gantt.
"""

import logging
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.user import User
from app.schemas.task import (
    PlanFixProjectItem,
    PlanFixSendRequest,
    PlanFixSendResult,
    PlanFixTaskItem,
    PlanFixUserItem,
)
from app.services.auth_service import get_current_user
from app.services.planfix_service import get_planfix_service
from app.services.planfix_sync import (
    get_projects_from_cache,
    get_sync_state,
    get_tasks_by_user_from_cache,
    get_users_from_cache,
    sync_planfix_tasks_to_db,
    sync_planfix_to_db,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _check_configured():
    if not settings.PLANFIX_ACCOUNT or not settings.PLANFIX_API_TOKEN:
        raise HTTPException(400, "PlanFix не настроен")


@router.get("/planfix/status")
async def planfix_status(user: User = Depends(get_current_user)):
    """Проверка настроен ли PlanFix + информация о последней синхронизации."""
    state = await get_sync_state()
    return {
        "configured": bool(settings.PLANFIX_ACCOUNT and settings.PLANFIX_API_TOKEN),
        "account": settings.PLANFIX_ACCOUNT or None,
        "sync": state,
    }


@router.get("/planfix/users", response_model=list[PlanFixUserItem])
async def list_planfix_users(user: User = Depends(get_current_user)):
    """Пользователи PlanFix из локального кеша (мгновенно)."""
    _check_configured()
    return await get_users_from_cache()


@router.get("/planfix/projects", response_model=list[PlanFixProjectItem])
async def list_planfix_projects(user: User = Depends(get_current_user)):
    """Проекты PlanFix из локального кеша (мгновенно)."""
    _check_configured()
    return await get_projects_from_cache()


@router.post("/planfix/sync")
async def trigger_planfix_sync(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Запустить фоновую синхронизацию справочников и сразу вернуть текущее состояние.

    Пользователь видит «синхронизируется...» и через 30–60 сек список обновится.
    """
    _check_configured()
    background.add_task(sync_planfix_to_db)
    return await get_sync_state()


@router.get("/planfix/tasks", response_model=list[PlanFixTaskItem])
async def list_planfix_tasks(
    project_id: int | None = None,
    user_id: str | None = None,
    user: User = Depends(get_current_user),
):
    """Задачи PlanFix для диаграммы Ганта.

    Передайте либо project_id (все задачи проекта — live API),
    либо user_id (все задачи пользователя через все проекты — из локального кеша).

    Кеш по user_id заполняется фоновым job-ом `sync_planfix_tasks_to_db`
    раз в час. Без этого ограниченный scope токена не даёт server-side
    фильтр по assignee, и активные задачи (обычно с большими offset)
    в выборку не попадают.
    """
    _check_configured()
    if (project_id is None) == (user_id is None):
        raise HTTPException(400, "Укажите ровно один из параметров: project_id ИЛИ user_id")
    svc = get_planfix_service()
    try:
        if user_id is not None:
            cached = await get_tasks_by_user_from_cache(user_id)
            if cached is not None:
                return cached
            # Cache ещё пуст — live (с ограниченной глубиной)
            logger.info(f"PlanFix tasks cache пуст, fallback на live API для {user_id}")
            return await svc.get_tasks_by_user(user_id)
        return await svc.get_tasks_by_project(project_id)
    except httpx.TimeoutException:
        raise HTTPException(504, "PlanFix API не отвечает (таймаут)")
    except httpx.ConnectError:
        raise HTTPException(502, "PlanFix API недоступен")


@router.post("/planfix/sync/tasks")
async def trigger_planfix_tasks_sync(
    background: BackgroundTasks,
    user: User = Depends(get_current_user),
):
    """Принудительная синхронизация задач (5–10 мин в фоне)."""
    _check_configured()
    background.add_task(sync_planfix_tasks_to_db)
    return await get_sync_state()


@router.post(
    "/meetings/{meeting_id}/tasks/send-to-planfix",
    response_model=list[PlanFixSendResult],
)
async def send_tasks_to_planfix(
    meeting_id: int,
    data: PlanFixSendRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отправить выбранные задачи в PlanFix."""
    _check_configured()

    # Проверить что совещание принадлежит пользователю
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(404, "Совещание не найдено")

    # Загрузить выбранные задачи
    result = await db.execute(
        select(Task).where(
            Task.meeting_id == meeting_id,
            Task.id.in_(data.task_ids),
        )
    )
    tasks = result.scalars().all()
    if not tasks:
        raise HTTPException(400, "Задачи не найдены")

    svc = get_planfix_service()
    results = []

    for task in tasks:
        # Пропустить уже отправленные
        if task.planfix_task_id:
            results.append(PlanFixSendResult(
                task_id=task.id,
                planfix_task_id=task.planfix_task_id,
                success=True,
                error="Уже отправлена",
            ))
            continue

        # Определить исполнителя для этой задачи
        assignee_list = None
        if data.assignee_ids and str(task.id) in data.assignee_ids:
            assignee_list = [data.assignee_ids[str(task.id)]]

        try:
            # Описание для PlanFix: контекст («зачем») идёт в тело,
            # сам description — заголовок задачи.
            pf_description = task.description
            if task.context:
                pf_description = f"{task.description}\n\nКонтекст: {task.context}"

            pf_result = await svc.create_task(
                name=task.description,
                description=pf_description,
                project_id=data.project_id,
                assignee_ids=assignee_list,
                creator_id=data.creator_id,
                deadline=data.deadline or task.deadline,
            )
            pf_id = pf_result.get("id") or pf_result.get("task", {}).get("id")
            task.planfix_task_id = pf_id
            task.planfix_sent_at = datetime.now(timezone.utc).isoformat()
            results.append(PlanFixSendResult(
                task_id=task.id, planfix_task_id=pf_id, success=True
            ))
            logger.info(f"Задача {task.id} отправлена в PlanFix: pf_id={pf_id}")
        except Exception as e:
            logger.error(f"Ошибка отправки задачи {task.id} в PlanFix: {e}")
            # SECURITY: Do not leak internal exception details to the client
            results.append(PlanFixSendResult(
                task_id=task.id, planfix_task_id=None, success=False,
                error="Ошибка отправки в PlanFix",
            ))

    await db.commit()
    return results

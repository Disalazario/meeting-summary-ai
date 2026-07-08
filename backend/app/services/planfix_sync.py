"""Фоновая синхронизация справочников PlanFix в локальный кеш.

Использование:
    await sync_planfix_to_db()                 # справочники (users/projects, ~30с)
    await sync_planfix_tasks_to_db()           # ВСЕ задачи (~5–10 мин)
    schedule_planfix_sync(scheduler)           # обе синхронизации фоном
"""

import asyncio
import json
import logging
from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select

from app.config import settings
from app.database import async_session
from app.models.planfix_cache import (
    PlanFixProjectCache, PlanFixSyncState, PlanFixTaskCache,
    PlanFixTaskUserLink, PlanFixUserCache,
)
from app.services.planfix_service import get_planfix_service

logger = logging.getLogger(__name__)

_sync_lock = asyncio.Lock()
_tasks_sync_lock = asyncio.Lock()

# Максимум страниц при полной синхронизации задач. 500 × 100 = 50 тыс. задач.
# Хватит на годы работы 4–7 человек.
MAX_TASKS_SYNC_PAGES = 500


async def _save_sync_state(
    status: str, error: str | None,
    users: int | None = None, projects: int | None = None, tasks: int | None = None,
):
    """Обновить состояние последней синхронизации. None → оставить как было."""
    async with async_session() as session:
        result = await session.execute(
            select(PlanFixSyncState).where(PlanFixSyncState.key == "last_sync")
        )
        row = result.scalar_one_or_none()
        now = datetime.utcnow()
        if row is None:
            row = PlanFixSyncState(
                key="last_sync", last_sync_at=now, last_status=status,
                last_error=error,
                user_count=users or 0, project_count=projects or 0, task_count=tasks or 0,
            )
            session.add(row)
        else:
            row.last_sync_at = now
            row.last_status = status
            row.last_error = error
            if users is not None:
                row.user_count = users
            if projects is not None:
                row.project_count = projects
            if tasks is not None:
                row.task_count = tasks
        await session.commit()


async def sync_planfix_to_db() -> dict:
    """Полная синхронизация: тянет с PlanFix → переписывает кеш в БД.

    Возвращает dict со статистикой. Если синхронизация уже идёт — ждёт её
    окончания и возвращает результат (без двойной нагрузки на API).
    """
    if not (settings.PLANFIX_ACCOUNT and settings.PLANFIX_API_TOKEN):
        logger.info("PlanFix sync: не настроен, пропускаем")
        return {"status": "skipped", "reason": "not_configured"}

    if _sync_lock.locked():
        logger.info("PlanFix sync: уже идёт, ждём")
    async with _sync_lock:
        svc = get_planfix_service()
        logger.info("PlanFix sync: начало")
        start = datetime.utcnow()
        try:
            users = await svc.get_users(force_refresh=True)
            projects = await svc.get_projects(force_refresh=True)
        except Exception as e:
            logger.exception("PlanFix sync: ошибка")
            await _save_sync_state("error", str(e)[:300], 0, 0)
            return {"status": "error", "error": str(e)}

        async with async_session() as session:
            await session.execute(delete(PlanFixUserCache))
            for u in users:
                session.add(PlanFixUserCache(planfix_id=u["id"], name=u["name"]))
            await session.execute(delete(PlanFixProjectCache))
            for p in projects:
                session.add(PlanFixProjectCache(planfix_id=p["id"], name=p["name"]))
            await session.commit()

        await _save_sync_state("ok", None, users=len(users), projects=len(projects))
        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(
            f"PlanFix sync: успешно. Users={len(users)}, projects={len(projects)}, {elapsed:.1f}s"
        )
        return {
            "status": "ok",
            "users": len(users),
            "projects": len(projects),
            "elapsed_seconds": elapsed,
        }


async def sync_planfix_tasks_to_db() -> dict:
    """Полная синхронизация всех задач PlanFix в локальный кеш.

    Тянет до MAX_TASKS_SYNC_PAGES × 100 = 50 тыс. задач с pagination и
    rate-limit 1 req/s — занимает несколько минут. Запускается фоновым
    APScheduler-job-ом раз в час.
    """
    if not (settings.PLANFIX_ACCOUNT and settings.PLANFIX_API_TOKEN):
        logger.info("PlanFix tasks sync: не настроен, пропускаем")
        return {"status": "skipped"}

    if _tasks_sync_lock.locked():
        logger.info("PlanFix tasks sync: уже идёт, пропускаем")
        return {"status": "skipped", "reason": "in_progress"}

    async with _tasks_sync_lock:
        svc = get_planfix_service()
        start = datetime.utcnow()
        logger.info(f"PlanFix tasks sync: начало (до {MAX_TASKS_SYNC_PAGES} страниц)")

        try:
            raw_tasks = await svc._paginate_tasks(
                payload={"fields": svc._TASK_FIELDS},
                max_pages=MAX_TASKS_SYNC_PAGES,
            )
        except Exception as e:
            logger.exception("PlanFix tasks sync: ошибка")
            await _save_sync_state("error", str(e)[:300])
            return {"status": "error", "error": str(e)}

        # Соберём словарь project_id → name из локального кеша проектов
        # (тот же приём, что в _fill_project_names)
        async with async_session() as session:
            result = await session.execute(select(PlanFixProjectCache))
            project_names = {p.planfix_id: p.name for p in result.scalars()}

        # Перепишем кеш задач
        async with async_session() as session:
            await session.execute(delete(PlanFixTaskUserLink))
            await session.execute(delete(PlanFixTaskCache))
            await session.commit()

        skipped = 0
        async with async_session() as session:
            for t in raw_tasks:
                try:
                    task_id = t["id"]
                    status = t.get("status") or {}
                    dt = t.get("dateTime") or {}
                    end_dt = t.get("endDateTime") or {}
                    project = t.get("project") or {}
                    assignees = (t.get("assignees") or {}).get("users") or []
                    assigner = t.get("assigner")

                    project_id = project.get("id")
                    project_name = project.get("name") or project_names.get(project_id)

                    session.add(PlanFixTaskCache(
                        id=task_id,
                        name=t.get("name", "") or "",
                        description=t.get("description", "") or "",
                        start_date=dt.get("datetime"),
                        end_date=(end_dt or {}).get("datetime"),
                        status_name=status.get("name", "") or "",
                        status_color=status.get("color", "#888") or "#888",
                        is_active=bool(status.get("isActive", False)),
                        project_id=project_id,
                        project_name=project_name,
                        assignees_json=json.dumps(
                            [{"id": u.get("id"), "name": u.get("name", "")} for u in assignees],
                            ensure_ascii=False,
                        ),
                        assigner_json=json.dumps(
                            {"id": assigner["id"], "name": assigner.get("name", "")},
                            ensure_ascii=False,
                        ) if assigner and assigner.get("id") else None,
                        updated_at=datetime.utcnow(),
                    ))

                    seen_links: set[tuple[str, str]] = set()
                    for u in assignees:
                        uid = u.get("id")
                        if uid and (uid, "assignee") not in seen_links:
                            session.add(PlanFixTaskUserLink(
                                task_id=task_id, user_id=uid, role="assignee",
                            ))
                            seen_links.add((uid, "assignee"))
                    if assigner and assigner.get("id"):
                        uid = assigner["id"]
                        if (uid, "assigner") not in seen_links:
                            session.add(PlanFixTaskUserLink(
                                task_id=task_id, user_id=uid, role="assigner",
                            ))
                except Exception:
                    skipped += 1
                    logger.warning(f"PlanFix tasks sync: пропуск задачи {t.get('id', '?')}", exc_info=True)
            await session.commit()

        # Получить текущий sync_state и обновить только task-поля
        async with async_session() as session:
            res = await session.execute(select(PlanFixSyncState).where(PlanFixSyncState.key == "last_sync"))
            row = res.scalar_one_or_none()
            users_n = row.user_count if row else 0
            projects_n = row.project_count if row else 0

        saved = len(raw_tasks) - skipped
        await _save_sync_state("ok", None, users=users_n, projects=projects_n, tasks=saved)
        elapsed = (datetime.utcnow() - start).total_seconds()
        logger.info(
            f"PlanFix tasks sync: успешно. Tasks={saved} (skipped={skipped}), "
            f"{elapsed:.1f}s ({elapsed/60:.1f} мин)"
        )
        return {"status": "ok", "tasks": saved, "skipped": skipped, "elapsed_seconds": elapsed}


async def get_tasks_by_user_from_cache(user_id: str) -> list[dict] | None:
    """Прочитать задачи user_id из локального кеша.

    Возвращает None, если кеш ещё не заполнен (ни одной задачи) —
    вызывающий код может тогда fallback'нуться на live API.
    """
    async with async_session() as session:
        # Проверим, что кеш в принципе не пустой
        total_q = await session.execute(select(PlanFixTaskCache.id).limit(1))
        if total_q.scalar_one_or_none() is None:
            return None

        result = await session.execute(
            select(PlanFixTaskCache)
            .join(
                PlanFixTaskUserLink,
                PlanFixTaskUserLink.task_id == PlanFixTaskCache.id,
            )
            .where(PlanFixTaskUserLink.user_id == user_id)
            .order_by(PlanFixTaskCache.start_date.desc().nullslast())
        )
        rows = result.scalars().all()

    out = []
    seen = set()
    for r in rows:
        if r.id in seen:
            continue  # на случай, если user одновременно assignee и assigner
        seen.add(r.id)
        try:
            assignees = json.loads(r.assignees_json or "[]")
        except json.JSONDecodeError:
            assignees = []
        try:
            assigner = json.loads(r.assigner_json) if r.assigner_json else None
        except json.JSONDecodeError:
            assigner = None
        out.append({
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "start_date": r.start_date,
            "end_date": r.end_date,
            "status_name": r.status_name,
            "status_color": r.status_color,
            "is_active": r.is_active,
            "project_id": r.project_id,
            "project_name": r.project_name,
            "assignees": assignees,
            "assigner": assigner,
        })
    return out


async def get_users_from_cache() -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(PlanFixUserCache).order_by(PlanFixUserCache.name)
        )
        return [{"id": r.planfix_id, "name": r.name} for r in result.scalars()]


async def get_projects_from_cache() -> list[dict]:
    async with async_session() as session:
        result = await session.execute(
            select(PlanFixProjectCache).order_by(PlanFixProjectCache.name)
        )
        return [{"id": r.planfix_id, "name": r.name} for r in result.scalars()]


async def get_sync_state() -> dict:
    async with async_session() as session:
        result = await session.execute(
            select(PlanFixSyncState).where(PlanFixSyncState.key == "last_sync")
        )
        row = result.scalar_one_or_none()
        if row is None:
            return {"last_sync_at": None, "status": None, "users": 0, "projects": 0}
        return {
            "last_sync_at": row.last_sync_at.isoformat() if row.last_sync_at else None,
            "status": row.last_status,
            "error": row.last_error,
            "users": row.user_count,
            "projects": row.project_count,
        }


def schedule_planfix_sync(
    scheduler: AsyncIOScheduler,
    interval_minutes: int = 15,
    tasks_interval_minutes: int = 60,
):
    """Зарегистрировать периодические синхронизации.

    Справочники (users/projects) — раз в 15 мин, ~30с.
    Задачи — раз в 60 мин, может занимать 5–10 мин.
    Оба job-а стартуют через 30с / 90с после старта, чтобы не задерживать lifespan.
    """
    if not (settings.PLANFIX_ACCOUNT and settings.PLANFIX_API_TOKEN):
        logger.info("PlanFix sync schedule: не настроен, не планируем")
        return

    from apscheduler.triggers.date import DateTrigger
    from apscheduler.triggers.interval import IntervalTrigger
    from datetime import timedelta

    # Справочники — быстро и часто.
    scheduler.add_job(
        sync_planfix_to_db,
        trigger=DateTrigger(run_date=datetime.now() + timedelta(seconds=30)),
        id="planfix_sync_initial", replace_existing=True,
    )
    scheduler.add_job(
        sync_planfix_to_db,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id="planfix_sync_periodic", replace_existing=True,
    )

    # Задачи — долго и реже. Первый запуск через 90с — чтобы справочники успели
    # синхронизироваться раньше (используются для resolve project_name).
    scheduler.add_job(
        sync_planfix_tasks_to_db,
        trigger=DateTrigger(run_date=datetime.now() + timedelta(seconds=90)),
        id="planfix_tasks_sync_initial", replace_existing=True,
    )
    scheduler.add_job(
        sync_planfix_tasks_to_db,
        trigger=IntervalTrigger(minutes=tasks_interval_minutes),
        id="planfix_tasks_sync_periodic", replace_existing=True,
    )
    logger.info(
        f"PlanFix sync: справочники каждые {interval_minutes} мин, "
        f"задачи каждые {tasks_interval_minutes} мин"
    )

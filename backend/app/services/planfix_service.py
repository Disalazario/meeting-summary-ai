"""PlanFix REST API v2 клиент с rate limiting и кэшированием.

Особенности:
- Домен .planfix.ru (не .com)
- Токен с ограниченным scope: task/list + task/create + task/get
- user/list и project/list недоступны — извлекаем из task/list
- ID пользователей: строки вида "user:1", "contact:102"
"""

import asyncio
import logging
import time

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class PlanFixService:
    def __init__(self):
        self._base_url = f"https://{settings.PLANFIX_ACCOUNT}.planfix.ru/rest"
        self._token = settings.PLANFIX_API_TOKEN
        self._last_request_time: float = 0.0
        self._users_cache: list[dict] | None = None
        self._users_cache_time: float = 0.0
        self._projects_cache: list[dict] | None = None
        self._projects_cache_time: float = 0.0
        self._cache_ttl = settings.PLANFIX_CACHE_TTL

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    async def _rate_limit(self):
        """Enforce max 1 request per second (PlanFix limit)."""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        self._last_request_time = time.monotonic()

    async def _request(self, method: str, path: str, **kwargs) -> dict:
        """Rate-limited request to PlanFix API."""
        await self._rate_limit()
        url = f"{self._base_url}/{path.lstrip('/')}"
        logger.info(f"PlanFix API: {method} {path}")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.request(
                    method, url, headers=self._headers(), **kwargs
                )
                if response.status_code >= 400:
                    body = response.text[:300]
                    logger.error(f"PlanFix API error {response.status_code}: {body}")
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            logger.error(f"PlanFix API timeout: {method} {path}")
            raise
        except httpx.ConnectError:
            logger.error(f"PlanFix API unreachable: {method} {path}")
            raise

    def _is_cache_valid(self, cache_time: float) -> bool:
        return (time.monotonic() - cache_time) < self._cache_ttl

    async def _paginate_tasks(
        self, payload: dict, max_pages: int = 20, page_size: int = 100,
    ) -> list[dict]:
        """Пагинация по task/list с общим rate-limiting.

        Возвращает плоский список задач из всех страниц.
        """
        all_tasks: list[dict] = []
        offset = payload.get("offset", 0)

        for _ in range(max_pages):
            page_payload = {**payload, "offset": offset, "pageSize": page_size}
            data = await self._request("POST", "/task/list", json=page_payload)
            tasks = data.get("tasks", [])
            all_tasks.extend(tasks)

            if len(tasks) < page_size:
                break
            offset += page_size
        else:
            logger.warning(
                f"PlanFix: достигнут лимит {max_pages} страниц при пагинации task/list"
            )

        return all_tasks

    async def _fetch_all_tasks_metadata(self) -> tuple[list[dict], list[dict]]:
        """Извлечь пользователей и проекты из task/list (workaround для ограниченного scope)."""
        users = {}
        projects = {}

        all_tasks = await self._paginate_tasks(
            payload={"fields": "id,assignees,assigner,project"},
            max_pages=20,
        )

        for t in all_tasks:
            # Собрать пользователей из assignees
            for u in t.get("assignees", {}).get("users", []):
                uid = u.get("id", "")
                if uid.startswith("user:") and u.get("name"):
                    users[uid] = u["name"]
            # Собрать пользователей из assigner
            a = t.get("assigner")
            if a and str(a.get("id", "")).startswith("user:") and a.get("name"):
                users[a["id"]] = a["name"]
            # Собрать проекты
            p = t.get("project")
            if p and p.get("id"):
                pid = p["id"]
                name = p.get("name") or f"Проект #{pid}"
                projects[pid] = name

        users_list = [{"id": uid, "name": name} for uid, name in sorted(users.items())]
        projects_list = [{"id": pid, "name": name} for pid, name in sorted(projects.items())]
        return users_list, projects_list

    async def get_users(self, force_refresh: bool = False) -> list[dict]:
        """Список пользователей PlanFix (кэшируется)."""
        if not force_refresh and self._users_cache is not None and self._is_cache_valid(self._users_cache_time):
            return self._users_cache

        users, projects = await self._fetch_all_tasks_metadata()
        self._users_cache = users
        self._users_cache_time = time.monotonic()
        self._projects_cache = projects
        self._projects_cache_time = time.monotonic()
        logger.info(f"PlanFix: загружено {len(users)} пользователей, {len(projects)} проектов (из task/list)")
        return self._users_cache

    async def get_projects(self, force_refresh: bool = False) -> list[dict]:
        """Список проектов PlanFix (кэшируется)."""
        if not force_refresh and self._projects_cache is not None and self._is_cache_valid(self._projects_cache_time):
            return self._projects_cache

        # Попробовать прямой API (если scope разрешает)
        try:
            data = await self._request("POST", "/project/list", json={
                "offset": 0, "pageSize": 100, "fields": "id,name",
            })
            projects = data.get("projects", [])
            self._projects_cache = [
                {"id": p["id"], "name": p.get("name") or f"Проект #{p['id']}"}
                for p in projects
            ]
            self._projects_cache_time = time.monotonic()
            logger.info(f"PlanFix: загружено {len(self._projects_cache)} проектов (из /project/list)")
            return self._projects_cache
        except Exception:
            logger.info("PlanFix: /project/list недоступен, извлекаю проекты из task/list")

        # Fallback — извлечь из задач
        users, projects = await self._fetch_all_tasks_metadata()
        self._users_cache = users
        self._users_cache_time = time.monotonic()
        self._projects_cache = projects
        self._projects_cache_time = time.monotonic()
        return self._projects_cache

    @staticmethod
    def _task_to_dict(t: dict) -> dict | None:
        """Привести raw task из PlanFix к плоской структуре для UI."""
        try:
            dt = t.get("dateTime") or {}
            end_dt = t.get("endDateTime") or {}
            assignees = [
                {"id": u["id"], "name": u.get("name", "")}
                for u in t.get("assignees", {}).get("users", [])
            ]
            assigner = t.get("assigner")
            status = t.get("status") or {}
            project = t.get("project") or {}

            return {
                "id": t["id"],
                "name": t.get("name", ""),
                "description": t.get("description", ""),
                "start_date": dt.get("datetime"),
                "end_date": end_dt.get("datetime") if end_dt else None,
                "status_name": status.get("name", ""),
                "status_color": status.get("color", "#888"),
                "is_active": status.get("isActive", False),
                "assignees": assignees,
                "assigner": {"id": assigner["id"], "name": assigner.get("name", "")} if assigner else None,
                "project_id": project.get("id"),
                "project_name": project.get("name"),
            }
        except Exception:
            logger.warning(f"PlanFix: ошибка разбора задачи {t.get('id', '?')}", exc_info=True)
            return None

    _TASK_FIELDS = "id,name,description,dateTime,endDateTime,duration,status,assignees,assigner,project"

    async def get_tasks_by_project(self, project_id: int) -> list[dict]:
        """Получить задачи проекта для диаграммы Ганта."""
        try:
            raw_tasks = await self._paginate_tasks(
                payload={
                    "fields": self._TASK_FIELDS,
                    "filter": {
                        "type": 7001,
                        "field": "project",
                        "operator": "equal",
                        "value": {"id": project_id},
                    },
                },
                max_pages=10,
            )
        except Exception:
            logger.exception(f"PlanFix: ошибка загрузки задач проекта {project_id}")
            raise

        tasks = [d for d in (self._task_to_dict(t) for t in raw_tasks) if d is not None]
        logger.info(f"PlanFix: загружено {len(tasks)} задач для проекта {project_id}")
        return tasks

    async def get_tasks_by_user(self, user_id: str) -> list[dict]:
        """Задачи где user_id — assignee (или assigner).

        user_id — строка вида "user:1" / "contact:102".

        PlanFix-токен с ограниченным scope не даёт server-side фильтр по
        assignee надёжно, поэтому тянем все задачи (с пагинацией) и
        фильтруем на стороне приложения. Для 4–7 пользователей это ОК.

        После фильтрации обогащаем project_name из локального кеша
        (task/list часто отдаёт только project.id без name).
        """
        try:
            raw_tasks = await self._paginate_tasks(
                payload={"fields": self._TASK_FIELDS},
                max_pages=20,
            )
        except Exception:
            logger.exception(f"PlanFix: ошибка загрузки задач для пользователя {user_id}")
            raise

        result = []
        for t in raw_tasks:
            assignees = t.get("assignees", {}).get("users", []) or []
            assigner = t.get("assigner") or {}
            user_ids_in_task = {u.get("id") for u in assignees if u.get("id")}
            if assigner.get("id"):
                user_ids_in_task.add(assigner["id"])
            if user_id not in user_ids_in_task:
                continue
            d = self._task_to_dict(t)
            if d is not None:
                result.append(d)

        await self._fill_project_names(result)

        logger.info(
            f"PlanFix: для {user_id} найдено {len(result)} задач (из {len(raw_tasks)} всего)"
        )
        return result

    @staticmethod
    async def _fill_project_names(tasks: list[dict]) -> None:
        """Достать project_name из planfix_projects_cache, если PlanFix вернул только id."""
        missing_ids = {t["project_id"] for t in tasks if t.get("project_id") and not t.get("project_name")}
        if not missing_ids:
            return
        try:
            from sqlalchemy import select
            from app.database import async_session
            from app.models.planfix_cache import PlanFixProjectCache
            async with async_session() as session:
                result = await session.execute(
                    select(PlanFixProjectCache).where(PlanFixProjectCache.planfix_id.in_(missing_ids))
                )
                name_by_id = {p.planfix_id: p.name for p in result.scalars()}
        except Exception as e:
            logger.warning(f"Не удалось дотянуть имена проектов из кеша: {e}")
            return
        for t in tasks:
            if (not t.get("project_name")) and t.get("project_id") in name_by_id:
                t["project_name"] = name_by_id[t["project_id"]]

    async def create_task(
        self,
        name: str,
        description: str = "",
        project_id: int | None = None,
        assignee_ids: list[str] | None = None,
        creator_id: str | None = None,
        deadline: str | None = None,
    ) -> dict:
        """Создать задачу в PlanFix.

        assignee_ids и creator_id — строки вида "user:1".
        """
        payload: dict = {
            "name": name[:250],
            "description": description,
        }
        if project_id:
            payload["project"] = {"id": project_id}
        if assignee_ids:
            payload["assignees"] = {"users": [{"id": uid} for uid in assignee_ids]}
        if creator_id:
            payload["assigner"] = {"id": creator_id}
        if deadline:
            payload["endDateTime"] = deadline

        result = await self._request("POST", "/task/", json=payload)
        task_id = result.get("id", "?")
        logger.info(f"PlanFix: задача создана, id={task_id}")
        return result


# Singleton
_instance: PlanFixService | None = None


def get_planfix_service() -> PlanFixService:
    global _instance
    if _instance is None:
        _instance = PlanFixService()
    return _instance

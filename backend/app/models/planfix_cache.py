"""Persistent кеш справочников PlanFix.

Назначение: убрать 30–45-секундные блокировки UI при загрузке списков
пользователей/проектов/задач. Кеш заполняется фоновым APScheduler-job и
читается из БД мгновенно.

Особенно важно для задач: наш PlanFix-токен с ограниченным scope не даёт
ни server-side фильтр по assignee, ни сортировки. Без локального кеша
поиск активных задач конкретного пользователя в БД на 20+ тыс. задач
требует обхода всех страниц — для UI это неприемлемо.
"""

from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PlanFixUserCache(Base):
    __tablename__ = "planfix_users_cache"

    # PlanFix-id вида "user:1" — естественный primary key
    planfix_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )


class PlanFixProjectCache(Base):
    __tablename__ = "planfix_projects_cache"

    planfix_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow,
    )


class PlanFixSyncState(Base):
    """Состояние последней синхронизации (один row, key='last_sync')."""

    __tablename__ = "planfix_sync_state"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_status: Mapped[str | None] = mapped_column(String, nullable=True)  # ok | error
    last_error: Mapped[str | None] = mapped_column(String, nullable=True)
    user_count: Mapped[int] = mapped_column(Integer, default=0)
    project_count: Mapped[int] = mapped_column(Integer, default=0)
    task_count: Mapped[int] = mapped_column(Integer, default=0)


class PlanFixTaskCache(Base):
    """Полный кеш всех задач PlanFix.

    Хранится плоско, готово к рендеру в UI без дополнительной обработки.
    """

    __tablename__ = "planfix_tasks_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, default="")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    start_date: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)
    status_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    status_color: Mapped[str] = mapped_column(String, nullable=False, default="#888")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    project_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON-строки: assignees = list[{id,name}], assigner = {id,name} | null
    assignees_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    assigner_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class PlanFixTaskUserLink(Base):
    """Many-to-many между задачами и участниками.

    Позволяет быстро искать все задачи конкретного user_id (assignee либо
    assigner). Композитный PK + индекс на user_id.
    """

    __tablename__ = "planfix_task_users"

    task_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("planfix_tasks_cache.id", ondelete="CASCADE"), primary_key=True,
    )
    user_id: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    role: Mapped[str] = mapped_column(String, primary_key=True)  # "assignee" | "assigner"

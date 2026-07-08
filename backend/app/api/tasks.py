from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.task import Task
from app.models.user import User
from app.schemas.task import TaskResponse, TaskUpdateRequest
from app.services.auth_service import get_current_user

router = APIRouter()


@router.get("/{meeting_id}/tasks", response_model=list[TaskResponse])
async def get_tasks(
    meeting_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    result = await db.execute(
        select(Task).where(Task.meeting_id == meeting_id).order_by(Task.id)
    )
    return result.scalars().all()


@router.patch("/{meeting_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    meeting_id: int,
    task_id: int,
    data: TaskUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.meeting_id == meeting_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    if data.description is not None:
        task.description = data.description
    if data.context is not None:
        # пустая строка означает «убрать контекст»
        task.context = data.context or None
    if data.assignee is not None:
        task.assignee = data.assignee or None
    if data.deadline is not None:
        task.deadline = data.deadline or None
    if data.done is not None:
        task.done = data.done

    await db.commit()
    return task


@router.delete("/{meeting_id}/tasks/{task_id}", status_code=204)
async def delete_task(
    meeting_id: int,
    task_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _check_meeting(db, meeting_id, user.id)

    result = await db.execute(
        select(Task).where(Task.id == task_id, Task.meeting_id == meeting_id)
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Задача не найдена")

    await db.delete(task)
    await db.commit()


async def _check_meeting(db: AsyncSession, meeting_id: int, user_id: int):
    result = await db.execute(
        select(Meeting).where(Meeting.id == meeting_id)
    )
    meeting = result.scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="Совещание не найдено")
    return meeting

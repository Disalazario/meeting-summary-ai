import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.meeting import Meeting
from app.models.telegram_group import TelegramGroup
from app.models.user import User
from app.services.auth_service import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()


class TelegramGroupCreate(BaseModel):
    name: str
    chat_id: str


class TelegramGroupResponse(BaseModel):
    id: int
    name: str
    chat_id: str
    created_at: str

    model_config = {"from_attributes": True}


@router.get("/groups", response_model=list[TelegramGroupResponse])
async def list_groups(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список Telegram-групп."""
    result = await db.execute(
        select(TelegramGroup)
        .where(TelegramGroup.created_by == user.id)
        .order_by(TelegramGroup.created_at.desc())
    )
    groups = result.scalars().all()
    return [
        TelegramGroupResponse(
            id=g.id,
            name=g.name,
            chat_id=g.chat_id,
            created_at=g.created_at.isoformat(),
        )
        for g in groups
    ]


@router.post("/groups", response_model=TelegramGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    body: TelegramGroupCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Добавить Telegram-группу."""
    telegram = request.app.state.telegram

    # Проверить что бот может писать в группу
    ok = await telegram.send_message(
        body.chat_id,
        "Meeting Summary Bot подключён к этой группе.",
    )
    if not ok:
        raise HTTPException(
            status_code=400,
            detail="Не удалось отправить сообщение. Убедитесь что бот добавлен в группу и chat_id верный.",
        )

    group = TelegramGroup(
        name=body.name,
        chat_id=body.chat_id,
        created_by=user.id,
    )
    db.add(group)
    await db.commit()
    await db.refresh(group)

    logger.info(f"Telegram группа добавлена: {body.name} ({body.chat_id})")
    return TelegramGroupResponse(
        id=group.id,
        name=group.name,
        chat_id=group.chat_id,
        created_at=group.created_at.isoformat(),
    )


@router.delete("/groups/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Удалить Telegram-группу."""
    result = await db.execute(
        select(TelegramGroup).where(
            TelegramGroup.id == group_id,
            TelegramGroup.created_by == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    await db.delete(group)
    await db.commit()
    logger.info(f"Telegram группа удалена: id={group_id}")


@router.post("/test/{group_id}")
async def test_group(
    group_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отправить тестовое сообщение."""
    result = await db.execute(
        select(TelegramGroup).where(
            TelegramGroup.id == group_id,
            TelegramGroup.created_by == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    telegram = request.app.state.telegram
    ok = await telegram.send_message(group.chat_id, "Тестовое сообщение от Meeting Summary Bot")
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось отправить сообщение")

    return {"status": "sent"}


class SendLinkRequest(BaseModel):
    meeting_id: int


@router.post("/groups/{group_id}/send-link")
async def send_link_to_group(
    group_id: int,
    body: SendLinkRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Отправить ссылку на встречу в Telegram-группу."""
    # Получить группу
    result = await db.execute(
        select(TelegramGroup).where(
            TelegramGroup.id == group_id,
            TelegramGroup.created_by == user.id,
        )
    )
    group = result.scalar_one_or_none()
    if not group:
        raise HTTPException(status_code=404, detail="Группа не найдена")

    # Получить встречу
    result = await db.execute(
        select(Meeting).where(
            Meeting.id == body.meeting_id,
            Meeting.owner_id == user.id,
        )
    )
    meeting = result.scalar_one_or_none()
    if not meeting:
        raise HTTPException(status_code=404, detail="Встреча не найдена")

    if not meeting.meeting_url:
        raise HTTPException(status_code=400, detail="У встречи нет ссылки на созвон")

    telegram = request.app.state.telegram
    ok = await telegram.send_meeting_link(group.chat_id, meeting.title, meeting.meeting_url)
    if not ok:
        raise HTTPException(status_code=500, detail="Не удалось отправить сообщение в Telegram")

    logger.info(f"Ссылка на встречу {meeting.id} отправлена в группу {group.name} ({group.chat_id})")
    return {"status": "sent", "group": group.name}


@router.get("/bot-info")
async def bot_info(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Информация о Telegram-боте."""
    telegram = request.app.state.telegram
    info = await telegram.verify_bot()
    if not info:
        raise HTTPException(status_code=500, detail="Токен бота невалиден или бот недоступен")
    return info

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import UserResponse, CreateUserRequest, CreateUserResponse
from app.services.auth_service import get_admin_user, hash_password, generate_password

router = APIRouter()


@router.get("", response_model=list[UserResponse])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return result.scalars().all()


@router.post("", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: CreateUserRequest,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    # Check uniqueness
    existing = await db.execute(select(User).where(User.username == data.username))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Пользователь с таким логином уже существует",
        )

    password = generate_password()
    user = User(
        username=data.username,
        display_name=data.display_name,
        hashed_password=hash_password(password),
        role="user",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return CreateUserResponse(
        id=user.id,
        username=user.username,
        display_name=user.display_name,
        role=user.role,
        password=password,
    )


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(get_admin_user),
):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.role == "admin":
        raise HTTPException(status_code=400, detail="Невозможно удалить администратора")
    await db.delete(user)
    await db.commit()

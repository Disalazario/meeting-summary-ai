import logging
import string
import secrets
from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.telegram_auth import validate_init_data

logger = logging.getLogger(__name__)

security = HTTPBearer()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())


def generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def create_access_token(user: User) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role,
        "exp": expire,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Недействительный токен авторизации",
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(credentials.credentials)
    user_id = int(payload.get("sub", 0))
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Пользователь не найден",
        )
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Доступ только для администраторов",
        )
    return user


async def get_telegram_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """Авторизация через Telegram Mini App initData."""
    init_data = request.headers.get("X-Telegram-Init-Data")
    if not init_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Отсутствуют данные авторизации Telegram",
        )

    tg_user = validate_init_data(init_data)
    if not tg_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Невалидные данные авторизации Telegram",
        )

    telegram_id = str(tg_user["id"])

    # Поиск пользователя по telegram_id
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()

    # Автоматическое создание пользователя при первом входе
    if not user:
        display_name = f"{tg_user.get('first_name', '')} {tg_user.get('last_name', '')}".strip()
        user = User(
            username=f"tg_{telegram_id}",
            telegram_id=telegram_id,
            display_name=display_name or f"User {telegram_id}",
            role="user",
            hashed_password="",
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"Создан пользователь из Telegram Mini App: {display_name} (tg_id={telegram_id})")

    return user

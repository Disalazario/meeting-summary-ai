import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.user import LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import verify_password, create_access_token, get_current_user

router = APIRouter()

# SECURITY: Simple in-memory rate limiter for brute-force protection.
# Tracks failed login attempts per IP. After MAX_ATTEMPTS within WINDOW_SECONDS,
# further login attempts are rejected.
_login_attempts: dict[str, list[float]] = defaultdict(list)
_MAX_ATTEMPTS = 10
_WINDOW_SECONDS = 300  # 5 minutes


def _check_rate_limit(client_ip: str) -> None:
    """Raise 429 if the IP has exceeded the login attempt limit."""
    now = time.monotonic()
    # Prune old entries
    _login_attempts[client_ip] = [
        t for t in _login_attempts[client_ip] if now - t < _WINDOW_SECONDS
    ]
    if len(_login_attempts[client_ip]) >= _MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Слишком много попыток входа. Попробуйте позже.",
        )


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    _check_rate_limit(client_ip)

    result = await db.execute(select(User).where(User.username == data.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(data.password, user.hashed_password):
        _login_attempts[client_ip].append(time.monotonic())
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный логин или пароль",
        )
    # Successful login: clear attempts for this IP
    _login_attempts.pop(client_ip, None)
    token = create_access_token(user)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserResponse)
async def me(user: User = Depends(get_current_user)):
    return user

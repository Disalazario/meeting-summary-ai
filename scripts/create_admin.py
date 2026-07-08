#!/usr/bin/env python3
"""Скрипт создания администратора."""
import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select
from app.database import async_session, engine, Base
from app.models.user import User
from app.services.auth_service import hash_password


async def main():
    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    username = input("Введите логин администратора: ").strip()
    if not username:
        print("Логин не может быть пустым")
        return

    password = input("Введите пароль: ").strip()
    if not password:
        print("Пароль не может быть пустым")
        return

    display_name = input("Введите отображаемое имя (или Enter для использования логина): ").strip()
    if not display_name:
        display_name = username

    async with async_session() as session:
        existing = await session.execute(select(User).where(User.username == username))
        if existing.scalar_one_or_none():
            print(f"Пользователь '{username}' уже существует")
            return

        user = User(
            username=username,
            hashed_password=hash_password(password),
            display_name=display_name,
            role="admin",
        )
        session.add(user)
        await session.commit()
        print(f"Администратор '{username}' успешно создан!")


if __name__ == "__main__":
    asyncio.run(main())

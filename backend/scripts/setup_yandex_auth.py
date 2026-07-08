"""
Скрипт первичной авторизации в Яндекс для Телемост-бота.

Запускается ОДИН РАЗ в headed-режиме. Пользователь:
1. Логинится в Яндекс ID (passport.yandex.ru)
2. ОТДЕЛЬНО — на telemost.yandex.ru нажимает «Создать видеовстречу»,
   после чего Яндекс перенаправит через pwl-yandex (b2b/360-контур);
   там, возможно, попросит подтвердить вход. Нужно довести до момента,
   когда страница покажет ссылку на готовую конференцию.

Без второго шага в куках будет только passport-сессия, а b2b-сессия —
которая ДЕЙСТВИТЕЛЬНО нужна для создания встреч — будет отсутствовать.

Запуск:
    cd backend
    python scripts/setup_yandex_auth.py
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from playwright.async_api import async_playwright


async def main():
    print("=" * 60)
    print("Авторизация в Яндекс для бота Телемост")
    print("=" * 60)
    print()

    async with async_playwright() as pw:
        # WSLg-friendly запуск: без аппаратного GPU, с явным размером окна,
        # принудительный вывод через X11 на случай битого Wayland-сокета.
        browser = await pw.chromium.launch(
            headless=False,
            args=[
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--start-maximized",
                "--window-size=1280,900",
                "--window-position=80,40",
                "--ozone-platform=x11",
            ],
            ignore_default_args=["--no-startup-window"],
        )
        context = await browser.new_context(
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        try:
            await page.bring_to_front()
        except Exception:
            pass

        # ── Шаг 1: passport.yandex.ru ─────────────────────────────────
        print("ШАГ 1/2 — Базовая авторизация в Яндекс ID")
        print("  • Откроется страница passport.yandex.ru/auth")
        print("  • Войдите под аккаунтом, через который должны создаваться встречи")
        print("  • После полного входа вернитесь сюда и нажмите Enter")
        print()
        await page.goto("https://passport.yandex.ru/auth")
        input(">>> [Шаг 1] Залогинились в Яндекс — нажмите Enter...")

        # Быстрая sanity-проверка
        await page.goto("https://passport.yandex.ru/profile", wait_until="domcontentloaded")
        if "/auth" in page.url:
            print("❌ Похоже, вход в Яндекс ID не прошёл. Запустите скрипт ещё раз.")
            await browser.close()
            return
        print(f"✓ Passport авторизация ОК (URL: {page.url})")
        print()

        # ── Шаг 2: telemost.yandex.ru — пройти b2b-флоу ───────────────
        print("ШАГ 2/2 — b2b-флоу Telemost (Яндекс 360)")
        print("  • Откроется telemost.yandex.ru")
        print("  • Нажмите кнопку «Создать видеовстречу»")
        print("  • Если откроется страница «Войти в Яндекс 360» — пройдите её")
        print("  • Дождитесь, когда покажется ссылка на готовую конференцию")
        print("    (это значит — b2b-сессия установлена)")
        print("  • После этого вернитесь сюда и нажмите Enter")
        print()
        await page.goto("https://telemost.yandex.ru/")
        input(">>> [Шаг 2] Встреча создалась, ссылка видна — нажмите Enter...")

        # Финальная проверка: куки pwl-yandex должны появиться
        cookies = await context.cookies()
        domains = sorted({c.get("domain", "") for c in cookies})
        has_passport = any("passport.yandex" in d for d in domains)
        has_telemost = any("telemost.yandex" in d for d in domains)
        print()
        print(f"Куков всего: {len(cookies)}, домены: {domains}")
        if not has_passport:
            print("⚠ Куков passport.yandex нет — пройдите шаг 1 заново.")
        if not has_telemost:
            print("⚠ Куков telemost.yandex нет — нажмите «Создать видеовстречу» в браузере перед Enter.")

        # Сохраняем
        from app.services.telemost_auth import YandexAuth
        auth = YandexAuth()
        auth.save_cookies(cookies)
        print(f"✓ Куки сохранены ({len(cookies)} шт.) → backend/data/yandex_cookies.enc")
        print()
        print("Перезапустите backend (./start.sh stop && ./start.sh backend),")
        print("и проверьте создание встречи.")

        await browser.close()


asyncio.run(main())

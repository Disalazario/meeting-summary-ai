"""
Авторизация в Яндекс и создание конференций Телемост через Playwright.

ВАЖНО:
- Первичная авторизация выполняется ВРУЧНУЮ через headed-браузер
  (скрипт scripts/setup_yandex_auth.py).
- После первичной авторизации куки сохраняются в зашифрованный файл.
- Далее бот использует сохранённые куки для авторизации.
- Куки Яндекса живут долго (месяцы), но могут протухнуть.
  При протухании нужно запустить setup_yandex_auth.py заново.
"""

import asyncio
import json
import logging
import re
from pathlib import Path

from cryptography.fernet import Fernet
from playwright.async_api import async_playwright

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
COOKIES_PATH = DATA_DIR / "yandex_cookies.enc"
COOKIES_KEY_PATH = DATA_DIR / "cookies.key"


class YandexAuth:
    """Управление авторизацией Яндекс."""

    def __init__(self):
        self._fernet = self._load_or_create_key()

    def _load_or_create_key(self) -> Fernet:
        COOKIES_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if COOKIES_KEY_PATH.exists():
            key = COOKIES_KEY_PATH.read_bytes()
        else:
            key = Fernet.generate_key()
            COOKIES_KEY_PATH.write_bytes(key)
        return Fernet(key)

    def save_cookies(self, cookies: list[dict]):
        """Сохранить куки в зашифрованный файл."""
        data = json.dumps(cookies).encode()
        encrypted = self._fernet.encrypt(data)
        COOKIES_PATH.parent.mkdir(parents=True, exist_ok=True)
        COOKIES_PATH.write_bytes(encrypted)
        logger.info(f"Куки Яндекс сохранены ({len(cookies)} шт.)")

    def load_cookies(self) -> list[dict]:
        """Загрузить куки из зашифрованного файла."""
        if not COOKIES_PATH.exists():
            raise FileNotFoundError(
                "Куки Яндекс не найдены. Запустите: python scripts/setup_yandex_auth.py"
            )
        encrypted = COOKIES_PATH.read_bytes()
        data = self._fernet.decrypt(encrypted)
        cookies = json.loads(data.decode())
        logger.info(f"Куки Яндекс загружены ({len(cookies)} шт.)")
        return cookies

    @property
    def is_authenticated(self) -> bool:
        return COOKIES_PATH.exists()


class TelemostMeetingCreator:
    """Создание конференций Телемост через браузер."""

    def __init__(self, auth: YandexAuth):
        self.auth = auth

    async def create_meeting(self, max_retries: int = 3) -> str:
        """
        Создать новую конференцию в Телемост.
        Возвращает URL конференции.
        Retry при сетевых ошибках (DNS, timeout).
        """
        last_error = None
        for attempt in range(max_retries):
            try:
                return await self._create_meeting_attempt()
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "ERR_NAME_NOT_RESOLVED" in err_str or "net::" in err_str or "Timeout" in err_str:
                    delay = (attempt + 1) * 5
                    logger.warning(
                        f"Создание конференции: попытка {attempt+1}/{max_retries} "
                        f"не удалась ({type(e).__name__}), повтор через {delay}с"
                    )
                    await asyncio.sleep(delay)
                else:
                    raise  # Не сетевая ошибка — пробрасываем сразу
        raise last_error

    async def _create_meeting_attempt(self) -> str:
        """Одна попытка создания конференции."""
        logger.info("Создание конференции Телемост...")
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
            context = await browser.new_context()

            # Загрузить куки
            cookies = self.auth.load_cookies()
            await context.add_cookies(cookies)

            page = await context.new_page()
            await page.goto("https://telemost.yandex.ru", wait_until="networkidle")

            # Проверить что авторизованы
            if "passport.yandex" in page.url:
                await browser.close()
                raise RuntimeError(
                    "Куки Яндекс протухли. Запустите: python scripts/setup_yandex_auth.py"
                )

            logger.info(f"Страница Телемост загружена: {page.url}")

            # Клик по кнопке создания встречи
            logger.info("Клик по кнопке создания встречи...")
            create_selectors = [
                'button:has-text("Создать видеовстречу")',
                'button:has-text("Создать встречу")',
                '[data-testid="create-meeting"]',
            ]

            clicked = False
            for sel in create_selectors:
                try:
                    btn = await page.wait_for_selector(sel, timeout=3000)
                    if btn:
                        initial_url = page.url
                        await btn.click()
                        logger.info(f"Нажата кнопка: {sel}")
                        clicked = True

                        # Ждём изменения URL или открытия новой страницы
                        await page.wait_for_timeout(2000)

                        # Проверяем открылась ли новая страница
                        pages = context.pages
                        if len(pages) > 1:
                            page = pages[-1]  # Переключаемся на последнюю открытую страницу
                            logger.info(f"Открылась новая вкладка: {page.url}")
                        elif page.url != initial_url:
                            logger.info(f"URL изменился: {page.url}")
                        else:
                            logger.info("URL не изменился, ждём загрузки...")
                        break
                except Exception as e:
                    logger.debug(f"Селектор '{sel}' не найден: {e}")
                    continue

            if not clicked:
                raise RuntimeError("Не удалось найти кнопку создания встречи")

            # Ждём пока React создаст конференцию (URL должен смениться на /j/...)
            logger.info("Ожидание создания конференции...")
            for attempt in range(15):
                await page.wait_for_timeout(1000)
                if "/j/" in page.url:
                    logger.info(f"Конференция создана: {page.url}")
                    break

            # Закрыть модалку с ошибкой видео (если есть)
            try:
                close_modal = await page.wait_for_selector('button:has-text("Понятно")', timeout=2000)
                if close_modal:
                    await close_modal.click()
                    logger.info("Закрыта модалка с ошибкой видео")
                    await page.wait_for_timeout(500)
            except Exception:
                pass

            # Извлечение ссылки
            meeting_url = None

            logger.info(f"Текущий URL страницы: {page.url}")

            # Вариант 1: URL страницы изменился
            if "/j/" in page.url:
                meeting_url = page.url
                logger.info(f"Ссылка найдена в URL: {meeting_url}")

            # Вариант 2: ссылка в поле ввода (ждём до 10 сек)
            if not meeting_url:
                link_selectors = [
                    'input[value*="telemost.yandex"]',
                    'input[readonly][value*="telemost"]',
                    '[data-testid="meeting-link"] input',
                    'a[href*="telemost.yandex.ru/j/"]',
                    'input[type="text"][value*="yandex.ru/j/"]',
                ]
                for sel in link_selectors:
                    try:
                        el = await page.wait_for_selector(sel, timeout=10000)
                        if el:
                            val = await el.get_attribute("value") or await el.get_attribute("href")
                            if val and ("telemost" in val or "/j/" in val):
                                meeting_url = val
                                logger.info(f"Ссылка найдена через селектор '{sel}': {meeting_url}")
                                break
                    except Exception as e:
                        logger.debug(f"Селектор '{sel}' не найден: {e}")
                        continue

            # Вариант 3: найти URL в тексте страницы
            if not meeting_url:
                content = await page.content()
                match = re.search(r'https://telemost\.yandex\.ru/j/\d+', content)
                if match:
                    meeting_url = match.group(0)
                    logger.info(f"Ссылка найдена в HTML: {meeting_url}")
                else:
                    # Отладка: скриншот и лог
                    screenshot_path = "/tmp/telemost_debug.png"
                    await page.screenshot(path=screenshot_path)
                    logger.warning(f"Ссылка не найдена. Скриншот сохранён: {screenshot_path}")
                    logger.warning(f"Содержимое страницы (первые 1000 символов):\n{content[:1000]}")

            await browser.close()

            if not meeting_url:
                raise RuntimeError("Не удалось получить ссылку на конференцию")

            logger.info(f"Конференция создана: {meeting_url}")
            return meeting_url

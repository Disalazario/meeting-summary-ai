"""
Playwright-бот для Яндекс Телемост.
Заходит в конференцию, мониторит участников, выходит.

ВАЖНО:
- Селекторы зависят от текущей вёрстки Телемост.
- При первом запуске тестировать в headed-режиме (headless=False).
- Скриншоты ошибок сохраняются в data/debug/.
"""

import asyncio
import base64
import logging
import os
import re
import subprocess
import wave
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page, BrowserContext

logger = logging.getLogger(__name__)

DEBUG_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "debug"
SILENCE_WAV = Path("/tmp/bot_silence.wav")

# JavaScript для перехвата WebRTC аудио в headless Chromium.
# Headless Chromium не рендерит аудио через PulseAudio,
# поэтому захватываем remote audio tracks через Web Audio API.
JS_AUDIO_CAPTURE = """
(function() {
    window.__audioChunks = [];
    window.__mediaRecorder = null;
    window.__remoteStreams = [];
    window.__captureStarted = false;

    // Перехватываем RTCPeerConnection для получения remote audio streams
    const origSetRemoteDescription = RTCPeerConnection.prototype.setRemoteDescription;
    RTCPeerConnection.prototype.setRemoteDescription = function(...args) {
        const pc = this;
        pc.addEventListener('track', function(event) {
            if (event.track.kind === 'audio') {
                event.streams.forEach(function(s) {
                    if (window.__remoteStreams.indexOf(s) === -1) {
                        window.__remoteStreams.push(s);
                        console.log('[AudioCapture] Remote audio stream получен:', s.id);
                        // Автозапуск записи если она уже должна идти
                        if (window.__captureStarted && !window.__mediaRecorder) {
                            window.__startAudioCapture();
                        }
                    }
                });
            }
        });
        return origSetRemoteDescription.apply(this, args);
    };

    window.__startAudioCapture = function() {
        window.__captureStarted = true;
        if (window.__remoteStreams.length === 0) {
            console.log('[AudioCapture] Нет remote streams, ждём...');
            return false;
        }
        if (window.__mediaRecorder && window.__mediaRecorder.state === 'recording') {
            return true; // Уже записываем
        }

        try {
            var ctx = new AudioContext();
            var dest = ctx.createMediaStreamDestination();

            window.__remoteStreams.forEach(function(stream) {
                stream.getAudioTracks().forEach(function(track) {
                    if (track.readyState === 'live') {
                        var source = ctx.createMediaStreamSource(new MediaStream([track]));
                        source.connect(dest);
                        console.log('[AudioCapture] Подключен аудио трек:', track.id);
                    }
                });
            });

            // Выбираем формат: предпочитаем opus в webm
            var mimeType = 'audio/webm;codecs=opus';
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                mimeType = 'audio/webm';
            }
            if (!MediaRecorder.isTypeSupported(mimeType)) {
                mimeType = '';  // Дефолтный
            }

            var options = mimeType ? { mimeType: mimeType } : {};
            var recorder = new MediaRecorder(dest.stream, options);
            recorder.ondataavailable = function(e) {
                if (e.data && e.data.size > 0) {
                    window.__audioChunks.push(e.data);
                }
            };
            recorder.start(1000);  // Чанк каждую секунду
            window.__mediaRecorder = recorder;
            console.log('[AudioCapture] Запись начата, mimeType:', mimeType || 'default');
            return true;
        } catch(e) {
            console.error('[AudioCapture] Ошибка запуска:', e);
            return false;
        }
    };

    window.__stopAudioCapture = function() {
        return new Promise(function(resolve) {
            if (!window.__mediaRecorder || window.__mediaRecorder.state !== 'recording') {
                console.log('[AudioCapture] Recorder не активен');
                resolve(null);
                return;
            }

            window.__mediaRecorder.onstop = function() {
                if (window.__audioChunks.length === 0) {
                    console.log('[AudioCapture] Нет данных');
                    resolve(null);
                    return;
                }

                var blob = new Blob(window.__audioChunks, { type: window.__mediaRecorder.mimeType || 'audio/webm' });
                console.log('[AudioCapture] Blob:', blob.size, 'bytes,', window.__audioChunks.length, 'chunks');

                var reader = new FileReader();
                reader.onloadend = function() {
                    // data:audio/webm;base64,XXXXX → берём только base64
                    var base64 = reader.result.split(',')[1];
                    resolve(base64);
                };
                reader.readAsDataURL(blob);
            };

            window.__mediaRecorder.stop();
        });
    };

    window.__getAudioStatus = function() {
        return {
            remoteStreams: window.__remoteStreams.length,
            chunks: window.__audioChunks.length,
            recording: window.__mediaRecorder ? window.__mediaRecorder.state : 'none',
            captureStarted: window.__captureStarted
        };
    };
})();
"""


def _ensure_silence_wav():
    """Создать тихий WAV-файл для фейкового микрофона."""
    if SILENCE_WAV.exists():
        return
    with wave.open(str(SILENCE_WAV), "w") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        # 10 секунд тишины
        w.writeframes(b"\x00" * 16000 * 2 * 10)


class TelemostBot:
    def __init__(self, meeting_url: str, bot_name: str = "Бот-секретарь",
                 headless: bool = True, pulse_sink: str = "bot_capture"):
        """pulse_sink — имя PulseAudio-sink, в который Chromium будет
        направлять аудио. Должен быть уникальным per-meeting для параллельной
        записи нескольких созвонов."""
        self.meeting_url = meeting_url
        self.bot_name = bot_name
        self.headless = headless
        self.pulse_sink = pulse_sink
        self.browser: Browser | None = None
        self.page: Page | None = None
        self.context: BrowserContext | None = None
        self._pw = None
        self._running = False
        self._participant_count = 0
        self._js_audio_active = False

    async def start(self, cookies: list[dict] | None = None):
        """Запуск браузера."""
        self._running = True
        self._pw = await async_playwright().start()

        # Тихий WAV вместо тестового сигнала (иначе бот тикает)
        _ensure_silence_wav()

        # PULSE_SERVER + per-meeting PULSE_SINK — иначе при параллельной
        # записи Chromium-ы микшировали бы аудио всех встреч в один sink.
        browser_env = {
            **os.environ,
            "PULSE_SERVER": "unix:/mnt/wslg/PulseServer",
            "PULSE_SINK": self.pulse_sink,
        }
        logger.info(f"PULSE_SINK для Chromium → {self.pulse_sink}")

        logger.info(f"Запуск Chromium: headless={self.headless}")

        self.browser = await self._pw.chromium.launch(
            headless=self.headless,
            args=[
                "--use-fake-ui-for-media-stream",
                "--use-fake-device-for-media-stream",
                f"--use-file-for-fake-audio-capture={SILENCE_WAV}",
                "--no-sandbox",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-gpu",
            ],
            env=browser_env,
        )

        self.context = await self.browser.new_context(
            permissions=["microphone", "camera"],
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
        )

        if cookies:
            await self.context.add_cookies(cookies)

        self.page = await self.context.new_page()

        # Inject JS для перехвата WebRTC аудио ПЕРЕД загрузкой страницы
        await self.page.add_init_script(JS_AUDIO_CAPTURE)

        logger.info(f"Браузер запущен (headless={self.headless})")

    async def join_meeting(self):
        """
        Зайти в конференцию Телемост.
        """
        logger.info(f"Вход в конференцию: {self.meeting_url}")
        await self.page.goto(self.meeting_url, wait_until="networkidle")
        await asyncio.sleep(3)

        await self._debug_screenshot("01_page_loaded")

        # Ввод имени (гостевой вход)
        try:
            name_input = await self.page.wait_for_selector(
                'input[placeholder*="имя" i], '
                'input[name="name"], '
                'input[data-testid="guest-name"]',
                timeout=5000,
            )
            if name_input:
                await name_input.fill(self.bot_name)
                await asyncio.sleep(0.5)
                await self._debug_screenshot("02_name_filled")
                logger.info(f"Имя введено: {self.bot_name}")
        except Exception:
            logger.info("Поле имени не найдено (авторизованный вход)")

        # Отключение камеры/микрофона (быстрые таймауты)
        media_selectors = [
            'button[aria-label*="икрофон" i]',
            'button[aria-label*="амер" i]',
            '[data-testid="mic-button"]',
            '[data-testid="camera-button"]',
        ]
        for sel in media_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, timeout=1000)
                if btn:
                    await btn.click()
                    await asyncio.sleep(0.3)
            except Exception:
                pass

        # Нажать "Присоединиться"
        join_selectors = [
            'button:has-text("Присоединиться")',
            'button:has-text("Войти")',
            'button:has-text("Подключиться")',
            'button:has-text("Join")',
            '[data-testid="join-button"]',
            'button[type="submit"]',
        ]
        joined = False
        for sel in join_selectors:
            try:
                btn = await self.page.wait_for_selector(sel, timeout=3000)
                if btn:
                    await btn.click()
                    joined = True
                    logger.info(f"Нажата кнопка входа: {sel}")
                    await self._debug_screenshot("03_join_clicked")
                    break
            except Exception:
                continue

        if not joined:
            await self._debug_screenshot("ERROR_join_failed")
            raise RuntimeError("Не удалось найти кнопку входа в конференцию")

        await asyncio.sleep(5)
        await self._debug_screenshot("04_in_meeting")
        logger.info("Бот вошёл в конференцию")

        # Выключить микрофон после входа (страховка от звука)
        await self._mute_microphone()

    async def start_js_audio_capture(self):
        """
        Начать захват аудио через JavaScript WebRTC API.
        Headless Chromium не рендерит аудио через PulseAudio,
        поэтому перехватываем remote audio tracks через Web Audio API.
        """
        logger.info("Запуск JS аудио захвата...")

        # Попытки начать запись (remote streams могут появиться не сразу)
        for attempt in range(30):
            try:
                started = await self.page.evaluate("window.__startAudioCapture()")
                status = await self.page.evaluate("window.__getAudioStatus()")
                logger.info(f"JS Audio статус (попытка {attempt+1}): {status}")

                if started and status.get("recording") == "recording":
                    self._js_audio_active = True
                    logger.info("JS аудио захват активен!")
                    return True
            except Exception as e:
                logger.warning(f"Ошибка JS аудио (попытка {attempt+1}): {e}")

            await asyncio.sleep(2)

        logger.error("JS аудио захват не удалось запустить — нет remote audio streams")
        return False

    async def stop_js_audio_capture(self, output_path: str) -> bool:
        """
        Остановить JS аудио захват и сохранить в файл.
        Возвращает True если файл создан.
        """
        try:
            status = await self.page.evaluate("window.__getAudioStatus()")
            logger.info(f"JS Audio статус при остановке: {status}")

            audio_base64 = await self.page.evaluate("window.__stopAudioCapture()")

            if not audio_base64:
                logger.error("JS аудио захват вернул пустые данные")
                return False

            # Декодируем base64 → webm файл
            audio_data = base64.b64decode(audio_base64)
            webm_path = output_path.replace(".wav", ".webm")
            with open(webm_path, "wb") as f:
                f.write(audio_data)
            logger.info(f"JS аудио сохранён: {webm_path} ({len(audio_data)} bytes)")

            # Конвертируем webm → wav через ffmpeg
            result = subprocess.run(
                ["ffmpeg", "-y", "-i", webm_path, "-ar", "16000", "-ac", "1",
                 "-acodec", "pcm_s16le", output_path],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                wav_size = Path(output_path).stat().st_size if Path(output_path).exists() else 0
                logger.info(f"WAV конвертирован: {output_path} ({wav_size} bytes)")
                return True
            else:
                logger.error(f"ffmpeg конвертация неудачна: {result.stderr[:500]}")
                return False

        except Exception as e:
            logger.exception(f"Ошибка остановки JS аудио: {e}")
            return False
        finally:
            self._js_audio_active = False

    async def redirect_audio_to_sink(self):
        """
        Перенаправить аудиовыход Chromium в PulseAudio sink bot_capture.
        Делаем несколько попыток — sink-input может появиться не сразу.
        """
        await asyncio.sleep(3)

        pulse_env = {**os.environ, "PULSE_SERVER": "unix:/mnt/wslg/PulseServer"}
        try:
            info = subprocess.run(
                ["pactl", "info"],
                capture_output=True, text=True, timeout=5, env=pulse_env,
            )
            for line in info.stdout.split("\n"):
                if "Default Sink:" in line:
                    logger.info(f"Текущий {line.strip()}")
                    break

            sinks = subprocess.run(
                ["pactl", "list", "short", "sinks"],
                capture_output=True, text=True, timeout=5, env=pulse_env,
            )
            logger.info(f"Доступные sinks:\n{sinks.stdout.strip()}")
        except Exception as e:
            logger.warning(f"Не удалось получить состояние PulseAudio: {e}")

        logger.info("Перенаправление аудио в bot_capture...")

        redirected = set()
        for attempt in range(15):
            try:
                result = subprocess.run(
                    ["pactl", "list", "short", "sink-inputs"],
                    capture_output=True, text=True, timeout=5, env=pulse_env,
                )
                logger.info(f"Попытка {attempt+1}/15 — sink-inputs:\n{result.stdout.strip()}")

                for line in result.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split("\t")
                    input_id = parts[0]
                    current_sink = parts[1] if len(parts) > 1 else "unknown"
                    if input_id not in redirected:
                        move_result = subprocess.run(
                            ["pactl", "move-sink-input", input_id, "bot_capture"],
                            capture_output=True, text=True, timeout=5, env=pulse_env,
                        )
                        if move_result.returncode == 0:
                            redirected.add(input_id)
                            logger.info(f"Sink-input {input_id} перенаправлен: {current_sink} → bot_capture")
                        else:
                            logger.warning(f"Не удалось перенаправить sink-input {input_id}: {move_result.stderr}")

                if redirected:
                    await asyncio.sleep(1)
                    verify = subprocess.run(
                        ["pactl", "list", "short", "sink-inputs"],
                        capture_output=True, text=True, timeout=5, env=pulse_env,
                    )
                    logger.info(f"Sink-inputs после перенаправления:\n{verify.stdout.strip()}")
                    return

            except Exception as e:
                logger.warning(f"Попытка перенаправления {attempt + 1}/15: {e}")
            await asyncio.sleep(2)

        if not redirected:
            logger.warning("Не найдено sink-input для перенаправления (используется JS захват)")

    async def _mute_microphone(self):
        """Выключить микрофон бота через UI."""
        mic_selectors = [
            'button[aria-label*="икрофон" i]',
            'button[aria-label*="Mute" i]',
            '[data-testid="mic-button"]',
            'button[aria-label*="micro" i]',
        ]
        for sel in mic_selectors:
            try:
                btn = await self.page.query_selector(sel)
                if btn:
                    aria = await btn.get_attribute("aria-label") or ""
                    classes = await btn.get_attribute("class") or ""
                    if "выкл" not in aria.lower() and "muted" not in classes.lower():
                        await btn.click()
                        logger.info(f"Микрофон выключен через UI: {sel}")
                    else:
                        logger.info("Микрофон уже выключен")
                    break
            except Exception:
                continue

    async def get_participant_names(self) -> list[str]:
        """
        Извлечь имена участников из DOM Телемоста.
        Парсит текст под плитками видео участников.
        """
        names = set()
        try:
            # Метод 1: текст внутри плиток участников (имена под аватарками)
            # Телемост показывает имена в элементах внутри контейнеров участников
            name_selectors = [
                '[class*="participant"] [class*="name"]',
                '[class*="member"] [class*="name"]',
                '[class*="tile"] [class*="name"]',
                '[class*="video-cell"] [class*="name"]',
                '[class*="cell"] [class*="display-name"]',
                '[data-testid*="participant-name"]',
            ]
            for sel in name_selectors:
                try:
                    elements = await self.page.query_selector_all(sel)
                    for el in elements:
                        text = (await el.inner_text()).strip()
                        if text:
                            # Убираем иконки микрофона (unicode символы в конце)
                            clean = re.sub(r'[\U0001F300-\U0001F9FF\u2000-\u27FF]', '', text).strip()
                            if clean:
                                names.add(clean)
                except Exception:
                    continue

            # Метод 2: fallback — все текстовые элементы внутри видео-контейнеров
            if not names:
                try:
                    # Ищем контейнеры с видео/аватарками и берём текст из них
                    cells = await self.page.query_selector_all(
                        '[class*="grid"] > div, [class*="gallery"] > div, [class*="layout"] > div'
                    )
                    for cell in cells:
                        try:
                            text = (await cell.inner_text()).strip()
                            # Имя участника — короткий текст (не пустой, не кнопка)
                            if text and 2 < len(text) < 60 and '\n' not in text:
                                clean = re.sub(r'[\U0001F300-\U0001F9FF\u2000-\u27FF]', '', text).strip()
                                if clean:
                                    names.add(clean)
                        except Exception:
                            continue
                except Exception:
                    pass

            # Метод 3: через кнопку "Участники" — открыть панель и прочитать список
            if not names:
                try:
                    participants_btn = await self.page.query_selector(
                        'button:has-text("Участники"), [data-testid="participants-button"]'
                    )
                    if participants_btn:
                        await participants_btn.click()
                        await asyncio.sleep(1)
                        # Читаем список из панели
                        panel_names = await self.page.query_selector_all(
                            '[class*="participant-list"] [class*="name"], '
                            '[class*="members-list"] [class*="name"]'
                        )
                        for el in panel_names:
                            text = (await el.inner_text()).strip()
                            if text:
                                names.add(text)
                        # Закрыть панель
                        await participants_btn.click()
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

        except Exception as e:
            logger.warning(f"Ошибка получения имён участников: {e}")

        # Исключить имя бота
        bot_name_lower = self.bot_name.lower()
        filtered = [n for n in names if bot_name_lower not in n.lower()]

        if filtered:
            logger.info(f"Участники Телемост: {filtered}")
        return filtered

    async def monitor_participants(self, check_interval: int = 15,
                                   alone_timeout: int = 60) -> bool:
        """
        Мониторинг участников.
        Возвращает False если бот остался один дольше alone_timeout секунд.
        """
        alone_since = None
        self._collected_names: set[str] = set()
        logger.info(f"Мониторинг участников (интервал={check_interval}с, таймаут одиночества={alone_timeout}с)")

        while self._running:
            try:
                count = await self._get_participant_count()
                self._participant_count = count

                # Периодически собираем имена участников
                try:
                    current_names = await self.get_participant_names()
                    if current_names:
                        new_names = set(current_names) - self._collected_names
                        if new_names:
                            logger.info(f"Новые участники: {new_names}")
                        self._collected_names.update(current_names)
                except Exception:
                    pass

                if count <= 1:
                    if alone_since is None:
                        alone_since = asyncio.get_event_loop().time()
                        logger.info("Бот остался один, начинаем отсчёт...")
                    elapsed = asyncio.get_event_loop().time() - alone_since
                    if elapsed >= alone_timeout:
                        logger.info(f"Бот один уже {elapsed:.0f}с — выходим")
                        return False
                else:
                    if alone_since is not None:
                        logger.info(f"Участники вернулись (всего: {count})")
                    alone_since = None

                # Периодически логируем статус аудио захвата
                if self._js_audio_active:
                    try:
                        status = await self.page.evaluate("window.__getAudioStatus()")
                        if status.get("chunks", 0) > 0 and status["chunks"] % 10 == 0:
                            logger.info(f"JS Audio: {status['chunks']} chunks, {status['remoteStreams']} streams")
                    except Exception:
                        pass

            except Exception as e:
                logger.warning(f"Ошибка мониторинга: {e}")

            await asyncio.sleep(check_interval)

        return True

    async def _get_participant_count(self) -> int:
        """Определить количество участников."""
        counter_selectors = [
            '[data-testid="participants-count"]',
            '.participants-count',
        ]
        for sel in counter_selectors:
            try:
                el = await self.page.query_selector(sel)
                if el:
                    text = await el.inner_text()
                    nums = re.findall(r'\d+', text)
                    if nums:
                        return int(nums[0])
            except Exception:
                pass

        try:
            videos = await self.page.query_selector_all("video")
            if len(videos) > 0:
                return len(videos)
        except Exception:
            pass

        try:
            avatars = await self.page.query_selector_all(
                '[class*="participant"], [class*="member"], [data-testid*="participant"]'
            )
            if len(avatars) > 0:
                return len(avatars)
        except Exception:
            pass

        return 0

    async def leave(self):
        """Выход из конференции."""
        self._running = False
        logger.info("Выход из конференции...")
        try:
            leave_selectors = [
                'button:has-text("Выйти")',
                'button:has-text("Завершить")',
                'button:has-text("Покинуть")',
                '[data-testid="leave-button"]',
            ]
            for sel in leave_selectors:
                try:
                    btn = await self.page.query_selector(sel)
                    if btn:
                        await btn.click()
                        logger.info(f"Нажата кнопка выхода: {sel}")
                        break
                except Exception:
                    continue
        except Exception:
            pass

        if self.browser:
            await self.browser.close()
            self.browser = None
        if self._pw:
            await self._pw.stop()
            self._pw = None
        logger.info("Браузер закрыт")

    async def _debug_screenshot(self, name: str):
        """Сохранить скриншот для отладки."""
        try:
            DEBUG_DIR.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = DEBUG_DIR / f"{ts}_{name}.png"
            await self.page.screenshot(path=str(path))
            logger.debug(f"Скриншот сохранён: {path}")
        except Exception:
            pass

    @property
    def participant_count(self) -> int:
        return self._participant_count

    @property
    def collected_participant_names(self) -> list[str]:
        """Все собранные имена участников за время мониторинга."""
        return list(getattr(self, '_collected_names', set()))

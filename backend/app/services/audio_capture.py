"""
Захват аудио из PulseAudio virtual sink через ffmpeg.

Архитектура (multi-bot):
- На каждое совещание создаётся свой sink `bot_capture_<meeting_id>`
- Chromium запускается с env PULSE_SINK=<этот sink> → аудио идёт только сюда
- ffmpeg слушает <sink>.monitor → пишет в WAV-файл этой встречи
- После остановки sink выгружается (unload-module) — освобождаются ресурсы

Раньше был один общий `bot_capture` с `set-default-sink`, что делало
параллельную запись невозможной (Chromium-ы микшировали аудио в один sink).
"""

import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

LEGACY_SINK_NAME = "bot_capture"  # для обратной совместимости со start.sh
PULSE_SERVER = "unix:/mnt/wslg/PulseServer"  # WSLg PulseAudio server


def _pulse_env():
    import os
    return {**os.environ, "PULSE_SERVER": PULSE_SERVER}


def sink_for_meeting(meeting_id: int | str) -> str:
    """Имя per-meeting PulseAudio sink. Уникально по meeting_id."""
    return f"bot_capture_{meeting_id}"


def ensure_pulseaudio_sink(sink_name: str = LEGACY_SINK_NAME) -> bool:
    """Создать PulseAudio null-sink, если он ещё не существует.

    ВАЖНО: больше НЕ меняет default sink — это ломало параллельную запись.
    Каждый бот должен явно указывать свой sink через env PULSE_SINK или
    параметром браузера.
    """
    env = _pulse_env()
    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sinks"],
            capture_output=True, text=True, timeout=5, env=env,
        )
        if sink_name in result.stdout:
            logger.info(f"PulseAudio sink '{sink_name}' уже существует")
            return True

        create_result = subprocess.run(
            [
                "pactl", "load-module", "module-null-sink",
                f"sink_name={sink_name}",
                f"sink_properties=device.description={sink_name}",
            ],
            capture_output=True, text=True, timeout=5, env=env,
        )
        if create_result.returncode != 0:
            logger.error(f"Не удалось создать sink {sink_name}: {create_result.stderr}")
            return False
        logger.info(f"PulseAudio sink '{sink_name}' создан (module-id={create_result.stdout.strip()})")
        return True
    except Exception as e:
        logger.error(f"Ошибка ensure_pulseaudio_sink({sink_name}): {e}")
        return False


def unload_pulseaudio_sink(sink_name: str) -> None:
    """Выгрузить null-sink после окончания записи. Безопасно, если sink не найден."""
    env = _pulse_env()
    try:
        # Найти module-id по имени sink'a
        result = subprocess.run(
            ["pactl", "list", "short", "modules"],
            capture_output=True, text=True, timeout=5, env=env,
        )
        module_ids = []
        for line in result.stdout.splitlines():
            # формат: <id>\tmodule-null-sink\tsink_name=bot_capture_42 ...
            if "module-null-sink" in line and f"sink_name={sink_name}" in line:
                module_ids.append(line.split("\t")[0])
        for mid in module_ids:
            subprocess.run(["pactl", "unload-module", mid], timeout=5, env=env)
            logger.info(f"PulseAudio sink '{sink_name}' выгружен (module-id={mid})")
        if not module_ids:
            logger.info(f"PulseAudio sink '{sink_name}': модуль не найден (уже выгружен)")
    except Exception as e:
        logger.warning(f"Не удалось выгрузить sink {sink_name}: {e}")


class AudioCapture:
    def __init__(self, output_path: str, sink_name: str = LEGACY_SINK_NAME):
        """sink_name должен быть уникальным per-meeting (см. sink_for_meeting)."""
        self.output_path = output_path
        self.sink_name = sink_name
        self.process: subprocess.Popen | None = None

    async def start(self):
        """Запуск записи."""
        import os
        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

        # Убедиться что PulseAudio sink для этой встречи существует
        await self._ensure_sink()

        logger.info(f"Начало записи аудио: {self.output_path} (sink: {self.sink_name})")

        log_path = Path(self.output_path).parent / "ffmpeg_capture.log"
        self._ffmpeg_log = open(log_path, "w")

        # PULSE_SERVER нужен чтобы ffmpeg подключился к правильному PulseAudio в WSLg
        ffmpeg_env = {**os.environ, "PULSE_SERVER": PULSE_SERVER}

        self.process = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-f", "pulse",
                "-i", f"{self.sink_name}.monitor",
                "-ar", "16000",
                "-ac", "1",
                "-acodec", "pcm_s16le",
                self.output_path,
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=self._ffmpeg_log,
            env=ffmpeg_env,
        )
        logger.info(f"Запись запущена (PID: {self.process.pid})")

        # Проверить что ffmpeg не упал сразу
        import asyncio
        await asyncio.sleep(1)
        if self.process.poll() is not None:
            self._ffmpeg_log.close()
            err = open(log_path).read()
            logger.error(f"ffmpeg завершился сразу (code={self.process.returncode}): {err[:500]}")
            self.process = None

        # Логируем текущее состояние sink-inputs
        try:
            result = subprocess.run(
                ["pactl", "list", "short", "sink-inputs"],
                capture_output=True, text=True, timeout=5,
                env=ffmpeg_env,
            )
            logger.info(f"Sink-inputs при старте записи:\n{result.stdout.strip()}")
        except Exception:
            pass

    async def stop(self) -> str:
        """Graceful stop — отправляет 'q' в ffmpeg."""
        if self.process and self.process.poll() is None:
            logger.info("Останавливаем запись аудио...")
            try:
                self.process.stdin.write(b"q")
                self.process.stdin.flush()
                self.process.wait(timeout=10)
                logger.info("Запись остановлена")
            except Exception as e:
                logger.warning(f"Graceful stop не удался, убиваем процесс: {e}")
                self.process.kill()
            self.process = None
        elif self.process:
            code = self.process.returncode
            logger.warning(f"ffmpeg уже завершён (code={code})")
            self.process = None

        if hasattr(self, "_ffmpeg_log") and self._ffmpeg_log:
            self._ffmpeg_log.close()

        # Проверить что файл создан
        out = Path(self.output_path)
        if out.exists():
            size_mb = out.stat().st_size / (1024 * 1024)
            logger.info(f"Аудио файл: {out} ({size_mb:.2f} MB)")
        else:
            log_path = out.parent / "ffmpeg_capture.log"
            err = ""
            if log_path.exists():
                err = open(log_path).read()[-500:]
            logger.error(f"Аудио файл НЕ создан: {out}. ffmpeg log: {err}")

        return self.output_path

    async def _ensure_sink(self):
        """Проверить/создать PulseAudio null-sink (БЕЗ установки default)."""
        ensure_pulseaudio_sink(self.sink_name)

    async def cleanup(self):
        """Выгрузить sink после остановки записи (если он per-meeting).

        Не трогаем legacy `bot_capture` чтобы start.sh продолжал работать.
        """
        if self.sink_name != LEGACY_SINK_NAME:
            unload_pulseaudio_sink(self.sink_name)

    @property
    def is_recording(self) -> bool:
        return self.process is not None and self.process.poll() is None

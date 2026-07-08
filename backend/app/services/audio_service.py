import asyncio
import json
import logging
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp3", ".mp4", ".wav", ".ogg", ".opus", ".webm", ".m4a", ".mkv", ".aac", ".flac"}


def validate_audio_extension(filename: str) -> bool:
    return Path(filename).suffix.lower() in SUPPORTED_EXTENSIONS


async def preprocess_audio(input_path: Path) -> tuple[Path, float]:
    """Конвертирует аудио/видео в WAV 16kHz mono. Возвращает (wav_path, duration_seconds).

    ВАЖНО про WebM-вход (MediaRecorder в Chrome):
    Часть веб-браузеров пишут WebM без Cues и без duration в EBML header.
    Без флагов ffmpeg при чтении доверяет битому header'у и обрабатывает
    только первый chunk → итоговый WAV ~1 секунда вместо реальных 30+ сек.

    Лечится `-fflags +genpts` (регенерация PTS) и явным просчётом длительности
    из WAV header (точно знает, сколько в нём фреймов).
    """
    output_path = input_path.parent / "audio.wav"

    input_size_mb = input_path.stat().st_size / 1024 / 1024 if input_path.exists() else 0
    logger.info(f"Конвертация {input_path} ({input_size_mb:.1f} MB) -> {output_path}")

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-fflags", "+genpts",              # перегенерировать PTS — лечит битые WebM от MediaRecorder
        "-i", str(input_path),
        "-vn",                              # игнорировать видеодорожку (если есть)
        "-ar", "16000", "-ac", "1", "-f", "wav",
        "-y", str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()

    if process.returncode != 0:
        raise RuntimeError(f"Ошибка ffmpeg: {stderr.decode()}")

    duration = _wav_duration(output_path)
    logger.info(f"Конвертация завершена. Длительность: {duration:.1f}с")

    return output_path, duration


def _wav_duration(wav_path: Path) -> float:
    """Точная длительность WAV из заголовка (frames / framerate).

    Раньше тут был ffprobe -show_format, но он иногда возвращает duration
    из контейнера (а не реальный) и врёт на 1.0с для битых входов.
    Чтение WAV-header — детерминированное и быстрое.
    """
    try:
        with wave.open(str(wav_path), "rb") as w:
            frames = w.getnframes()
            rate = w.getframerate()
            if rate <= 0:
                return 0.0
            return frames / rate
    except (wave.Error, EOFError, FileNotFoundError) as e:
        logger.warning(f"Не удалось прочитать WAV header {wav_path}: {e}; fallback ffprobe")
        # Fallback на старый путь — на крайний случай
        try:
            import subprocess
            out = subprocess.check_output(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_format", str(wav_path)],
                timeout=10,
            )
            return float(json.loads(out)["format"]["duration"])
        except Exception:
            return 0.0

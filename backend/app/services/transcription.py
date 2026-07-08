import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import torch

logger = logging.getLogger(__name__)

_model = None
_model_lock = Lock()


@dataclass
class WhisperSegment:
    text: str
    start: float
    end: float


def _get_model():
    global _model
    if _model is None:
        with _model_lock:
            if _model is None:
                logger.info("Загрузка модели faster-whisper large-v3...")
                from faster_whisper import WhisperModel
                _model = WhisperModel(
                    "large-v3",
                    device="cuda",
                    compute_type="float16",
                )
                logger.info("Модель faster-whisper загружена")
    return _model


def unload_model():
    """Выгрузить модель из GPU для освобождения памяти."""
    global _model
    if _model is not None:
        del _model
        _model = None
        torch.cuda.empty_cache()
        logger.info("Модель faster-whisper выгружена из GPU")


def _collect_segments(segments_iter) -> list[WhisperSegment]:
    """Собрать сегменты из итератора faster-whisper."""
    result = []
    for segment in segments_iter:
        text = segment.text.strip()
        if text:
            result.append(WhisperSegment(
                text=text,
                start=segment.start,
                end=segment.end,
            ))
    return result


def transcribe(wav_path: Path) -> list[WhisperSegment]:
    """Транскрибирует WAV-файл. Возвращает список сегментов."""
    model = _get_model()
    logger.info(f"Начало транскрибации: {wav_path}")

    # Попытка 1: с VAD фильтром (убирает шум/тишину)
    logger.info("Транскрибация с VAD фильтром...")
    segments, info = model.transcribe(
        str(wav_path),
        language="ru",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"threshold": 0.3},  # порог ниже дефолтного 0.5
    )

    result = _collect_segments(segments)
    logger.info(
        f"VAD транскрибация: {len(result)} сегментов, "
        f"язык: {info.language}, вероятность: {info.language_probability:.2f}"
    )

    # Попытка 2: если VAD удалил всё — повтор без VAD
    if not result:
        logger.warning("VAD фильтр удалил всё аудио! Повторяем без VAD...")
        segments, info = model.transcribe(
            str(wav_path),
            language="ru",
            beam_size=5,
            vad_filter=False,
        )
        result = _collect_segments(segments)
        logger.info(f"Транскрибация без VAD: {len(result)} сегментов")

    logger.info(f"Транскрибация завершена: {len(result)} сегментов")
    return result

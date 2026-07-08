import logging
from dataclasses import dataclass
from pathlib import Path

from diarize import diarize as run_diarize

logger = logging.getLogger(__name__)


@dataclass
class DiarizationSegment:
    speaker: str
    start: float
    end: float


def unload_pipeline():
    """No-op: diarize работает на CPU, выгрузка GPU не требуется."""
    pass


def diarize(wav_path: Path) -> list[DiarizationSegment]:
    """Выполняет диаризацию WAV-файла. Возвращает сегменты со спикерами."""
    logger.info(f"Начало диаризации (diarize, CPU): {wav_path}")

    result = run_diarize(str(wav_path))

    segments = []
    for seg in result.segments:
        segments.append(DiarizationSegment(
            speaker=seg.speaker,
            start=seg.start,
            end=seg.end,
        ))

    logger.info(f"Диаризация завершена: {len(segments)} сегментов, спикеров: {result.num_speakers}")
    return segments

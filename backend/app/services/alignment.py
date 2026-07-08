import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AlignedSegment:
    speaker: str
    text: str
    start: float
    end: float


def align(
    whisper_segments: list[Any],
    diarization_segments: list[Any],
) -> list[AlignedSegment]:
    """Совмещает транскрипцию и диаризацию по таймкодам."""
    logger.info(f"Совмещение: {len(whisper_segments)} whisper + {len(diarization_segments)} diarization сегментов")

    aligned = []
    for ws in whisper_segments:
        speaker = _find_speaker(ws.start, ws.end, diarization_segments)
        aligned.append(AlignedSegment(
            speaker=speaker,
            text=ws.text,
            start=ws.start,
            end=ws.end,
        ))

    # Merge consecutive segments from same speaker
    merged = _merge_consecutive(aligned)
    logger.info(f"Совмещение завершено: {len(merged)} объединённых сегментов")
    return merged


def _find_speaker(
    start: float, end: float, diarization_segments: list[Any]
) -> str:
    """Найти спикера по максимальному пересечению по времени."""
    best_speaker = "Неизвестный"
    best_overlap = 0.0

    for ds in diarization_segments:
        overlap_start = max(start, ds.start)
        overlap_end = min(end, ds.end)
        overlap = max(0.0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = ds.speaker

    return best_speaker


def _merge_consecutive(segments: list[AlignedSegment]) -> list[AlignedSegment]:
    """Объединить подряд идущие сегменты одного спикера."""
    if not segments:
        return []

    merged = [AlignedSegment(
        speaker=segments[0].speaker,
        text=segments[0].text,
        start=segments[0].start,
        end=segments[0].end,
    )]

    for seg in segments[1:]:
        if seg.speaker == merged[-1].speaker:
            merged[-1].text += " " + seg.text
            merged[-1].end = seg.end
        else:
            merged.append(AlignedSegment(
                speaker=seg.speaker,
                text=seg.text,
                start=seg.start,
                end=seg.end,
            ))

    return merged

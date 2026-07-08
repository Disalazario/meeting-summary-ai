"""Сопоставление кластеров диаризации с зарегистрированными голосами.

Алгоритм:
1. Для каждого SPEAKER_NN из диаризации находим самый длинный сегмент (5+ сек).
2. Извлекаем embedding этого фрагмента через ECAPA-TDNN.
3. Сравниваем с VoiceProfile-ами всех пользователей.
4. Назначаем имя если cosine similarity >= MATCH_THRESHOLD.
5. Глобально гарантируем один-к-одному (Hungarian): один user не может быть
   назначен двум разным SPEAKER_NN в одной встрече.
"""

import logging
from collections import defaultdict
from pathlib import Path

from app.services.speaker_embedding import (
    cosine_similarity, deserialize, get_extractor,
)

logger = logging.getLogger(__name__)

# Порог уверенности (cosine sim в нормализованной шкале 0..1).
# 0.75 для ECAPA — это уже довольно уверенное «тот же спикер».
MATCH_THRESHOLD = 0.75

# Минимальная длина фрагмента для извлечения embedding (сек).
MIN_SEGMENT_DURATION = 3.0


def _pick_anchor_segments(diarization_segments) -> dict[str, tuple[float, float]]:
    """Для каждого SPEAKER_NN выбрать самый длинный сегмент."""
    by_speaker: dict[str, list] = defaultdict(list)
    for seg in diarization_segments:
        by_speaker[seg.speaker].append(seg)

    anchors = {}
    for speaker, segs in by_speaker.items():
        longest = max(segs, key=lambda s: s.end - s.start)
        if longest.end - longest.start >= MIN_SEGMENT_DURATION:
            anchors[speaker] = (longest.start, longest.end)
        else:
            logger.info(
                f"Спикер {speaker}: длиннейший сегмент только {longest.end - longest.start:.1f}с, "
                f"пропускаем (нужно >= {MIN_SEGMENT_DURATION}с)"
            )
    return anchors


def match_speakers_to_users(
    wav_path: Path,
    diarization_segments: list,
    voice_profiles: list,
) -> dict[str, str]:
    """
    Сопоставить диаризационные метки SPEAKER_NN с именами пользователей.

    Args:
        wav_path: путь к WAV-файлу совещания.
        diarization_segments: сегменты из `diarize` (Segment(start, end, speaker)).
        voice_profiles: список VoiceProfile с уже подгруженным relationship `user`.

    Returns:
        Словарь {SPEAKER_NN: display_name}. Спикеры без уверенного matching не попадают.
    """
    if not voice_profiles:
        logger.info("Голосовых профилей нет — пропускаем embedding matching")
        return {}

    anchors = _pick_anchor_segments(diarization_segments)
    if not anchors:
        logger.info("Подходящих anchor-сегментов нет (нужны >=3с) — пропускаем")
        return {}

    extractor = get_extractor()

    # 1. Извлечь embeddings для каждого SPEAKER_NN.
    speaker_embeddings = {}
    for speaker, (start, end) in anchors.items():
        try:
            emb = extractor.extract_segment(wav_path, start, end)
            speaker_embeddings[speaker] = emb
        except Exception as e:
            logger.warning(f"Не удалось извлечь embedding для {speaker}: {e}")

    if not speaker_embeddings:
        return {}

    # 2. Матрица сходства speaker × user_profile.
    profiles_by_user = {p.user_id: (p.user.display_name, deserialize(p.embedding)) for p in voice_profiles}

    similarities = []  # (speaker, user_id, name, sim)
    for speaker, sp_emb in speaker_embeddings.items():
        for user_id, (name, profile_emb) in profiles_by_user.items():
            sim = cosine_similarity(sp_emb, profile_emb)
            similarities.append((speaker, user_id, name, sim))
            logger.debug(f"sim({speaker} ↔ {name})={sim:.3f}")

    # 3. Жадное назначение по убыванию similarity (одни-к-одному).
    similarities.sort(key=lambda x: -x[3])
    assigned_speakers = set()
    assigned_users = set()
    result: dict[str, str] = {}

    for speaker, user_id, name, sim in similarities:
        if sim < MATCH_THRESHOLD:
            break
        if speaker in assigned_speakers or user_id in assigned_users:
            continue
        result[speaker] = name
        assigned_speakers.add(speaker)
        assigned_users.add(user_id)
        logger.info(f"Match: {speaker} → {name} (sim={sim:.3f})")

    unmatched = set(speaker_embeddings) - assigned_speakers
    if unmatched:
        logger.info(f"Без matching (sim < {MATCH_THRESHOLD}): {unmatched}")

    return result

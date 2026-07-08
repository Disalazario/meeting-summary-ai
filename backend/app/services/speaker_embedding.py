"""Извлечение голосовых эмбеддингов через SpeechBrain ECAPA-TDNN.

Использование:
    extractor = get_extractor()
    emb = extractor.extract_from_wav(wav_path)            # весь файл
    emb = extractor.extract_segment(wav_path, 12.3, 18.7) # фрагмент

    sim = cosine_similarity(emb_a, emb_b)                 # 0..1
    blob = serialize(emb)                                 # для БД
    emb  = deserialize(blob)
"""

import logging
import threading
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

# ECAPA-TDNN отдаёт 192-dim float32
EMBEDDING_DIM = 192

_extractor = None
_extractor_lock = threading.Lock()


def _device() -> str:
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


class SpeakerEmbeddingExtractor:
    """Обёртка над SpeechBrain SpeakerRecognition (ECAPA-TDNN).

    Ленивая загрузка модели — при первом вызове ~500 МБ весов с HuggingFace.
    """

    def __init__(self):
        self._model = None
        self._device = _device()

    def _load(self):
        if self._model is not None:
            return
        logger.info(f"Загрузка ECAPA-TDNN (device={self._device})...")
        from speechbrain.inference.speaker import SpeakerRecognition
        self._model = SpeakerRecognition.from_hparams(
            source="speechbrain/spkrec-ecapa-voxceleb",
            savedir="/tmp/spkrec-ecapa-voxceleb",
            run_opts={"device": self._device},
        )
        logger.info("ECAPA-TDNN загружена")

    def extract_from_wav(self, wav_path: Path) -> np.ndarray:
        """Эмбеддинг для всего WAV-файла."""
        self._load()
        import torchaudio
        signal, sr = torchaudio.load(str(wav_path))
        if sr != 16000:
            signal = torchaudio.functional.resample(signal, sr, 16000)
        # Mono
        if signal.shape[0] > 1:
            signal = signal.mean(dim=0, keepdim=True)
        embeddings = self._model.encode_batch(signal)
        return embeddings.squeeze().detach().cpu().numpy().astype(np.float32)

    def extract_segment(self, wav_path: Path, start: float, end: float) -> np.ndarray:
        """Эмбеддинг для фрагмента [start, end] секунд WAV-файла."""
        self._load()
        import torchaudio
        info = torchaudio.info(str(wav_path))
        sr = info.sample_rate
        frame_offset = int(start * sr)
        num_frames = max(1, int((end - start) * sr))
        signal, _ = torchaudio.load(
            str(wav_path), frame_offset=frame_offset, num_frames=num_frames,
        )
        if sr != 16000:
            signal = torchaudio.functional.resample(signal, sr, 16000)
        if signal.shape[0] > 1:
            signal = signal.mean(dim=0, keepdim=True)
        embeddings = self._model.encode_batch(signal)
        return embeddings.squeeze().detach().cpu().numpy().astype(np.float32)


def get_extractor() -> SpeakerEmbeddingExtractor:
    global _extractor
    if _extractor is None:
        with _extractor_lock:
            if _extractor is None:
                _extractor = SpeakerEmbeddingExtractor()
    return _extractor


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Косинусное сходство (нормированное в 0..1)."""
    a = a.flatten().astype(np.float32)
    b = b.flatten().astype(np.float32)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom < 1e-9:
        return 0.0
    # Из [-1..1] в [0..1] — удобнее как «вероятность совпадения»
    raw = float(np.dot(a, b) / denom)
    return (raw + 1.0) / 2.0


def serialize(embedding: np.ndarray) -> bytes:
    return embedding.astype(np.float32).tobytes()


def deserialize(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def average(emb_a: np.ndarray, emb_b: np.ndarray, weight_a: int = 1, weight_b: int = 1) -> np.ndarray:
    """Взвешенное среднее двух эмбеддингов (для накопления profile при правках)."""
    total = weight_a + weight_b
    return ((emb_a * weight_a + emb_b * weight_b) / total).astype(np.float32)

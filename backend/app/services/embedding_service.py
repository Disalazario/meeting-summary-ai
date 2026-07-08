"""Локальный embedding-сервис на sentence-transformers (multilingual-e5-base).

Модель: intfloat/multilingual-e5-base — 278M параметров, поддерживает русский,
выдаёт 768-мерный вектор. Размер на диске ~500 МБ (скачивается при первом
запуске в ~/.cache/huggingface).

E5-семейство требует префиксов:
- для индексируемых текстов: "passage: <текст>"
- для поисковых запросов:    "query: <текст>"

Возвращаем l2-нормализованные float32 вектора, так что cosine similarity =
dot product — это упрощает retrieval (см. wiki_retrieval.py).

Загрузка модели ленивая: при первом вызове, потом кешируется. Прогрев на
GPU занимает 2-3 секунды, инференс на батч 32 текстов — десятки миллисекунд.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

logger = logging.getLogger(__name__)

MODEL_NAME = "intfloat/multilingual-e5-base"
EMBED_DIM = 768

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        import torch
        from sentence_transformers import SentenceTransformer
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"Загрузка embedding-модели {MODEL_NAME} на {device}...")
        _model = SentenceTransformer(MODEL_NAME, device=device)
        logger.info(
            f"Embedding-модель готова: dim={_model.get_sentence_embedding_dimension()}, "
            f"device={device}"
        )
        return _model


def embed_passages(texts: list[str], batch_size: int = 32) -> np.ndarray:
    """Эмбеддинги для документов/чанков. Префикс 'passage:' уже добавляется тут."""
    if not texts:
        return np.zeros((0, EMBED_DIM), dtype=np.float32)
    model = _get_model()
    inputs = [f"passage: {t}" for t in texts]
    arr = model.encode(
        inputs, batch_size=batch_size, normalize_embeddings=True,
        show_progress_bar=False, convert_to_numpy=True,
    )
    return arr.astype(np.float32, copy=False)


def embed_query(text: str) -> np.ndarray:
    """Эмбеддинг одного поискового запроса."""
    model = _get_model()
    arr = model.encode(
        [f"query: {text}"], normalize_embeddings=True,
        show_progress_bar=False, convert_to_numpy=True,
    )
    return arr[0].astype(np.float32, copy=False)


def encode_to_bytes(vec: np.ndarray) -> bytes:
    """Сериализация float32 вектора в bytes для хранения в SQLite BLOB."""
    return np.asarray(vec, dtype=np.float32).tobytes()


def decode_from_bytes(blob: bytes) -> np.ndarray:
    """Десериализация BLOB → float32 numpy array размерности EMBED_DIM."""
    return np.frombuffer(blob, dtype=np.float32)

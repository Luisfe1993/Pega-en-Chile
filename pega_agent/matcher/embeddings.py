"""Multilingual embedding helpers (ES/EN) for semantic matching.

We use `intfloat/multilingual-e5-small` by default: ~470MB, strong on ES+EN,
much lighter than bge-m3. Override via env: PEGA_EMBEDDING_MODEL=...

The model is loaded lazily inside `_get_model()` so importing this module
(or running tests) does NOT trigger a multi-hundred-MB download. If loading
fails for any reason, `embed_texts` returns an empty array and the matcher
falls back cleanly to keyword scoring.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import numpy as np

DEFAULT_MODEL = "intfloat/multilingual-e5-small"


@lru_cache(maxsize=1)
def _get_model() -> Any | None:
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
    except ImportError:
        return None
    try:
        name = os.getenv("PEGA_EMBEDDING_MODEL", DEFAULT_MODEL)
        return SentenceTransformer(name)
    except Exception:
        return None


def is_available() -> bool:
    return _get_model() is not None


def embed_texts(texts: list[str]) -> np.ndarray:
    """Return an (n, d) ndarray. Empty (0, 0) array if the model is unavailable."""
    model = _get_model()
    if model is None or not texts:
        return np.zeros((0, 0), dtype=np.float32)
    # e5 family expects "query: " / "passage: " prefixes for best quality.
    prefixed = [f"passage: {t}" for t in texts]
    vecs = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vecs, dtype=np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))

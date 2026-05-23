from __future__ import annotations

import math
from collections.abc import Iterable
from typing import Protocol
from memory.common.embedding import tokenize, character_ngrams

class EmbeddingModel(Protocol):
    dim: int

    def encode(self, text: str) -> list[float]:
        """Return a normalized vector for text."""


class HashEmbeddingModel:
    """Facade for the unified deterministic hash embedding, returning lists for JSON compatibility."""

    def __init__(self, dim: int = 384):
        from memory.common.embedding import UnifiedHashEmbeddingModel
        self.dim = dim
        self._model = UnifiedHashEmbeddingModel(dim=dim)

    def encode(self, text: str) -> list[float]:
        return self._model.encode(text).tolist()

    def encode_batch(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode_batch(texts).tolist()


def normalize(vector: Iterable[float]) -> list[float]:
    values = [float(v) for v in vector]
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    left = list(a)
    right = list(b)
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(sum(x * y for x, y in zip(left, right)))


def mean_embedding(vectors: Iterable[Iterable[float]], dim: int) -> list[float]:
    acc = [0.0] * dim
    count = 0
    for vector in vectors:
        values = list(vector)
        if len(values) != dim:
            continue
        count += 1
        for i, value in enumerate(values):
            acc[i] += float(value)
    if count == 0:
        return acc
    return normalize(value / count for value in acc)


def top_terms(text: str, limit: int = 3) -> list[str]:
    counts: dict[str, int] = {}
    for token in tokenize(text):
        if len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    return [term for term, _ in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]]

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import Iterable
from typing import Protocol, Union
import numpy as np

TOKEN_RE = re.compile(r"[A-Za-zА-Яа-я0-9_+#.-]+", re.UNICODE)


class UnifiedEmbedding(Protocol):
    dim: int

    def encode(self, text: str) -> np.ndarray:
        """Return a normalized numpy vector for text."""

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        """Return normalized numpy vectors for a list of texts."""


class UnifiedHashEmbeddingModel:
    """Deterministic local semantic-ish encoder with no network dependency.
    Outputs numpy arrays instead of raw lists for unified math consistency.
    """

    def __init__(self, dim: int = 384):
        if dim < 16:
            raise ValueError("dim must be >= 16")
        self.dim = dim

    def encode(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        tokens = tokenize(text)
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            primary = int.from_bytes(digest[:4], "big") % self.dim
            secondary = int.from_bytes(digest[4:8], "big") % self.dim
            sign = 1.0 if digest[8] % 2 == 0 else -1.0
            weight = 1.0 + min(len(token), 16) / 16.0
            vector[primary] += sign * weight
            vector[secondary] += sign * 0.35 * weight

            for ngram in character_ngrams(token):
                nd = hashlib.blake2b(ngram.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(nd[:4], "big") % self.dim
                vector[idx] += 0.08 if nd[4] % 2 == 0 else -0.08

        # Normalize using numpy
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        return np.vstack([self.encode(t) for t in texts])


class SentenceTransformerEmbeddingModel:
    """Encoder utilizing sentence-transformers if installed/configured,
    falling back to UnifiedHashEmbeddingModel.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", dim: int = 384):
        self.dim = dim
        self.model_name = model_name
        self.model = None
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(model_name)
            # update dim to model's native dim
            self.dim = self.model.get_sentence_embedding_dimension()
        except ImportError:
            print(f"[EmbeddingAdapter] sentence-transformers not found. Falling back to UnifiedHashEmbeddingModel.")
            self.fallback = UnifiedHashEmbeddingModel(dim=dim)
        except Exception as e:
            print(f"[EmbeddingAdapter] Failed to load model {model_name}: {e}. Falling back to UnifiedHashEmbeddingModel.")
            self.fallback = UnifiedHashEmbeddingModel(dim=dim)

    def encode(self, text: str) -> np.ndarray:
        if self.model is not None:
            vec = self.model.encode(text, convert_to_numpy=True, normalize_embeddings=True)
            return vec.astype(np.float32)
        return self.fallback.encode(text)

    def encode_batch(self, texts: list[str]) -> np.ndarray:
        if self.model is not None:
            vecs = self.model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
            return vecs.astype(np.float32)
        return self.fallback.encode_batch(texts)


class EmbeddingAdapter:
    """Factory and facade for unified embeddings."""

    @staticmethod
    def create(backend: str = "hash", dim: int = 384, model_name: str = "all-MiniLM-L6-v2") -> UnifiedEmbedding:
        if backend == "hash":
            return UnifiedHashEmbeddingModel(dim=dim)
        elif backend == "sentence-transformers":
            return SentenceTransformerEmbeddingModel(model_name=model_name, dim=dim)
        else:
            raise ValueError(f"Unknown embedding backend: {backend}")


def tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in TOKEN_RE.finditer(text or "")]


def character_ngrams(token: str, n: int = 3) -> Iterable[str]:
    if len(token) <= n:
        yield token
        return
    for i in range(len(token) - n + 1):
        yield token[i : i + n]

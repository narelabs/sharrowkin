"""Cached embedding model for faster memory operations."""

from __future__ import annotations

import hashlib
import pickle
from pathlib import Path
from typing import Any

from ..dsm.indexing.embedding import EmbeddingModel


class CachedEmbeddingModel:
    """Wrapper around embedding model with LRU cache.

    Caches embeddings in memory and optionally on disk to avoid
    recomputing the same embeddings multiple times.
    """

    def __init__(
        self,
        base_model: EmbeddingModel,
        cache_size: int = 10000,
        disk_cache_path: Path | None = None,
    ):
        self.base_model = base_model
        self.cache_size = cache_size
        self.disk_cache_path = disk_cache_path
        self._memory_cache: dict[str, list[float]] = {}
        self._cache_hits = 0
        self._cache_misses = 0

        if disk_cache_path and disk_cache_path.exists():
            self._load_disk_cache()

    @property
    def dim(self) -> int:
        return self.base_model.dim

    def encode(self, text: str) -> list[float]:
        """Encode text with caching."""
        # Create cache key from text hash
        cache_key = hashlib.md5(text.encode('utf-8')).hexdigest()

        # Check memory cache
        if cache_key in self._memory_cache:
            self._cache_hits += 1
            return self._memory_cache[cache_key]

        # Check disk cache
        if self.disk_cache_path:
            disk_result = self._load_from_disk(cache_key)
            if disk_result is not None:
                self._cache_hits += 1
                self._memory_cache[cache_key] = disk_result
                return disk_result

        # Cache miss - compute embedding
        self._cache_misses += 1
        embedding = self.base_model.encode(text)

        # Store in memory cache (with LRU eviction)
        if len(self._memory_cache) >= self.cache_size:
            # Remove oldest entry (simple FIFO for now)
            oldest_key = next(iter(self._memory_cache))
            del self._memory_cache[oldest_key]

        self._memory_cache[cache_key] = embedding

        # Store in disk cache
        if self.disk_cache_path:
            self._save_to_disk(cache_key, embedding)

        return embedding

    def _load_from_disk(self, cache_key: str) -> list[float] | None:
        """Load embedding from disk cache."""
        if not self.disk_cache_path:
            return None

        cache_file = self.disk_cache_path / f"{cache_key}.pkl"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        except Exception:
            return None

    def _save_to_disk(self, cache_key: str, embedding: list[float]) -> None:
        """Save embedding to disk cache."""
        if not self.disk_cache_path:
            return

        self.disk_cache_path.mkdir(parents=True, exist_ok=True)
        cache_file = self.disk_cache_path / f"{cache_key}.pkl"

        try:
            with open(cache_file, 'wb') as f:
                pickle.dump(embedding, f)
        except Exception:
            pass  # Ignore disk cache errors

    def _load_disk_cache(self) -> None:
        """Load all disk cache into memory on startup."""
        if not self.disk_cache_path or not self.disk_cache_path.exists():
            return

        for cache_file in self.disk_cache_path.glob("*.pkl"):
            try:
                cache_key = cache_file.stem
                with open(cache_file, 'rb') as f:
                    embedding = pickle.load(f)
                    self._memory_cache[cache_key] = embedding

                # Stop if memory cache is full
                if len(self._memory_cache) >= self.cache_size:
                    break
            except Exception:
                continue

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total = self._cache_hits + self._cache_misses
        hit_rate = self._cache_hits / total if total > 0 else 0.0

        return {
            "cache_hits": self._cache_hits,
            "cache_misses": self._cache_misses,
            "hit_rate": hit_rate,
            "memory_cache_size": len(self._memory_cache),
            "cache_size_limit": self.cache_size,
        }

    def clear_cache(self) -> None:
        """Clear all caches."""
        self._memory_cache.clear()
        self._cache_hits = 0
        self._cache_misses = 0

        if self.disk_cache_path and self.disk_cache_path.exists():
            for cache_file in self.disk_cache_path.glob("*.pkl"):
                cache_file.unlink()

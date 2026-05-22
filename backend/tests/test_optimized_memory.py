"""Tests for optimized memory components."""

import pytest
import time
from pathlib import Path
from backend.memory.optimized.cached_embedding import CachedEmbeddingModel
from backend.memory.dsm.indexing.embedding import HashEmbeddingModel


def test_cached_embedding_basic():
    """Test basic caching functionality."""
    base_model = HashEmbeddingModel()
    cached_model = CachedEmbeddingModel(base_model, cache_size=100)

    text = "Hello world"

    # First call - cache miss
    embedding1 = cached_model.encode(text)
    stats1 = cached_model.get_stats()
    assert stats1["cache_misses"] == 1
    assert stats1["cache_hits"] == 0

    # Second call - cache hit
    embedding2 = cached_model.encode(text)
    stats2 = cached_model.get_stats()
    assert stats2["cache_hits"] == 1
    assert stats2["cache_misses"] == 1

    # Embeddings should be identical
    assert embedding1 == embedding2


def test_cached_embedding_performance():
    """Test that caching improves performance."""
    base_model = HashEmbeddingModel()
    cached_model = CachedEmbeddingModel(base_model, cache_size=1000)

    texts = [f"Test text number {i}" for i in range(100)]

    # First pass - all cache misses
    start = time.time()
    for text in texts:
        cached_model.encode(text)
    first_pass_time = time.time() - start

    # Second pass - all cache hits
    start = time.time()
    for text in texts:
        cached_model.encode(text)
    second_pass_time = time.time() - start

    # Second pass should be significantly faster
    assert second_pass_time < first_pass_time * 0.5

    stats = cached_model.get_stats()
    assert stats["hit_rate"] == 0.5  # 50% hits (second pass)


def test_cached_embedding_lru_eviction():
    """Test LRU cache eviction."""
    base_model = HashEmbeddingModel()
    cached_model = CachedEmbeddingModel(base_model, cache_size=10)

    # Fill cache beyond limit
    for i in range(20):
        cached_model.encode(f"Text {i}")

    stats = cached_model.get_stats()
    assert stats["memory_cache_size"] == 10  # Should not exceed limit


def test_cached_embedding_disk_cache(tmp_path):
    """Test disk caching."""
    base_model = HashEmbeddingModel()
    cache_dir = tmp_path / "cache"

    # Create model with disk cache
    cached_model = CachedEmbeddingModel(
        base_model,
        cache_size=100,
        disk_cache_path=cache_dir
    )

    text = "Persistent text"
    embedding1 = cached_model.encode(text)

    # Create new model instance (simulating restart)
    cached_model2 = CachedEmbeddingModel(
        base_model,
        cache_size=100,
        disk_cache_path=cache_dir
    )

    # Should load from disk cache
    embedding2 = cached_model2.encode(text)
    stats = cached_model2.get_stats()

    assert embedding1 == embedding2
    assert stats["cache_hits"] == 1  # Loaded from disk


def test_cached_embedding_clear():
    """Test cache clearing."""
    base_model = HashEmbeddingModel()
    cached_model = CachedEmbeddingModel(base_model, cache_size=100)

    # Add some entries
    for i in range(10):
        cached_model.encode(f"Text {i}")

    stats1 = cached_model.get_stats()
    assert stats1["memory_cache_size"] == 10

    # Clear cache
    cached_model.clear_cache()

    stats2 = cached_model.get_stats()
    assert stats2["memory_cache_size"] == 0
    assert stats2["cache_hits"] == 0
    assert stats2["cache_misses"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

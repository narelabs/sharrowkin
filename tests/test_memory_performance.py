"""Performance test for optimized DSM memory."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.memory.dsm import DynamicSegmentedMemory


def test_memory_performance():
    """Test DSM with and without caching."""

    # Test data
    test_queries = [
        "How to implement authentication in FastAPI?",
        "What is the best way to handle database migrations?",
        "Explain React hooks and their usage",
        "How to optimize Python code performance?",
        "What are the benefits of TypeScript?",
    ] * 20  # 100 queries total

    print("=" * 60)
    print("DSM Memory Performance Test")
    print("=" * 60)

    # Test WITHOUT cache
    print("\n[1] Testing WITHOUT cache...")
    memory_no_cache = DynamicSegmentedMemory(enable_cache=False)

    # Write some test data
    for i in range(10):
        memory_no_cache.write(
            f"Test document {i}: This is sample content about programming topic {i}",
            category_path=f"docs/topic{i % 3}",
            importance=0.7
        )

    start = time.time()
    for query in test_queries:
        memory_no_cache.route(query, k=5)
    no_cache_time = time.time() - start

    print(f"   Time: {no_cache_time:.3f}s")
    print(f"   Queries/sec: {len(test_queries) / no_cache_time:.1f}")

    # Test WITH cache
    print("\n[2] Testing WITH cache (default)...")
    memory_with_cache = DynamicSegmentedMemory(enable_cache=True, cache_size=1000)

    # Write same test data
    for i in range(10):
        memory_with_cache.write(
            f"Test document {i}: This is sample content about programming topic {i}",
            category_path=f"docs/topic{i % 3}",
            importance=0.7
        )

    start = time.time()
    for query in test_queries:
        memory_with_cache.route(query, k=5)
    cache_time = time.time() - start

    print(f"   Time: {cache_time:.3f}s")
    print(f"   Queries/sec: {len(test_queries) / cache_time:.1f}")

    # Get cache stats
    if hasattr(memory_with_cache.embedding_model, 'get_stats'):
        stats = memory_with_cache.embedding_model.get_stats()
        print(f"\n   Cache stats:")
        print(f"   - Hits: {stats['cache_hits']}")
        print(f"   - Misses: {stats['cache_misses']}")
        print(f"   - Hit rate: {stats['hit_rate']:.1%}")
        print(f"   - Cache size: {stats['memory_cache_size']}")

    # Calculate speedup
    speedup = no_cache_time / cache_time
    print(f"\n[3] Results:")
    print(f"   Speedup: {speedup:.2f}x faster with cache")
    print(f"   Time saved: {no_cache_time - cache_time:.3f}s ({(1 - cache_time/no_cache_time)*100:.1f}%)")

    print("\n" + "=" * 60)
    print("Performance test completed")
    print("=" * 60)


if __name__ == "__main__":
    test_memory_performance()

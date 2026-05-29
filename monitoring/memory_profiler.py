"""Memory profiling and monitoring for Sharrowkin agent."""

from __future__ import annotations

import tracemalloc
import psutil
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class MemorySnapshot:
    """Memory usage snapshot."""
    timestamp: float
    current_mb: float
    peak_mb: float
    process_rss_mb: float
    process_vms_mb: float
    top_allocations: list[tuple[str, int]]


class MemoryProfiler:
    """Track memory usage and detect leaks."""

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.snapshots: list[MemorySnapshot] = []
        self.start_time = time.time()
        self.baseline_snapshot: Optional[MemorySnapshot] = None

        if self.enabled:
            tracemalloc.start()
            self.baseline_snapshot = self.take_snapshot()

    def take_snapshot(self) -> MemorySnapshot:
        """Take a memory snapshot."""
        if not self.enabled:
            return MemorySnapshot(
                timestamp=time.time(),
                current_mb=0.0,
                peak_mb=0.0,
                process_rss_mb=0.0,
                process_vms_mb=0.0,
                top_allocations=[]
            )

        # Get tracemalloc stats
        current, peak = tracemalloc.get_traced_memory()
        current_mb = current / 1024 / 1024
        peak_mb = peak / 1024 / 1024

        # Get process memory
        process = psutil.Process()
        mem_info = process.memory_info()
        rss_mb = mem_info.rss / 1024 / 1024
        vms_mb = mem_info.vms / 1024 / 1024

        # Get top allocations
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')
        top_allocations = [
            (str(stat), stat.size)
            for stat in top_stats[:10]
        ]

        return MemorySnapshot(
            timestamp=time.time(),
            current_mb=current_mb,
            peak_mb=peak_mb,
            process_rss_mb=rss_mb,
            process_vms_mb=vms_mb,
            top_allocations=top_allocations
        )

    def log_snapshot(self, label: str = ""):
        """Take and log a memory snapshot."""
        snapshot = self.take_snapshot()
        self.snapshots.append(snapshot)

        elapsed = snapshot.timestamp - self.start_time
        print(f"\n[Memory Profile] {label} (t={elapsed:.1f}s)")
        print(f"  Current: {snapshot.current_mb:.1f} MB")
        print(f"  Peak: {snapshot.peak_mb:.1f} MB")
        print(f"  Process RSS: {snapshot.process_rss_mb:.1f} MB")
        print(f"  Process VMS: {snapshot.process_vms_mb:.1f} MB")

        if self.baseline_snapshot:
            delta = snapshot.current_mb - self.baseline_snapshot.current_mb
            print(f"  Delta from baseline: {delta:+.1f} MB")

        return snapshot

    def detect_leak(self, threshold_mb: float = 50.0) -> bool:
        """Detect potential memory leak."""
        if not self.baseline_snapshot or len(self.snapshots) < 2:
            return False

        latest = self.snapshots[-1]
        delta = latest.current_mb - self.baseline_snapshot.current_mb

        if delta > threshold_mb:
            print(f"\n[Memory Leak Warning] Memory increased by {delta:.1f} MB")
            print("Top allocations:")
            for location, size in latest.top_allocations[:5]:
                print(f"  {size / 1024 / 1024:.1f} MB: {location}")
            return True

        return False

    def get_stats(self) -> dict:
        """Get memory statistics."""
        if not self.snapshots:
            return {}

        latest = self.snapshots[-1]
        return {
            "current_mb": latest.current_mb,
            "peak_mb": latest.peak_mb,
            "process_rss_mb": latest.process_rss_mb,
            "baseline_delta_mb": latest.current_mb - self.baseline_snapshot.current_mb if self.baseline_snapshot else 0.0,
            "snapshots_count": len(self.snapshots)
        }

    def stop(self):
        """Stop memory profiling."""
        if self.enabled:
            tracemalloc.stop()


# Global profiler instance
_global_profiler: Optional[MemoryProfiler] = None


def get_memory_profiler() -> MemoryProfiler:
    """Get or create global memory profiler."""
    global _global_profiler
    if _global_profiler is None:
        _global_profiler = MemoryProfiler(enabled=True)
    return _global_profiler


def log_memory(label: str = ""):
    """Quick helper to log memory."""
    profiler = get_memory_profiler()
    profiler.log_snapshot(label)

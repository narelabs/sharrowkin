"""Workspace caching to avoid redundant scans."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class CachedWorkspace:
    """Cached workspace scan results."""
    workspace_summary: str
    total_files: int
    total_lines: int
    complexity_avg: float
    circular_dependencies: int
    most_complex_functions: list[dict]
    semantic_insights: str
    timestamp: float
    last_mtime: float  # Latest file modification time in workspace

    def age_seconds(self) -> float:
        """Get cache age in seconds."""
        return time.time() - self.timestamp

    def is_stale(self, ttl_seconds: int) -> bool:
        """Check if cache is older than TTL."""
        return self.age_seconds() > ttl_seconds


class WorkspaceCache:
    """Cache for workspace scan results with smart invalidation."""

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 10):
        """
        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
            max_entries: Maximum number of cached workspaces (LRU eviction)
        """
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self.cache: dict[str, CachedWorkspace] = {}
        self.access_order: list[str] = []
        self.stats = {
            "hits": 0,
            "misses": 0,
            "invalidations": 0,
        }

    def get(self, workspace: Path) -> CachedWorkspace | None:
        """Get cached workspace data if valid."""
        key = str(workspace.resolve())

        if key not in self.cache:
            self.stats["misses"] += 1
            return None

        cached = self.cache[key]

        # Check if cache is stale (TTL expired)
        if cached.is_stale(self.ttl_seconds):
            self._invalidate(key, reason="ttl_expired")
            return None

        # Check if workspace files were modified
        if self._workspace_modified(workspace, cached.last_mtime):
            self._invalidate(key, reason="files_modified")
            return None

        # Cache hit - update access order
        self.stats["hits"] += 1
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

        return cached

    def set(self, workspace: Path, data: CachedWorkspace) -> None:
        """Store workspace scan results in cache."""
        key = str(workspace.resolve())

        # Update access order
        if key in self.access_order:
            self.access_order.remove(key)
        self.access_order.append(key)

        # Store in cache
        self.cache[key] = data

        # Evict oldest entries if over limit
        while len(self.cache) > self.max_entries:
            oldest_key = self.access_order.pop(0)
            if oldest_key in self.cache:
                del self.cache[oldest_key]

    def invalidate(self, workspace: Path) -> None:
        """Manually invalidate cache for a workspace."""
        key = str(workspace.resolve())
        self._invalidate(key, reason="manual")

    def clear(self) -> None:
        """Clear all cached entries."""
        self.stats["invalidations"] += len(self.cache)
        self.cache.clear()
        self.access_order.clear()

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total_requests if total_requests > 0 else 0.0

        return {
            "hits": self.stats["hits"],
            "misses": self.stats["misses"],
            "invalidations": self.stats["invalidations"],
            "hit_rate": hit_rate,
            "cached_workspaces": len(self.cache),
            "total_requests": total_requests,
        }

    def _invalidate(self, key: str, reason: str) -> None:
        """Remove entry from cache."""
        if key in self.cache:
            del self.cache[key]
        if key in self.access_order:
            self.access_order.remove(key)
        self.stats["invalidations"] += 1

    def _workspace_modified(self, workspace: Path, last_mtime: float) -> bool:
        """Check if any Python file in workspace was modified since last scan."""
        try:
            for file_path in workspace.rglob("*.py"):
                if file_path.is_file():
                    if file_path.stat().st_mtime > last_mtime:
                        return True
            return False
        except (OSError, PermissionError):
            # If we can't check, assume modified (safe default)
            return True

    def _get_latest_mtime(self, workspace: Path) -> float:
        """Get the latest modification time of any Python file in workspace."""
        try:
            mtimes = [
                file_path.stat().st_mtime
                for file_path in workspace.rglob("*.py")
                if file_path.is_file()
            ]
            return max(mtimes) if mtimes else time.time()
        except (OSError, PermissionError):
            return time.time()

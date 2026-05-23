"""Integration of workspace cache with file watcher."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .workspace_cache import WorkspaceCache
from .workspace_watcher import WorkspaceWatcher


class CachedWorkspaceManager:
    """Manages workspace cache with automatic file watching."""

    def __init__(self, workspace: Path, ttl_seconds: int = 3600):
        """
        Args:
            workspace: Root workspace directory
            ttl_seconds: Cache TTL in seconds
        """
        self.workspace = workspace
        self.cache = WorkspaceCache(ttl_seconds=ttl_seconds)
        self.watcher: Optional[WorkspaceWatcher] = None

    def start_watching(self):
        """Start file watcher for automatic cache invalidation."""
        if self.watcher is None:
            self.watcher = WorkspaceWatcher(self.workspace, self.cache)
            self.watcher.start()

    def stop_watching(self):
        """Stop file watcher."""
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher = None

    def get_cache(self) -> WorkspaceCache:
        """Get the cache instance."""
        return self.cache

    def __enter__(self):
        """Context manager entry."""
        self.start_watching()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop_watching()

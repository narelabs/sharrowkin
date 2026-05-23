"""File watcher for incremental workspace cache updates."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent


class WorkspaceFileWatcher(FileSystemEventHandler):
    """Watch workspace files and trigger cache updates on changes."""

    def __init__(
        self,
        workspace: Path,
        on_file_changed: Callable[[Path], None],
        on_file_created: Callable[[Path], None],
        on_file_deleted: Callable[[Path], None],
        debounce_ms: int = 500
    ):
        """
        Args:
            workspace: Root workspace directory to watch
            on_file_changed: Callback when file is modified
            on_file_created: Callback when file is created
            on_file_deleted: Callback when file is deleted
            debounce_ms: Debounce time in milliseconds to avoid rapid fire events
        """
        self.workspace = workspace
        self.on_file_changed = on_file_changed
        self.on_file_created = on_file_created
        self.on_file_deleted = on_file_deleted
        self.debounce_ms = debounce_ms
        self.last_event_time: dict[str, float] = {}

    def _should_process(self, path: str) -> bool:
        """Check if file should be processed (debouncing + filtering)."""
        # Ignore non-code files
        if not self._is_code_file(path):
            return False

        # Ignore common directories
        ignore_dirs = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', 'dist', 'build'}
        path_obj = Path(path)
        if any(part in ignore_dirs for part in path_obj.parts):
            return False

        # Debounce: ignore if same file was modified recently
        now = time.time()
        last_time = self.last_event_time.get(path, 0)
        if (now - last_time) * 1000 < self.debounce_ms:
            return False

        self.last_event_time[path] = now
        return True

    def _is_code_file(self, path: str) -> bool:
        """Check if file is a code file we care about."""
        code_extensions = {'.py', '.js', '.ts', '.tsx', '.jsx', '.java', '.cpp', '.c', '.h', '.go', '.rs', '.rb'}
        return Path(path).suffix in code_extensions

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification."""
        if event.is_directory:
            return

        if self._should_process(event.src_path):
            self.on_file_changed(Path(event.src_path))

    def on_created(self, event: FileSystemEvent):
        """Handle file creation."""
        if event.is_directory:
            return

        if self._should_process(event.src_path):
            self.on_file_created(Path(event.src_path))

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion."""
        if event.is_directory:
            return

        if self._should_process(event.src_path):
            self.on_file_deleted(Path(event.src_path))


class WorkspaceWatcher:
    """Manages file watching for workspace cache."""

    def __init__(self, workspace: Path, cache):
        """
        Args:
            workspace: Root workspace directory
            cache: WorkspaceCache instance to update
        """
        self.workspace = workspace
        self.cache = cache
        self.observer: Optional[Observer] = None
        self.handler: Optional[WorkspaceFileWatcher] = None

    def start(self):
        """Start watching workspace for changes."""
        if self.observer is not None:
            return  # Already watching

        self.handler = WorkspaceFileWatcher(
            workspace=self.workspace,
            on_file_changed=self._on_file_changed,
            on_file_created=self._on_file_created,
            on_file_deleted=self._on_file_deleted,
            debounce_ms=500
        )

        self.observer = Observer()
        self.observer.schedule(self.handler, str(self.workspace), recursive=True)
        self.observer.start()

    def stop(self):
        """Stop watching workspace."""
        if self.observer is not None:
            self.observer.stop()
            self.observer.join()
            self.observer = None
            self.handler = None

    def _on_file_changed(self, path: Path):
        """Handle file change - invalidate cache for this file."""
        # Invalidate entire workspace cache (simple approach)
        # In future, could do per-file cache invalidation
        self.cache.invalidate(self.workspace)

    def _on_file_created(self, path: Path):
        """Handle file creation - invalidate cache."""
        self.cache.invalidate(self.workspace)

    def _on_file_deleted(self, path: Path):
        """Handle file deletion - invalidate cache."""
        self.cache.invalidate(self.workspace)

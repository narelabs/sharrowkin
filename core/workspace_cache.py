"""Workspace caching to avoid redundant scans."""

from __future__ import annotations

import ast
import time
import pickle
import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

try:
    import msgpack
    HAS_MSGPACK = True
except ImportError:
    HAS_MSGPACK = False


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
    file_hashes: dict[str, str] = field(default_factory=dict)  # file_path -> hash
    ast_cache: dict[str, bytes] = field(default_factory=dict)  # file_path -> binary AST

    def age_seconds(self) -> float:
        """Get cache age in seconds."""
        return time.time() - self.timestamp

    def is_stale(self, ttl_seconds: int) -> bool:
        """Check if cache is older than TTL."""
        return self.age_seconds() > ttl_seconds


class WorkspaceCache:
    """Cache for workspace scan results with smart invalidation."""

    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 10, cache_dir: Optional[Path] = None):
        """
        Args:
            ttl_seconds: Time-to-live for cache entries (default 1 hour)
            max_entries: Maximum number of cached workspaces (LRU eviction)
            cache_dir: Directory for persistent cache (default: .sharrowkin/cache)
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

        # Persistent cache directory
        self.cache_dir = cache_dir or Path(".sharrowkin/cache")
        self.cache_dir.mkdir(parents=True, exist_ok=True)

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
        self.cache.clear()
        self.access_order.clear()
        self.stats["invalidations"] += len(self.cache)

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

    def update_file(self, file_path: Path, content: Optional[str] = None) -> None:
        """Incrementally update cache for a single file."""
        # Find workspace this file belongs to
        for workspace_key in self.cache.keys():
            workspace = Path(workspace_key)
            try:
                file_path.relative_to(workspace)
                # File belongs to this workspace
                cached = self.cache[workspace_key]

                # Update file hash
                if content is None:
                    content = file_path.read_text(encoding='utf-8', errors='ignore')

                file_hash = hashlib.sha256(content.encode()).hexdigest()
                cached.file_hashes[str(file_path)] = file_hash

                # Update AST cache if it's a Python file
                if file_path.suffix == '.py':
                    try:
                        import ast
                        tree = ast.parse(content)
                        cached.ast_cache[str(file_path)] = self._serialize_ast(tree)
                    except SyntaxError:
                        pass  # Invalid Python, skip AST

                # Update timestamp
                cached.last_mtime = max(cached.last_mtime, file_path.stat().st_mtime)

            except ValueError:
                continue  # File not in this workspace

    def remove_file(self, file_path: Path) -> None:
        """Remove file from cache."""
        for workspace_key in self.cache.keys():
            workspace = Path(workspace_key)
            try:
                file_path.relative_to(workspace)
                cached = self.cache[workspace_key]

                file_str = str(file_path)
                if file_str in cached.file_hashes:
                    del cached.file_hashes[file_str]
                if file_str in cached.ast_cache:
                    del cached.ast_cache[file_str]

            except ValueError:
                continue

    def save_to_disk(self, workspace: Path) -> None:
        """Save cache to disk in binary format."""
        key = str(workspace.resolve())
        if key not in self.cache:
            return

        cache_file = self._get_cache_file(workspace)
        cached = self.cache[key]

        if HAS_MSGPACK:
            # Use msgpack for better performance
            data = {
                'workspace_summary': cached.workspace_summary,
                'total_files': cached.total_files,
                'total_lines': cached.total_lines,
                'complexity_avg': cached.complexity_avg,
                'circular_dependencies': cached.circular_dependencies,
                'most_complex_functions': cached.most_complex_functions,
                'semantic_insights': cached.semantic_insights,
                'timestamp': cached.timestamp,
                'last_mtime': cached.last_mtime,
                'file_hashes': cached.file_hashes,
                'ast_cache': cached.ast_cache,
            }
            with open(cache_file, 'wb') as f:
                msgpack.pack(data, f)
        else:
            # Fallback to pickle
            with open(cache_file, 'wb') as f:
                pickle.dump(cached, f)

    def load_from_disk(self, workspace: Path) -> Optional[CachedWorkspace]:
        """Load cache from disk."""
        cache_file = self._get_cache_file(workspace)
        if not cache_file.exists():
            return None

        try:
            if HAS_MSGPACK:
                with open(cache_file, 'rb') as f:
                    data = msgpack.unpack(f)
                return CachedWorkspace(**data)
            else:
                with open(cache_file, 'rb') as f:
                    return pickle.load(f)
        except Exception:
            return None

    def _get_cache_file(self, workspace: Path) -> Path:
        """Get cache file path for workspace."""
        workspace_hash = hashlib.md5(str(workspace.resolve()).encode()).hexdigest()
        return self.cache_dir / f"{workspace_hash}.cache"

    def _serialize_ast(self, tree) -> bytes:
        """Serialize AST tree to bytes."""
        if HAS_MSGPACK:
            # Convert AST to dict representation
            return msgpack.packb(ast.dump(tree))
        else:
            return pickle.dumps(tree)

    def get_or_load(self, workspace: Path) -> Optional[CachedWorkspace]:
        """Get from memory cache or load from disk."""
        # Try memory cache first
        cached = self.get(workspace)
        if cached is not None:
            return cached

        # Try loading from disk
        cached = self.load_from_disk(workspace)
        if cached is not None and not cached.is_stale(self.ttl_seconds):
            # Load into memory cache
            self.cache[str(workspace.resolve())] = cached
            self.stats["hits"] += 1
            return cached

        return None

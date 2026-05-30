"""Database configuration and connection management for memory systems."""

import os
import json
import time
import shutil
from pathlib import Path
from typing import Optional
from qdrant_client import QdrantClient
import threading

# Global Qdrant client instance with thread-safety
_qdrant_client: Optional[QdrantClient] = None
_qdrant_lock = threading.Lock()
_client_workspace: Optional[Path] = None


def _is_corrupt_storage_error(exc: Exception) -> bool:
    """A corrupt/empty local Qdrant store surfaces as a JSON decode failure
    when it tries to read meta.json on load."""
    return isinstance(exc, json.JSONDecodeError) or "Expecting value" in str(exc)


def _reset_storage_dir(db_path: Path) -> None:
    """Move aside a corrupt Qdrant storage dir so a fresh one can be created.
    We rename rather than delete outright, so no memory is silently lost if a
    human wants to inspect it later."""
    if not db_path.exists():
        return
    backup = db_path.with_name(f"{db_path.name}.corrupt")
    try:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        db_path.rename(backup)
        print(f"[Qdrant] Corrupt storage moved to {backup}")
    except Exception:
        # If we can't rename, fall back to wiping it.
        shutil.rmtree(db_path, ignore_errors=True)
        print(f"[Qdrant] Corrupt storage removed at {db_path}")


def get_qdrant_client(workspace_path: Path) -> QdrantClient:
    """
    Get or initialize a local Qdrant client instance with connection pooling.
    Uses the workspace's .sharrowkin/qdrant directory for persistent local storage.
    Falls back to in-memory mode if the database is locked or unrecoverable.

    Thread-safe singleton pattern ensures only one client per workspace.
    """
    global _qdrant_client, _client_workspace

    with _qdrant_lock:
        # Return existing client if it's for the same workspace
        if _qdrant_client is not None and _client_workspace == workspace_path:
            return _qdrant_client

        # Close old client if workspace changed
        if _qdrant_client is not None and _client_workspace != workspace_path:
            try:
                _qdrant_client.close()
            except Exception:
                pass
            _qdrant_client = None

        db_path = workspace_path / ".sharrowkin" / "qdrant"
        db_path.mkdir(parents=True, exist_ok=True)

        def _connect() -> QdrantClient:
            return QdrantClient(
                path=str(db_path),
                timeout=30.0,
                prefer_grpc=False,  # Use HTTP for better compatibility
            )

        # Try to initialize local persistent Qdrant with optimized settings.
        try:
            _qdrant_client = _connect()
            _client_workspace = workspace_path
            print(f"[Qdrant] Connected to persistent storage at {db_path}")
        except Exception as e:
            # Database locked by another process → in-memory mode.
            if "already accessed" in str(e) or "locked" in str(e).lower():
                print(f"[Qdrant] Database locked, using in-memory mode")
                _qdrant_client = QdrantClient(":memory:")
                _client_workspace = workspace_path
            # Empty/half-written meta.json. This is usually transient: another
            # session was mid-write when we read it. Retry a few times before
            # treating the store as genuinely corrupt, so we don't wipe good memory.
            elif _is_corrupt_storage_error(e):
                print(f"[Qdrant] meta.json unreadable ({e}); retrying before reset")
                connected = False
                for attempt in range(5):
                    time.sleep(0.3)
                    try:
                        _qdrant_client = _connect()
                        _client_workspace = workspace_path
                        connected = True
                        print(f"[Qdrant] Recovered on retry {attempt + 1}")
                        break
                    except Exception as retry_exc:
                        if not _is_corrupt_storage_error(retry_exc):
                            raise
                # Still failing → the store really is corrupt. Reset once.
                if not connected:
                    print(f"[Qdrant] Storage still unreadable; resetting")
                    _reset_storage_dir(db_path)
                    db_path.mkdir(parents=True, exist_ok=True)
                    try:
                        _qdrant_client = _connect()
                        _client_workspace = workspace_path
                        print(f"[Qdrant] Reconnected to fresh storage at {db_path}")
                    except Exception as e2:
                        print(f"[Qdrant] Reset failed ({e2}); using in-memory mode")
                        _qdrant_client = QdrantClient(":memory:")
                        _client_workspace = workspace_path
            else:
                raise

        return _qdrant_client

def close_qdrant_client() -> None:
    """✅ NEW: Properly close the Qdrant client and release resources."""
    global _qdrant_client, _client_workspace

    with _qdrant_lock:
        if _qdrant_client is not None:
            try:
                _qdrant_client.close()
                print(f"[Qdrant] Client closed")
            except Exception as e:
                print(f"[Qdrant] Error closing client: {e}")
            finally:
                _qdrant_client = None
                _client_workspace = None

def reset_qdrant_client() -> None:
    """Reset the global Qdrant client instance."""
    close_qdrant_client()


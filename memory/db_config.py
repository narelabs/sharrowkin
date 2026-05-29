"""Database configuration and connection management for memory systems."""

import os
from pathlib import Path
from typing import Optional
from qdrant_client import QdrantClient
import threading

# Global Qdrant client instance with thread-safety
_qdrant_client: Optional[QdrantClient] = None
_qdrant_lock = threading.Lock()
_client_workspace: Optional[Path] = None

def get_qdrant_client(workspace_path: Path) -> QdrantClient:
    """
    Get or initialize a local Qdrant client instance with connection pooling.
    Uses the workspace's .sharrowkin/qdrant directory for persistent local storage.
    Falls back to in-memory mode if the database is already locked by another process.

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

        # Try to initialize local persistent Qdrant with optimized settings
        try:
            _qdrant_client = QdrantClient(
                path=str(db_path),
                # ✅ NEW: Connection pooling settings
                timeout=30.0,  # 30 second timeout
                prefer_grpc=False,  # Use HTTP for better compatibility
            )
            _client_workspace = workspace_path
            print(f"[Qdrant] Connected to persistent storage at {db_path}")
        except Exception as e:
            # If database is locked, fall back to in-memory mode
            if "already accessed" in str(e) or "locked" in str(e).lower():
                print(f"[Qdrant] Database locked, using in-memory mode")
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


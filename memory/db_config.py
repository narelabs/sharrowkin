"""Database configuration and connection management for memory systems."""

import os
from pathlib import Path
from typing import Optional
from qdrant_client import QdrantClient

# Global Qdrant client instance
_qdrant_client: Optional[QdrantClient] = None

def get_qdrant_client(workspace_path: Path) -> QdrantClient:
    """
    Get or initialize a local Qdrant client instance.
    Uses the workspace's .sharrowkin/qdrant directory for persistent local storage.
    Falls back to in-memory mode if the database is already locked by another process.
    """
    global _qdrant_client

    if _qdrant_client is not None:
        return _qdrant_client

    db_path = workspace_path / ".sharrowkin" / "qdrant"
    db_path.mkdir(parents=True, exist_ok=True)

    # Try to initialize local persistent Qdrant
    try:
        _qdrant_client = QdrantClient(path=str(db_path))
    except Exception as e:
        # If database is locked, fall back to in-memory mode
        if "already accessed" in str(e) or "locked" in str(e).lower():
            print(f"[Qdrant] Database locked, using in-memory mode")
            _qdrant_client = QdrantClient(":memory:")
        else:
            raise

    return _qdrant_client

def reset_qdrant_client() -> None:
    """Reset the global Qdrant client instance."""
    global _qdrant_client
    _qdrant_client = None

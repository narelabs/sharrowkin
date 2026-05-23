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
    """
    global _qdrant_client
    
    if _qdrant_client is not None:
        return _qdrant_client
        
    db_path = workspace_path / ".sharrowkin" / "qdrant"
    db_path.mkdir(parents=True, exist_ok=True)
    
    # Initialize local persistent Qdrant
    _qdrant_client = QdrantClient(path=str(db_path))
    
    return _qdrant_client

def reset_qdrant_client() -> None:
    """Reset the global Qdrant client instance."""
    global _qdrant_client
    _qdrant_client = None

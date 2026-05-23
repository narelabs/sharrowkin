from __future__ import annotations

from typing import Any
import uuid

from qdrant_client.http.models import Distance, VectorParams, PointStruct

from .embedding import cosine
from ..core.models import MemorySegment
from ...db_config import get_qdrant_client
from pathlib import Path
import os


class SegmentIndex:
    """Fast segment index backed by Qdrant vector database."""

    def __init__(self, backend: str = "qdrant") -> None:
        self.backend = backend
        self.collection_name = "dsm_segments"
        
        # Determine workspace path (hacky but works since we know it runs from workspace)
        # Ideally passed in, but we fallback to CWD
        workspace = Path(os.environ.get("WORKSPACE_PATH", os.getcwd()))
        
        self.client = get_qdrant_client(workspace)
        self._dim = 0
        self._size = 0
        self._initialized = False

    def _ensure_collection(self, dim: int):
        if self._initialized and self._dim == dim:
            return
            
        if not self.client.collection_exists(self.collection_name):
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        self._dim = dim
        self._initialized = True

    def rebuild(self, segments: dict[str, MemorySegment]) -> None:
        """Rebuild the Qdrant index with the current segments."""
        if not segments:
            self._size = 0
            return
            
        # Get dim from first segment
        first_emb = next(iter(segments.values())).embedding
        self._ensure_collection(len(first_emb))
        
        points = []
        for segment_id, segment in segments.items():
            # Qdrant requires UUIDs or integers. We'll use uuid.uuid5 to generate stable UUIDs from segment_id
            point_id = str(uuid.uuid5(uuid.NAMESPACE_OID, segment_id))
            points.append(
                PointStruct(
                    id=point_id,
                    vector=segment.embedding,
                    payload={"segment_id": segment_id}
                )
            )
            
        if points:
            # Overwrite collection
            self.client.recreate_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=self._dim, distance=Distance.COSINE)
            )
            
            # Batch upload
            batch_size = 100
            for i in range(0, len(points), batch_size):
                self.client.upsert(
                    collection_name=self.collection_name,
                    points=points[i:i + batch_size]
                )
        self._size = len(points)

    def search(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        if not self._initialized or self._size == 0:
            return []
            
        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=max(0, k)
        )
        
        return [(hit.payload["segment_id"], hit.score) for hit in search_result.points]

    @property
    def size(self) -> int:
        return self._size

    @property
    def backend_name(self) -> str:
        return "qdrant"

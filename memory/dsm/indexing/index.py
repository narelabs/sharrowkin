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

    def upsert(self, segment: MemorySegment) -> None:
        """✅ NEW: Incremental upsert single segment without rebuilding entire index."""
        self._ensure_collection(len(segment.embedding))

        point_id = str(uuid.uuid5(uuid.NAMESPACE_OID, segment.id))
        self.client.upsert(
            collection_name=self.collection_name,
            points=[PointStruct(
                id=point_id,
                vector=segment.embedding,
                payload={"segment_id": segment.id}
            )]
        )
        self._size += 1

    def search(self, query_embedding: list[float], k: int, offset: int = 0) -> list[tuple[str, float]]:
        """Search with pagination support to prevent memory leaks.

        Args:
            query_embedding: Query vector
            k: Number of results to return
            offset: Number of results to skip (for pagination)
        """
        if not self._initialized or self._size == 0:
            return []

        # Limit k to prevent excessive memory usage
        k = min(k, 1000)  # Max 1000 results per query

        search_result = self.client.query_points(
            collection_name=self.collection_name,
            query=query_embedding,
            limit=max(0, k),
            offset=offset
        )

        return [(hit.payload["segment_id"], hit.score) for hit in search_result.points]

    def batch_search(self, queries: list[list[float]], k: int) -> list[list[tuple[str, float]]]:
        """✅ NEW: Batch search for multiple queries at once.

        Args:
            queries: List of query vectors
            k: Number of results per query

        Returns:
            List of search results, one per query
        """
        if not self._initialized or self._size == 0:
            return [[] for _ in queries]

        # Limit k to prevent excessive memory usage
        k = min(k, 1000)

        results = []
        # Process in batches of 10 to avoid overwhelming the server
        batch_size = 10
        for i in range(0, len(queries), batch_size):
            batch = queries[i:i + batch_size]
            batch_results = []

            for query in batch:
                search_result = self.client.query_points(
                    collection_name=self.collection_name,
                    query=query,
                    limit=k
                )
                batch_results.append([
                    (hit.payload["segment_id"], hit.score)
                    for hit in search_result.points
                ])

            results.extend(batch_results)

        return results

    @property
    def size(self) -> int:
        return self._size

    @property
    def backend_name(self) -> str:
        return "qdrant"

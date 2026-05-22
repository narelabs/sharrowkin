from __future__ import annotations

from typing import Any

from .embedding import cosine
from ..core.models import MemorySegment


class SegmentIndex:
    """Fast segment index with FAISS/HNSW when available and exact fallback."""

    def __init__(self, backend: str = "auto") -> None:
        self.backend = backend
        self._ids: list[str] = []
        self._vectors: list[list[float]] = []
        self._faiss: Any = None
        self._faiss_index: Any = None
        self._dim = 0

    def rebuild(self, segments: dict[str, MemorySegment]) -> None:
        self._ids = []
        self._vectors = []
        for segment_id, segment in segments.items():
            self._ids.append(segment_id)
            self._vectors.append(segment.embedding)
        self._dim = len(self._vectors[0]) if self._vectors else 0
        self._build_faiss()

    def search(self, query_embedding: list[float], k: int) -> list[tuple[str, float]]:
        if self._faiss_index is not None and self._faiss is not None and self._ids:
            import numpy as np

            query = np.array([query_embedding], dtype="float32")
            self._faiss.normalize_L2(query)
            scores, indices = self._faiss_index.search(query, max(0, min(k, len(self._ids))))
            out: list[tuple[str, float]] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0:
                    out.append((self._ids[int(idx)], float(score)))
            return out

        scored = [
            (segment_id, cosine(query_embedding, embedding))
            for segment_id, embedding in zip(self._ids, self._vectors)
        ]
        scored.sort(reverse=True, key=lambda item: item[1])
        return scored[: max(0, k)]

    @property
    def size(self) -> int:
        return len(self._ids)

    @property
    def backend_name(self) -> str:
        return "faiss_hnsw" if self._faiss_index is not None else "exact"

    def _build_faiss(self) -> None:
        self._faiss = None
        self._faiss_index = None
        if self.backend == "exact" or not self._vectors or self._dim == 0:
            return
        try:
            import faiss
            import numpy as np
        except ImportError:
            if self.backend == "faiss":
                raise
            return

        vectors = np.array(self._vectors, dtype="float32")
        faiss.normalize_L2(vectors)
        index = faiss.IndexHNSWFlat(self._dim, 32, faiss.METRIC_INNER_PRODUCT)
        index.hnsw.efConstruction = 64
        index.hnsw.efSearch = 64
        index.add(vectors)
        self._faiss = faiss
        self._faiss_index = index

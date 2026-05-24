"""Spatial index for fast nearest-neighbor gene search in RLD.

Uses Ball Tree for O(N log N) gene merging instead of O(N²) brute force.
"""

from __future__ import annotations

import numpy as np
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ReasoningGene


class GeneSpatialIndex:
    """Ball Tree spatial index for fast gene similarity search.

    Reduces gene merging from O(N²) to O(N log N) by using spatial indexing
    for nearest-neighbor queries in embedding space.
    """

    def __init__(self, leaf_size: int = 40):
        """
        Args:
            leaf_size: Number of points at which to switch to brute-force search.
                      Smaller values = faster queries, slower build.
        """
        self.leaf_size = leaf_size
        self._tree = None
        self._gene_ids: list[str] = []
        self._embeddings: np.ndarray | None = None

    def build(self, genes: dict[str, ReasoningGene]) -> None:
        """Build spatial index from genes.

        Args:
            genes: Dictionary of gene_id -> ReasoningGene
        """
        if not genes:
            self._tree = None
            self._gene_ids = []
            self._embeddings = None
            return

        try:
            from sklearn.neighbors import BallTree
        except ImportError:
            # Fallback: no spatial index, will use brute force
            self._tree = None
            self._gene_ids = []
            self._embeddings = None
            return

        self._gene_ids = list(genes.keys())
        self._embeddings = np.array([genes[gid].embedding for gid in self._gene_ids], dtype=np.float32)

        # Build Ball Tree with cosine distance (1 - cosine similarity)
        self._tree = BallTree(self._embeddings, leaf_size=self.leaf_size, metric='cosine')

    def find_similar(
        self,
        gene: ReasoningGene,
        similarity_threshold: float,
        max_results: int = 50
    ) -> list[tuple[str, float]]:
        """Find genes similar to the given gene.

        Args:
            gene: Query gene
            similarity_threshold: Minimum cosine similarity (0-1)
            max_results: Maximum number of results to return

        Returns:
            List of (gene_id, similarity) tuples, sorted by similarity descending
        """
        if self._tree is None or self._embeddings is None:
            return []

        query = np.array([gene.embedding], dtype=np.float32)

        # Convert similarity threshold to distance threshold
        # cosine_distance = 1 - cosine_similarity
        distance_threshold = 1.0 - similarity_threshold

        # Query ball tree for neighbors within distance threshold
        # k = min(max_results + 1, len(self._gene_ids)) to account for self-match
        k = min(max_results + 1, len(self._gene_ids))
        distances, indices = self._tree.query(query, k=k)

        # Convert back to similarities and filter
        results: list[tuple[str, float]] = []
        for dist, idx in zip(distances[0], indices[0]):
            similarity = 1.0 - dist
            if similarity >= similarity_threshold:
                gene_id = self._gene_ids[idx]
                # Skip self-match
                if gene_id != gene.id:
                    results.append((gene_id, float(similarity)))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:max_results]

    def is_available(self) -> bool:
        """Check if spatial index is available (sklearn installed)."""
        return self._tree is not None

from __future__ import annotations

import math
from collections import Counter

from .embedding import tokenize
from ..core.models import MemorySegment, SparseIndexEntry


class SparseIndex:
    """BM25-like keyword index for exact technical retrieval."""

    def __init__(self, entries: dict[str, SparseIndexEntry] | None = None):
        self.entries: dict[str, SparseIndexEntry] = entries or {}
        self._doc_freq: dict[str, int] = {}
        self._avg_len = 0.0
        self._recompute_stats()

    def rebuild(self, segments: dict[str, MemorySegment]) -> None:
        self.entries = {
            segment_id: SparseIndexEntry(
                segment_id=segment_id,
                terms=dict(Counter(tokenize(sparse_text(segment)))),
                length=max(1, len(tokenize(sparse_text(segment)))),
            )
            for segment_id, segment in segments.items()
        }
        self._recompute_stats()

    def upsert(self, segment: MemorySegment) -> None:
        terms = Counter(tokenize(sparse_text(segment)))
        self.entries[segment.id] = SparseIndexEntry(
            segment_id=segment.id,
            terms=dict(terms),
            length=max(1, sum(terms.values())),
        )
        self._recompute_stats()

    def remove(self, segment_id: str) -> None:
        if segment_id in self.entries:
            del self.entries[segment_id]
            self._recompute_stats()

    def search(self, query: str, k: int) -> list[tuple[str, float, int]]:
        query_terms = tokenize(query)
        if not query_terms:
            return []
        scored = []
        for segment_id, entry in self.entries.items():
            score = self._bm25(query_terms, entry)
            exact = sum(1 for term in query_terms if term in entry.terms)
            if score > 0 or exact:
                scored.append((segment_id, score, exact))
        scored.sort(reverse=True, key=lambda item: (item[2], item[1]))
        return scored[: max(0, k)]

    def to_dict(self) -> dict[str, dict]:
        return {segment_id: entry.to_dict() for segment_id, entry in sorted(self.entries.items())}

    @classmethod
    def from_dict(cls, data: dict[str, dict]) -> "SparseIndex":
        return cls({segment_id: SparseIndexEntry.from_dict(item) for segment_id, item in data.items()})

    @property
    def size(self) -> int:
        return len(self.entries)

    def _bm25(self, query_terms: list[str], entry: SparseIndexEntry) -> float:
        k1 = 1.5
        b = 0.75
        score = 0.0
        total_docs = max(1, len(self.entries))
        avg_len = max(1.0, self._avg_len)
        for term in query_terms:
            freq = entry.terms.get(term, 0)
            if freq == 0:
                continue
            doc_freq = self._doc_freq.get(term, 0)
            idf = math.log(1.0 + (total_docs - doc_freq + 0.5) / (doc_freq + 0.5))
            denom = freq + k1 * (1.0 - b + b * entry.length / avg_len)
            score += idf * (freq * (k1 + 1.0)) / denom
        return score

    def _recompute_stats(self) -> None:
        self._doc_freq = {}
        total_len = 0
        for entry in self.entries.values():
            total_len += entry.length
            for term in entry.terms:
                self._doc_freq[term] = self._doc_freq.get(term, 0) + 1
        self._avg_len = total_len / len(self.entries) if self.entries else 0.0


def sparse_text(segment: MemorySegment) -> str:
    path = " ".join(segment.category_path)
    metadata = " ".join(str(value) for value in segment.metadata.values())
    return f"{path}\n{segment.description}\n{metadata}\n{segment.text}"

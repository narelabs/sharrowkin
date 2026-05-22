"""Lazy-loading wrapper for DSM segments."""

from typing import Any, Callable
from ..dsm.core.models import MemorySegment


class LazySegment:
    """Lazy-loading proxy for MemorySegment.

    Only loads full segment data when accessed, keeping memory footprint low.
    """

    def __init__(self, segment_id: str, loader: Callable[[str], MemorySegment]):
        self._id = segment_id
        self._loader = loader
        self._segment: MemorySegment | None = None
        self._loaded = False

    def _ensure_loaded(self) -> None:
        """Load segment on first access."""
        if not self._loaded:
            self._segment = self._loader(self._id)
            self._loaded = True

    @property
    def id(self) -> str:
        """ID is always available without loading."""
        return self._id

    @property
    def embedding(self) -> list[float]:
        """Embedding is always available without loading full text."""
        self._ensure_loaded()
        return self._segment.embedding

    @property
    def text(self) -> str:
        """Text requires full load."""
        self._ensure_loaded()
        return self._segment.text

    @property
    def description(self) -> str:
        """Description requires full load."""
        self._ensure_loaded()
        return self._segment.description

    @property
    def category_path(self) -> tuple[str, ...]:
        """Category path requires full load."""
        self._ensure_loaded()
        return self._segment.category_path

    @property
    def priorities(self) -> Any:
        """Priorities require full load."""
        self._ensure_loaded()
        return self._segment.priorities

    @property
    def metadata(self) -> dict[str, Any]:
        """Metadata requires full load."""
        self._ensure_loaded()
        return self._segment.metadata

    def __getattr__(self, name: str) -> Any:
        """Fallback for any other attributes."""
        self._ensure_loaded()
        return getattr(self._segment, name)

    def is_loaded(self) -> bool:
        """Check if segment is loaded."""
        return self._loaded

    def unload(self) -> None:
        """Unload segment to free memory."""
        self._segment = None
        self._loaded = False


class LazySegmentCache:
    """Cache for lazy-loaded segments with LRU eviction."""

    def __init__(self, max_loaded: int = 100):
        self.max_loaded = max_loaded
        self.segments: dict[str, LazySegment] = {}
        self.access_order: list[str] = []

    def get(self, segment_id: str, loader: Callable[[str], MemorySegment]) -> LazySegment:
        """Get or create lazy segment."""
        if segment_id not in self.segments:
            self.segments[segment_id] = LazySegment(segment_id, loader)

        # Track access for LRU
        if segment_id in self.access_order:
            self.access_order.remove(segment_id)
        self.access_order.append(segment_id)

        # Evict oldest if over limit
        self._evict_if_needed()

        return self.segments[segment_id]

    def _evict_if_needed(self) -> None:
        """Evict least recently used loaded segments."""
        loaded_count = sum(1 for seg in self.segments.values() if seg.is_loaded())

        while loaded_count > self.max_loaded and self.access_order:
            # Find oldest loaded segment
            for segment_id in self.access_order:
                segment = self.segments.get(segment_id)
                if segment and segment.is_loaded():
                    segment.unload()
                    loaded_count -= 1
                    break

    def clear(self) -> None:
        """Clear all segments."""
        self.segments.clear()
        self.access_order.clear()

    def get_stats(self) -> dict[str, int]:
        """Get cache statistics."""
        loaded = sum(1 for seg in self.segments.values() if seg.is_loaded())
        return {
            "total_segments": len(self.segments),
            "loaded_segments": loaded,
            "unloaded_segments": len(self.segments) - loaded,
        }

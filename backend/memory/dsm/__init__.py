"""Dynamic Segmented Memory public API.

Restructured for clarity:
- core/ - Main memory logic and models
- indexing/ - Category tree, vector index, embeddings
- retrieval/ - Hybrid search and semantic graph
- storage/ - Document and memory storage
- utils/ - Thermodynamics and visualization
"""

# Core exports
from .core.memory import DynamicSegmentedMemory
from .core.models import (
    ActiveContext,
    MemorySegment,
    PriorityVector,
    ReasoningTrace,
    RouteResult,
)

# Indexing exports
from .indexing.embedding import HashEmbeddingModel
from .indexing.category import CategoryTree
from .indexing.index import SegmentIndex

# Retrieval exports
from .retrieval.graph import MemoryGraph

__all__ = [
    # Core
    "ActiveContext",
    "DynamicSegmentedMemory",
    "MemorySegment",
    "PriorityVector",
    "ReasoningTrace",
    "RouteResult",
    # Indexing
    "CategoryTree",
    "HashEmbeddingModel",
    "SegmentIndex",
    # Retrieval
    "MemoryGraph",
]

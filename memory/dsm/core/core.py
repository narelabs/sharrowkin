import uuid
import time
from typing import List, Dict, Tuple, Any, Optional

from .schema import MemorySegment
from ..retrieval.hybrid_search import HybridSearchEngine, SparseSearchEngine
from ..utils.thermodynamics import DSMThermodynamics

class DynamicSegmentedMemory:
    """
    The Core Facade for DSM 3.0.
    Integrates schemas, hybrid search, and thermodynamics.
    """
    def __init__(self, rrf_k: int = 60, decay_rate: float = 0.01, eviction_threshold: float = 0.1):
        # In-memory Hot Storage
        self.hot_memory: Dict[str, MemorySegment] = {}
        # Cold Storage (Archived segments)
        self.cold_memory: Dict[str, MemorySegment] = {}
        
        self.search_engine = HybridSearchEngine(rrf_k=rrf_k)
        self.sparse_engine = SparseSearchEngine()
        self.thermodynamics = DSMThermodynamics(decay_rate=decay_rate, eviction_threshold=eviction_threshold)

    def add_memory(self, content: str, dense_vector: List[float] = None, sparse_vector: Dict[str, float] = None, metadata: Dict[str, Any] = None) -> str:
        """
        Adds a new segment to Hot Memory and indexes it for lexical search.
        """
        seg_id = str(uuid.uuid4())
        segment = MemorySegment(
            id=seg_id,
            content=content,
            dense_vector=dense_vector,
            sparse_vector=sparse_vector,
            metadata=metadata or {}
        )
        self.hot_memory[seg_id] = segment
        
        # Индексируем для точного поиска по словам
        self.sparse_engine.index_segment(segment)
        
        return seg_id

    def search(self, query: str, query_dense: List[float] = None, top_k: int = 5) -> List[Tuple[MemorySegment, float]]:
        """
        Performs a hybrid search (Dense + Sparse) combined with Heat physics.
        """
        # 1. Точный лексический поиск (BM25)
        sparse_results = self.sparse_engine.search(query)
        
        # 2. Семантический поиск (имитация, пока нет внешней Vector DB)
        dense_results = []
        if query_dense:
            # Если есть вектор запроса, имитируем поиск
            for seg_id in self.hot_memory.keys():
                dense_results.append((seg_id, 0.5))
        else:
            # Если вектора нет, семантический поиск дает 0
            dense_results = [(sid, 0.0) for sid in self.hot_memory.keys()]
            
        # Rank the candidates using Hybrid Search + Thermodynamics
        ranked_segments = self.search_engine.rank_segments(
            dense_results=dense_results,
            sparse_results=sparse_results,
            segments_db=self.hot_memory
        )
        
        # Reheat accessed segments (Consolidation)
        top_segments = ranked_segments[:top_k]
        for segment, score in top_segments:
            self.thermodynamics.reheat(segment)
            
        return top_segments

    def maintenance_loop(self) -> int:
        """
        Runs the thermodynamics engine to decay heat and evict cold segments.
        Returns the number of segments evicted.
        """
        evicted_ids = self.thermodynamics.apply_decay(self.hot_memory)
        
        for seg_id in evicted_ids:
            # Move from Hot to Cold storage
            self.cold_memory[seg_id] = self.hot_memory.pop(seg_id)
            
        return len(evicted_ids)

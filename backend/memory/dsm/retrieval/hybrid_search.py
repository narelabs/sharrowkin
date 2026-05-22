import math
import re
from typing import List, Dict, Tuple, Set
from ..core.schema import MemorySegment

def tokenize(text: str) -> List[str]:
    """Tokenizer that splits text into alphanumeric tokens, handling snake_case and delimiters."""
    # Разделяем по всему, что не является буквой или цифрой
    return [t for t in re.split(r'[^a-z0-9]+', text.lower()) if t]

class SparseSearchEngine:
    """
    A lightweight BM25-like search engine for lexical retrieval in DSM.
    """
    def __init__(self):
        self.index: Dict[str, Set[str]] = {}  # word -> set of segment IDs
        self.doc_lengths: Dict[str, int] = {} # segment ID -> word count
        self.segments: Dict[str, MemorySegment] = {}
        self.avg_dl = 0.0

    def index_segment(self, segment: MemorySegment):
        """Adds a segment to the lexical index."""
        tokens = tokenize(segment.content)
        self.doc_lengths[segment.id] = len(tokens)
        self.segments[segment.id] = segment
        
        unique_tokens = set(tokens)
        for token in unique_tokens:
            if token not in self.index:
                self.index[token] = set()
            self.index[token].add(segment.id)
            
        # Update average document length
        self.avg_dl = sum(self.doc_lengths.values()) / len(self.doc_lengths)

    def search(self, query: str) -> List[Tuple[str, float]]:
        """
        Performs lexical search using a simplified BM25 scoring.
        Returns a list of (segment_id, score) sorted by score.
        """
        query_tokens = tokenize(query)
        scores: Dict[str, float] = {}
        
        k1 = 1.5
        b = 0.75
        N = len(self.doc_lengths)
        
        for token in query_tokens:
            if token not in self.index:
                continue
                
            # Inverse Document Frequency
            n_q = len(self.index[token])
            idf = math.log((N - n_q + 0.5) / (n_q + 0.5) + 1.0)
            
            for seg_id in self.index[token]:
                # Term Frequency in document
                content = self.segments[seg_id].content.lower()
                tf = content.count(token)
                
                # BM25 Formula
                dl = self.doc_lengths[seg_id]
                score = idf * (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * (dl / self.avg_dl)))
                scores[seg_id] = scores.get(seg_id, 0.0) + score
                
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

def compute_rrf(dense_ranks: Dict[str, int], sparse_ranks: Dict[str, int], k: int = 60) -> Dict[str, float]:
    """
    Computes Reciprocal Rank Fusion (RRF) scores.
    Args:
        dense_ranks: Dictionary mapping segment ID to its rank in dense search (1-indexed).
        sparse_ranks: Dictionary mapping segment ID to its rank in sparse search (1-indexed).
        k: Smoothing constant.
    Returns:
        Dictionary mapping segment ID to its RRF score.
    """
    rrf_scores: Dict[str, float] = {}
    
    # Collect all unique segment IDs
    all_ids = set(dense_ranks.keys()).union(set(sparse_ranks.keys()))
    
    for seg_id in all_ids:
        score = 0.0
        if seg_id in dense_ranks:
            score += 1.0 / (k + dense_ranks[seg_id])
        if seg_id in sparse_ranks:
            score += 1.0 / (k + sparse_ranks[seg_id])
        rrf_scores[seg_id] = score
        
    return rrf_scores

class HybridSearchEngine:
    """
    Engine to fuse Dense and Sparse retrieval results using RRF and apply Heat.
    """
    def __init__(self, rrf_k: int = 60):
        self.rrf_k = rrf_k
        
    def rank_segments(self, 
                      dense_results: List[Tuple[str, float]], 
                      sparse_results: List[Tuple[str, float]], 
                      segments_db: Dict[str, MemorySegment]) -> List[Tuple[MemorySegment, float]]:
        """
        Ranks segments based on Dense+Sparse RRF, multiplied by the segment's Heat.
        """
        # Фильтруем результаты с нулевым скором, чтобы они не получали ранги
        dense_filtered = [res for res in dense_results if res[1] > 0]
        sparse_filtered = [res for res in sparse_results if res[1] > 0]

        # 1. Convert lists to rank dictionaries (rank is index + 1)
        dense_ranks = {item[0]: i + 1 for i, item in enumerate(dense_filtered)}
        sparse_ranks = {item[0]: i + 1 for i, item in enumerate(sparse_filtered)}
        
        # 2. Compute RRF
        rrf_scores = compute_rrf(dense_ranks, sparse_ranks, k=self.rrf_k)
        
        # 3. Apply Heat Physics
        final_scores = []
        for seg_id, rrf_score in rrf_scores.items():
            if seg_id in segments_db:
                segment = segments_db[seg_id]
                # The core DSM Formula: Score = RRF * Heat
                final_score = rrf_score * segment.heat
                final_scores.append((segment, final_score))
                
        # 4. Sort by final score descending
        final_scores.sort(key=lambda x: x[1], reverse=True)
        return final_scores

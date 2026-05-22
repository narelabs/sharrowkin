from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time

class MemorySegment(BaseModel):
    """
    Core data structure for the Dynamic Segmented Memory (DSM).
    Represents an isolated chunk of memory with its own thermodynamic 'heat'.
    """
    id: str = Field(..., description="Unique identifier for the segment")
    content: str = Field(..., description="The raw text/code content of the memory")
    dense_vector: Optional[List[float]] = Field(default=None, description="Semantic dense embedding")
    sparse_vector: Optional[Dict[str, float]] = Field(default=None, description="Lexical sparse embedding (e.g., BM25)")
    heat: float = Field(default=1.0, description="Current activation energy/relevance (0.0 to 1.0)")
    last_accessed: float = Field(default_factory=time.time, description="Unix timestamp of last access/modification")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context (file path, logical parent, etc.)")

    def touch(self) -> None:
        """
        Reheats the segment and updates access time.
        Called when the segment is successfully retrieved and used.
        """
        self.heat = 1.0
        self.last_accessed = time.time()

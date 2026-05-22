import time
import math
from typing import Dict, List
from ..core.schema import MemorySegment

class DSMThermodynamics:
    """
    Handles the physics of forgetting in the DSM.
    Applies exponential decay to segment heat and manages eviction to cold storage.
    """
    def __init__(self, decay_rate: float = 0.01, eviction_threshold: float = 0.1):
        # decay_rate: Lambda (λ) in the exponential decay formula. Higher = faster forgetting.
        self.decay_rate = decay_rate
        # eviction_threshold: If heat falls below this, the segment is evicted.
        self.eviction_threshold = eviction_threshold
        
    def apply_decay(self, segments_db: Dict[str, MemorySegment], current_time: float = None) -> List[str]:
        """
        Applies exponential decay to all segments in the database based on time passed.
        Returns a list of segment IDs that should be evicted to cold storage.
        """
        if current_time is None:
            current_time = time.time()
            
        evicted_ids = []
        
        for seg_id, segment in segments_db.items():
            # Calculate time delta in hours (or preferred unit)
            # Defaulting to hours for a reasonable decay rate
            time_delta_seconds = current_time - segment.last_accessed
            time_delta_hours = time_delta_seconds / 3600.0
            
            if time_delta_hours > 0:
                # Calculate new heat: H_new = H_old * e^(-λ * Δt)
                decay_factor = math.exp(-self.decay_rate * time_delta_hours)
                segment.heat = segment.heat * decay_factor
                
                # We do NOT update last_accessed here, as it signifies the last *actual* interaction.
            
            if segment.heat < self.eviction_threshold:
                evicted_ids.append(seg_id)
                
        return evicted_ids
        
    def reheat(self, segment: MemorySegment) -> None:
        """
        Restores a segment's heat to maximum.
        """
        segment.touch()

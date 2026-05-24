"""MemoryField for Sharrowkin - Symbolic state transition memory.

✅ OPTIMIZED: Removed unused Hebbian W matrix (was 1.2 MB dead code).
Now only tracks symbolic phase transitions which are actually used.
"""

from __future__ import annotations

import json
from pathlib import Path

class MemoryField:
    """Symbolic MemoryField for tracking successful phase transitions.

    Maintains only the symbolic transition network for high-level state attractors.
    The dense Hebbian matrix W was removed as it was never read for predictions.
    """

    def __init__(self, filepath: Path, default_dim: int = 128) -> None:
        self.filepath = Path(filepath)
        self.symbolic_network: dict[str, float] = {}

        self.load()

    def load(self) -> None:
        """Load symbolic weights from disk."""
        if not self.filepath.exists():
            self._init_empty()
            return

        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.symbolic_network = data.get("symbolic_network", {})
        except Exception as e:
            print(f"[MemoryField] Error loading memory field, initializing empty: {e}")
            self._init_empty()

    def _init_empty(self) -> None:
        """Initialize default phase transitions."""
        self.symbolic_network = {
            "Observe -> Recall": 0.85,
            "Recall -> Reason": 0.75,
            "Reason -> Stabilize": 0.65,
            "Stabilize -> Commit": 0.80,
            "Stabilize -> Reason (Self-Healing)": 0.70
        }
        self.save()

    def save(self) -> None:
        """Save the MemoryField state to disk."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "symbolic_network": self.symbolic_network
                }, f, indent=2)
        except Exception as e:
            print(f"[MemoryField] Error saving memory field: {e}")

    def update_hebbian(self, z_start: list[float], z_end: list[float], decay: float = 0.95, eta: float = 0.05) -> None:
        """✅ DEPRECATED: Hebbian updates removed (W matrix was never used for predictions).

        This method is kept for backward compatibility but does nothing.
        Use update_symbolic() instead for phase transition learning.
        """
        pass  # No-op for backward compatibility

    def update_symbolic(self, state_from: str, state_to: str, success: bool, decay: float = 0.96, eta: float = 0.08) -> None:
        """Update attractor transition weight: weight = decay * weight + eta * (1.0 if success else -0.5)"""
        key = f"{state_from} -> {state_to}"
        current = self.symbolic_network.get(key, 0.1)
        delta = 1.0 if success else -0.5
        new_weight = max(0.0, min(1.0, decay * current + eta * delta))
        self.symbolic_network[key] = round(new_weight, 4)
        self.save()

    def get_top_associations(self, limit: int = 10) -> list[dict[str, object]]:
        """Get the sorted list of symbolic state transitions and their strengths."""
        sorted_links = sorted(self.symbolic_network.items(), key=lambda x: x[1], reverse=True)
        return [{"source": k.split(" -> ")[0], "target": k.split(" -> ")[1], "weight": w} for k, w in sorted_links[:limit]]

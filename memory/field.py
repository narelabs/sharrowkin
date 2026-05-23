"""MemoryField for Sharrowkin - Parametric Hebbian attractor memory."""

from __future__ import annotations

import json
from pathlib import Path
import math

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

class MemoryField:
    """Parametric MemoryField.
    
    Maintains a dense Hebbian associative weight matrix W for continuous latent states
    and a symbolic transition network for high-level state attractors.
    """
    
    def __init__(self, filepath: Path, default_dim: int = 128) -> None:
        self.filepath = Path(filepath)
        self.default_dim = default_dim
        self.dim = default_dim
        self.W: list[list[float]] = []
        self.symbolic_network: dict[str, float] = {}
        
        self.load()
        
    def load(self) -> None:
        """Load W and symbolic weights from disk."""
        if not self.filepath.exists():
            self._init_empty(self.default_dim)
            return
            
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.dim = data.get("dim", self.default_dim)
                self.W = data.get("W", [])
                self.symbolic_network = data.get("symbolic_network", {})
                
                # Validation of W matrix
                if len(self.W) != self.dim or any(len(row) != self.dim for row in self.W):
                    self._init_empty(self.dim)
        except Exception as e:
            print(f"[MemoryField] Error loading memory field, initializing empty: {e}")
            self._init_empty(self.default_dim)

    def _init_empty(self, dim: int) -> None:
        """Initialize an empty matrix W."""
        self.dim = dim
        self.W = [[0.0] * dim for _ in range(dim)]
        self.symbolic_network = {
            "Observe -> Recall": 0.85,
            "Recall -> Reason": 0.75,
            "Reason -> Stabilize": 0.65,
            "Stabilize -> Commit": 0.80,
            "Stabilize -> Reason (Self-Healing)": 0.70  # Increased from 0.30 to 0.70
        }
        self.save()

    def save(self) -> None:
        """Save the MemoryField state to disk."""
        try:
            self.filepath.parent.mkdir(parents=True, exist_ok=True)
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump({
                    "dim": self.dim,
                    "W": self.W,
                    "symbolic_network": self.symbolic_network
                }, f, indent=2)
        except Exception as e:
            print(f"[MemoryField] Error saving memory field: {e}")

    def update_hebbian(self, z_start: list[float], z_end: list[float], decay: float = 0.95, eta: float = 0.05) -> None:
        """Perform continuous Hebbian update: W = decay * W + eta * (dz * dz^T)"""
        if len(z_start) != len(z_end):
            return
            
        target_dim = len(z_start)
        if target_dim != self.dim or not self.W:
            self._init_empty(target_dim)
            
        # Compute dz = z_end - z_start
        dz = [z_end[i] - z_start[i] for i in range(target_dim)]
        
        # Unit normalization of dz
        sq_sum = sum(val * val for val in dz)
        magnitude = math.sqrt(sq_sum)
        if magnitude > 1e-6:
            dz = [val / magnitude for val in dz]
        else:
            dz = [0.0] * target_dim
            
        # Outer product and weight update
        if HAS_NUMPY:
            try:
                W_arr = np.array(self.W, dtype=float)
                dz_arr = np.array(dz, dtype=float)
                W_arr = decay * W_arr + eta * np.outer(dz_arr, dz_arr)
                self.W = W_arr.tolist()
            except Exception as e:
                print(f"[MemoryField] NumPy Hebbian update failed, falling back to pure Python: {e}")
                for i in range(self.dim):
                    for j in range(self.dim):
                        self.W[i][j] = decay * self.W[i][j] + eta * (dz[i] * dz[j])
        else:
            for i in range(self.dim):
                for j in range(self.dim):
                    self.W[i][j] = decay * self.W[i][j] + eta * (dz[i] * dz[j])
                
        self.save()

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

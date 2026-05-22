from __future__ import annotations
import sys
import torch
from pathlib import Path
from typing import Optional, Any

# Импортируем наше ядро
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "modules" / "dsm" / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "modules" / "nare_field" / "src"))

from narefield.core.model import NAREFieldModel, NAREConfig
from dsm.memory import DynamicSegmentedMemory

class FieldScript:
    """
    FieldScript Engine: Прототип языка для ИИ-разрабов.
    """
    def __init__(self, dim: int = 512):
        self.config = NAREConfig(dim=dim)
        self.model = NAREFieldModel(self.config)
        self.memory = DynamicSegmentedMemory(storage_path=".dsm/script_memory.json")
        self.context = None

    def observe(self, data: Any):
        """Фаза наблюдения."""
        if isinstance(data, str):
            self.context = torch.randn(1, self.config.dim)
        else:
            self.context = data
        print(f"[OBSERVE] State encoded with dim {self.config.dim}")
        return self

    def reason(self, depth: int = 3):
        """Фаза рассуждения."""
        print(f"[REASON] Depth {depth}...")
        result = self.model(self.context)
        self.context = result.latent
        self.last_result = result
        return self

    def recall(self, query: str):
        """Фаза извлечения."""
        print(f"[RECALL] Query: '{query}'")
        segments = self.memory.route(query, k=1)
        if segments:
            print(f"[RECALL] Found: {segments[0].segment.description}")
        return self

    def stabilize(self):
        """Фаза фиксации инвариантов."""
        energy = self.last_result.loss.total.item()
        print(f"[STABILIZE] Energy = {energy:.4f}")
        if energy < 0.5:
            print("[STABILIZE] State is stable.")
        else:
            print("[STABILIZE] State is volatile!")
        return self

    def commit(self, info: str):
        """Запись в долгосрочную память."""
        self.memory.write(info, importance=0.8)
        self.memory.save()
        print(f"[COMMIT] Field updated: {info[:30]}...")
        return self

if __name__ == "__main__":
    with torch.no_grad():
        fs = FieldScript()
        (fs.observe("Field Test")
           .reason()
           .stabilize()
           .commit("Test success"))

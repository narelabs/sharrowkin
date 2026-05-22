from __future__ import annotations

from dataclasses import dataclass

import torch
from torch import nn

from dsm import DynamicSegmentedMemory
from dsm.embedding import normalize
from dsm.models import RouteResult


@dataclass(slots=True)
class NAREFieldConfig:
    dsm_dim: int
    residual_dim: int
    k: int = 4
    cognitive_temperature: float = 0.35
    rhythm_decay: float = 0.95
    vision_dim: int = 768 # Default for SigLIP base


class NAREField(nn.Module):
    """DSM attractor field coupled to a model residual stream."""

    def __init__(self, memory: DynamicSegmentedMemory, config: NAREFieldConfig):
        super().__init__()
        if memory.embedding_model.dim != config.dsm_dim:
            raise ValueError("DSM embedding dimension and field config dsm_dim must match")
        self.memory = memory
        self.config = config
        self.query_bridge = nn.Linear(config.residual_dim, config.dsm_dim, bias=False)
        self.attractor_bridge = nn.Linear(config.dsm_dim, config.residual_dim, bias=False)
        self.vision_bridge = nn.Linear(config.vision_dim, config.dsm_dim, bias=False)
        self.gate = nn.Parameter(torch.tensor(float(config.cognitive_temperature)))
        self.last_routes: list[RouteResult | str] = []
        self.last_attractor: torch.Tensor | None = None
        self.last_delta_val: float = 0.0
        self.last_h: torch.Tensor | None = None
        
        # Latent Memory Bank (The "Internal Brain")
        self.memory_bank = None # Will be initialized during baking
        self.memory_metadata = [] # To keep track of what's inside
        
        # Symbiotic Rhythm State
        self.rhythm = nn.Parameter(torch.tensor(0.5))
        self.rhythm_ref = 0.0 # Rolling baseline

    def retrieve(self, hidden_state: torch.Tensor) -> tuple[torch.Tensor, list[RouteResult]]:
        query_vector = self.hidden_to_dsm_vector(hidden_state)
        routes = self.memory.route_by_vector(query_vector, k=self.config.k)
        if not routes:
            attractor = torch.zeros(
                self.config.dsm_dim,
                dtype=hidden_state.dtype,
                device=hidden_state.device,
            )
            return attractor, routes

        embeddings = torch.tensor(
            [route.segment.embedding for route in routes],
            dtype=hidden_state.dtype,
            device=hidden_state.device,
        )
        scores = torch.tensor(
            [route.total_score for route in routes],
            dtype=hidden_state.dtype,
            device=hidden_state.device,
        )
        weights = torch.softmax(scores, dim=0)
        return torch.sum(weights.unsqueeze(-1) * embeddings, dim=0), routes

    def native_retrieve(self, hidden_state: torch.Tensor) -> torch.Tensor:
        """
        High-speed retrieval directly from the internal weight bank.
        Returns the blended attractor and populates self.last_routes with recalled text.
        """
        if self.memory_bank is None:
            return torch.zeros(self.config.dsm_dim, device=hidden_state.device)
            
        query_vector = self.hidden_to_dsm_vector(hidden_state)
        query_tensor = torch.tensor(query_vector, device=self.memory_bank.device).float()
        
        # Neural Similarity Scan
        similarities = torch.matmul(self.memory_bank, query_tensor)
        weights = torch.softmax(similarities / 0.1, dim=0) 
        
        # Recall Top-K textual segments for the prompt
        topk_scores, topk_indices = torch.topk(similarities, k=min(self.config.k, len(self.memory_metadata)), dim=0)
        recalled_text = [self.memory_metadata[idx] for idx in topk_indices.tolist()]
        # We simulate RouteResult for compatibility with the main loop's print/prompt logic
        self.last_routes = recalled_text # Store the raw text for now
        
        attractor = torch.sum(weights.unsqueeze(-1) * self.memory_bank, dim=0)
        return attractor

    def bake_memory(self):
        """
        Transfers the external DSM content into the internal neural bank.
        """
        print(f"[NARE-Field] Initiating Latent Brain Bake...")
        # Accessing the underlying segments dictionary directly
        all_segments = list(self.memory.segments.values())
        if not all_segments:
            print("[NARE-Field] Warning: No segments found in DSM to bake.")
            return

        embeddings = [s.embedding for s in all_segments]
        self.memory_bank = nn.Parameter(torch.tensor(embeddings).float())
        self.memory_metadata = [s.text for s in all_segments]
        print(f"[NARE-Field] Baked {len(all_segments)} segments into latent weights.")

    def forward(
        self, 
        hidden_state: torch.Tensor, 
        visual_features: torch.Tensor | None = None
    ) -> torch.Tensor:
        """
        Multimodal Forward Pass with Delta-Complexity.
        Blends textual and visual context into a single cognitive attractor.
        """
        # O(∇) DELTA-COMPLEXITY CALCULATION
        # Calculate semantic surprise relative to last state
        if self.last_h is not None:
            with torch.no_grad():
                h_flat = hidden_state.view(-1).float()
                lh_flat = self.last_h.view(-1).float()
                # Cosine distance as Surprise (Delta)
                cos_sim = torch.nn.functional.cosine_similarity(h_flat, lh_flat, dim=0)
                surprise = 1.0 - cos_sim.item()
                self.last_delta_val = max(0.0, surprise)
        else:
            self.last_delta_val = 0.5 # Initial wake-up
            
        self.last_h = hidden_state.detach()

        # 1. Textual Attractor
        if self.memory_bank is not None:
            text_attractor = self.native_retrieve(hidden_state)
        else:
            text_attractor, routes = self.retrieve(hidden_state)
            self.last_routes = routes
            
        # 2. Visual Attractor (If Eye is active)
        if visual_features is not None:
            # Ensure it's a tensor and on correct device
            v_tensor = visual_features[0] if not torch.is_tensor(visual_features) else visual_features
            visual_attractor = self.vision_bridge(v_tensor.float().to(self.device))
            # Cross-modal blend
            attractor = (text_attractor + visual_attractor) / 2.0
        else:
            attractor = text_attractor
            
        self.last_attractor = attractor.detach()
        delta_vec = self.attractor_bridge(attractor).view(*([1] * (hidden_state.ndim - 1)), -1)
        
        # Surprise-Driven Throttling (Wake-up Cascade)
        # Higher surprise -> Higher activation
        activation = torch.clamp(torch.tensor(self.last_delta_val * 2.0).to(hidden_state.device), 0.1, 1.0)
        
        # Dynamic Rhythmic Gating
        rhythm_factor = torch.sigmoid(self.rhythm * 2.0)
        gate = torch.clamp(self.gate * rhythm_factor * activation, 0.0, 1.0)
        
        return hidden_state + gate * delta_vec

    def hidden_to_dsm_vector(self, hidden_state: torch.Tensor) -> list[float]:
        pooled = hidden_state
        while pooled.ndim > 1:
            pooled = pooled.mean(dim=0)
        projected = self.query_bridge(pooled.detach().float())
        return normalize(projected.cpu().tolist())

    def apply_plasticity(self, learning_rate: float = 0.01):
        """
        Hebbian-style update for the neural bridges.
        Strengthens the connection between the last hidden state and the retrieved attractor.
        """
        if self.last_attractor is None or self.last_delta is None:
            return

        with torch.no_grad():
            # We adjust the gate based on the 'energy' of the interaction
            # Higher energy = more plastic change
            energy = torch.norm(self.last_delta).item()
            update_scale = learning_rate * energy
            
            # 1. Update the gate (Cognitive Temperature)
            self.gate.data += update_scale * 0.1
            self.gate.data = torch.clamp(self.gate.data, 0.0, 1.0)
            
            # 2. Hebbian update for the bridges (simplified)
            self.attractor_bridge.weight.data += update_scale * 0.05
            
            # 3. Evolve the Symbiotic Rhythm
            # Rhythm increases with energy, then decays
            self.rhythm.data = self.rhythm.data * self.config.rhythm_decay + update_scale
            self.rhythm_ref = 0.9 * self.rhythm_ref + 0.1 * energy
            
        return energy

    @property
    def current_rhythm(self) -> float:
        return self.rhythm.item()

    def add_logic_gene(
        self,
        text: str,
        vector: list[float],
        *,
        category_path: tuple[str, ...] = ("Attractors", "LogicGenes"),
    ) -> str:
        segment = self.memory.write_attractor(
            text,
            vector,
            category_path=category_path,
            importance=1.0,
            metadata={"nare_field": True, "logic_gene": True},
        )
        return segment.id

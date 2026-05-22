"""
RLD-Anthill Hybrid Core
Integrates Recursive Latent DNA with Anthill Expert Routing.
"""
import torch
import torch.nn as nn
from typing import List, Dict, Any
from .core import RecursiveLatentDNA, ActivatedGene
from narefield.core.routing import AnthillLayer, AnthillRouterConfig

class RLDAnthillBridge(nn.Module):
    """
    Bridge between RLD Knowledge and Anthill Expert Layer.
    Translates activated genes into expert weights for latent injection.
    """
    def __init__(self, rld: RecursiveLatentDNA, config: AnthillRouterConfig):
        super().__init__()
        self.rld = rld
        self.config = config
        # The Anthill Layer that will actually transform the hidden states
        self.anthill = AnthillLayer.identity(config)
        
    def forward(self, hidden_states: torch.Tensor, query_text: str) -> torch.Tensor:
        """
        1. Activate genes from RLD based on current context.
        2. Map genes to experts.
        3. Apply Anthill transformation to hidden_states.
        """
        # Activate genes (latent discovery)
        activated = self.rld.activate(query_text, top_k=self.config.top_k)
        
        if not activated:
            return hidden_states # No guidance found, proceed as normal

        # Map each activated gene to an expert index
        # For now, we use a simple mapping: gene_hash % num_experts
        # In the future, this will be a learned mapping.
        expert_weights = torch.zeros(self.config.num_experts, device=hidden_states.device)
        for ag in activated:
            expert_idx = hash(ag.gene.id) % self.config.num_experts
            expert_weights[expert_idx] = ag.probability

        # Apply expert-weighted transformation
        # This bypasses the internal router of AnthillLayer and uses RLD guidance instead
        output = torch.zeros_like(hidden_states)
        for idx, weight in enumerate(expert_weights):
            if weight > 0:
                output += weight * self.experts[idx](hidden_states)
        
        return output

    @property
    def experts(self):
        return self.anthill.experts

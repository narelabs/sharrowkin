from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import nn


class PredictionEnergyLoss(nn.Module):
    """Energy loss between predicted latent trajectory and target logic state."""

    def forward(self, prediction: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
        return F.mse_loss(prediction, target)


class CognitiveInvariant(nn.Module):
    """Keeps fixed latent coordinates stable during attractor injection."""

    def __init__(self, mask: torch.Tensor, weight: float = 1.0):
        super().__init__()
        self.register_buffer("mask", mask.float())
        self.weight = float(weight)

    def forward(self, before: torch.Tensor, after: torch.Tensor) -> torch.Tensor:
        mask = self.mask.to(device=before.device, dtype=before.dtype)
        while mask.ndim < before.ndim:
            mask = mask.unsqueeze(0)
        return self.weight * F.mse_loss(after * mask, before * mask)

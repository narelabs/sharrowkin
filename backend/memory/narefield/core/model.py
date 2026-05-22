from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import torch
from torch import nn

from narefield.core.field import NAREField


class LatentObserver:
    """Forward hook that captures latent residual states."""

    def __init__(self, layer: nn.Module):
        self.layer = layer
        self.hidden_state: torch.Tensor | None = None
        self.handle = layer.register_forward_hook(self._capture)

    def close(self) -> None:
        self.handle.remove()

    def _capture(self, module: nn.Module, inputs: tuple[object, ...], output: object) -> None:
        tensor = output[0] if isinstance(output, tuple) else output
        if not isinstance(tensor, torch.Tensor):
            raise TypeError("LatentObserver can only capture tensor outputs")
        self.hidden_state = tensor.detach()


@dataclass(slots=True)
class NAREFieldAdapter:
    model: nn.Module
    field: NAREField
    layer_path: str
    layer: nn.Module | None = None
    observer: LatentObserver | None = None
    handle: object | None = None

    def __post_init__(self) -> None:
        self.layer = resolve_module(self.model, self.layer_path)
        self.observer = LatentObserver(self.layer)
        self.handle = self.layer.register_forward_hook(self._inject)

    def close(self) -> None:
        if self.handle is not None:
            self.handle.remove()
        if self.observer is not None:
            self.observer.close()

    def _inject(self, module: nn.Module, inputs: tuple[object, ...], output: object) -> object:
        if isinstance(output, tuple):
            hidden = output[0]
            if not isinstance(hidden, torch.Tensor):
                raise TypeError("NARE-Field injection requires tensor hidden state")
            return (self.field(hidden), *output[1:])
        if not isinstance(output, torch.Tensor):
            raise TypeError("NARE-Field injection requires tensor hidden state")
        return self.field(output)


def resolve_module(model: nn.Module, path: str) -> nn.Module:
    if not path:
        return model
    modules = dict(model.named_modules())
    if path not in modules:
        raise KeyError(f"module path not found: {path}")
    return modules[path]


class LayerStackModel(nn.Module):
    def __init__(self, layers: Sequence[nn.Module]):
        super().__init__()
        self.layers = nn.ModuleList(layers)

    def forward(self, hidden_state: torch.Tensor) -> torch.Tensor:
        h = hidden_state
        for layer in self.layers:
            h = layer(h)
        return h

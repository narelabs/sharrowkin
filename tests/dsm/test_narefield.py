from __future__ import annotations

import torch
from torch import nn

from dsm import DynamicSegmentedMemory
from narefield import CognitiveInvariant, NAREField, NAREFieldAdapter, NAREFieldConfig
from narefield.core.model import LayerStackModel


def test_narefield_retrieves_dsm_attractor_and_injects_delta() -> None:
    torch.manual_seed(7)
    memory = DynamicSegmentedMemory()
    config = NAREFieldConfig(dsm_dim=memory.embedding_model.dim, residual_dim=4, k=1)
    field = NAREField(memory, config)

    with torch.no_grad():
        field.query_bridge.weight.zero_()
        field.query_bridge.weight[0, 0] = 1.0
        field.attractor_bridge.weight.zero_()
        field.attractor_bridge.weight[0, 0] = 1.0
        field.gate.fill_(1.0)

    gene = [0.0] * memory.embedding_model.dim
    gene[0] = 1.0
    segment_id = field.add_logic_gene("Logic Gene: use reconstruction loss path.", gene)
    hidden = torch.tensor([[1.0, 0.0, 0.0, 0.0]])

    shifted = field(hidden)

    assert field.last_routes
    assert field.last_routes[0].segment.id == segment_id
    assert shifted[0, 0] > hidden[0, 0]


def test_adapter_hooks_layer_and_recovers_reasoning_path() -> None:
    torch.manual_seed(11)
    memory = DynamicSegmentedMemory()
    config = NAREFieldConfig(dsm_dim=memory.embedding_model.dim, residual_dim=3, k=1)
    field = NAREField(memory, config)
    model = LayerStackModel([nn.Identity(), nn.Linear(3, 1, bias=False)])

    with torch.no_grad():
        model.layers[1].weight.copy_(torch.tensor([[0.0, 1.0, 0.0]]))
        field.query_bridge.weight.zero_()
        field.query_bridge.weight[0, 0] = 1.0
        field.attractor_bridge.weight.zero_()
        field.attractor_bridge.weight[1, 0] = 2.2
        field.gate.fill_(1.0)

    gene = [0.0] * memory.embedding_model.dim
    gene[0] = 1.0
    field.add_logic_gene("Logic Gene: shift failed query toward y-axis reasoning.", gene)
    adapter = NAREFieldAdapter(model, field, "layers.0")

    failed_input = torch.tensor([[1.0, 0.0, 0.0]])
    recovered = model(failed_input)
    adapter.close()

    assert recovered.item() > 1.5
    assert adapter.observer.hidden_state is not None


def test_prediction_energy_and_cognitive_invariant() -> None:
    before = torch.tensor([[1.0, 2.0, 3.0]])
    after = torch.tensor([[1.0, 5.0, 3.0]])
    target = torch.tensor([[1.0, 6.0, 3.0]])
    energy = torch.nn.functional.mse_loss(after, target)
    invariant = CognitiveInvariant(torch.tensor([1.0, 0.0, 1.0]))

    assert energy < torch.nn.functional.mse_loss(before, target)
    assert invariant(before, after).item() == 0.0

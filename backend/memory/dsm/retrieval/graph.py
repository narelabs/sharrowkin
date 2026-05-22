from __future__ import annotations

import heapq

from ..core.models import GraphEdge


class MemoryGraph:
    """Undirected semantic graph between memory segments."""

    def __init__(self, edges: dict[str, dict[str, GraphEdge]] | None = None):
        self.edges: dict[str, dict[str, GraphEdge]] = edges or {}

    def add_node(self, node_id: str) -> None:
        self.edges.setdefault(node_id, {})

    def add_edge(
        self,
        left: str,
        right: str,
        *,
        relation: str = "semantic",
        weight: float = 1.0,
        reason: str = "",
    ) -> None:
        if left == right:
            return
        self.add_node(left)
        self.add_node(right)
        self._upsert(left, right, relation, weight, reason)
        self._upsert(right, left, relation, weight, reason)

    def remove_node(self, node_id: str) -> None:
        neighbors = set(self.edges.pop(node_id, {}))
        for neighbor in neighbors:
            if neighbor in self.edges:
                self.edges[neighbor].pop(node_id, None)

    def neighbors(self, node_id: str) -> set[str]:
        return set(self.edges.get(node_id, {}))

    def edge(self, left: str, right: str) -> GraphEdge | None:
        return self.edges.get(left, {}).get(right)

    def expand(self, seed_ids: list[str], max_hops: int = 2, limit: int = 32) -> dict[str, int]:
        return {node_id: distance for node_id, (distance, _) in self.expand_weighted(seed_ids, max_hops, limit).items()}

    def expand_weighted(
        self,
        seed_ids: list[str],
        max_hops: int = 2,
        limit: int = 32,
    ) -> dict[str, tuple[int, float]]:
        distances: dict[str, int] = {}
        weights: dict[str, float] = {}
        heap: list[tuple[float, int, str]] = [(-1.0, 0, seed) for seed in seed_ids]
        heapq.heapify(heap)

        while heap and len(distances) < limit:
            neg_weight, distance, node_id = heapq.heappop(heap)
            path_weight = -neg_weight
            if node_id in distances or distance > max_hops:
                continue
            distances[node_id] = distance
            weights[node_id] = path_weight
            if distance == max_hops:
                continue
            for neighbor, edge in sorted(self.edges.get(node_id, {}).items()):
                if neighbor not in distances:
                    heapq.heappush(heap, (-(path_weight * edge.weight), distance + 1, neighbor))

        return {node_id: (distances[node_id], weights[node_id]) for node_id in distances}

    def to_dict(self) -> dict[str, list[dict]]:
        return {
            node_id: [edge.to_dict() for edge in sorted(neighbors.values(), key=lambda item: item.target_id)]
            for node_id, neighbors in sorted(self.edges.items())
        }

    @classmethod
    def from_dict(cls, data: dict[str, list[dict] | list[str]]) -> "MemoryGraph":
        graph = cls()
        for node_id, neighbors in data.items():
            graph.add_node(str(node_id))
            for item in neighbors:
                if isinstance(item, str):
                    graph.add_edge(str(node_id), item)
                else:
                    edge = GraphEdge.from_dict(item)
                    graph.edges[str(node_id)][edge.target_id] = edge
        return graph

    def _upsert(self, left: str, right: str, relation: str, weight: float, reason: str) -> None:
        weight = min(1.0, max(0.0, weight))
        existing = self.edges[left].get(right)
        if existing:
            existing.strengthen(weight, reason)
            if relation not in existing.relation:
                existing.relation = f"{existing.relation}+{relation}"
            return
        self.edges[left][right] = GraphEdge(
            target_id=right,
            relation=relation,
            weight=weight,
            reason=reason,
        )

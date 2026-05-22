from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def now_ts() -> float:
    return time.time()


@dataclass(slots=True)
class SparseIndexEntry:
    segment_id: str
    terms: dict[str, int]
    length: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "segment_id": self.segment_id,
            "terms": self.terms,
            "length": self.length,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SparseIndexEntry":
        return cls(
            segment_id=str(data["segment_id"]),
            terms={str(term): int(count) for term, count in data.get("terms", {}).items()},
            length=int(data.get("length", 0)),
        )


@dataclass(slots=True)
class GraphEdge:
    target_id: str
    relation: str = "semantic"
    weight: float = 1.0
    reason: str = ""
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    def strengthen(self, weight: float, reason: str = "") -> None:
        self.weight = min(1.0, max(self.weight, weight))
        if reason and reason not in self.reason:
            self.reason = f"{self.reason}; {reason}" if self.reason else reason
        self.updated_at = now_ts()

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_id": self.target_id,
            "relation": self.relation,
            "weight": self.weight,
            "reason": self.reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphEdge":
        return cls(
            target_id=str(data["target_id"]),
            relation=str(data.get("relation", "semantic")),
            weight=float(data.get("weight", 1.0)),
            reason=str(data.get("reason", "")),
            created_at=float(data.get("created_at", now_ts())),
            updated_at=float(data.get("updated_at", now_ts())),
        )


@dataclass(slots=True)
class ConflictRecord:
    left_id: str
    right_id: str
    field: str
    left_value: str
    right_value: str
    severity: float
    reason: str
    created_at: float = field(default_factory=now_ts)
    resolved: bool = False

    def key(self) -> tuple[str, str, str]:
        ordered = tuple(sorted((self.left_id, self.right_id)))
        return ordered[0], ordered[1], self.field

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "field": self.field,
            "left_value": self.left_value,
            "right_value": self.right_value,
            "severity": self.severity,
            "reason": self.reason,
            "created_at": self.created_at,
            "resolved": self.resolved,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConflictRecord":
        return cls(
            left_id=str(data["left_id"]),
            right_id=str(data["right_id"]),
            field=str(data.get("field", "value")),
            left_value=str(data.get("left_value", "")),
            right_value=str(data.get("right_value", "")),
            severity=float(data.get("severity", 0.5)),
            reason=str(data.get("reason", "")),
            created_at=float(data.get("created_at", now_ts())),
            resolved=bool(data.get("resolved", False)),
        )


from backend.memory.common.schema import (
    PriorityVector,
    UnifiedMemorySegment as MemorySegment
)


@dataclass(slots=True)
class CategoryNode:
    name: str
    path: tuple[str, ...]
    embedding: list[float]
    children: dict[str, "CategoryNode"] = field(default_factory=dict)
    segment_ids: set[str] = field(default_factory=set)
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)

    def add_child(self, name: str, embedding: list[float]) -> "CategoryNode":
        if name not in self.children:
            self.children[name] = CategoryNode(name=name, path=self.path + (name,), embedding=embedding)
        return self.children[name]

    def find(self, path: tuple[str, ...]) -> "CategoryNode | None":
        if not path:
            return self
        head, *tail = path
        child = self.children.get(head)
        if child is None:
            return None
        return child.find(tuple(tail))

    def walk(self) -> list["CategoryNode"]:
        nodes = [self]
        for child in self.children.values():
            nodes.extend(child.walk())
        return nodes

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": list(self.path),
            "embedding": self.embedding,
            "segment_ids": sorted(self.segment_ids),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "children": {name: child.to_dict() for name, child in sorted(self.children.items())},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CategoryNode":
        node = cls(
            name=str(data.get("name", "Memory")),
            path=tuple(str(p) for p in data.get("path", ())),
            embedding=[float(v) for v in data.get("embedding", [])],
            segment_ids={str(v) for v in data.get("segment_ids", [])},
            created_at=float(data.get("created_at", now_ts())),
            updated_at=float(data.get("updated_at", now_ts())),
        )
        node.children = {
            str(name): cls.from_dict(child) for name, child in data.get("children", {}).items()
        }
        return node


@dataclass(slots=True)
class RouteResult:
    segment: MemorySegment
    similarity: float
    priority_score: float
    graph_distance: int
    total_score: float
    category_score: float = 0.0
    graph_weight: float = 0.0
    sparse_score: float = 0.0
    exact_matches: int = 0


@dataclass(slots=True)
class ReasoningStep:
    query: str
    selected_ids: list[str]
    focus_terms: list[str]
    observation: str


@dataclass(slots=True)
class ReasoningTrace:
    original_query: str
    steps: list[ReasoningStep]
    context: "ActiveContext"

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_query": self.original_query,
            "steps": [
                {
                    "query": step.query,
                    "selected_ids": step.selected_ids,
                    "focus_terms": step.focus_terms,
                    "observation": step.observation,
                }
                for step in self.steps
            ],
            "segment_ids": self.context.segment_ids,
        }


@dataclass(slots=True)
class ActiveContext:
    query: str
    selected: list[RouteResult]
    context_text: str
    token_budget: int
    estimated_tokens: int
    global_summary: str

    @property
    def segment_ids(self) -> list[str]:
        return [item.segment.id for item in self.selected]


@dataclass(slots=True)
class TiidoTurn:
    user_message: str
    active_context: ActiveContext
    answer: str
    learned_segment_ids: list[str]


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))

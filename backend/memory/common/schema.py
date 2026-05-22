from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MemoryKind(str, Enum):
    TEMPORAL = "temporal"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"


def _clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))


@dataclass(slots=True)
class PriorityVector:
    relevance: float = 0.5
    importance: float = 0.5
    recency: float = 1.0
    frequency: float = 0.0

    def clamp(self) -> None:
        self.relevance = _clamp01(self.relevance)
        self.importance = _clamp01(self.importance)
        self.recency = _clamp01(self.recency)
        self.frequency = _clamp01(self.frequency)

    def total(self, similarity: float, age_seconds: float) -> float:
        recency_decay = 1.0 / (1.0 + max(age_seconds, 0.0) / 86_400.0)
        recency_score = 0.5 * self.recency + 0.5 * recency_decay
        score = (
            0.42 * similarity
            + 0.22 * self.relevance
            + 0.18 * self.importance
            + 0.10 * recency_score
            + 0.08 * self.frequency
        )
        return _clamp01(score)

    def touch(self, similarity: float, boost: float = 0.08) -> None:
        self.relevance = max(self.relevance, _clamp01(similarity))
        self.recency = 1.0
        self.frequency = _clamp01(self.frequency + boost)
        self.clamp()

    def decay(self, amount: float = 0.02) -> None:
        self.recency = _clamp01(self.recency - amount)
        self.relevance = _clamp01(self.relevance - amount * 0.4)

    def to_dict(self) -> dict[str, float]:
        return {
            "relevance": self.relevance,
            "importance": self.importance,
            "recency": self.recency,
            "frequency": self.frequency,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "PriorityVector":
        if not data:
            return cls()
        item = cls(
            relevance=float(data.get("relevance", 0.5)),
            importance=float(data.get("importance", 0.5)),
            recency=float(data.get("recency", 1.0)),
            frequency=float(data.get("frequency", 0.0)),
        )
        item.clamp()
        return item


@dataclass(slots=True)
class UnifiedMemorySegment:
    # Core Fields (DSM & DPM merged)
    text: str
    embedding: list[float]
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    kind: MemoryKind = MemoryKind.SEMANTIC
    value: str = ""
    description: str = ""
    category_path: tuple[str, ...] = ("General",)
    links: set[str] = field(default_factory=set)
    priorities: PriorityVector = field(default_factory=PriorityVector)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_accessed_at: float = field(default_factory=time.time)
    access_count: int = 0
    utility: float = 1.0  # From DPM record
    metadata: dict[str, Any] = field(default_factory=dict)
    compressed_from: list[str] = field(default_factory=list)
    schema_version: int = 1

    @property
    def estimated_tokens(self) -> int:
        return max(1, len(self.text.split()))

    def touch(self, similarity: float) -> None:
        self.last_accessed_at = time.time()
        self.access_count += 1
        self.priorities.touch(similarity)

    def update_text(self, text: str, description: str, embedding: list[float]) -> None:
        self.text = text
        self.description = description
        self.embedding = embedding
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "embedding": self.embedding,
            "kind": self.kind.value,
            "value": self.value or self.text,
            "description": self.description,
            "category_path": list(self.category_path),
            "links": sorted(self.links),
            "priorities": self.priorities.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_accessed_at": self.last_accessed_at,
            "access_count": self.access_count,
            "utility": self.utility,
            "metadata": self.metadata,
            "compressed_from": self.compressed_from,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "UnifiedMemorySegment":
        # Check and handle legacy schema migration
        raw_kind = data.get("kind", "semantic")
        try:
            kind = MemoryKind(raw_kind)
        except ValueError:
            kind = MemoryKind.SEMANTIC

        # Automatic schema upgrades/migrations if missing schema_version or fields
        version = int(data.get("schema_version", 1))
        
        # If loading legacy DPM MemoryRecord dict format:
        # e.g., mapping record.key -> embedding, record.value -> value, etc.
        text = str(data.get("text", ""))
        embedding = [float(v) for v in (data.get("embedding") or data.get("key") or [])]
        value = str(data.get("value", "")) or text
        
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex),
            text=text,
            embedding=embedding,
            kind=kind,
            value=value,
            description=str(data.get("description", "")),
            category_path=tuple(str(p) for p in data.get("category_path", ["General"])),
            links={str(v) for v in data.get("links", [])},
            priorities=PriorityVector.from_dict(data.get("priorities")),
            created_at=float(data.get("created_at") or data.get("created_at") or time.time()),
            updated_at=float(data.get("updated_at") or data.get("last_used_at") or time.time()),
            last_accessed_at=float(data.get("last_accessed_at") or data.get("last_used_at") or time.time()),
            access_count=int(data.get("access_count", 0)),
            utility=float(data.get("utility", 1.0)),
            metadata=dict(data.get("metadata", {})),
            compressed_from=[str(v) for v in data.get("compressed_from", [])],
            schema_version=version
        )

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


def now_ts() -> float:
    return time.time()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


@dataclass(slots=True)
class LatentState:
    label: str
    text: str
    vector: list[float]
    role: str = "state"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "text": self.text,
            "vector": self.vector,
            "role": self.role,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LatentState":
        return cls(
            label=str(data.get("label", "")),
            text=str(data.get("text", "")),
            vector=[float(value) for value in data.get("vector", [])],
            role=str(data.get("role", "state")),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(slots=True)
class LatentDelta:
    start: LatentState
    end: LatentState
    vector: list[float]
    operator: str
    magnitude: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.to_dict(),
            "end": self.end.to_dict(),
            "vector": self.vector,
            "operator": self.operator,
            "magnitude": self.magnitude,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LatentDelta":
        return cls(
            start=LatentState.from_dict(dict(data.get("start", {}))),
            end=LatentState.from_dict(dict(data.get("end", {}))),
            vector=[float(value) for value in data.get("vector", [])],
            operator=str(data.get("operator", "delta")),
            magnitude=float(data.get("magnitude", 0.0)),
        )


@dataclass(slots=True)
class ActivationTrace:
    query: str
    gene_id: str
    dense_score: float
    trigger_overlap: float
    success_score: float
    stability_score: float
    utility_score: float
    reuse_score: float
    probability: float
    weight: float
    threshold: float
    selected: bool
    dsm_score: float = 0.0
    dsm_segment_id: str = ""
    created_at: float = field(default_factory=now_ts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "gene_id": self.gene_id,
            "dense_score": self.dense_score,
            "trigger_overlap": self.trigger_overlap,
            "success_score": self.success_score,
            "stability_score": self.stability_score,
            "utility_score": self.utility_score,
            "reuse_score": self.reuse_score,
            "probability": self.probability,
            "weight": self.weight,
            "threshold": self.threshold,
            "selected": self.selected,
            "dsm_score": self.dsm_score,
            "dsm_segment_id": self.dsm_segment_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActivationTrace":
        return cls(
            query=str(data.get("query", "")),
            gene_id=str(data.get("gene_id", "")),
            dense_score=clamp01(float(data.get("dense_score", 0.0))),
            trigger_overlap=clamp01(float(data.get("trigger_overlap", 0.0))),
            success_score=clamp01(float(data.get("success_score", 0.0))),
            stability_score=clamp01(float(data.get("stability_score", 0.0))),
            utility_score=clamp01(float(data.get("utility_score", 0.0))),
            reuse_score=clamp01(float(data.get("reuse_score", 0.0))),
            probability=clamp01(float(data.get("probability", 0.0))),
            weight=clamp01(float(data.get("weight", 0.0))),
            threshold=clamp01(float(data.get("threshold", 0.0))),
            selected=bool(data.get("selected", False)),
            dsm_score=float(data.get("dsm_score", 0.0)),
            dsm_segment_id=str(data.get("dsm_segment_id", "")),
            created_at=float(data.get("created_at", now_ts())),
        )

    @property
    def reasons(self) -> list[str]:
        return [
            f"dense={self.dense_score:.3f}",
            f"trigger_overlap={self.trigger_overlap:.3f}",
            f"success={self.success_score:.3f}",
            f"stability={self.stability_score:.3f}",
            f"utility={self.utility_score:.3f}",
            f"reuse={self.reuse_score:.3f}",
            f"dsm={self.dsm_score:.3f}",
        ]


@dataclass(slots=True)
class ReasoningTrajectory:
    task: str
    states: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    final_answer: str = ""
    success: bool = True
    utility: float = 0.7
    intermediate_representations: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("traj"))
    created_at: float = field(default_factory=now_ts)

    def text(self) -> str:
        parts = [
            f"Task: {self.task}",
            f"States: {' | '.join(self.states)}",
            f"Actions: {' | '.join(self.actions)}",
            f"Intermediate: {' | '.join(self.intermediate_representations)}",
            f"Tools: {' | '.join(self.tools_used)}",
            f"Answer: {self.final_answer}",
        ]
        return "\n".join(part for part in parts if part.split(": ", 1)[-1])

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "states": self.states,
            "actions": self.actions,
            "final_answer": self.final_answer,
            "success": self.success,
            "utility": self.utility,
            "intermediate_representations": self.intermediate_representations,
            "tools_used": self.tools_used,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReasoningTrajectory":
        return cls(
            id=str(data["id"]),
            task=str(data.get("task", "")),
            states=[str(item) for item in data.get("states", [])],
            actions=[str(item) for item in data.get("actions", [])],
            final_answer=str(data.get("final_answer", "")),
            success=bool(data.get("success", True)),
            utility=float(data.get("utility", 0.7)),
            intermediate_representations=[
                str(item) for item in data.get("intermediate_representations", [])
            ],
            tools_used=[str(item) for item in data.get("tools_used", [])],
            metadata=dict(data.get("metadata", {})),
            created_at=float(data.get("created_at", now_ts())),
        )


@dataclass(slots=True)
class GeneStats:
    success_count: int = 0
    failure_count: int = 0
    reuse_count: int = 0
    stability: float = 0.5
    average_utility: float = 0.5

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        if total == 0:
            return 0.5
        return self.success_count / total

    def activation_score(self) -> float:
        frequency = min(1.0, self.reuse_count / 12.0)
        return clamp01(
            0.38 * self.success_rate
            + 0.28 * self.stability
            + 0.22 * self.average_utility
            + 0.12 * frequency
        )

    def record_activation(self, success: bool | None = None, utility: float | None = None) -> None:
        self.reuse_count += 1
        if success is True:
            self.success_count += 1
        elif success is False:
            self.failure_count += 1
        if utility is not None:
            self.average_utility = clamp01((self.average_utility + clamp01(utility)) / 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "reuse_count": self.reuse_count,
            "stability": self.stability,
            "average_utility": self.average_utility,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "GeneStats":
        if not data:
            return cls()
        return cls(
            success_count=int(data.get("success_count", 0)),
            failure_count=int(data.get("failure_count", 0)),
            reuse_count=int(data.get("reuse_count", 0)),
            stability=clamp01(float(data.get("stability", 0.5))),
            average_utility=clamp01(float(data.get("average_utility", 0.5))),
        )


@dataclass(slots=True)
class ReasoningGene:
    task_context: str
    transformation_delta: str
    reasoning_steps: list[str]
    solution_schema: str
    trigger_terms: list[str]
    embedding: list[float]
    latent_states: list[LatentState] = field(default_factory=list)
    latent_delta: LatentDelta | None = None
    category_path: tuple[str, ...] = ("RLD", "Reasoning Gene")
    tools_used: list[str] = field(default_factory=list)
    stats: GeneStats = field(default_factory=GeneStats)
    source_trajectory_ids: list[str] = field(default_factory=list)
    parent_gene_ids: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: new_id("gene"))
    created_at: float = field(default_factory=now_ts)
    updated_at: float = field(default_factory=now_ts)
    last_activated_at: float = 0.0
    weight: float = 1.0

    def compatibility_text(self) -> str:
        return "\n".join(
            [
                self.task_context,
                self.transformation_delta,
                " ".join(self.trigger_terms),
                " ".join(self.reasoning_steps),
                self.solution_schema,
            ]
        )

    def memory_text(self) -> str:
        return "\n".join(
            [
                f"RLD Gene: {self.id}",
                f"Task context: {self.task_context}",
                f"Delta: {self.transformation_delta}",
                f"Latent operator: {self.latent_delta.operator if self.latent_delta else 'none'}",
                f"Trigger terms: {', '.join(self.trigger_terms)}",
                f"Tools: {', '.join(self.tools_used)}",
                "Reasoning steps:",
                *[f"{index}. {step}" for index, step in enumerate(self.reasoning_steps, start=1)],
                f"Solution schema: {self.solution_schema}",
            ]
        )

    def activate(self, weight: float) -> None:
        self.last_activated_at = now_ts()
        self.weight = clamp01(weight)
        self.stats.record_activation()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_context": self.task_context,
            "transformation_delta": self.transformation_delta,
            "reasoning_steps": self.reasoning_steps,
            "solution_schema": self.solution_schema,
            "trigger_terms": self.trigger_terms,
            "embedding": self.embedding,
            "latent_states": [state.to_dict() for state in self.latent_states],
            "latent_delta": self.latent_delta.to_dict() if self.latent_delta else None,
            "category_path": list(self.category_path),
            "tools_used": self.tools_used,
            "stats": self.stats.to_dict(),
            "source_trajectory_ids": self.source_trajectory_ids,
            "parent_gene_ids": self.parent_gene_ids,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "last_activated_at": self.last_activated_at,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReasoningGene":
        return cls(
            id=str(data["id"]),
            task_context=str(data.get("task_context", "")),
            transformation_delta=str(data.get("transformation_delta", "")),
            reasoning_steps=[str(item) for item in data.get("reasoning_steps", [])],
            solution_schema=str(data.get("solution_schema", "")),
            trigger_terms=[str(item) for item in data.get("trigger_terms", [])],
            embedding=[float(item) for item in data.get("embedding", [])],
            latent_states=[
                LatentState.from_dict(dict(item)) for item in data.get("latent_states", [])
            ],
            latent_delta=(
                LatentDelta.from_dict(dict(data["latent_delta"]))
                if data.get("latent_delta")
                else None
            ),
            category_path=tuple(str(item) for item in data.get("category_path", ["RLD"])),
            tools_used=[str(item) for item in data.get("tools_used", [])],
            stats=GeneStats.from_dict(data.get("stats")),
            source_trajectory_ids=[str(item) for item in data.get("source_trajectory_ids", [])],
            parent_gene_ids=[str(item) for item in data.get("parent_gene_ids", [])],
            created_at=float(data.get("created_at", now_ts())),
            updated_at=float(data.get("updated_at", now_ts())),
            last_activated_at=float(data.get("last_activated_at", 0.0)),
            weight=float(data.get("weight", 1.0)),
        )


@dataclass(slots=True)
class ActivatedGene:
    gene: ReasoningGene
    probability: float
    weight: float
    reasons: list[str]
    trace: ActivationTrace | None = None

    def prompt_block(self, index: int) -> str:
        latent = self.gene.latent_delta
        latent_line = (
            f"latent_delta={latent.operator} magnitude={latent.magnitude:.3f}"
            if latent
            else "latent_delta=none"
        )
        return "\n".join(
            [
                f"[RLD GENE {index}] id={self.gene.id}",
                f"weight={self.weight:.3f} probability={self.probability:.3f}",
                f"context={self.gene.task_context}",
                f"delta={self.gene.transformation_delta}",
                latent_line,
                f"steps={'; '.join(self.gene.reasoning_steps)}",
                f"solution_schema={self.gene.solution_schema}",
            ]
        )


@dataclass(slots=True)
class RLDContext:
    query: str
    activated: list[ActivatedGene]
    context_text: str
    traces: list[ActivationTrace] = field(default_factory=list)

    @property
    def gene_ids(self) -> list[str]:
        return [item.gene.id for item in self.activated]


@dataclass(slots=True)
class ConsolidationReport:
    pruned: list[str] = field(default_factory=list)
    merged: list[str] = field(default_factory=list)
    stabilized: list[str] = field(default_factory=list)
    rewritten: list[str] = field(default_factory=list)
    # --- Sleep Phase fields (革命) ---
    decayed: dict[str, float] = field(default_factory=dict)
    """gene_id → amount of stability lost to entropic decay."""
    merge_lineage: dict[str, list[str]] = field(default_factory=dict)
    """child_gene_id → [parent_gene_ids] — full chromosome ancestry."""
    centroid_shifts: dict[str, float] = field(default_factory=dict)
    """gene_id → cosine distance the embedding moved during re-anchoring."""
    genes_before: int = 0
    genes_after: int = 0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "pruned": self.pruned,
            "merged": self.merged,
            "stabilized": self.stabilized,
            "rewritten": self.rewritten,
            "decayed": self.decayed,
            "merge_lineage": self.merge_lineage,
            "centroid_shifts": self.centroid_shifts,
            "genes_before": self.genes_before,
            "genes_after": self.genes_after,
            "duration_seconds": round(self.duration_seconds, 4),
        }

    @property
    def summary(self) -> str:
        lines = [
            f"Sleep Report: {self.genes_before} → {self.genes_after} genes ({self.duration_seconds:.2f}s)",
            f"  Decayed:    {len(self.decayed)} genes lost stability",
            f"  Pruned:     {len(self.pruned)} dead genes removed",
            f"  Merged:     {len(self.merged)} chromosomes synthesized",
            f"  Stabilized: {len(self.stabilized)} genes hardened",
            f"  Rewritten:  {len(self.rewritten)} genes re-encoded",
            f"  Reanchored: {len(self.centroid_shifts)} embeddings shifted",
        ]
        return "\n".join(lines)


GENE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "id",
        "task_context",
        "transformation_delta",
        "reasoning_steps",
        "solution_schema",
        "trigger_terms",
        "latent_states",
        "latent_delta",
        "stats",
    ],
    "properties": {
        "id": {"type": "string"},
        "task_context": {"type": "string"},
        "transformation_delta": {"type": "string"},
        "reasoning_steps": {"type": "array", "items": {"type": "string"}},
        "solution_schema": {"type": "string"},
        "trigger_terms": {"type": "array", "items": {"type": "string"}},
        "latent_states": {"type": "array", "items": {"type": "object"}},
        "latent_delta": {"type": ["object", "null"]},
        "tools_used": {"type": "array", "items": {"type": "string"}},
        "stats": {"type": "object"},
        "source_trajectory_ids": {"type": "array", "items": {"type": "string"}},
        "parent_gene_ids": {"type": "array", "items": {"type": "string"}},
    },
}


def clamp01(value: float) -> float:
    return min(1.0, max(0.0, float(value)))

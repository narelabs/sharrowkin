from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Protocol

from memory.dsm.indexing.embedding import EmbeddingModel, HashEmbeddingModel, cosine, mean_embedding, tokenize, top_terms
from memory.dsm.core.memory import DynamicSegmentedMemory
from memory.dsm.core.models import RouteResult
from memory.dsm.storage.storage import JsonStorage
from memory.rld.sqlite_store import RldSqliteStore

import os

logger = logging.getLogger("rld")


def default_embedding_model() -> EmbeddingModel:
    """Try neural encoder first, fall back to hash."""
    if os.getenv("SHARROWKIN_USE_NEURAL") != "1":
        logger.info("RLD: Neural embeddings not enabled via SHARROWKIN_USE_NEURAL. Defaulting to HashEmbeddingModel.")
        return HashEmbeddingModel()

    try:
        import socket
        orig_timeout = socket.getdefaulttimeout()
        socket.setdefaulttimeout(2.0)
        try:
            from sentence_transformers import SentenceTransformer

            class _NeuralEmbedding:
                def __init__(self):
                    try:
                        self._model = SentenceTransformer("all-MiniLM-L6-v2", local_files_only=True)
                    except Exception:
                        self._model = SentenceTransformer("all-MiniLM-L6-v2")
                    self.dim = self._model.get_embedding_dimension()

                def encode(self, text: str) -> list[float]:
                    return self._model.encode(text, normalize_embeddings=True).tolist()

            model = _NeuralEmbedding()
            logger.info("RLD: Using neural encoder (all-MiniLM-L6-v2, dim=%d)", model.dim)
            return model
        finally:
            socket.setdefaulttimeout(orig_timeout)
    except Exception:
        logger.info("RLD: Falling back to HashEmbeddingModel")
        return HashEmbeddingModel()

from .models import (
    ActivatedGene,
    ActivationTrace,
    ConsolidationReport,
    GENE_SCHEMA,
    GeneStats,
    LatentDelta,
    LatentState,
    RLDContext,
    ReasoningGene,
    ReasoningTrajectory,
    clamp01,
    now_ts,
)


class LatentEncoder(Protocol):
    dim: int

    def encode_state(self, label: str, text: str, role: str = "state") -> LatentState:
        """Encode text into an explicit latent reasoning state."""

    def encode_delta(self, start: LatentState, end: LatentState, operator: str) -> LatentDelta:
        """Encode the transformation between two latent states."""


class GeneExtractor(Protocol):
    def extract(self, trajectory: ReasoningTrajectory) -> ReasoningGene:
        """Compress a trajectory τ into a reusable reasoning gene g=f(τ)."""


class DSMPolicy(Protocol):
    threshold: float
    top_k: int

    def evaluate(self, query: str, query_state: LatentState, gene: ReasoningGene) -> ActivationTrace:
        """Return P(g|x), activation weight and selection diagnostics."""


class HashLatentEncoder:
    def __init__(self, embedding_model: EmbeddingModel | None = None):
        self.embedding_model = embedding_model or HashEmbeddingModel()
        self.dim = self.embedding_model.dim

    def encode_state(self, label: str, text: str, role: str = "state") -> LatentState:
        return LatentState(
            label=label,
            text=summarize_phrase(text, limit=240),
            vector=self.embedding_model.encode(text),
            role=role,
        )

    def encode_delta(self, start: LatentState, end: LatentState, operator: str) -> LatentDelta:
        vector = [
            end_value - start_value for start_value, end_value in zip(start.vector, end.vector)
        ]
        magnitude = sum(value * value for value in vector) ** 0.5
        if magnitude:
            vector = [value / magnitude for value in vector]
        return LatentDelta(
            start=start,
            end=end,
            vector=vector,
            operator=operator,
            magnitude=magnitude,
        )


class TrajectoryGeneExtractor:
    def __init__(self, latent_encoder: LatentEncoder, embedding_model: EmbeddingModel):
        self.latent_encoder = latent_encoder
        self.embedding_model = embedding_model

    def extract(self, trajectory: ReasoningTrajectory) -> ReasoningGene:
        return gene_from_trajectory(trajectory, self.embedding_model, self.latent_encoder)


class WeightedDSMPolicy:
    def __init__(
        self,
        threshold: float = 0.35,
        top_k: int = 5,
        dense_weight: float = 0.52,
        trigger_weight: float = 0.20,
        success_weight: float = 0.10,
        stability_weight: float = 0.08,
        utility_weight: float = 0.06,
        reuse_weight: float = 0.04,
    ):
        self.threshold = threshold
        self.top_k = top_k
        self.dense_weight = dense_weight
        self.trigger_weight = trigger_weight
        self.success_weight = success_weight
        self.stability_weight = stability_weight
        self.utility_weight = utility_weight
        self.reuse_weight = reuse_weight

    def evaluate(self, query: str, query_state: LatentState, gene: ReasoningGene) -> ActivationTrace:
        dense = max(0.0, cosine(query_state.vector, gene.embedding))
        query_terms = set(tokenize(query))
        gene_terms = set(token.lower() for token in gene.trigger_terms)
        trigger_overlap = len(query_terms & gene_terms) / max(1, len(gene_terms))
        success_score = gene.stats.success_rate
        stability_score = gene.stats.stability
        utility_score = gene.stats.average_utility
        reuse_score = min(1.0, gene.stats.reuse_count / 12.0)
        probability = clamp01(
            self.dense_weight * dense
            + self.trigger_weight * trigger_overlap
            + self.success_weight * success_score
            + self.stability_weight * stability_score
            + self.utility_weight * utility_score
            + self.reuse_weight * reuse_score
        )
        weight = clamp01(0.58 * probability + 0.26 * stability_score + 0.16 * utility_score)
        return ActivationTrace(
            query=query,
            gene_id=gene.id,
            dense_score=dense,
            trigger_overlap=trigger_overlap,
            success_score=success_score,
            stability_score=stability_score,
            utility_score=utility_score,
            reuse_score=reuse_score,
            probability=probability,
            weight=weight,
            threshold=self.threshold,
            selected=probability >= self.threshold,
        )

    def to_dict(self) -> dict[str, float | int]:
        return {
            "threshold": self.threshold,
            "top_k": self.top_k,
            "dense_weight": self.dense_weight,
            "trigger_weight": self.trigger_weight,
            "success_weight": self.success_weight,
            "stability_weight": self.stability_weight,
            "utility_weight": self.utility_weight,
            "reuse_weight": self.reuse_weight,
        }


class RecursiveLatentDNA:
    """Recursive Latent DNA: reasoning as modular memory.

    RLD stores reusable reasoning transformations as compact genes. The DSM controller
    dynamically activates a sparse top-k subset for the current context and an offline
    sleep phase prunes, merges and stabilizes the gene library.
    """

    def __init__(
        self,
        storage_path: str | Path | None = None,
        embedding_model: EmbeddingModel | None = None,
        activation_threshold: float = 0.35,
        top_k: int = 5,
        latent_encoder: LatentEncoder | None = None,
        gene_extractor: GeneExtractor | None = None,
        dsm_policy: DSMPolicy | None = None,
        dsm_memory: DynamicSegmentedMemory | None = None,
        use_dsm_backend: bool = True,
    ):
        self.embedding_model = embedding_model or default_embedding_model()
        self.latent_encoder = latent_encoder or HashLatentEncoder(self.embedding_model)
        self.dsm_policy = dsm_policy or WeightedDSMPolicy(activation_threshold, top_k)
        self.gene_extractor = gene_extractor or TrajectoryGeneExtractor(
            self.latent_encoder, self.embedding_model
        )
        db_path = Path(str(storage_path).replace(".json", ".db")) if storage_path else Path(".rld") / "genes.db"
        self.storage = RldSqliteStore(db_path)
        self.dsm_memory = dsm_memory or DynamicSegmentedMemory(
            self.storage.path.with_name("rld_dsm_memory.json"),
            embedding_model=self.embedding_model,
        )
        self.use_dsm_backend = use_dsm_backend
        self.activation_threshold = self.dsm_policy.threshold
        self.top_k = self.dsm_policy.top_k
        self.genes: dict[str, ReasoningGene] = {}
        self.gene_segment_ids: dict[str, str] = {}
        self.trajectories: dict[str, ReasoningTrajectory] = {}
        self.activation_traces: list[ActivationTrace] = []
        if self.storage.exists():
            self.load()

    def observe(
        self,
        task: str,
        *,
        states: list[str] | None = None,
        actions: list[str] | None = None,
        final_answer: str = "",
        success: bool = True,
        utility: float = 0.7,
        intermediate_representations: list[str] | None = None,
        tools_used: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        generate_gene: bool = True,
    ) -> ReasoningTrajectory:
        trajectory = ReasoningTrajectory(
            task=task,
            states=states or [],
            actions=actions or [],
            final_answer=final_answer,
            success=success,
            utility=clamp01(utility),
            intermediate_representations=intermediate_representations or [],
            tools_used=tools_used or [],
            metadata=metadata or {},
        )
        self.trajectories[trajectory.id] = trajectory
        if generate_gene:
            self.generate_gene(trajectory)
        return trajectory

    def generate_gene(self, trajectory: ReasoningTrajectory) -> ReasoningGene:
        gene = self.gene_extractor.extract(trajectory)
        existing = self._nearest_gene(gene.embedding, threshold=0.82)
        if existing:
            self._update_gene(existing, gene, trajectory)
            self._index_gene(existing)
            return existing
        self.genes[gene.id] = gene
        self._index_gene(gene)
        return gene

    def activate(
        self,
        query: str,
        *,
        threshold: float | None = None,
        top_k: int | None = None,
    ) -> list[ActivatedGene]:
        query_state = self.latent_encoder.encode_state("query", query, role="query")
        scored: list[ActivatedGene] = []
        traces: list[ActivationTrace] = []
        active_threshold = threshold if threshold is not None else self.dsm_policy.threshold
        for gene, route in self._candidate_genes(query, top_k=top_k):
            trace = self.dsm_policy.evaluate(query, query_state, gene)
            if route is not None:
                trace.dsm_score = route.total_score
                trace.dsm_segment_id = route.segment.id
                trace.probability = clamp01(
                    0.72 * trace.probability + 0.28 * max(0.0, route.total_score)
                )
                trace.weight = clamp01(0.70 * trace.weight + 0.30 * max(0.0, route.total_score))
            trace.threshold = active_threshold
            trace.selected = trace.probability >= active_threshold
            traces.append(trace)
            if not trace.selected:
                continue
            scored.append(
                ActivatedGene(
                    gene=gene,
                    probability=trace.probability,
                    weight=trace.weight,
                    reasons=trace.reasons,
                    trace=trace,
                )
            )

        scored.sort(reverse=True, key=lambda item: (item.probability, item.weight))
        selected = scored[: max(0, top_k if top_k is not None else self.dsm_policy.top_k)]
        selected_ids = {item.gene.id for item in selected}
        for trace in traces:
            trace.selected = trace.gene_id in selected_ids
        for item in selected:
            item.gene.activate(item.weight)
        self.activation_traces.extend(traces)
        return selected

    def active_context(
        self,
        query: str,
        *,
        threshold: float | None = None,
        top_k: int | None = None,
    ) -> RLDContext:
        previous_trace_count = len(self.activation_traces)
        activated = self.activate(query, threshold=threshold, top_k=top_k)
        traces = self.activation_traces[previous_trace_count:]
        parts = [
            "RLD ACTIVE CONTEXT",
            f"QUERY: {query}",
            "Only the following reasoning genes are active; compose them sparsely.",
        ]
        for index, gene in enumerate(activated, start=1):
            parts.append(gene.prompt_block(index))
        if not activated:
            parts.append("No reasoning genes passed the DSM activation threshold.")
        return RLDContext(
            query=query,
            activated=activated,
            context_text="\n\n---\n\n".join(parts),
            traces=traces,
        )

    def consolidate(
        self,
        *,
        min_value: float = 0.18,
        merge_similarity: float = 0.74,
        stabilize_reuse: int = 3,
    ) -> ConsolidationReport:
        t0 = now_ts()
        report = ConsolidationReport(genes_before=len(self.genes))
        self._prune_low_value(min_value, report)
        self._merge_compatible(merge_similarity, report)
        self._stabilize(stabilize_reuse, report)
        self._rebuild_gene_index()
        report.genes_after = len(self.genes)
        report.duration_seconds = now_ts() - t0
        return report

    def sleep(
        self,
        *,
        decay_rate: float = 0.06,
        decay_floor: float = 0.08,
        min_value: float = 0.18,
        merge_similarity: float = 0.74,
        stabilize_reuse: int = 3,
        centroid_reanchor_threshold: int = 4,
        save_after: bool = True,
    ) -> ConsolidationReport:
        """Offline consolidation — the Sleep Phase.

        Runs the full cognitive lifecycle in one call:
          1. **Entropic Decay** — all genes lose stability proportional
             to inactivity (biological forgetting). Genes that haven't
             been activated recently decay faster.
          2. **Prune** — genes whose value falls below ``min_value``
             after decay are permanently removed.
          3. **Merge** — semantically compatible genes are fused into
             higher-order *chromosomes of reasoning*, with full
             lineage tracking.
          4. **Stabilize** — high-reuse genes have their steps and
             terms deduplicated and re-encoded.
          5. **Centroid Re-anchor** — genes with enough trajectory
             evidence have their embeddings recalculated from the
             centroid of all source trajectories, pulling the
             representation toward its true latent basin.
          6. **Save** — persist the consolidated genome to disk.

        Returns a :class:`ConsolidationReport` with full metrics.
        """
        t0 = now_ts()
        report = ConsolidationReport(genes_before=len(self.genes))

        # ── Phase 1: Entropic Decay ──
        self._entropic_decay(decay_rate, decay_floor, report)

        # ── Phase 2: Prune ──
        self._prune_low_value(min_value, report)

        # ── Phase 3: Merge (Chromosome Synthesis) ──
        self._merge_compatible(merge_similarity, report)

        # ── Phase 4: Stabilize ──
        self._stabilize(stabilize_reuse, report)

        # ── Phase 5: Centroid Re-anchor ──
        self._reanchor_centroids(centroid_reanchor_threshold, report)

        # ── Finalize ──
        self._rebuild_gene_index()
        report.genes_after = len(self.genes)
        report.duration_seconds = now_ts() - t0
        if save_after:
            self.save()
        logger.info(
            "RLD Sleep complete: %d→%d genes in %.3fs (pruned=%d, merged=%d, decayed=%d)",
            report.genes_before, report.genes_after, report.duration_seconds,
            len(report.pruned), len(report.merged), len(report.decayed),
        )
        return report

    def record_outcome(self, gene_id: str, *, success: bool, utility: float = 0.7) -> None:
        gene = self.genes[gene_id]
        gene.stats.record_activation(success=success, utility=utility)
        gene.stats.stability = clamp01((gene.stats.stability + (1.0 if success else 0.0)) / 2)
        gene.updated_at = now_ts()

    def save(self) -> None:
        self.storage.save(
            {
                "version": 1,
                "activation_threshold": self.activation_threshold,
                "top_k": self.top_k,
                "embedding_dim": self.embedding_model.dim,
                "use_dsm_backend": self.use_dsm_backend,
                "gene_segment_ids": self.gene_segment_ids,
                "dsm_policy": (
                    self.dsm_policy.to_dict()
                    if isinstance(self.dsm_policy, WeightedDSMPolicy)
                    else {"threshold": self.dsm_policy.threshold, "top_k": self.dsm_policy.top_k}
                ),
                "genes": [gene.to_dict() for gene in self.genes.values()],
                "trajectories": [
                    trajectory.to_dict() for trajectory in self.trajectories.values()
                ],
                "activation_traces": [
                    trace.to_dict() for trace in self.activation_traces[-500:]
                ],
            }
        )

    def load(self) -> None:
        data = self.storage.load()
        self.activation_threshold = float(data.get("activation_threshold", self.activation_threshold))
        self.top_k = int(data.get("top_k", self.top_k))
        self.use_dsm_backend = bool(data.get("use_dsm_backend", self.use_dsm_backend))
        self.gene_segment_ids = {
            str(gene_id): str(segment_id)
            for gene_id, segment_id in data.get("gene_segment_ids", {}).items()
        }
        policy_data = data.get("dsm_policy", {})
        if isinstance(self.dsm_policy, WeightedDSMPolicy) and isinstance(policy_data, dict):
            self.dsm_policy = WeightedDSMPolicy(
                threshold=float(policy_data.get("threshold", self.activation_threshold)),
                top_k=int(policy_data.get("top_k", self.top_k)),
                dense_weight=float(policy_data.get("dense_weight", 0.40)),
                trigger_weight=float(policy_data.get("trigger_weight", 0.18)),
                success_weight=float(policy_data.get("success_weight", 0.16)),
                stability_weight=float(policy_data.get("stability_weight", 0.12)),
                utility_weight=float(policy_data.get("utility_weight", 0.10)),
                reuse_weight=float(policy_data.get("reuse_weight", 0.04)),
            )
            self.activation_threshold = self.dsm_policy.threshold
            self.top_k = self.dsm_policy.top_k
        self.genes = {
            gene.id: gene for gene in (ReasoningGene.from_dict(item) for item in data.get("genes", []))
        }
        self.trajectories = {
            trajectory.id: trajectory
            for trajectory in (
                ReasoningTrajectory.from_dict(item) for item in data.get("trajectories", [])
            )
        }
        self.activation_traces = [
            ActivationTrace.from_dict(item) for item in data.get("activation_traces", [])
        ]
        self._rebuild_gene_index()

    def stats(self) -> dict[str, Any]:
        return {
            "genes": len(self.genes),
            "trajectories": len(self.trajectories),
            "activation_traces": len(self.activation_traces),
            "dsm_backend": self.use_dsm_backend,
            "dsm_segments": self.dsm_memory.stats()["segments"],
            "indexed_genes": len(self.gene_segment_ids),
            "activation_threshold": self.activation_threshold,
            "top_k": self.top_k,
            "gene_schema": GENE_SCHEMA,
            "average_gene_value": (
                sum(gene_value(gene) for gene in self.genes.values()) / len(self.genes)
                if self.genes
                else 0.0
            ),
        }

    def _nearest_gene(self, embedding: list[float], threshold: float) -> ReasoningGene | None:
        if not self.genes:
            return None
        best = max(self.genes.values(), key=lambda gene: cosine(embedding, gene.embedding))
        if cosine(embedding, best.embedding) >= threshold:
            return best
        return None

    def _candidate_genes(
        self,
        query: str,
        *,
        top_k: int | None,
    ) -> list[tuple[ReasoningGene, RouteResult | None]]:
        if not self.use_dsm_backend or not self.gene_segment_ids:
            return [(gene, None) for gene in self.genes.values()]

        route_limit = max((top_k if top_k is not None else self.dsm_policy.top_k) * 4, 16)
        routed = self.dsm_memory.route(query, k=route_limit)
        candidates: list[tuple[ReasoningGene, RouteResult | None]] = []
        seen: set[str] = set()
        for item in routed:
            gene_id = str(item.segment.metadata.get("rld_gene_id", ""))
            gene = self.genes.get(gene_id)
            if gene is None or gene.id in seen:
                continue
            seen.add(gene.id)
            candidates.append((gene, item))

        if len(candidates) < min(len(self.genes), route_limit):
            query_vector = self.embedding_model.encode(query)
            missing = [gene for gene in self.genes.values() if gene.id not in seen]
            missing.sort(reverse=True, key=lambda gene: cosine(query_vector, gene.embedding))
            for gene in missing[: route_limit - len(candidates)]:
                candidates.append((gene, None))
        return candidates

    def _index_gene(self, gene: ReasoningGene) -> None:
        if not self.use_dsm_backend:
            return
        previous_segment_id = self.gene_segment_ids.get(gene.id)
        written = self.dsm_memory.write(
            gene.memory_text(),
            description=f"RLD gene {gene.id}: {gene.task_context}",
            category_path=gene.category_path,
            metadata={
                "rld_gene_id": gene.id,
                "kind": "rld_reasoning_gene",
                "source_trajectory_ids": gene.source_trajectory_ids,
                "parent_gene_ids": gene.parent_gene_ids,
            },
            importance=gene_value(gene),
            update_existing=False,
            link_related=True,
        )
        if written:
            self.gene_segment_ids[gene.id] = written[0].id
        current_segment_id = self.gene_segment_ids.get(gene.id)
        if previous_segment_id and previous_segment_id != current_segment_id:
            self._remove_dsm_segment(previous_segment_id)

    def _rebuild_gene_index(self) -> None:
        if not self.use_dsm_backend:
            return
        indexed_gene_ids = {
            str(segment.metadata.get("rld_gene_id", ""))
            for segment in self.dsm_memory.segments.values()
            if segment.metadata.get("kind") == "rld_reasoning_gene"
        }
        for gene in self.genes.values():
            if gene.id not in indexed_gene_ids:
                self._index_gene(gene)

    def _remove_dsm_segment(self, segment_id: str) -> None:
        segment = self.dsm_memory.segments.get(segment_id)
        if segment is None:
            return
        self.dsm_memory.categories.remove_segment(segment)
        self.dsm_memory.graph.remove_node(segment.id)
        self.dsm_memory.sparse_index.remove(segment.id)
        self.dsm_memory.segments.pop(segment.id, None)
        self.dsm_memory._rebuild_index()
        self.dsm_memory.categories.refresh_embeddings(self.dsm_memory.segments)

    def _update_gene(
        self,
        existing: ReasoningGene,
        incoming: ReasoningGene,
        trajectory: ReasoningTrajectory,
    ) -> None:
        existing.reasoning_steps = stable_union(existing.reasoning_steps, incoming.reasoning_steps, limit=8)
        existing.trigger_terms = stable_union(existing.trigger_terms, incoming.trigger_terms, limit=16)
        existing.tools_used = stable_union(existing.tools_used, incoming.tools_used, limit=10)
        existing.latent_states = merge_latent_states(existing.latent_states, incoming.latent_states)
        if existing.latent_delta and incoming.latent_delta:
            existing.latent_delta = merge_latent_delta(
                existing.latent_delta, incoming.latent_delta, self.latent_encoder
            )
        existing.source_trajectory_ids = stable_union(
            existing.source_trajectory_ids, [trajectory.id], limit=48
        )
        existing.embedding = mean_embedding(
            [existing.embedding, incoming.embedding], self.embedding_model.dim
        )
        existing.stats.record_activation(success=trajectory.success, utility=trajectory.utility)
        existing.stats.stability = clamp01((existing.stats.stability + trajectory.utility) / 2)
        existing.updated_at = now_ts()

    def _prune_low_value(self, min_value: float, report: ConsolidationReport) -> None:
        remove_ids = [
            gene.id
            for gene in self.genes.values()
            if gene_value(gene) < min_value and gene.stats.reuse_count > 0
        ]
        for gene_id in remove_ids:
            self.genes.pop(gene_id, None)
            segment_id = self.gene_segment_ids.pop(gene_id, "")
            if segment_id:
                self._remove_dsm_segment(segment_id)
        report.pruned.extend(remove_ids)

    def _merge_compatible(self, similarity: float, report: ConsolidationReport) -> None:
        visited: set[str] = set()
        for left in list(self.genes.values()):
            if left.id in visited or left.id not in self.genes:
                continue
            group = [left]
            for right in list(self.genes.values()):
                if right.id == left.id or right.id in visited:
                    continue
                if compatible_genes(left, right, similarity):
                    group.append(right)
            if len(group) < 2:
                continue
            merged = merge_genes(group, self.embedding_model)
            for gene in group:
                visited.add(gene.id)
                self.genes.pop(gene.id, None)
                segment_id = self.gene_segment_ids.pop(gene.id, "")
                if segment_id:
                    self._remove_dsm_segment(segment_id)
            self.genes[merged.id] = merged
            self._index_gene(merged)
            report.merged.append(merged.id)
            report.merge_lineage[merged.id] = [g.id for g in group]

    def _stabilize(self, reuse_threshold: int, report: ConsolidationReport) -> None:
        for gene in self.genes.values():
            if gene.stats.reuse_count < reuse_threshold and gene.stats.success_count < reuse_threshold:
                continue
            stable_steps = dedupe_phrases(gene.reasoning_steps, limit=6)
            stable_terms = dedupe_phrases(gene.trigger_terms, limit=12)
            if stable_steps != gene.reasoning_steps or stable_terms != gene.trigger_terms:
                gene.reasoning_steps = stable_steps
                gene.trigger_terms = stable_terms
                gene.embedding = self.embedding_model.encode(gene.compatibility_text())
                gene.updated_at = now_ts()
                report.rewritten.append(gene.id)
                self._index_gene(gene)
            gene.stats.stability = clamp01(gene.stats.stability + 0.12)
            report.stabilized.append(gene.id)

    def _entropic_decay(self, rate: float, floor: float, report: ConsolidationReport) -> None:
        """Biological forgetting: genes lose stability over time when unused.

        The decay formula is::

            Δstability = rate × (1 + inactivity_multiplier)
            inactivity_multiplier = min(2.0, hours_since_last_activation / 24)

        Genes that were activated recently (< 1 hour) are immune.
        Stability never drops below ``floor``.
        """
        current_time = now_ts()
        for gene in list(self.genes.values()):
            last = gene.last_activated_at or gene.created_at
            hours_idle = (current_time - last) / 3600.0
            if hours_idle < 1.0:
                continue  # recently active — immune
            inactivity = min(2.0, hours_idle / 24.0)
            decay_amount = rate * (1.0 + inactivity)
            old_stability = gene.stats.stability
            gene.stats.stability = max(floor, old_stability - decay_amount)
            actual_loss = old_stability - gene.stats.stability
            if actual_loss > 0.001:
                report.decayed[gene.id] = round(actual_loss, 5)
                gene.updated_at = current_time

    def _reanchor_centroids(self, min_trajectories: int, report: ConsolidationReport) -> None:
        """Pull gene embeddings toward the centroid of their source trajectories.

        When a gene has accumulated enough trajectory evidence
        (≥ ``min_trajectories``), its embedding is recalculated as the
        mean of all source trajectory embeddings. This gradually pulls
        the gene toward its true latent basin as more evidence arrives,
        correcting for initial noisy single-trajectory representations.
        """
        for gene in list(self.genes.values()):
            if len(gene.source_trajectory_ids) < min_trajectories:
                continue
            # Collect embeddings from all source trajectories we still have
            trajectory_embeddings: list[list[float]] = []
            for tid in gene.source_trajectory_ids:
                traj = self.trajectories.get(tid)
                if traj is None:
                    continue
                trajectory_embeddings.append(
                    self.embedding_model.encode(traj.text())
                )
            if len(trajectory_embeddings) < 2:
                continue
            # Compute centroid
            centroid = mean_embedding(trajectory_embeddings, self.embedding_model.dim)
            # Measure how far the gene drifted from the centroid
            shift = 1.0 - cosine(gene.embedding, centroid)
            if shift < 0.005:
                continue  # already anchored
            # Blend: 70% centroid + 30% current (soft re-anchor)
            blended = [
                0.7 * c + 0.3 * g
                for c, g in zip(centroid, gene.embedding)
            ]
            # Normalize
            mag = sum(v * v for v in blended) ** 0.5
            if mag > 0:
                blended = [v / mag for v in blended]
            gene.embedding = blended
            gene.updated_at = now_ts()
            report.centroid_shifts[gene.id] = round(shift, 5)
            self._index_gene(gene)


def gene_from_trajectory(
    trajectory: ReasoningTrajectory,
    embedding_model: EmbeddingModel,
    latent_encoder: LatentEncoder | None = None,
) -> ReasoningGene:
    encoder = latent_encoder or HashLatentEncoder(embedding_model)
    reasoning_steps = trajectory.actions or trajectory.states or [trajectory.final_answer or trajectory.task]
    context = summarize_phrase(trajectory.task, limit=160)
    delta = infer_delta(trajectory)
    schema = infer_solution_schema(trajectory)
    terms = top_terms(trajectory.text(), limit=12)
    latent_states = latent_states_from_trajectory(trajectory, encoder)
    latent_delta = build_latent_delta(latent_states, encoder)
    embedding_parts = [context, delta, " ".join(reasoning_steps), schema]
    if latent_delta:
        embedding_parts.extend([latent_delta.start.text, latent_delta.end.text])
    embedding = embedding_model.encode("\n".join(embedding_parts))
    stats = GeneStats(
        success_count=1 if trajectory.success else 0,
        failure_count=0 if trajectory.success else 1,
        reuse_count=0,
        stability=0.55 + 0.35 * trajectory.utility if trajectory.success else 0.25,
        average_utility=trajectory.utility,
    )
    return ReasoningGene(
        task_context=context,
        transformation_delta=delta,
        reasoning_steps=dedupe_phrases(reasoning_steps, limit=8),
        solution_schema=schema,
        trigger_terms=terms,
        embedding=embedding,
        latent_states=latent_states,
        latent_delta=latent_delta,
        tools_used=trajectory.tools_used,
        stats=stats,
        source_trajectory_ids=[trajectory.id],
    )


def infer_delta(trajectory: ReasoningTrajectory) -> str:
    if trajectory.states and len(trajectory.states) >= 2:
        return f"{summarize_phrase(trajectory.states[0])} -> {summarize_phrase(trajectory.states[-1])}"
    if trajectory.actions:
        return " -> ".join(summarize_phrase(action, limit=80) for action in trajectory.actions[:4])
    return summarize_phrase(trajectory.final_answer or trajectory.task, limit=160)


def infer_solution_schema(trajectory: ReasoningTrajectory) -> str:
    pieces = []
    if trajectory.intermediate_representations:
        pieces.append("represent")
    if trajectory.actions:
        pieces.append("transform")
    if trajectory.tools_used:
        pieces.append("tool-use")
    if trajectory.final_answer:
        pieces.append("answer")
    return " → ".join(pieces or ["reason", "answer"])


def merge_genes(genes: list[ReasoningGene], embedding_model: EmbeddingModel) -> ReasoningGene:
    steps: list[str] = []
    terms: list[str] = []
    tools: list[str] = []
    trajectory_ids: list[str] = []
    parent_ids: list[str] = []
    latent_states: list[LatentState] = []
    deltas: list[LatentDelta] = []
    for gene in genes:
        steps = stable_union(steps, gene.reasoning_steps, limit=10)
        terms = stable_union(terms, gene.trigger_terms, limit=18)
        tools = stable_union(tools, gene.tools_used, limit=12)
        trajectory_ids = stable_union(trajectory_ids, gene.source_trajectory_ids, limit=80)
        latent_states = merge_latent_states(latent_states, gene.latent_states)
        if gene.latent_delta:
            deltas.append(gene.latent_delta)
        parent_ids.append(gene.id)
    context = summarize_phrase(" / ".join(gene.task_context for gene in genes), limit=180)
    delta = summarize_phrase(" + ".join(gene.transformation_delta for gene in genes), limit=220)
    schema = "chromosome: " + " + ".join(sorted({gene.solution_schema for gene in genes}))
    embedding = mean_embedding([gene.embedding for gene in genes], embedding_model.dim)
    latent_encoder = HashLatentEncoder(embedding_model)
    latent_delta = merge_many_latent_deltas(deltas, latent_encoder) if deltas else None
    stats = GeneStats(
        success_count=sum(gene.stats.success_count for gene in genes),
        failure_count=sum(gene.stats.failure_count for gene in genes),
        reuse_count=sum(gene.stats.reuse_count for gene in genes),
        stability=sum(gene.stats.stability for gene in genes) / len(genes),
        average_utility=sum(gene.stats.average_utility for gene in genes) / len(genes),
    )
    return ReasoningGene(
        task_context=context,
        transformation_delta=delta,
        reasoning_steps=steps,
        solution_schema=schema,
        trigger_terms=terms,
        embedding=embedding,
        latent_states=latent_states,
        latent_delta=latent_delta,
        tools_used=tools,
        stats=stats,
        source_trajectory_ids=trajectory_ids,
        parent_gene_ids=parent_ids,
    )


def compatible_genes(left: ReasoningGene, right: ReasoningGene, similarity: float) -> bool:
    same_schema = left.solution_schema == right.solution_schema
    shared_terms = bool(set(left.trigger_terms) & set(right.trigger_terms))
    latent_similarity = 0.0
    if left.latent_delta and right.latent_delta:
        latent_similarity = cosine(left.latent_delta.vector, right.latent_delta.vector)
    return (
        cosine(left.embedding, right.embedding) >= similarity
        or latent_similarity >= similarity
        or (same_schema and shared_terms)
    )


def gene_value(gene: ReasoningGene) -> float:
    return clamp01(
        0.42 * gene.stats.success_rate
        + 0.24 * gene.stats.stability
        + 0.22 * gene.stats.average_utility
        + 0.12 * min(1.0, gene.stats.reuse_count / 10.0)
    )


def stable_union(left: list[str], right: list[str], limit: int) -> list[str]:
    result = list(left)
    seen = {item.casefold() for item in result}
    for item in right:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
        if len(result) >= limit:
            break
    return result


def dedupe_phrases(items: list[str], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        phrase = summarize_phrase(item, limit=140)
        key = " ".join(tokenize(phrase))
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(phrase)
        if len(result) >= limit:
            break
    return result


def summarize_phrase(text: str, limit: int = 120) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def latent_states_from_trajectory(
    trajectory: ReasoningTrajectory,
    encoder: LatentEncoder,
) -> list[LatentState]:
    states: list[LatentState] = [encoder.encode_state("task", trajectory.task, role="input")]
    for index, state in enumerate(trajectory.states, start=1):
        states.append(encoder.encode_state(f"s{index}", state, role="state"))
    for index, representation in enumerate(trajectory.intermediate_representations, start=1):
        states.append(encoder.encode_state(f"z{index}", representation, role="representation"))
    for index, action in enumerate(trajectory.actions, start=1):
        states.append(encoder.encode_state(f"a{index}", action, role="action"))
    if trajectory.final_answer:
        states.append(encoder.encode_state("answer", trajectory.final_answer, role="output"))
    return states


def build_latent_delta(
    states: list[LatentState],
    encoder: LatentEncoder,
) -> LatentDelta | None:
    if len(states) < 2:
        return None
    return encoder.encode_delta(states[0], states[-1], operator="trajectory_delta")


def merge_latent_states(left: list[LatentState], right: list[LatentState]) -> list[LatentState]:
    result = list(left)
    seen = {(state.role, " ".join(tokenize(state.text))) for state in result}
    for state in right:
        key = (state.role, " ".join(tokenize(state.text)))
        if key in seen:
            continue
        seen.add(key)
        result.append(state)
        if len(result) >= 24:
            break
    return result


def merge_latent_delta(
    left: LatentDelta,
    right: LatentDelta,
    encoder: LatentEncoder,
) -> LatentDelta:
    start = encoder.encode_state(
        "merged_start",
        f"{left.start.text} / {right.start.text}",
        role="input",
    )
    end = encoder.encode_state(
        "merged_end",
        f"{left.end.text} / {right.end.text}",
        role="output",
    )
    return encoder.encode_delta(start, end, operator="merged_delta")


def merge_many_latent_deltas(
    deltas: list[LatentDelta],
    encoder: LatentEncoder,
) -> LatentDelta:
    current = deltas[0]
    for delta in deltas[1:]:
        current = merge_latent_delta(current, delta, encoder)
    return current

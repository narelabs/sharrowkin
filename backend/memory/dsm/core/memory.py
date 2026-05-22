from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..indexing.category import CategoryTree
from ..storage.document import chunk_text, split_document
from ..indexing.embedding import EmbeddingModel, HashEmbeddingModel, cosine, normalize, top_terms
from ..retrieval.graph import MemoryGraph
from ..indexing.index import SegmentIndex
from ...optimized.cached_embedding import CachedEmbeddingModel
from .models import (
    ActiveContext,
    ConflictRecord,
    MemorySegment,
    PriorityVector,
    ReasoningStep,
    ReasoningTrace,
    RouteResult,
    now_ts,
)
from ..indexing.sparse import SparseIndex
from ..storage.storage import HeadStorage, JsonStorage


class DynamicSegmentedMemory:
    """Dynamic Segmented Memory engine.

    DSM state is ({S_i}, T, G): segments, hierarchy and graph. Queries route through
    categories, segment embeddings, graph expansion and priority scoring, then build
    a bounded active context instead of exposing the whole memory to the model.
    """

    def __init__(
        self,
        storage_path: str | Path | None = None,
        embedding_model: EmbeddingModel | None = None,
        segment_token_limit: int = 20_000,
        active_segment_limit: int = 5,
        active_token_budget: int = 100_000,
        index_backend: str = "auto",
        enable_cache: bool = True,
        cache_size: int = 10000,
    ):
        base_model = embedding_model or HashEmbeddingModel()
        self.embedding_model = CachedEmbeddingModel(base_model, cache_size=cache_size) if enable_cache else base_model
        self.segment_token_limit = segment_token_limit
        self.active_segment_limit = active_segment_limit
        self.active_token_budget = active_token_budget
        self.storage = JsonStorage(storage_path) if storage_path else HeadStorage()

        self.segments: dict[str, MemorySegment] = {}
        self.categories = CategoryTree(self.embedding_model)
        self.graph = MemoryGraph()
        self.index = SegmentIndex(index_backend)
        self.sparse_index = SparseIndex()
        self.conflicts: list[ConflictRecord] = []
        self.document_segments: dict[str, list[str]] = {}

        if self.storage.exists():
            self.load()

    def write(
        self,
        text: str,
        *,
        description: str | None = None,
        category_path: tuple[str, ...] | list[str] | str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        update_existing: bool = True,
        link_related: bool = True,
    ) -> list[MemorySegment]:
        chunks = chunk_text(text, self.segment_token_limit)
        written: list[MemorySegment] = []

        for chunk in chunks:
            chunk_description = description or summarize(chunk)
            path = normalize_path(category_path) if category_path else self.categories.choose_path(chunk)
            embedding = self.embedding_model.encode(f"{chunk_description}\n{chunk}")
            existing = self._find_existing(embedding) if update_existing else None

            if existing:
                merged = merge_text(existing.text, chunk, self.segment_token_limit)
                existing.update_text(merged, summarize(merged), self.embedding_model.encode(merged))
                existing.priorities.importance = max(existing.priorities.importance, importance)
                existing.priorities.touch(cosine(embedding, existing.embedding), boost=0.05)
                existing.metadata.update(metadata or {})
                segment = existing
            else:
                segment = MemorySegment(
                    text=chunk,
                    description=chunk_description,
                    category_path=tuple(path),
                    embedding=embedding,
                    priorities=PriorityVector(importance=importance),
                    metadata=metadata or {},
                )
                self.segments[segment.id] = segment
                self.categories.add_segment(segment)
                self.graph.add_node(segment.id)
                self._detect_conflicts_for(segment)

            written.append(segment)

        if link_related:
            self._link_related(written)

        self._rebuild_index()
        self.categories.refresh_embeddings(self.segments)
        return written

    def write_attractor(
        self,
        text: str,
        vector: list[float],
        *,
        description: str | None = None,
        category_path: tuple[str, ...] | list[str] | str = ("Attractors", "LogicGenes"),
        metadata: dict[str, Any] | None = None,
        importance: float = 0.9,
    ) -> MemorySegment:
        if len(vector) != self.embedding_model.dim:
            raise ValueError("attractor vector dimension must match DSM embedding dimension")
        path = normalize_path(category_path)
        segment = MemorySegment(
            text=text,
            description=description or summarize(text),
            category_path=tuple(path),
            embedding=normalize(vector),
            priorities=PriorityVector(importance=importance),
            metadata={"attractor": True, **(metadata or {})},
        )
        self.segments[segment.id] = segment
        self.categories.add_segment(segment)
        self.graph.add_node(segment.id)
        self.sparse_index.upsert(segment)
        self._link_related([segment])
        self._rebuild_index()
        self.categories.refresh_embeddings(self.segments)
        return segment

    def route(
        self,
        query: str,
        *,
        k: int | None = None,
        category_beam: int = 4,
        graph_hops: int = 2,
        similarity_floor: float = -1.0,
        dense_weight: float = 0.55,
        sparse_weight: float = 0.25,
        personal_dna_boost: float = 0.18,
    ) -> list[RouteResult]:
        if not self.segments:
            return []

        if self.sparse_index.size != len(self.segments):
            self.sparse_index.rebuild(self.segments)

        query_embedding = self.embedding_model.encode(query)
        sparse_limit = max((k or self.active_segment_limit) * 4, 64)
        sparse_hits = self.sparse_index.search(query, sparse_limit)
        sparse_scores = normalize_sparse_scores(sparse_hits)
        exact_matches = {segment_id: exact for segment_id, _, exact in sparse_hits}

        category_routes = self.categories.route_categories(query_embedding, beam_width=category_beam)
        category_scores = {node.path: score for node, score in category_routes}
        candidate_ids: set[str] = {segment_id for segment_id, _, _ in sparse_hits}

        for node, _ in category_routes:
            candidate_ids.update(node.segment_ids)
            for child in node.children.values():
                candidate_ids.update(child.segment_ids)

        direct_hits = self.index.search(query_embedding, max(k or self.active_segment_limit, 16))
        candidate_ids.update(segment_id for segment_id, score in direct_hits if score >= similarity_floor)

        seed_ids = [segment_id for segment_id, _ in direct_hits[: max(1, self.active_segment_limit)]]
        seed_ids.extend(segment_id for segment_id, _, _ in sparse_hits[: max(1, self.active_segment_limit)])
        graph_routes = self.graph.expand_weighted(seed_ids, max_hops=graph_hops)
        candidate_ids.update(graph_routes)

        scored: list[RouteResult] = []
        current_time = now_ts()
        for segment_id in candidate_ids:
            segment = self.segments.get(segment_id)
            if not segment:
                continue
            if segment_id in graph_routes:
                graph_distance, graph_weight = graph_routes[segment_id]
            elif any(segment_id == hit_id for hit_id, _ in direct_hits):
                graph_distance, graph_weight = 0, 1.0
            else:
                graph_distance, graph_weight = 99, 0.0

            similarity = cosine(query_embedding, segment.embedding)
            category_score = best_category_score(segment.category_path, category_scores)
            graph_bonus = 0.0 if graph_distance == 99 else 0.10 * graph_weight / (graph_distance + 1)
            age_seconds = current_time - segment.last_accessed_at
            priority_score = segment.priorities.total(similarity, age_seconds)
            sparse_score = sparse_scores.get(segment_id, 0.0)
            exact_match_count = exact_matches.get(segment_id, 0)
            dna_boost = personal_dna_boost if is_personal_dna_path(segment.category_path) else 0.0
            total = (
                dense_weight * similarity
                + sparse_weight * sparse_score
                + 0.24 * priority_score
                + 0.12 * category_score
                + graph_bonus
                + dna_boost
                + min(0.08, 0.02 * exact_match_count)
            )
            scored.append(
                RouteResult(
                    segment=segment,
                    similarity=similarity,
                    priority_score=priority_score,
                    graph_distance=graph_distance,
                    total_score=total,
                    category_score=category_score,
                    graph_weight=graph_weight,
                    sparse_score=sparse_score,
                    exact_matches=exact_match_count,
                )
            )

        scored.sort(reverse=True, key=lambda item: item.total_score)
        selected = scored[: max(0, k or self.active_segment_limit)]
        for item in selected:
            item.segment.touch(item.similarity)
        return selected

    def route_by_vector(
        self,
        query_embedding: list[float],
        *,
        k: int | None = None,
        graph_hops: int = 1,
        similarity_floor: float = -1.0,
        personal_dna_boost: float = 0.18,
    ) -> list[RouteResult]:
        if not self.segments:
            return []
        query = normalize(query_embedding)
        if len(query) != self.embedding_model.dim:
            raise ValueError("query vector dimension must match DSM embedding dimension")
        limit = max(k or self.active_segment_limit, 16)
        direct_hits = self.index.search(query, limit)
        candidate_ids = {segment_id for segment_id, score in direct_hits if score >= similarity_floor}
        graph_routes = self.graph.expand_weighted(
            [segment_id for segment_id, _ in direct_hits[: max(1, self.active_segment_limit)]],
            max_hops=graph_hops,
        )
        candidate_ids.update(graph_routes)
        direct_scores = dict(direct_hits)
        scored: list[RouteResult] = []
        current_time = now_ts()
        for segment_id in candidate_ids:
            segment = self.segments.get(segment_id)
            if not segment:
                continue
            graph_distance, graph_weight = graph_routes.get(
                segment_id,
                (0 if segment_id in direct_scores else 99, 1.0 if segment_id in direct_scores else 0.0),
            )
            similarity = cosine(query, segment.embedding)
            priority_score = segment.priorities.total(similarity, current_time - segment.last_accessed_at)
            graph_bonus = 0.0 if graph_distance == 99 else 0.10 * graph_weight / (graph_distance + 1)
            dna_boost = personal_dna_boost if is_personal_dna_path(segment.category_path) else 0.0
            total = 0.66 * similarity + 0.24 * priority_score + graph_bonus + dna_boost
            scored.append(
                RouteResult(
                    segment=segment,
                    similarity=similarity,
                    priority_score=priority_score,
                    graph_distance=graph_distance,
                    total_score=total,
                    graph_weight=graph_weight,
                )
            )
        scored.sort(reverse=True, key=lambda item: item.total_score)
        selected = scored[: max(0, k or self.active_segment_limit)]
        for item in selected:
            item.segment.touch(item.similarity)
        return selected

    def extract_personal_dna(self, message: str) -> list[MemorySegment]:
        extracted: list[MemorySegment] = []
        for fact in personal_dna_facts(message):
            extracted.extend(
                self.write(
                    fact,
                    category_path=("User", "Danil", "Profile"),
                    importance=0.96,
                    metadata={"tiido_dna": True, "source": "user_message"},
                )
            )
        return extracted

    def learn_tiido_turn(
        self,
        query: str,
        answer: str,
        active_context: ActiveContext | None = None,
    ) -> list[MemorySegment]:
        self.extract_personal_dna(query)
        metadata: dict[str, Any] = {"tiido_turn": True}
        if active_context:
            metadata["active_segment_ids"] = active_context.segment_ids
        return self.update_from_interaction(
            query,
            answer,
            importance=0.82,
            metadata=metadata,
        )

    def reason(
        self,
        query: str,
        *,
        loops: int = 3,
        k: int | None = None,
        token_budget: int | None = None,
    ) -> ReasoningTrace:
        steps: list[ReasoningStep] = []
        seen_segment_ids: set[str] = set()
        working_query = query
        for _ in range(max(1, loops)):
            routed = self.route(working_query, k=k or self.active_segment_limit)
            selected_ids = [item.segment.id for item in routed]
            focus_terms = next_focus_terms(working_query, routed, seen_segment_ids)
            observation = "; ".join(item.segment.description for item in routed[:3])
            steps.append(
                ReasoningStep(
                    query=working_query,
                    selected_ids=selected_ids,
                    focus_terms=focus_terms,
                    observation=observation,
                )
            )
            new_ids = set(selected_ids) - seen_segment_ids
            seen_segment_ids.update(selected_ids)
            if not focus_terms or not new_ids:
                break
            working_query = f"{query} {' '.join(focus_terms)}"

        final_query = " ".join([query, *(term for step in steps for term in step.focus_terms)])
        context = self.active_context(final_query, k=k, token_budget=token_budget)
        return ReasoningTrace(original_query=query, steps=steps, context=context)

    def upsert_document(
        self,
        document_id: str,
        text: str,
        *,
        category_path: tuple[str, ...] | list[str] | str | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
        chunk_token_limit: int | None = None,
    ) -> dict[str, Any]:
        chunks = split_document(document_id, text, chunk_token_limit or self.segment_token_limit)
        previous_ids = set(self.document_segments.get(document_id, []))
        next_ids: list[str] = []
        changed = 0
        created = 0

        for chunk in chunks:
            segment_id = chunk.stable_id
            next_ids.append(segment_id)
            chunk_metadata = {
                **(metadata or {}),
                "document_id": document_id,
                "chunk_index": chunk.chunk_index,
                "digest": chunk.digest,
            }
            existing = self.segments.get(segment_id)
            if existing and existing.metadata.get("digest") == chunk.digest:
                continue
            embedding = self.embedding_model.encode(chunk.text)
            if existing:
                existing.update_text(chunk.text, summarize(chunk.text), embedding)
                existing.metadata.update(chunk_metadata)
                existing.priorities.importance = max(existing.priorities.importance, importance)
                changed += 1
            else:
                path = normalize_path(category_path) if category_path else self.categories.choose_path(chunk.text)
                existing = MemorySegment(
                    id=segment_id,
                    text=chunk.text,
                    description=summarize(chunk.text),
                    category_path=tuple(path),
                    embedding=embedding,
                    priorities=PriorityVector(importance=importance),
                    metadata=chunk_metadata,
                )
                self.segments[existing.id] = existing
                self.categories.add_segment(existing)
                self.graph.add_node(existing.id)
                created += 1
            self.sparse_index.upsert(existing)
            self._detect_conflicts_for(existing)

        removed_ids = previous_ids - set(next_ids)
        for segment_id in removed_ids:
            segment = self.segments.get(segment_id)
            if segment:
                self.categories.remove_segment(segment)
                self.graph.remove_node(segment.id)
                self.sparse_index.remove(segment.id)
                del self.segments[segment.id]

        self.document_segments[document_id] = next_ids
        changed_segments = [self.segments[segment_id] for segment_id in next_ids if segment_id in self.segments]
        self._link_related(changed_segments)
        self._rebuild_index()
        self.categories.refresh_embeddings(self.segments)
        return {
            "document_id": document_id,
            "chunks": len(chunks),
            "created": created,
            "updated": changed,
            "removed": len(removed_ids),
            "unchanged": len(chunks) - created - changed,
        }

    def active_context(
        self,
        query: str,
        *,
        k: int | None = None,
        token_budget: int | None = None,
    ) -> ActiveContext:
        budget = token_budget or self.active_token_budget
        selected: list[RouteResult] = []
        used = 0
        for item in self.route(query, k=k):
            cost = item.segment.estimated_tokens
            if selected and used + cost > budget:
                continue
            selected.append(item)
            used += cost

        global_summary = self._global_summary(selected)
        parts = [
            f"QUERY:\n{query}",
            f"GLOBAL SUMMARY TOKENS:\n{global_summary}",
        ]
        for index, item in enumerate(selected, start=1):
            segment = item.segment
            path = " → ".join(segment.category_path)
            parts.append(
                "\n".join(
                    [
                        f"[SEGMENT {index}] id={segment.id}",
                        f"category={path}",
                        f"description={segment.description}",
                        (
                            "scores="
                            f"sim:{item.similarity:.3f} "
                            f"priority:{item.priority_score:.3f} "
                            f"category:{item.category_score:.3f} "
                            f"total:{item.total_score:.3f}"
                        ),
                        "text:",
                        segment.text,
                    ]
                )
            )

        return ActiveContext(
            query=query,
            selected=selected,
            context_text="\n\n---\n\n".join(parts),
            token_budget=budget,
            estimated_tokens=used + len(query.split()) + len(global_summary.split()),
            global_summary=global_summary,
        )

    def update_from_interaction(
        self,
        query: str,
        answer: str,
        *,
        importance: float = 0.6,
        metadata: dict[str, Any] | None = None,
    ) -> list[MemorySegment]:
        routed = self.route(query, k=1)
        if routed and routed[0].similarity >= 0.62:
            target = routed[0].segment
            text = merge_text(target.text, f"Query: {query}\nAnswer: {answer}", self.segment_token_limit)
            target.update_text(text, summarize(text), self.embedding_model.encode(text))
            target.priorities.importance = max(target.priorities.importance, importance)
            target.priorities.touch(routed[0].similarity)
            target.metadata.update(metadata or {})
            self._detect_conflicts_for(target)
            self._rebuild_index()
            self.categories.refresh_embeddings(self.segments)
            return [target]

        return self.write(
            f"Query: {query}\nAnswer: {answer}",
            description=summarize(query),
            importance=importance,
            metadata=metadata,
        )

    def rebuild_structure(self) -> int:
        moved = self.categories.rebuild_dynamic_clusters(self.segments)
        self._link_related(list(self.segments.values()))
        self.check_consistency()
        self._rebuild_index()
        return moved

    def compress(
        self,
        *,
        similarity_threshold: float = 0.78,
        min_group_size: int = 2,
        max_summary_tokens: int | None = None,
        preserve_sources: bool = False,
    ) -> list[MemorySegment]:
        groups = self._compression_groups(similarity_threshold, min_group_size)
        compressed: list[MemorySegment] = []
        for group in groups:
            source_ids = [segment.id for segment in group]
            merged_text = compress_segments(group, max_summary_tokens or self.segment_token_limit)
            category_path = longest_common_path([segment.category_path for segment in group])
            importance = max(segment.priorities.importance for segment in group)
            segment = MemorySegment(
                text=merged_text,
                description=summarize(merged_text),
                category_path=category_path,
                embedding=self.embedding_model.encode(merged_text),
                priorities=PriorityVector(
                    relevance=max(segment.priorities.relevance for segment in group),
                    importance=importance,
                    recency=max(segment.priorities.recency for segment in group),
                    frequency=max(segment.priorities.frequency for segment in group),
                ),
                metadata={"compressed": True, "source_count": len(group)},
                compressed_from=source_ids,
            )
            self.segments[segment.id] = segment
            self.categories.add_segment(segment)
            self.graph.add_node(segment.id)
            if preserve_sources:
                for source in group:
                    self.graph.add_edge(
                        segment.id,
                        source.id,
                        relation="compression",
                        weight=0.95,
                        reason="summary segment preserves source memory",
                    )
            else:
                for source in group:
                    self.categories.remove_segment(source)
                    self.graph.remove_node(source.id)
                    self.sparse_index.remove(source.id)
                    self.segments.pop(source.id, None)
            compressed.append(segment)

        if compressed:
            self._link_related(compressed)
            self._rebuild_index()
            self.categories.refresh_embeddings(self.segments)
        return compressed

    def maintain(
        self,
        *,
        max_segments: int | None = None,
        min_priority: float = 0.08,
        compress_similarity: float = 0.78,
    ) -> dict[str, Any]:
        self.decay_priorities()
        compressed = self.compress(similarity_threshold=compress_similarity)
        removed = self.prune(max_segments=max_segments, min_priority=min_priority)
        conflicts = self.check_consistency()
        return {
            "compressed": len(compressed),
            "pruned": len(removed),
            "conflicts": len(conflicts),
        }

    def prune(
        self,
        *,
        max_segments: int | None = None,
        min_priority: float = 0.08,
        archive_path: str | Path | None = None,
    ) -> list[MemorySegment]:
        current_time = now_ts()
        ranked = sorted(
            self.segments.values(),
            key=lambda segment: segment.priorities.total(0.0, current_time - segment.last_accessed_at),
        )
        remove_ids: set[str] = set()

        for segment in ranked:
            score = segment.priorities.total(0.0, current_time - segment.last_accessed_at)
            if score < min_priority:
                remove_ids.add(segment.id)

        if max_segments is not None and len(self.segments) - len(remove_ids) > max_segments:
            needed = len(self.segments) - len(remove_ids) - max_segments
            for segment in ranked:
                if needed <= 0:
                    break
                if segment.id not in remove_ids:
                    remove_ids.add(segment.id)
                    needed -= 1

        removed = [self.segments[segment_id] for segment_id in remove_ids if segment_id in self.segments]
        if archive_path and removed:
            archive = JsonStorage(archive_path)
            archive.save({"segments": [segment.to_dict() for segment in removed]})

        for segment in removed:
            self.categories.remove_segment(segment)
            self.graph.remove_node(segment.id)
            self.sparse_index.remove(segment.id)
            del self.segments[segment.id]

        if removed:
            self._rebuild_index()
            self.categories.refresh_embeddings(self.segments)
        return removed

    def check_consistency(self) -> list[ConflictRecord]:
        self.conflicts = []
        for left in self.segments.values():
            for right in self.segments.values():
                if left.id >= right.id:
                    continue
                if not related_for_conflict(left, right):
                    continue
                for conflict in detect_pair_conflicts(left, right):
                    self._add_conflict(conflict)
                    self.graph.add_edge(
                        left.id,
                        right.id,
                        relation="conflict",
                        weight=max(0.4, conflict.severity),
                        reason=conflict.reason,
                    )
        return list(self.conflicts)

    def conflicts_for(self, segment_id: str) -> list[ConflictRecord]:
        return [
            conflict
            for conflict in self.conflicts
            if not conflict.resolved and segment_id in (conflict.left_id, conflict.right_id)
        ]

    def decay_priorities(self, amount: float = 0.02) -> None:
        for segment in self.segments.values():
            segment.priorities.decay(amount)

    def save(self) -> None:
        self.storage.save(self.snapshot())

    def snapshot(self, path: str | Path | None = None) -> dict[str, Any]:
        data = {
            "version": 1,
            "segment_token_limit": self.segment_token_limit,
            "active_segment_limit": self.active_segment_limit,
            "active_token_budget": self.active_token_budget,
            "embedding_dim": self.embedding_model.dim,
            "index_backend": self.index.backend,
            "segments": [segment.to_dict() for segment in self.segments.values()],
            "categories": self.categories.to_dict(),
            "graph": self.graph.to_dict(),
            "sparse_index": self.sparse_index.to_dict(),
            "document_segments": self.document_segments,
            "conflicts": [conflict.to_dict() for conflict in self.conflicts],
        }
        if path is not None:
            JsonStorage(path).save(data)
        return data

    def load(self) -> None:
        data = self.storage.load()
        self.load_snapshot(data)

    def load_snapshot(self, data: dict[str, Any]) -> None:
        self.segment_token_limit = int(data.get("segment_token_limit", self.segment_token_limit))
        self.active_segment_limit = int(data.get("active_segment_limit", self.active_segment_limit))
        self.active_token_budget = int(data.get("active_token_budget", self.active_token_budget))
        self.index.backend = str(data.get("index_backend", self.index.backend))
        self.segments = {
            segment.id: segment
            for segment in (
                MemorySegment.from_dict(item) for item in data.get("segments", [])
            )
        }
        if data.get("categories"):
            self.categories = CategoryTree.from_dict(self.embedding_model, data["categories"])
        else:
            self.categories = CategoryTree(self.embedding_model)
            for segment in self.segments.values():
                self.categories.add_segment(segment)
        self.graph = MemoryGraph.from_dict(data.get("graph", {}))
        self.sparse_index = SparseIndex.from_dict(data.get("sparse_index", {}))
        if self.sparse_index.size == 0 and self.segments:
            self.sparse_index.rebuild(self.segments)
        self.document_segments = {
            str(document_id): [str(segment_id) for segment_id in segment_ids]
            for document_id, segment_ids in data.get("document_segments", {}).items()
        }
        self.conflicts = [
            ConflictRecord.from_dict(item) for item in data.get("conflicts", [])
        ]
        for segment in self.segments.values():
            self.graph.add_node(segment.id)
            for linked_id in list(segment.links):
                if linked_id in self.segments:
                    self.graph.add_edge(segment.id, linked_id, relation="legacy")
        self._rebuild_index()
        self.categories.refresh_embeddings(self.segments)

    def export_json(self, path: str | Path) -> None:
        self.snapshot(path)

    def stats(self) -> dict[str, Any]:
        nodes = self.categories.root.walk()
        edge_count = sum(len(v) for v in self.graph.edges.values()) // 2
        tokens = sum(segment.estimated_tokens for segment in self.segments.values())
        return {
            "segments": len(self.segments),
            "categories": len(nodes),
            "graph_edges": edge_count,
            "estimated_tokens": tokens,
            "index_size": self.index.size,
            "index_backend": self.index.backend_name,
            "sparse_index_size": self.sparse_index.size,
            "documents": len(self.document_segments),
            "conflicts": len([conflict for conflict in self.conflicts if not conflict.resolved]),
            "compressed_segments": len(
                [segment for segment in self.segments.values() if segment.compressed_from]
            ),
            "segment_token_limit": self.segment_token_limit,
            "active_segment_limit": self.active_segment_limit,
            "active_token_budget": self.active_token_budget,
        }

    def _find_existing(self, embedding: list[float], threshold: float = 0.84) -> MemorySegment | None:
        if not self.segments:
            return None
        hits = self.index.search(embedding, 1)
        if not hits:
            return None
        segment_id, score = hits[0]
        if score >= threshold:
            return self.segments.get(segment_id)
        return None

    def _link_related(self, segments: list[MemorySegment], threshold: float = 0.58, max_links: int = 4) -> None:
        for segment in segments:
            self.graph.add_node(segment.id)
            candidates = [
                other
                for other in self.segments.values()
                if other.id != segment.id
            ]
            scored = [
                link_score(segment, other, cosine(segment.embedding, other.embedding))
                for other in candidates
                if share_terms(segment.text, other.text)
                or same_parent(segment.category_path, other.category_path)
                or cosine(segment.embedding, other.embedding) >= threshold
            ]
            scored.sort(reverse=True, key=lambda item: item[0])
            for score, other, relation, reason in scored[:max_links]:
                self.graph.add_edge(
                    segment.id,
                    other.id,
                    relation=relation,
                    weight=score,
                    reason=reason,
                )
                segment.links.add(other.id)
                other.links.add(segment.id)

    def _compression_groups(self, threshold: float, min_group_size: int) -> list[list[MemorySegment]]:
        visited: set[str] = set()
        groups: list[list[MemorySegment]] = []
        by_category: dict[tuple[str, ...], list[MemorySegment]] = defaultdict(list)
        for segment in self.segments.values():
            if not segment.compressed_from:
                by_category[segment.category_path].append(segment)

        for category_segments in by_category.values():
            for segment in category_segments:
                if segment.id in visited:
                    continue
                group = [segment]
                for other in category_segments:
                    if other.id == segment.id or other.id in visited:
                        continue
                    if cosine(segment.embedding, other.embedding) >= threshold or share_terms(segment.text, other.text):
                        group.append(other)
                if len(group) >= min_group_size:
                    for item in group:
                        visited.add(item.id)
                    groups.append(group)
        return groups

    def _detect_conflicts_for(self, segment: MemorySegment) -> None:
        for other in self.segments.values():
            if other.id == segment.id or not related_for_conflict(segment, other):
                continue
            for conflict in detect_pair_conflicts(segment, other):
                self._add_conflict(conflict)
                self.graph.add_edge(
                    segment.id,
                    other.id,
                    relation="conflict",
                    weight=max(0.4, conflict.severity),
                    reason=conflict.reason,
                )

    def _add_conflict(self, conflict: ConflictRecord) -> None:
        keys = {item.key() for item in self.conflicts}
        if conflict.key() not in keys:
            self.conflicts.append(conflict)

    def _rebuild_index(self) -> None:
        self.index.rebuild(self.segments)
        self.sparse_index.rebuild(self.segments)

    def _global_summary(self, selected: list[RouteResult]) -> str:
        if not selected:
            return "No active memory segments selected."
        lines = []
        for item in selected:
            segment = item.segment
            lines.append(
                f"- {' → '.join(segment.category_path)}: {segment.description} "
                f"(score={item.total_score:.3f})"
            )
        return "\n".join(lines)


def summarize(text: str, max_words: int = 24) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    words = compact.split()
    if not words:
        return "Empty segment"
    if len(words) <= max_words:
        return compact
    terms = top_terms(compact, limit=4)
    prefix = " ".join(words[:max_words])
    if terms:
        return f"{prefix}… [{', '.join(terms)}]"
    return f"{prefix}…"


def merge_text(existing: str, addition: str, token_limit: int) -> str:
    old = existing.strip()
    new = addition.strip()
    if not old:
        merged = new
    elif new in old:
        merged = old
    else:
        merged = f"{old}\n\n{new}"
    words = merged.split()
    if len(words) <= token_limit:
        return merged
    return " ".join(words[-token_limit:])


def normalize_path(path: tuple[str, ...] | list[str] | str) -> tuple[str, ...]:
    if isinstance(path, str):
        parts = re.split(r"[>/→|]+", path)
    else:
        parts = [str(part) for part in path]
    cleaned = tuple(part.strip() for part in parts if part and part.strip())
    return cleaned or ("General",)


def best_category_score(path: tuple[str, ...], category_scores: dict[tuple[str, ...], float]) -> float:
    best = 0.0
    for i in range(len(path) + 1):
        prefix = path[:i]
        best = max(best, category_scores.get(prefix, 0.0))
    return best


def normalize_sparse_scores(hits: list[tuple[str, float, int]]) -> dict[str, float]:
    if not hits:
        return {}
    max_score = max((score for _, score, _ in hits), default=0.0)
    max_exact = max((exact for _, _, exact in hits), default=0)
    scores: dict[str, float] = {}
    for segment_id, score, exact in hits:
        bm25 = score / max_score if max_score > 0 else 0.0
        exact_score = exact / max_exact if max_exact > 0 else 0.0
        scores[segment_id] = min(1.0, 0.65 * bm25 + 0.35 * exact_score)
    return scores


def next_focus_terms(
    query: str,
    routed: list[RouteResult],
    seen_segment_ids: set[str],
    limit: int = 4,
) -> list[str]:
    query_terms = set(top_terms(query, limit=12))
    focus: list[str] = []
    for item in routed:
        if item.segment.id in seen_segment_ids:
            continue
        for term in top_terms(item.segment.text, limit=8):
            if term not in query_terms and term not in focus:
                focus.append(term)
            if len(focus) >= limit:
                return focus
    return focus


def is_personal_dna_path(path: tuple[str, ...]) -> bool:
    return path[:3] == ("User", "Danil", "Profile") or path[:2] == ("Identity", "Core")


def personal_dna_facts(message: str) -> list[str]:
    compact = re.sub(r"\s+", " ", message or "").strip()
    if not compact:
        return []
    lower = compact.lower()
    signals = (
        "я ",
        "мне ",
        "мой ",
        "моя ",
        "мои ",
        "меня ",
        "люблю",
        "хочу",
        "надо",
        "запомни",
        "danil",
        "данил",
        "tiido",
        "dsm",
    )
    if not any(signal in lower for signal in signals):
        return []
    return [f"Danil profile memory: {compact}"]


def share_terms(left: str, right: str) -> bool:
    left_terms = set(top_terms(left, limit=8))
    right_terms = set(top_terms(right, limit=8))
    return bool(left_terms & right_terms)


def link_score(
    left: MemorySegment,
    right: MemorySegment,
    similarity: float,
) -> tuple[float, MemorySegment, str, str]:
    shared = set(top_terms(left.text, limit=8)) & set(top_terms(right.text, limit=8))
    same_topic = same_parent(left.category_path, right.category_path)
    relation = "semantic"
    reasons: list[str] = []
    score = max(0.0, min(1.0, similarity))
    if shared:
        relation = "shared_terms"
        score = max(score, min(1.0, 0.45 + 0.08 * len(shared)))
        reasons.append(f"shared terms: {', '.join(sorted(shared)[:5])}")
    if same_topic:
        relation = f"{relation}+category"
        score = max(score, 0.62)
        reasons.append("same category branch")
    if similarity >= 0.58:
        reasons.append(f"embedding similarity {similarity:.3f}")
    return score, right, relation, "; ".join(reasons)


def same_parent(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return False
    depth = min(len(left), len(right), 2)
    return left[:depth] == right[:depth]


def longest_common_path(paths: list[tuple[str, ...]]) -> tuple[str, ...]:
    if not paths:
        return ("General",)
    shortest = min(len(path) for path in paths)
    common: list[str] = []
    for index in range(shortest):
        values = {path[index] for path in paths}
        if len(values) != 1:
            break
        common.append(paths[0][index])
    return tuple(common) or paths[0][:1] or ("General",)


def compress_segments(segments: list[MemorySegment], token_limit: int) -> str:
    descriptions = []
    facts = []
    for segment in segments:
        descriptions.append(f"- {' → '.join(segment.category_path)}: {segment.description}")
        for sentence in split_sentences(segment.text):
            if sentence not in facts:
                facts.append(sentence)
    text = "Compressed memory summary:\n" + "\n".join(descriptions) + "\n\nFacts:\n"
    text += "\n".join(f"- {fact}" for fact in facts)
    words = text.split()
    if len(words) <= token_limit:
        return text
    return " ".join(words[:token_limit])


def related_for_conflict(left: MemorySegment, right: MemorySegment) -> bool:
    return (
        same_parent(left.category_path, right.category_path)
        or share_terms(left.text, right.text)
        or cosine(left.embedding, right.embedding) >= 0.45
    )


def detect_pair_conflicts(left: MemorySegment, right: MemorySegment) -> list[ConflictRecord]:
    left_facts = extract_numeric_facts(left.text)
    right_facts = extract_numeric_facts(right.text)
    conflicts: list[ConflictRecord] = []
    for left_fact in left_facts:
        for right_fact in right_facts:
            if left_fact["subject"] != right_fact["subject"]:
                continue
            if left_fact["unit"] != right_fact["unit"]:
                continue
            if left_fact["value"] == right_fact["value"]:
                continue
            delta = abs(left_fact["value"] - right_fact["value"])
            base = max(abs(left_fact["value"]), abs(right_fact["value"]), 1.0)
            severity = min(1.0, delta / base)
            conflicts.append(
                ConflictRecord(
                    left_id=left.id,
                    right_id=right.id,
                    field=left_fact["subject"],
                    left_value=left_fact["raw"],
                    right_value=right_fact["raw"],
                    severity=severity,
                    reason="same subject has different numeric values",
                )
            )
    return conflicts


def extract_numeric_facts(text: str) -> list[dict[str, Any]]:
    pattern = re.compile(
        r"(?P<context>(?:[A-Za-zА-Яа-я0-9_+-]+\s+){0,5})"
        r"(?P<value>\d+(?:[.,]\d+)?)\s*"
        r"(?P<unit>₽|руб(?:\.|лей|ля)?|usd|eur|dollars?|percent|%)?",
        re.IGNORECASE,
    )
    facts: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        context = normalize_subject_context(match.group("context"))
        terms = top_terms(context, limit=4)
        if not terms:
            continue
        value = float(match.group("value").replace(",", "."))
        unit = (match.group("unit") or "number").lower().rstrip(".")
        subject = " ".join(terms)
        facts.append(
            {
                "subject": subject,
                "value": value,
                "unit": unit,
                "raw": match.group(0).strip(),
            }
        )
    return facts


def normalize_subject_context(context: str) -> str:
    stopwords = {
        "за",
        "на",
        "в",
        "и",
        "я",
        "ты",
        "он",
        "она",
        "купил",
        "купила",
        "купили",
        "стоил",
        "стоила",
        "стоит",
        "цена",
        "цены",
        "price",
        "cost",
        "bought",
        "paid",
        "for",
        "the",
        "a",
        "an",
    }
    tokens = [token for token in top_terms(context.lower(), limit=8) if token not in stopwords]
    return " ".join(tokens)


def split_sentences(text: str) -> list[str]:
    return [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text)
        if part.strip()
    ]


def sparse_attention_cost(active_tokens: int, total_tokens: int) -> dict[str, float]:
    active = max(0, active_tokens)
    total = max(active, total_tokens)
    dense = float(total * total)
    sparse = float(active * active)
    return {
        "dense_attention_ops": dense,
        "active_attention_ops": sparse,
        "reduction_ratio": math.inf if sparse == 0 else dense / sparse,
    }

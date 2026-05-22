"""Context linker for connecting code entities with their broader context.

This module links code entities to:
- Documentation (README, docstrings, comments)
- Git history (commits, authors, change frequency)
- Cross-references (callers, callees, dependencies)
- Related entities (similar functions, related classes)
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .semantic_graph import CodeNode, SemanticGraph


@dataclass
class CodeContext:
    """Rich context for a code entity."""

    node_id: str

    # Documentation context
    docstring: str = ""
    inline_comments: list[str] = field(default_factory=list)
    related_docs: list[dict[str, str]] = field(default_factory=list)  # [{title, path, section}]

    # Git context
    last_modified_by: str = ""
    last_modified_date: str = ""
    change_frequency: int = 0  # Number of times modified
    related_commits: list[dict[str, str]] = field(default_factory=list)  # [{hash, message, author, date}]

    # Cross-reference context
    callers: list[str] = field(default_factory=list)  # Functions that call this
    callees: list[str] = field(default_factory=list)  # Functions this calls
    dependencies: list[str] = field(default_factory=list)  # Modules/classes this depends on
    dependents: list[str] = field(default_factory=list)  # Modules/classes that depend on this

    # Semantic context
    similar_entities: list[tuple[str, float]] = field(default_factory=list)  # [(node_id, similarity_score)]
    related_patterns: list[str] = field(default_factory=list)  # Design patterns this participates in

    # Usage context
    usage_examples: list[str] = field(default_factory=list)  # Code snippets showing usage
    test_coverage: float = 0.0  # Percentage of lines covered by tests

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "node_id": self.node_id,
            "docstring": self.docstring,
            "inline_comments": self.inline_comments,
            "related_docs": self.related_docs,
            "last_modified_by": self.last_modified_by,
            "last_modified_date": self.last_modified_date,
            "change_frequency": self.change_frequency,
            "related_commits": self.related_commits,
            "callers": self.callers,
            "callees": self.callees,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "similar_entities": self.similar_entities,
            "related_patterns": self.related_patterns,
            "usage_examples": self.usage_examples,
            "test_coverage": self.test_coverage,
        }


class ContextLinker:
    """Links code entities with their broader context."""

    def __init__(self, semantic_graph: SemanticGraph, workspace: Path) -> None:
        self.graph = semantic_graph
        self.workspace = workspace
        self.contexts: dict[str, CodeContext] = {}

    def build_context(self, node_id: str) -> CodeContext:
        """Build rich context for a code entity."""
        node = self.graph.get_node(node_id)
        if not node:
            return CodeContext(node_id=node_id)

        context = CodeContext(node_id=node_id)

        # Documentation context
        context.docstring = node.docstring
        context.inline_comments = self._extract_inline_comments(node)
        context.related_docs = node.metadata.get("doc_links", [])

        # Git context
        git_info = self._get_git_context(node)
        context.last_modified_by = git_info.get("author", "")
        context.last_modified_date = git_info.get("date", "")
        context.change_frequency = git_info.get("frequency", 0)
        context.related_commits = git_info.get("commits", [])

        # Cross-reference context
        context.callers = self._find_callers(node)
        context.callees = self._find_callees(node)
        context.dependencies = self._find_dependencies(node)
        context.dependents = self._find_dependents(node)

        # Semantic context
        context.similar_entities = self._find_similar_entities(node)
        context.related_patterns = node.metadata.get("detected_patterns", [])

        # Usage context
        context.usage_examples = self._find_usage_examples(node)
        context.test_coverage = self._calculate_test_coverage(node)

        self.contexts[node_id] = context
        return context

    def get_context(self, node_id: str) -> CodeContext | None:
        """Get cached context or build new one."""
        if node_id in self.contexts:
            return self.contexts[node_id]
        return self.build_context(node_id)

    def get_change_impact(self, node_id: str) -> dict[str, Any]:
        """Analyze the impact of changing a code entity."""
        context = self.get_context(node_id)
        if not context:
            return {"error": "Node not found"}

        # Direct impact: entities that directly depend on this
        direct_impact = set(context.dependents + context.callers)

        # Indirect impact: entities that depend on the direct dependents
        indirect_impact = set()
        for dep_id in direct_impact:
            dep_context = self.get_context(dep_id)
            if dep_context:
                indirect_impact.update(dep_context.dependents)
                indirect_impact.update(dep_context.callers)

        # Remove direct impact from indirect to avoid duplication
        indirect_impact -= direct_impact
        indirect_impact.discard(node_id)

        # Test impact: tests that cover this entity
        test_files = self._find_test_files(node_id)

        return {
            "node_id": node_id,
            "direct_impact": list(direct_impact),
            "indirect_impact": list(indirect_impact),
            "total_affected": len(direct_impact) + len(indirect_impact),
            "test_files": test_files,
            "change_frequency": context.change_frequency,
            "risk_level": self._assess_risk_level(len(direct_impact), len(indirect_impact), context.change_frequency),
        }

    def find_related_code(self, node_id: str, max_results: int = 10) -> list[tuple[str, str, float]]:
        """Find code entities related to the given node.

        Returns:
            List of (node_id, relationship_type, relevance_score) tuples
        """
        context = self.get_context(node_id)
        if not context:
            return []

        related = []

        # Direct callers (high relevance)
        for caller_id in context.callers[:5]:
            related.append((caller_id, "caller", 0.9))

        # Direct callees (high relevance)
        for callee_id in context.callees[:5]:
            related.append((callee_id, "callee", 0.85))

        # Dependencies (medium relevance)
        for dep_id in context.dependencies[:5]:
            related.append((dep_id, "dependency", 0.7))

        # Similar entities (medium relevance)
        for similar_id, score in context.similar_entities[:5]:
            related.append((similar_id, "similar", score * 0.6))

        # Sort by relevance and return top results
        related.sort(key=lambda x: x[2], reverse=True)
        return related[:max_results]

    def get_context_summary(self, node_id: str) -> str:
        """Generate a human-readable context summary for LLM consumption."""
        context = self.get_context(node_id)
        if not context:
            return f"No context available for {node_id}"

        lines = [f"Context for {node_id}:", ""]

        # Documentation
        if context.docstring:
            lines.append(f"Documentation: {context.docstring[:200]}...")

        # Git history
        if context.last_modified_by:
            lines.append(f"Last modified by {context.last_modified_by} on {context.last_modified_date}")
        if context.change_frequency > 0:
            lines.append(f"Changed {context.change_frequency} times (hotspot)")

        # Dependencies
        if context.callers:
            lines.append(f"Called by: {', '.join(context.callers[:5])}")
        if context.callees:
            lines.append(f"Calls: {', '.join(context.callees[:5])}")

        # Patterns
        if context.related_patterns:
            lines.append(f"Design patterns: {', '.join(context.related_patterns)}")

        # Test coverage
        if context.test_coverage > 0:
            lines.append(f"Test coverage: {context.test_coverage:.1f}%")

        return "\n".join(lines)

    def _extract_inline_comments(self, node: CodeNode) -> list[str]:
        """Extract inline comments from source code."""
        if not node.file_path or not node.source_code:
            return []

        comments = []
        try:
            lines = node.source_code.split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#") and not stripped.startswith("##"):
                    comment = stripped[1:].strip()
                    if comment and len(comment) > 3:  # Skip trivial comments
                        comments.append(comment)
        except Exception:
            pass

        return comments

    def _get_git_context(self, node: CodeNode) -> dict[str, Any]:
        """Get git history context for a node."""
        if not node.file_path:
            return {}

        # Check if file is in git hotspots
        frequency = 0
        for hotspot_path, count in self.graph.git_hotspots:
            if node.file_path.endswith(hotspot_path) or hotspot_path.endswith(node.file_path):
                frequency = count
                break

        # Find related commits
        related_commits = []
        for commit in self.graph.recent_commits[:20]:
            # Simple heuristic: commit mentions the file or function name
            if node.file_path in commit.get("message", "") or node.name in commit.get("message", ""):
                related_commits.append(commit)

        result = {"frequency": frequency, "commits": related_commits}

        if related_commits:
            result["author"] = related_commits[0].get("author", "")
            result["date"] = related_commits[0].get("date", "")

        return result

    def _find_callers(self, node: CodeNode) -> list[str]:
        """Find functions that call this node."""
        callers = []

        # Search through all function nodes
        for other_node in self.graph.nodes.values():
            if other_node.id == node.id:
                continue

            # Check if other_node calls this node
            call_targets = other_node.metadata.get("calls", [])
            if node.id in call_targets or node.name in call_targets:
                callers.append(other_node.id)

        return callers

    def _find_callees(self, node: CodeNode) -> list[str]:
        """Find functions that this node calls."""
        return node.metadata.get("calls", [])

    def _find_dependencies(self, node: CodeNode) -> list[str]:
        """Find modules/classes this node depends on."""
        return node.metadata.get("imports", [])

    def _find_dependents(self, node: CodeNode) -> list[str]:
        """Find modules/classes that depend on this node."""
        dependents = []

        for other_node in self.graph.nodes.values():
            if other_node.id == node.id:
                continue

            imports = other_node.metadata.get("imports", [])
            if node.id in imports or node.name in imports:
                dependents.append(other_node.id)

        return dependents

    def _find_similar_entities(self, node: CodeNode) -> list[tuple[str, float]]:
        """Find entities similar to this node based on name, signature, and structure."""
        similar = []

        for other_node in self.graph.nodes.values():
            if other_node.id == node.id or other_node.node_type != node.node_type:
                continue

            # Calculate similarity score
            score = 0.0

            # Name similarity (simple substring matching)
            if node.name.lower() in other_node.name.lower() or other_node.name.lower() in node.name.lower():
                score += 0.3

            # Signature similarity
            if node.signature and other_node.signature:
                node_args = set(node.signature.split(", "))
                other_args = set(other_node.signature.split(", "))
                if node_args and other_args:
                    overlap = len(node_args & other_args) / max(len(node_args), len(other_args))
                    score += overlap * 0.3

            # Complexity similarity
            if node.complexity > 0 and other_node.complexity > 0:
                complexity_diff = abs(node.complexity - other_node.complexity)
                if complexity_diff <= 2:
                    score += 0.2

            # Same parent (same class or module)
            if node.parent_id == other_node.parent_id:
                score += 0.2

            if score > 0.3:  # Threshold for similarity
                similar.append((other_node.id, score))

        # Sort by score descending
        similar.sort(key=lambda x: x[1], reverse=True)
        return similar[:10]

    def _find_usage_examples(self, node: CodeNode) -> list[str]:
        """Find code snippets showing how this entity is used."""
        examples = []

        # Look for test files that use this entity
        test_nodes = [n for n in self.graph.nodes.values() if "test" in n.file_path.lower()]

        for test_node in test_nodes:
            if node.name in test_node.source_code:
                # Extract a snippet around the usage
                lines = test_node.source_code.split("\n")
                for i, line in enumerate(lines):
                    if node.name in line:
                        start = max(0, i - 2)
                        end = min(len(lines), i + 3)
                        snippet = "\n".join(lines[start:end])
                        examples.append(snippet)
                        break

        return examples[:3]  # Return up to 3 examples

    def _calculate_test_coverage(self, node: CodeNode) -> float:
        """Calculate test coverage for this entity (simplified)."""
        # This is a simplified heuristic - real coverage needs pytest-cov
        test_nodes = [n for n in self.graph.nodes.values() if "test" in n.file_path.lower()]

        mentions = 0
        for test_node in test_nodes:
            if node.name in test_node.source_code or node.name in test_node.name:
                mentions += 1

        # Rough heuristic: if mentioned in tests, assume some coverage
        if mentions > 0:
            return min(100.0, mentions * 25.0)
        return 0.0

    def _find_test_files(self, node_id: str) -> list[str]:
        """Find test files that cover this entity."""
        node = self.graph.get_node(node_id)
        if not node:
            return []

        test_files = []
        test_nodes = [n for n in self.graph.nodes.values() if "test" in n.file_path.lower()]

        for test_node in test_nodes:
            if node.name in test_node.source_code:
                if test_node.file_path not in test_files:
                    test_files.append(test_node.file_path)

        return test_files

    def _assess_risk_level(self, direct_impact: int, indirect_impact: int, change_frequency: int) -> str:
        """Assess the risk level of changing this entity."""
        total_impact = direct_impact + indirect_impact

        if total_impact > 20 or change_frequency > 10:
            return "HIGH"
        elif total_impact > 10 or change_frequency > 5:
            return "MEDIUM"
        elif total_impact > 5:
            return "LOW"
        else:
            return "MINIMAL"

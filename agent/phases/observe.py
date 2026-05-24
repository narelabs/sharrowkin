"""Phase 1: Observe - Workspace scanning and context gathering.

Handles workspace analysis, file scanning, git status, and initial context building.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
import asyncio

from core.tools import scan_workspace, summarize_workspace
from agent.workspace_cache import WorkspaceCache, CachedWorkspace
from analysis.code.dependency import DependencyAnalyzer
from analysis.code.semantic_graph import SemanticGraph, SemanticGraphBuilder


class ObserveModule:
    """Phase 1: Observe - Scan workspace and gather context."""

    def __init__(self, workspace_cache: WorkspaceCache, config: Any):
        self.workspace_cache = workspace_cache
        self.config = config

    async def observe(
        self,
        workspace: Path,
        task: str,
        ui_delays_enabled: bool = False
    ) -> dict[str, Any]:
        """Scan workspace and build initial context.

        Returns:
            Dictionary with:
            - workspace_summary: str
            - total_files: int
            - complexity_avg: float
            - circular_dependencies: int
            - most_complex_functions: list[dict]
            - semantic_graph: SemanticGraph
        """
        # Check cache first
        cached = self.workspace_cache.get(workspace)
        if cached:
            return {
                "workspace_summary": cached.summary,
                "total_files": cached.total_files,
                "complexity_avg": cached.complexity_avg,
                "circular_dependencies": cached.circular_dependencies,
                "most_complex_functions": cached.most_complex_functions,
                "semantic_graph": cached.semantic_graph,
            }

        # Cold scan
        if ui_delays_enabled:
            await asyncio.sleep(0.3)

        scan_result = scan_workspace(workspace)
        total_files = len(scan_result.get("files", []))

        # Dependency analysis
        dep_analyzer = DependencyAnalyzer(workspace)
        dep_result = dep_analyzer.analyze()
        circular_deps = len(dep_result.get("circular_dependencies", []))

        # Semantic graph
        graph_builder = SemanticGraphBuilder(workspace)
        semantic_graph = graph_builder.build()

        # Complexity analysis
        complexity_avg = 0.0
        most_complex = []
        if semantic_graph and semantic_graph.nodes:
            complexities = [
                node.complexity
                for node in semantic_graph.nodes.values()
                if node.complexity > 0
            ]
            if complexities:
                complexity_avg = sum(complexities) / len(complexities)

            # Top 5 most complex functions
            sorted_nodes = sorted(
                semantic_graph.nodes.values(),
                key=lambda n: n.complexity,
                reverse=True
            )
            most_complex = [
                {
                    "name": node.name,
                    "file": str(node.file_path),
                    "complexity": node.complexity,
                }
                for node in sorted_nodes[:5]
                if node.complexity > 0
            ]

        # Generate summary
        summary = summarize_workspace(scan_result)

        # Cache result
        cached_ws = CachedWorkspace(
            workspace=workspace,
            summary=summary,
            total_files=total_files,
            complexity_avg=complexity_avg,
            circular_dependencies=circular_deps,
            most_complex_functions=most_complex,
            semantic_graph=semantic_graph,
        )
        self.workspace_cache.put(workspace, cached_ws)

        return {
            "workspace_summary": summary,
            "total_files": total_files,
            "complexity_avg": complexity_avg,
            "circular_dependencies": circular_deps,
            "most_complex_functions": most_complex,
            "semantic_graph": semantic_graph,
        }

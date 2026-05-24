"""Semantic graph context builder for LLM prompts."""

from __future__ import annotations
from pathlib import Path
from typing import Any


def build_semantic_context(semantic_graph: Any, max_nodes: int = 30) -> str:
    """Build structured semantic graph context for LLM prompt.

    Args:
        semantic_graph: SemanticGraph instance from analysis.code.semantic_graph
        max_nodes: Maximum number of nodes to include

    Returns:
        Formatted string with semantic graph information
    """
    if not semantic_graph or not hasattr(semantic_graph, 'nodes'):
        return ""

    if not semantic_graph.nodes:
        return "=== SEMANTIC GRAPH ===\nNo code structure analyzed yet.\n"

    lines = ["=== SEMANTIC GRAPH (Code Architecture) ===\n"]

    # 1. High-level statistics
    from collections import Counter
    node_types = Counter(node.node_type.value for node in semantic_graph.nodes.values())
    lines.append(f"Total entities: {len(semantic_graph.nodes)}")
    lines.append(f"  Modules: {node_types.get('module', 0)}")
    lines.append(f"  Classes: {node_types.get('class', 0)}")
    lines.append(f"  Functions: {node_types.get('function', 0) + node_types.get('method', 0)}")
    lines.append("")

    # 2. Complexity hotspots (top 5 most complex functions)
    complex_nodes = sorted(
        [n for n in semantic_graph.nodes.values() if n.complexity > 0],
        key=lambda n: n.complexity,
        reverse=True
    )[:5]

    if complex_nodes:
        lines.append("⚠️ COMPLEXITY HOTSPOTS (High Risk Areas):")
        for node in complex_nodes:
            lines.append(f"  - {node.id} (complexity: {node.complexity})")
            if node.file_path:
                lines.append(f"    File: {node.file_path}:{node.line_number}")
        lines.append("")

    # 3. Design patterns detected
    if hasattr(semantic_graph, 'get_detected_patterns'):
        patterns = semantic_graph.get_detected_patterns()
        detected = {k: v for k, v in patterns.items() if v}
        if detected:
            lines.append("🎨 DESIGN PATTERNS DETECTED:")
            for pattern, classes in detected.items():
                lines.append(f"  - {pattern}: {', '.join(classes[:3])}")
            lines.append("")

    # 4. Module structure (top-level modules and their key classes)
    modules = [n for n in semantic_graph.nodes.values() if n.node_type.value == 'module']
    if modules:
        lines.append("📦 MODULE STRUCTURE:")
        for mod in modules[:10]:  # Top 10 modules
            lines.append(f"\n  Module: {mod.name}")
            if mod.file_path:
                lines.append(f"    Path: {mod.file_path}")

            # Find classes in this module
            classes = [n for n in semantic_graph.nodes.values()
                      if n.node_type.value == 'class' and n.parent_id == mod.id]
            if classes:
                lines.append(f"    Classes ({len(classes)}):")
                for cls in classes[:3]:  # Top 3 classes per module
                    lines.append(f"      - {cls.name}")
                    # Count methods
                    methods = [n for n in semantic_graph.nodes.values()
                             if n.parent_id == cls.id]
                    if methods:
                        lines.append(f"        Methods: {len(methods)}")
        lines.append("")

    # 5. Git hotspots (frequently changed files)
    if hasattr(semantic_graph, 'git_hotspots') and semantic_graph.git_hotspots:
        lines.append("🔥 GIT HOTSPOTS (Frequently Changed):")
        for file_path, change_count in semantic_graph.git_hotspots[:5]:
            lines.append(f"  - {file_path} ({change_count} changes)")
        lines.append("")

    return "\n".join(lines)


def build_dependency_context(dependency_graph: Any) -> str:
    """Build dependency analysis context for LLM prompt.

    Args:
        dependency_graph: DependencyGraph instance from analysis.code.dependency

    Returns:
        Formatted string with dependency information
    """
    if not dependency_graph or not hasattr(dependency_graph, 'dependencies'):
        return ""

    if not dependency_graph.dependencies:
        return "=== DEPENDENCY ANALYSIS ===\nNo dependencies analyzed yet.\n"

    lines = ["=== DEPENDENCY ANALYSIS ===\n"]

    # 1. Circular dependencies (critical issue)
    if hasattr(dependency_graph, 'find_circular_dependencies'):
        cycles = dependency_graph.find_circular_dependencies()
        if cycles:
            lines.append("❌ CIRCULAR DEPENDENCIES DETECTED (Must Fix!):")
            for cycle in cycles[:5]:  # Top 5 cycles
                cycle_str = " → ".join(cycle) + f" → {cycle[0]}"
                lines.append(f"  - {cycle_str}")
            lines.append("")

    # 2. Dependency statistics
    from collections import Counter
    dep_types = Counter(d.dep_type.value for d in dependency_graph.dependencies)
    lines.append(f"Total dependencies: {len(dependency_graph.dependencies)}")
    for dep_type, count in dep_types.most_common():
        lines.append(f"  {dep_type}: {count}")
    lines.append("")

    # 3. Highly coupled modules (top 5 with most dependencies)
    from collections import defaultdict
    outgoing = defaultdict(int)
    incoming = defaultdict(int)

    for dep in dependency_graph.dependencies:
        outgoing[dep.source] += 1
        incoming[dep.target] += 1

    if outgoing:
        lines.append("⚠️ HIGHLY COUPLED MODULES (Many Dependencies):")
        top_coupled = sorted(outgoing.items(), key=lambda x: x[1], reverse=True)[:5]
        for entity, count in top_coupled:
            lines.append(f"  - {entity} (depends on {count} others)")
        lines.append("")

    # 4. Core modules (many incoming dependencies)
    if incoming:
        lines.append("🎯 CORE MODULES (Many Dependents):")
        top_core = sorted(incoming.items(), key=lambda x: x[1], reverse=True)[:5]
        for entity, count in top_core:
            lines.append(f"  - {entity} (used by {count} others)")
        lines.append("")

    return "\n".join(lines)

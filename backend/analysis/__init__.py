"""Code analysis modules for deep codebase understanding.

Restructured for clarity:
- code/ - Semantic graph, data flow, dependencies, context
- git/ - Git history analysis
- patterns/ - Design patterns and anti-patterns detection
"""

# Code analysis
from .code import (
    CodeContext,
    CodeNode,
    CodeNodeType,
    ContextLinker,
    DataFlowAnalyzer,
    DataFlowIssue,
    DataFlowNode,
    DataFlowPath,
    DependencyAnalyzer,
    DependencyGraph,
    DependencyType,
    SemanticGraph,
    SemanticGraphBuilder,
)

# Git analysis
from .git import GitAnalyzer

# Pattern detection
from .patterns import PatternDetector

__all__ = [
    # Code analysis
    "CodeContext",
    "CodeNode",
    "CodeNodeType",
    "ContextLinker",
    "DataFlowAnalyzer",
    "DataFlowIssue",
    "DataFlowNode",
    "DataFlowPath",
    "DependencyAnalyzer",
    "DependencyGraph",
    "DependencyType",
    "SemanticGraph",
    "SemanticGraphBuilder",
    # Git analysis
    "GitAnalyzer",
    "GitBlame",
    "GitHotspot",
    # Pattern detection
    "AntiPattern",
    "DesignPattern",
    "PatternDetector",
]

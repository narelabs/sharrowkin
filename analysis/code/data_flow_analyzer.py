"""Data flow analyzer for tracking how data moves through code.

This module analyzes:
- Variable definitions and usage
- Data flow paths through functions
- Potential data flow issues (unused variables, uninitialized access)
- Data transformations and mutations
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from .semantic_graph import CodeNode, SemanticGraph


class DataFlowType(Enum):
    """Types of data flow operations."""
    DEFINITION = "definition"  # Variable is defined
    USAGE = "usage"  # Variable is read
    MUTATION = "mutation"  # Variable is modified
    PARAMETER = "parameter"  # Function parameter
    RETURN = "return"  # Function return value
    GLOBAL = "global"  # Global variable access


@dataclass
class DataFlowNode:
    """Represents a point in data flow."""

    variable_name: str
    flow_type: DataFlowType
    line_number: int
    scope: str  # Function or class scope

    # Context
    statement: str = ""  # The actual code statement
    value_type: str = ""  # Inferred type if available

    # Relationships
    depends_on: list[str] = field(default_factory=list)  # Variables this depends on
    flows_to: list[int] = field(default_factory=list)  # Line numbers where this flows to


@dataclass
class DataFlowPath:
    """Represents a complete data flow path."""

    variable_name: str
    start_line: int
    end_line: int
    path_nodes: list[DataFlowNode] = field(default_factory=list)

    def __str__(self) -> str:
        """String representation of the path."""
        steps = []
        for node in self.path_nodes:
            steps.append(f"L{node.line_number}: {node.flow_type.value} - {node.statement[:50]}")
        return f"{self.variable_name}: {' -> '.join(steps)}"


@dataclass
class DataFlowIssue:
    """Represents a potential data flow issue."""

    issue_type: str  # "unused", "uninitialized", "shadowing", "mutation"
    severity: str  # "error", "warning", "info"
    variable_name: str
    line_number: int
    message: str
    suggestion: str = ""


class DataFlowAnalyzer:
    """Analyzes data flow through Python code."""

    def __init__(self, semantic_graph: SemanticGraph | None = None) -> None:
        self.graph = semantic_graph
        self.flow_nodes: dict[str, list[DataFlowNode]] = {}  # node_id -> flow nodes
        self.issues: dict[str, list[DataFlowIssue]] = {}  # node_id -> issues

    def analyze_function(self, node: CodeNode) -> dict[str, Any]:
        """Analyze data flow in a function."""
        if not node.source_code:
            return {"error": "No source code available"}

        try:
            tree = ast.parse(node.source_code)
            visitor = DataFlowVisitor(node.name)
            visitor.visit(tree)
            visitor.finalize()

            self.flow_nodes[node.id] = visitor.flow_nodes
            self.issues[node.id] = visitor.issues

            # Build data flow paths
            paths = self._build_flow_paths(visitor.flow_nodes)

            return {
                "node_id": node.id,
                "total_variables": len(set(n.variable_name for n in visitor.flow_nodes)),
                "flow_nodes": len(visitor.flow_nodes),
                "paths": [str(p) for p in paths],
                "issues": [self._issue_to_dict(i) for i in visitor.issues],
                "complexity_score": self._calculate_flow_complexity(visitor.flow_nodes),
            }
        except Exception as e:
            return {"error": f"Analysis failed: {e}"}

    def analyze_file(self, file_path: Path) -> dict[str, Any]:
        """Analyze data flow in an entire file."""
        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))

            # Analyze each function in the file
            results = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    visitor = DataFlowVisitor(node.name)
                    visitor.visit(node)
                    visitor.finalize()

                    results.append({
                        "function": node.name,
                        "line": node.lineno,
                        "variables": len(set(n.variable_name for n in visitor.flow_nodes)),
                        "issues": len(visitor.issues),
                        "complexity": self._calculate_flow_complexity(visitor.flow_nodes),
                    })

            return {
                "file_path": str(file_path),
                "functions_analyzed": len(results),
                "results": results,
            }
        except Exception as e:
            return {"error": f"File analysis failed: {e}"}

    def get_variable_flow(self, node_id: str, variable_name: str) -> list[DataFlowNode]:
        """Get all flow nodes for a specific variable in a function."""
        if node_id not in self.flow_nodes:
            return []

        return [n for n in self.flow_nodes[node_id] if n.variable_name == variable_name]

    def get_issues(self, node_id: str) -> list[DataFlowIssue]:
        """Get all data flow issues for a function."""
        return self.issues.get(node_id, [])

    def find_unused_variables(self, node_id: str) -> list[str]:
        """Find variables that are defined but never used."""
        if node_id not in self.flow_nodes:
            return []

        flow_nodes = self.flow_nodes[node_id]
        defined = set()
        used = set()

        for node in flow_nodes:
            if node.flow_type in (DataFlowType.DEFINITION, DataFlowType.PARAMETER):
                defined.add(node.variable_name)
            elif node.flow_type == DataFlowType.USAGE:
                used.add(node.variable_name)

        return list(defined - used)

    def find_uninitialized_access(self, node_id: str) -> list[tuple[str, int]]:
        """Find variables that are used before being defined."""
        if node_id not in self.flow_nodes:
            return []

        flow_nodes = sorted(self.flow_nodes[node_id], key=lambda n: n.line_number)
        defined = set()
        uninitialized = []

        for node in flow_nodes:
            if node.flow_type == DataFlowType.USAGE and node.variable_name not in defined:
                uninitialized.append((node.variable_name, node.line_number))
            elif node.flow_type in (DataFlowType.DEFINITION, DataFlowType.PARAMETER):
                defined.add(node.variable_name)

        return uninitialized

    def trace_variable(self, node_id: str, variable_name: str, start_line: int) -> DataFlowPath:
        """Trace the flow of a variable from a specific line."""
        flow_nodes = self.get_variable_flow(node_id, variable_name)

        # Find nodes at or after start_line
        relevant_nodes = [n for n in flow_nodes if n.line_number >= start_line]
        relevant_nodes.sort(key=lambda n: n.line_number)

        if not relevant_nodes:
            return DataFlowPath(variable_name, start_line, start_line)

        return DataFlowPath(
            variable_name=variable_name,
            start_line=start_line,
            end_line=relevant_nodes[-1].line_number,
            path_nodes=relevant_nodes,
        )

    def get_data_dependencies(self, node_id: str, line_number: int) -> list[str]:
        """Get all variables that a line depends on."""
        if node_id not in self.flow_nodes:
            return []

        dependencies = []
        for node in self.flow_nodes[node_id]:
            if node.line_number == line_number:
                dependencies.extend(node.depends_on)

        return list(set(dependencies))

    def _build_flow_paths(self, flow_nodes: list[DataFlowNode]) -> list[DataFlowPath]:
        """Build complete data flow paths from flow nodes."""
        paths = []
        variables = set(n.variable_name for n in flow_nodes)

        for var in variables:
            var_nodes = [n for n in flow_nodes if n.variable_name == var]
            var_nodes.sort(key=lambda n: n.line_number)

            if var_nodes:
                path = DataFlowPath(
                    variable_name=var,
                    start_line=var_nodes[0].line_number,
                    end_line=var_nodes[-1].line_number,
                    path_nodes=var_nodes,
                )
                paths.append(path)

        return paths

    def _calculate_flow_complexity(self, flow_nodes: list[DataFlowNode]) -> int:
        """Calculate data flow complexity score."""
        if not flow_nodes:
            return 0

        # Factors that increase complexity:
        # - Number of unique variables
        # - Number of mutations
        # - Number of dependencies between variables

        unique_vars = len(set(n.variable_name for n in flow_nodes))
        mutations = sum(1 for n in flow_nodes if n.flow_type == DataFlowType.MUTATION)
        dependencies = sum(len(n.depends_on) for n in flow_nodes)

        return unique_vars + mutations * 2 + dependencies

    def _issue_to_dict(self, issue: DataFlowIssue) -> dict[str, Any]:
        """Convert issue to dictionary."""
        return {
            "type": issue.issue_type,
            "severity": issue.severity,
            "variable": issue.variable_name,
            "line": issue.line_number,
            "message": issue.message,
            "suggestion": issue.suggestion,
        }


class DataFlowVisitor(ast.NodeVisitor):
    """AST visitor for tracking data flow."""

    def __init__(self, scope_name: str) -> None:
        self.scope_name = scope_name
        self.flow_nodes: list[DataFlowNode] = []
        self.issues: list[DataFlowIssue] = []
        self.defined_vars: set[str] = set()
        self.used_vars: set[str] = set()
        self.current_line: int = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Handle function definitions."""
        # Record parameters as definitions
        for arg in node.args.args:
            self.flow_nodes.append(DataFlowNode(
                variable_name=arg.arg,
                flow_type=DataFlowType.PARAMETER,
                line_number=node.lineno,
                scope=self.scope_name,
                statement=f"def {node.name}(...{arg.arg}...)",
            ))
            self.defined_vars.add(arg.arg)

        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        """Handle assignments."""
        self.current_line = node.lineno

        # Get assigned variable names
        targets = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                targets.append(target.id)
            elif isinstance(target, ast.Tuple):
                for elt in target.elts:
                    if isinstance(elt, ast.Name):
                        targets.append(elt.id)

        # Get dependencies (variables used in the value)
        dependencies = self._extract_names(node.value)

        # Record the assignment
        for var_name in targets:
            flow_type = DataFlowType.MUTATION if var_name in self.defined_vars else DataFlowType.DEFINITION

            self.flow_nodes.append(DataFlowNode(
                variable_name=var_name,
                flow_type=flow_type,
                line_number=node.lineno,
                scope=self.scope_name,
                statement=ast.unparse(node) if hasattr(ast, 'unparse') else f"{var_name} = ...",
                depends_on=dependencies,
            ))
            self.defined_vars.add(var_name)

        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        """Handle augmented assignments (+=, -=, etc.)."""
        if isinstance(node.target, ast.Name):
            var_name = node.target.id
            dependencies = self._extract_names(node.value)
            dependencies.append(var_name)  # Augmented assign depends on itself

            self.flow_nodes.append(DataFlowNode(
                variable_name=var_name,
                flow_type=DataFlowType.MUTATION,
                line_number=node.lineno,
                scope=self.scope_name,
                statement=ast.unparse(node) if hasattr(ast, 'unparse') else f"{var_name} += ...",
                depends_on=dependencies,
            ))

        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        """Handle variable usage."""
        if isinstance(node.ctx, ast.Load):
            # Variable is being read
            self.flow_nodes.append(DataFlowNode(
                variable_name=node.id,
                flow_type=DataFlowType.USAGE,
                line_number=node.lineno,
                scope=self.scope_name,
            ))
            self.used_vars.add(node.id)

            # Check for uninitialized access
            if node.id not in self.defined_vars and not node.id.startswith('_'):
                self.issues.append(DataFlowIssue(
                    issue_type="uninitialized",
                    severity="warning",
                    variable_name=node.id,
                    line_number=node.lineno,
                    message=f"Variable '{node.id}' may be used before assignment",
                    suggestion=f"Ensure '{node.id}' is defined before use",
                ))

        self.generic_visit(node)

    def visit_Return(self, node: ast.Return) -> None:
        """Handle return statements."""
        if node.value:
            dependencies = self._extract_names(node.value)

            for var_name in dependencies:
                self.flow_nodes.append(DataFlowNode(
                    variable_name=var_name,
                    flow_type=DataFlowType.RETURN,
                    line_number=node.lineno,
                    scope=self.scope_name,
                    statement=ast.unparse(node) if hasattr(ast, 'unparse') else "return ...",
                ))

        self.generic_visit(node)

    def visit_Global(self, node: ast.Global) -> None:
        """Handle global declarations."""
        for name in node.names:
            self.flow_nodes.append(DataFlowNode(
                variable_name=name,
                flow_type=DataFlowType.GLOBAL,
                line_number=node.lineno,
                scope=self.scope_name,
                statement=f"global {name}",
            ))
            self.defined_vars.add(name)

        self.generic_visit(node)

    def _extract_names(self, node: ast.AST) -> list[str]:
        """Extract all variable names from an AST node."""
        names = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                names.append(child.id)
        return names

    def finalize(self) -> None:
        """Finalize analysis and detect unused variables."""
        unused = self.defined_vars - self.used_vars

        for var_name in unused:
            if not var_name.startswith('_'):  # Ignore private variables
                # Find the line where it was defined
                for node in self.flow_nodes:
                    if node.variable_name == var_name and node.flow_type == DataFlowType.DEFINITION:
                        self.issues.append(DataFlowIssue(
                            issue_type="unused",
                            severity="info",
                            variable_name=var_name,
                            line_number=node.line_number,
                            message=f"Variable '{var_name}' is defined but never used",
                            suggestion=f"Remove '{var_name}' or prefix with '_' if intentionally unused",
                        ))
                        break

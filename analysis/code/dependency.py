"""Dependency analyzer for tracking imports, calls, and inheritance.

This module analyzes code dependencies to understand relationships between
modules, classes, and functions.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class DependencyType(Enum):
    """Types of dependencies between code entities."""
    IMPORT = "import"  # Module imports another module
    FUNCTION_CALL = "function_call"  # Function calls another function
    CLASS_INHERITANCE = "class_inheritance"  # Class inherits from another
    ATTRIBUTE_ACCESS = "attribute_access"  # Accesses attribute/method
    DECORATOR = "decorator"  # Decorator applied to function/class
    TYPE_ANNOTATION = "type_annotation"  # Type hint reference


@dataclass
class Dependency:
    """Represents a dependency between code entities."""

    source: str  # Source entity (e.g., "module.Class.method")
    target: str  # Target entity
    dep_type: DependencyType
    line_number: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.source} --[{self.dep_type.value}]--> {self.target}"


class DependencyGraph:
    """Graph of dependencies in a codebase."""

    def __init__(self) -> None:
        self.dependencies: list[Dependency] = []
        self.nodes: set[str] = set()  # All entities (modules, classes, functions)

    def add_dependency(self, dep: Dependency) -> None:
        """Add a dependency to the graph."""
        self.dependencies.append(dep)
        self.nodes.add(dep.source)
        self.nodes.add(dep.target)

    def get_dependencies_of(self, entity: str, dep_type: DependencyType | None = None) -> list[Dependency]:
        """Get all dependencies where entity is the source."""
        deps = [d for d in self.dependencies if d.source == entity]
        if dep_type:
            deps = [d for d in deps if d.dep_type == dep_type]
        return deps

    def get_dependents_of(self, entity: str, dep_type: DependencyType | None = None) -> list[Dependency]:
        """Get all dependencies where entity is the target."""
        deps = [d for d in self.dependencies if d.target == entity]
        if dep_type:
            deps = [d for d in deps if d.dep_type == dep_type]
        return deps

    def get_transitive_dependencies(self, entity: str, max_depth: int = 10) -> set[str]:
        """Get all transitive dependencies of an entity."""
        visited = set()
        to_visit = [(entity, 0)]

        while to_visit:
            current, depth = to_visit.pop()
            if current in visited or depth >= max_depth:
                continue

            visited.add(current)
            deps = self.get_dependencies_of(current)
            for dep in deps:
                if dep.target not in visited:
                    to_visit.append((dep.target, depth + 1))

        visited.discard(entity)  # Remove the entity itself
        return visited

    def get_circular_dependencies(self) -> list[list[str]]:
        """Find circular dependencies in the graph."""
        cycles = []
        visited = set()

        def dfs(node: str, path: list[str]) -> None:
            if node in path:
                # Found a cycle
                cycle_start = path.index(node)
                cycle = path[cycle_start:] + [node]
                if cycle not in cycles:
                    cycles.append(cycle)
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            deps = self.get_dependencies_of(node)
            for dep in deps:
                dfs(dep.target, path.copy())

        for node in self.nodes:
            dfs(node, [])

        return cycles

    def get_module_dependencies(self) -> dict[str, set[str]]:
        """Get module-level dependencies (imports only)."""
        module_deps: dict[str, set[str]] = {}

        for dep in self.dependencies:
            if dep.dep_type == DependencyType.IMPORT:
                source_module = dep.source.split(".")[0]
                target_module = dep.target.split(".")[0]

                if source_module not in module_deps:
                    module_deps[source_module] = set()
                module_deps[source_module].add(target_module)

        return module_deps

    def visualize(self, entity: str | None = None, max_depth: int = 2) -> str:
        """Generate a text visualization of dependencies."""
        lines = ["Dependency Graph", "=" * 50]

        if entity:
            lines.append(f"\nDependencies of: {entity}")
            lines.append("-" * 50)
            self._visualize_entity(entity, lines, depth=0, max_depth=max_depth, visited=set())
        else:
            # Show module-level dependencies
            module_deps = self.get_module_dependencies()
            for module, deps in sorted(module_deps.items()):
                lines.append(f"\n{module}:")
                for dep in sorted(deps):
                    lines.append(f"  → {dep}")

        return "\n".join(lines)

    def _visualize_entity(
        self,
        entity: str,
        lines: list[str],
        depth: int,
        max_depth: int,
        visited: set[str],
    ) -> None:
        """Recursively visualize entity dependencies."""
        if depth >= max_depth or entity in visited:
            return

        visited.add(entity)
        indent = "  " * depth

        deps = self.get_dependencies_of(entity)
        for dep in deps:
            symbol = {
                DependencyType.IMPORT: "📦",
                DependencyType.FUNCTION_CALL: "🔧",
                DependencyType.CLASS_INHERITANCE: "🧬",
                DependencyType.ATTRIBUTE_ACCESS: "🔗",
                DependencyType.DECORATOR: "✨",
                DependencyType.TYPE_ANNOTATION: "📝",
            }.get(dep.dep_type, "→")

            lines.append(f"{indent}{symbol} {dep.target} ({dep.dep_type.value})")
            self._visualize_entity(dep.target, lines, depth + 1, max_depth, visited)


class DependencyAnalyzer:
    """Analyzes Python code to extract dependencies."""

    def __init__(self) -> None:
        self.graph = DependencyGraph()

    def analyze_file(self, file_path: Path, module_name: str | None = None) -> None:
        """Analyze a Python file and extract dependencies."""
        if module_name is None:
            module_name = file_path.stem

        try:
            source = file_path.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(file_path))
            visitor = DependencyVisitor(module_name, self.graph)
            visitor.visit(tree)
        except Exception as e:
            print(f"Warning: Could not analyze {file_path}: {e}")

    def analyze_directory(self, directory: Path, recursive: bool = True) -> None:
        """Analyze all Python files in a directory."""
        pattern = "**/*.py" if recursive else "*.py"
        ignored_dirs = {"venv", "node_modules", "blocksuite", "archive", "media_assets", "memory_dumps", "storage"}
        for file_path in directory.glob(pattern):
            try:
                parts = file_path.relative_to(directory).parts
                if any(p.startswith(".") or p in ignored_dirs for p in parts[:-1]):
                    continue
            except Exception:
                pass

            if file_path.name.startswith("__") or file_path.name.startswith("."):
                continue

            # Calculate module name from path
            relative = file_path.relative_to(directory)
            module_name = str(relative.with_suffix("")).replace("/", ".").replace("\\", ".")
            self.analyze_file(file_path, module_name)

    def get_graph(self) -> DependencyGraph:
        """Get the dependency graph."""
        return self.graph


class DependencyVisitor(ast.NodeVisitor):
    """AST visitor for extracting dependencies."""

    def __init__(self, module_name: str, graph: DependencyGraph) -> None:
        self.module_name = module_name
        self.graph = graph
        self.current_class: str | None = None
        self.current_function: str | None = None

    def _get_current_context(self) -> str:
        """Get the current context (module.Class.function)."""
        parts = [self.module_name]
        if self.current_class:
            parts.append(self.current_class)
        if self.current_function:
            parts.append(self.current_function)
        return ".".join(parts)

    def visit_Import(self, node: ast.Import) -> None:
        """Handle import statements."""
        context = self._get_current_context()
        for alias in node.names:
            dep = Dependency(
                source=context,
                target=alias.name,
                dep_type=DependencyType.IMPORT,
                line_number=node.lineno,
            )
            self.graph.add_dependency(dep)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Handle from...import statements."""
        context = self._get_current_context()
        if node.module:
            for alias in node.names:
                target = f"{node.module}.{alias.name}"
                dep = Dependency(
                    source=context,
                    target=target,
                    dep_type=DependencyType.IMPORT,
                    line_number=node.lineno,
                )
                self.graph.add_dependency(dep)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Handle class definitions."""
        old_class = self.current_class
        self.current_class = node.name

        # Handle inheritance
        context = self._get_current_context()
        for base in node.bases:
            if isinstance(base, ast.Name):
                dep = Dependency(
                    source=context,
                    target=base.id,
                    dep_type=DependencyType.CLASS_INHERITANCE,
                    line_number=node.lineno,
                )
                self.graph.add_dependency(dep)
            elif isinstance(base, ast.Attribute):
                target = self._get_attribute_name(base)
                dep = Dependency(
                    source=context,
                    target=target,
                    dep_type=DependencyType.CLASS_INHERITANCE,
                    line_number=node.lineno,
                )
                self.graph.add_dependency(dep)

        # Handle decorators
        for decorator in node.decorator_list:
            target = self._get_decorator_name(decorator)
            if target:
                dep = Dependency(
                    source=context,
                    target=target,
                    dep_type=DependencyType.DECORATOR,
                    line_number=node.lineno,
                )
                self.graph.add_dependency(dep)

        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Handle function definitions."""
        old_function = self.current_function
        self.current_function = node.name

        context = self._get_current_context()

        # Handle decorators
        for decorator in node.decorator_list:
            target = self._get_decorator_name(decorator)
            if target:
                dep = Dependency(
                    source=context,
                    target=target,
                    dep_type=DependencyType.DECORATOR,
                    line_number=node.lineno,
                )
                self.graph.add_dependency(dep)

        # Handle type annotations
        if node.returns:
            target = self._get_annotation_name(node.returns)
            if target:
                dep = Dependency(
                    source=context,
                    target=target,
                    dep_type=DependencyType.TYPE_ANNOTATION,
                    line_number=node.lineno,
                )
                self.graph.add_dependency(dep)

        self.generic_visit(node)
        self.current_function = old_function

    def visit_Call(self, node: ast.Call) -> None:
        """Handle function calls."""
        context = self._get_current_context()
        target = None

        if isinstance(node.func, ast.Name):
            target = node.func.id
        elif isinstance(node.func, ast.Attribute):
            target = self._get_attribute_name(node.func)

        if target:
            dep = Dependency(
                source=context,
                target=target,
                dep_type=DependencyType.FUNCTION_CALL,
                line_number=node.lineno,
            )
            self.graph.add_dependency(dep)

        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Handle attribute access."""
        context = self._get_current_context()
        target = self._get_attribute_name(node)

        if target:
            dep = Dependency(
                source=context,
                target=target,
                dep_type=DependencyType.ATTRIBUTE_ACCESS,
                line_number=node.lineno,
            )
            self.graph.add_dependency(dep)

        self.generic_visit(node)

    def _get_attribute_name(self, node: ast.Attribute) -> str:
        """Get the full name of an attribute access."""
        parts = [node.attr]
        current = node.value

        while isinstance(current, ast.Attribute):
            parts.append(current.attr)
            current = current.value

        if isinstance(current, ast.Name):
            parts.append(current.id)

        return ".".join(reversed(parts))

    def _get_decorator_name(self, node: ast.expr) -> str | None:
        """Get the name of a decorator."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                return node.func.id
            elif isinstance(node.func, ast.Attribute):
                return self._get_attribute_name(node.func)
        return None

    def _get_annotation_name(self, node: ast.expr) -> str | None:
        """Get the name from a type annotation."""
        if isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return self._get_attribute_name(node)
        elif isinstance(node, ast.Subscript):
            # Handle generics like List[str]
            if isinstance(node.value, ast.Name):
                return node.value.id
        return None

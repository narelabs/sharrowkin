"""Design pattern detection for code analysis."""

from __future__ import annotations

import ast
from typing import Any


class PatternDetector:
    """Detects common design patterns in Python code."""

    def __init__(self) -> None:
        self.detected_patterns: dict[str, list[str]] = {
            "Singleton": [],
            "Factory": [],
            "Builder": [],
            "Observer": [],
            "Decorator": [],
        }

    def analyze_node(self, node: ast.ClassDef, class_name: str) -> None:
        """Analyze a class node for design patterns.

        Args:
            node: AST ClassDef node
            class_name: Name of the class
        """
        # Detect Singleton pattern
        if self._is_singleton(node):
            self.detected_patterns["Singleton"].append(class_name)

        # Detect Factory pattern
        if self._is_factory(node, class_name):
            self.detected_patterns["Factory"].append(class_name)

        # Detect Builder pattern
        if self._is_builder(node, class_name):
            self.detected_patterns["Builder"].append(class_name)

        # Detect Observer pattern
        if self._is_observer(node):
            self.detected_patterns["Observer"].append(class_name)

        # Detect Decorator pattern
        if self._is_decorator_pattern(node):
            self.detected_patterns["Decorator"].append(class_name)

    def _is_singleton(self, node: ast.ClassDef) -> bool:
        """Check if class implements Singleton pattern."""
        has_instance = False
        has_new_override = False

        for item in node.body:
            # Check for _instance class variable
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id in ("_instance", "instance"):
                        has_instance = True

            # Check for __new__ override
            if isinstance(item, ast.FunctionDef) and item.name == "__new__":
                has_new_override = True

        return has_instance or has_new_override

    def _is_factory(self, node: ast.ClassDef, class_name: str) -> bool:
        """Check if class implements Factory pattern."""
        # Factory classes often have "Factory" in name
        if "Factory" in class_name or "Creator" in class_name:
            return True

        # Check for create/make methods
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name in ("create", "make", "build", "get_instance"):
                    return True

        return False

    def _is_builder(self, node: ast.ClassDef, class_name: str) -> bool:
        """Check if class implements Builder pattern."""
        # Builder classes often have "Builder" in name
        if "Builder" in class_name:
            return True

        # Check for method chaining (methods returning self)
        method_count = 0
        returns_self = 0

        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name not in ("__init__", "__new__"):
                method_count += 1
                # Check if method returns self
                for child in ast.walk(item):
                    if isinstance(child, ast.Return) and isinstance(child.value, ast.Name):
                        if child.value.id == "self":
                            returns_self += 1
                            break

        # If most methods return self, likely a builder
        return method_count > 2 and returns_self >= method_count * 0.6

    def _is_observer(self, node: ast.ClassDef) -> bool:
        """Check if class implements Observer pattern."""
        has_observers = False
        has_notify = False

        for item in node.body:
            # Check for observer list
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if "observer" in target.id.lower() or "listener" in target.id.lower():
                            has_observers = True

            # Check for notify/update methods
            if isinstance(item, ast.FunctionDef):
                if item.name in ("notify", "notify_observers", "update", "attach", "detach"):
                    has_notify = True

        return has_observers and has_notify

    def _is_decorator_pattern(self, node: ast.ClassDef) -> bool:
        """Check if class implements Decorator pattern."""
        # Check for wrapped component
        has_component = False
        has_delegation = False

        for item in node.body:
            # Check for component attribute
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        if "component" in target.id.lower() or "wrapped" in target.id.lower():
                            has_component = True

            # Check for __init__ accepting component
            if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                for arg in item.args.args:
                    if "component" in arg.arg.lower() or "wrapped" in arg.arg.lower():
                        has_component = True

            # Check for delegation (calling methods on component)
            if isinstance(item, ast.FunctionDef):
                for child in ast.walk(item):
                    if isinstance(child, ast.Attribute):
                        if isinstance(child.value, ast.Attribute):
                            if child.value.attr in ("component", "wrapped", "_component"):
                                has_delegation = True

        return has_component and has_delegation

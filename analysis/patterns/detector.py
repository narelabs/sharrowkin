import ast
from typing import Any


class PatternDetector:
    """AST analyzer to detect design patterns in Python classes."""

    def __init__(self) -> None:
        self.detected_patterns: dict[str, list[str]] = {
            "Singleton": [],
            "Factory": [],
            "Builder": [],
            "Observer": [],
            "Decorator": []
        }

    def analyze_node(self, node: ast.AST, class_name: str) -> None:
        """Analyze a class node for design pattern signatures."""
        if not isinstance(node, ast.ClassDef):
            return

        is_singleton = self._check_singleton(node)
        is_factory = self._check_factory(node)
        is_builder = self._check_builder(node)
        is_observer = self._check_observer(node)
        is_decorator = self._check_decorator(node)

        if is_singleton:
            self.detected_patterns["Singleton"].append(class_name)
        if is_factory:
            self.detected_patterns["Factory"].append(class_name)
        if is_builder:
            self.detected_patterns["Builder"].append(class_name)
        if is_observer:
            self.detected_patterns["Observer"].append(class_name)
        if is_decorator:
            self.detected_patterns["Decorator"].append(class_name)

    def _check_singleton(self, node: ast.ClassDef) -> bool:
        """Singleton: has `_instance` class variable or custom __new__."""
        has_instance_var = False
        has_new_method = False

        for body_item in node.body:
            # Check class variables
            if isinstance(body_item, ast.Assign):
                for target in body_item.targets:
                    if isinstance(target, ast.Name) and target.id in ("_instance", "instance"):
                        has_instance_var = True
            elif isinstance(body_item, ast.AnnAssign):
                if isinstance(body_item.target, ast.Name) and body_item.target.id in ("_instance", "instance"):
                    has_instance_var = True

            # Check __new__ or get_instance
            if isinstance(body_item, ast.FunctionDef):
                if body_item.name in ("__new__", "get_instance", "get_client"):
                    has_new_method = True

        return has_instance_var or has_new_method

    def _check_factory(self, node: ast.ClassDef) -> bool:
        """Factory: Class name ends with Factory/Creator or has create_xx methods."""
        if "factory" in node.name.lower() or "creator" in node.name.lower():
            return True

        for body_item in node.body:
            if isinstance(body_item, ast.FunctionDef):
                # Look for create_something or build_something
                if body_item.name.startswith("create_") or body_item.name.startswith("get_"):
                    # Check if it returns an instantiation
                    for sub_node in ast.walk(body_item):
                        if isinstance(sub_node, ast.Return) and isinstance(sub_node.value, ast.Call):
                            return True
        return False

    def _check_builder(self, node: ast.ClassDef) -> bool:
        """Builder: Class name ends with Builder or methods return self."""
        if "builder" in node.name.lower():
            return True

        # Check if methods return self
        chaining_methods = 0
        for body_item in node.body:
            if isinstance(body_item, ast.FunctionDef):
                for sub_node in ast.walk(body_item):
                    if isinstance(sub_node, ast.Return):
                        if isinstance(sub_node.value, ast.Name) and sub_node.value.id == "self":
                            chaining_methods += 1
                        elif isinstance(sub_node.value, ast.Attribute) and isinstance(sub_node.value.value, ast.Name) and sub_node.value.value.id == "self":
                            # return self.some_attr
                            pass
        # If multiple methods return self, it is likely a Builder
        return chaining_methods >= 2

    def _check_observer(self, node: ast.ClassDef) -> bool:
        """Observer: contains methods to subscribe, unsubscribe, notify, register, emit."""
        has_subscribe = False
        has_unsubscribe = False
        has_notify = False

        # Look for observer list attribute initialization in __init__
        has_observer_list = False
        for body_item in node.body:
            if isinstance(body_item, ast.FunctionDef) and body_item.name == "__init__":
                for sub_node in ast.walk(body_item):
                    if isinstance(sub_node, ast.Assign):
                        for target in sub_node.targets:
                            if isinstance(target, ast.Attribute) and target.attr in ("observers", "listeners", "_listeners", "_observers"):
                                has_observer_list = True

            if isinstance(body_item, ast.FunctionDef):
                name = body_item.name.lower()
                if any(x in name for x in ("subscribe", "add_listener", "register", "attach")):
                    has_subscribe = True
                if any(x in name for x in ("unsubscribe", "remove_listener", "unregister", "detach")):
                    has_unsubscribe = True
                if any(x in name for x in ("notify", "emit", "broadcast", "trigger")):
                    has_notify = True

        return (has_subscribe and has_notify) or (has_observer_list and has_notify)

    def _check_decorator(self, node: ast.ClassDef) -> bool:
        """Decorator: Initializer wraps another class instance, delegates calls."""
        if "decorator" in node.name.lower() or "wrapper" in node.name.lower():
            return True

        # Check if init accepts another instance and stores it
        init_takes_wrapped = False
        for body_item in node.body:
            if isinstance(body_item, ast.FunctionDef) and body_item.name == "__init__":
                args = [arg.arg for arg in body_item.args.args if arg.arg != "self"]
                if any(arg in ("wrapped", "component", "inner", "delegate", "func") for arg in args):
                    init_takes_wrapped = True

        return init_takes_wrapped

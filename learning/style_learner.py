"""Code style learner for adapting to project conventions.

Learns and adapts to:
- Naming conventions
- Indentation style
- Import organization
- Comment style
- Documentation patterns
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from collections import Counter


@dataclass
class CodeStyle:
    """Learned code style for a project."""
    project_name: str
    indent_style: str  # "spaces" or "tabs"
    indent_size: int
    max_line_length: int
    naming_convention: Dict[str, str]  # function, class, variable, constant
    import_style: str  # "absolute", "relative", "mixed"
    quote_style: str  # "single", "double", "mixed"
    docstring_style: str  # "google", "numpy", "sphinx", "none"
    comment_density: float  # Comments per 100 lines
    type_hints_usage: float  # Percentage of functions with type hints
    samples_analyzed: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> CodeStyle:
        """Create from dictionary."""
        return cls(**data)


class StyleLearner:
    """Learns code style from existing project files.

    Analyzes Python files to extract:
    - Formatting conventions
    - Naming patterns
    - Documentation style
    - Import organization
    """

    def __init__(self, workspace: Path):
        """Initialize style learner.

        Args:
            workspace: Workspace directory
        """
        self.workspace = workspace
        self.storage_dir = workspace / ".sharrowkin" / "learning"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / "code_style.json"

        self.learned_style: Optional[CodeStyle] = None

        # Load existing style
        self._load()

    def analyze_project(self, max_files: int = 50) -> CodeStyle:
        """Analyze project files to learn code style.

        Args:
            max_files: Maximum files to analyze

        Returns:
            Learned CodeStyle
        """
        python_files = list(self.workspace.rglob("*.py"))

        # Filter out common non-project files
        python_files = [
            f for f in python_files
            if not any(part in f.parts for part in [".venv", "venv", "__pycache__", ".git", "node_modules"])
        ]

        # Limit files
        python_files = python_files[:max_files]

        if not python_files:
            return self._default_style()

        # Collect style metrics
        indent_styles = []
        indent_sizes = []
        line_lengths = []
        function_names = []
        class_names = []
        variable_names = []
        constant_names = []
        import_types = []
        quote_types = []
        docstring_types = []
        total_lines = 0
        total_comments = 0
        functions_with_hints = 0
        total_functions = 0

        for file_path in python_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Analyze indentation
                indent_info = self._analyze_indentation(content)
                if indent_info:
                    indent_styles.append(indent_info["style"])
                    indent_sizes.append(indent_info["size"])

                # Analyze line lengths
                for line in content.split('\n'):
                    if line.strip():
                        line_lengths.append(len(line))

                # Count lines and comments
                lines = content.split('\n')
                total_lines += len(lines)
                total_comments += sum(1 for line in lines if line.strip().startswith('#'))

                # Parse AST for naming and type hints
                try:
                    tree = ast.parse(content)

                    for node in ast.walk(tree):
                        # Function names
                        if isinstance(node, ast.FunctionDef):
                            function_names.append(node.name)
                            total_functions += 1

                            # Check for type hints
                            if node.returns or any(arg.annotation for arg in node.args.args):
                                functions_with_hints += 1

                            # Check for docstring
                            if ast.get_docstring(node):
                                docstring_types.append(self._detect_docstring_style(ast.get_docstring(node)))

                        # Class names
                        elif isinstance(node, ast.ClassDef):
                            class_names.append(node.name)

                        # Variable assignments
                        elif isinstance(node, ast.Assign):
                            for target in node.targets:
                                if isinstance(target, ast.Name):
                                    name = target.id
                                    if name.isupper():
                                        constant_names.append(name)
                                    else:
                                        variable_names.append(name)

                        # Import style
                        elif isinstance(node, ast.Import):
                            import_types.append("absolute")
                        elif isinstance(node, ast.ImportFrom):
                            if node.level > 0:
                                import_types.append("relative")
                            else:
                                import_types.append("absolute")

                    # Detect quote style
                    single_quotes = content.count("'")
                    double_quotes = content.count('"')
                    if single_quotes > double_quotes * 1.5:
                        quote_types.append("single")
                    elif double_quotes > single_quotes * 1.5:
                        quote_types.append("double")
                    else:
                        quote_types.append("mixed")

                except SyntaxError:
                    pass

            except Exception as e:
                print(f"[StyleLearner] Error analyzing {file_path}: {e}")

        # Aggregate results
        indent_style = Counter(indent_styles).most_common(1)[0][0] if indent_styles else "spaces"
        indent_size = int(sum(indent_sizes) / len(indent_sizes)) if indent_sizes else 4
        max_line_length = int(sum(line_lengths) / len(line_lengths) * 1.2) if line_lengths else 88

        naming_convention = {
            "function": self._detect_naming_pattern(function_names),
            "class": self._detect_naming_pattern(class_names),
            "variable": self._detect_naming_pattern(variable_names),
            "constant": self._detect_naming_pattern(constant_names)
        }

        import_style = Counter(import_types).most_common(1)[0][0] if import_types else "absolute"
        quote_style = Counter(quote_types).most_common(1)[0][0] if quote_types else "double"
        docstring_style = Counter(docstring_types).most_common(1)[0][0] if docstring_types else "none"

        comment_density = (total_comments / total_lines * 100) if total_lines > 0 else 0.0
        type_hints_usage = (functions_with_hints / total_functions * 100) if total_functions > 0 else 0.0

        self.learned_style = CodeStyle(
            project_name=self.workspace.name,
            indent_style=indent_style,
            indent_size=indent_size,
            max_line_length=max_line_length,
            naming_convention=naming_convention,
            import_style=import_style,
            quote_style=quote_style,
            docstring_style=docstring_style,
            comment_density=comment_density,
            type_hints_usage=type_hints_usage,
            samples_analyzed=len(python_files)
        )

        self._save()
        return self.learned_style

    def get_style(self) -> Optional[CodeStyle]:
        """Get learned style or analyze if not available.

        Returns:
            CodeStyle or None
        """
        if self.learned_style is None:
            self.analyze_project()

        return self.learned_style

    def format_code_suggestion(self, code: str) -> str:
        """Suggest formatting improvements based on learned style.

        Args:
            code: Code to format

        Returns:
            Formatted code
        """
        if self.learned_style is None:
            return code

        # Apply learned style (basic implementation)
        lines = code.split('\n')
        formatted_lines = []

        for line in lines:
            # Apply indentation
            if line.startswith('\t') and self.learned_style.indent_style == "spaces":
                line = line.replace('\t', ' ' * self.learned_style.indent_size)
            elif line.startswith(' ') and self.learned_style.indent_style == "tabs":
                # Count leading spaces
                spaces = len(line) - len(line.lstrip())
                tabs = spaces // self.learned_style.indent_size
                line = '\t' * tabs + line.lstrip()

            formatted_lines.append(line)

        return '\n'.join(formatted_lines)

    def _analyze_indentation(self, content: str) -> Optional[Dict[str, Any]]:
        """Analyze indentation style.

        Args:
            content: File content

        Returns:
            Dict with style and size
        """
        lines = content.split('\n')
        tab_count = 0
        space_count = 0
        space_sizes = []

        for line in lines:
            if line.startswith('\t'):
                tab_count += 1
            elif line.startswith(' '):
                space_count += 1
                # Count leading spaces
                spaces = len(line) - len(line.lstrip())
                if spaces > 0:
                    space_sizes.append(spaces)

        if tab_count > space_count:
            return {"style": "tabs", "size": 1}
        elif space_count > 0:
            # Find most common space size
            if space_sizes:
                size = Counter(space_sizes).most_common(1)[0][0]
                return {"style": "spaces", "size": size}

        return None

    def _detect_naming_pattern(self, names: List[str]) -> str:
        """Detect naming convention from names.

        Args:
            names: List of names

        Returns:
            Convention name
        """
        if not names:
            return "unknown"

        snake_case = sum(1 for n in names if '_' in n and n.islower())
        camel_case = sum(1 for n in names if n[0].islower() and any(c.isupper() for c in n[1:]))
        pascal_case = sum(1 for n in names if n[0].isupper() and any(c.isupper() for c in n[1:]))
        upper_case = sum(1 for n in names if n.isupper())

        counts = {
            "snake_case": snake_case,
            "camelCase": camel_case,
            "PascalCase": pascal_case,
            "UPPER_CASE": upper_case
        }

        return max(counts, key=counts.get)

    def _detect_docstring_style(self, docstring: str) -> str:
        """Detect docstring style.

        Args:
            docstring: Docstring text

        Returns:
            Style name
        """
        if "Args:" in docstring and "Returns:" in docstring:
            return "google"
        elif "Parameters" in docstring and "Returns" in docstring:
            return "numpy"
        elif ":param" in docstring and ":return:" in docstring:
            return "sphinx"
        else:
            return "plain"

    def _default_style(self) -> CodeStyle:
        """Return default Python style (PEP 8).

        Returns:
            Default CodeStyle
        """
        return CodeStyle(
            project_name=self.workspace.name,
            indent_style="spaces",
            indent_size=4,
            max_line_length=88,
            naming_convention={
                "function": "snake_case",
                "class": "PascalCase",
                "variable": "snake_case",
                "constant": "UPPER_CASE"
            },
            import_style="absolute",
            quote_style="double",
            docstring_style="google",
            comment_density=5.0,
            type_hints_usage=50.0,
            samples_analyzed=0
        )

    def _save(self) -> None:
        """Save learned style to disk."""
        if self.learned_style is None:
            return

        try:
            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(self.learned_style.to_dict(), f, indent=2)
        except Exception as e:
            print(f"[StyleLearner] Error saving: {e}")

    def _load(self) -> None:
        """Load learned style from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.learned_style = CodeStyle.from_dict(data)
            print(f"[StyleLearner] Loaded style for {self.learned_style.project_name}")
        except Exception as e:
            print(f"[StyleLearner] Error loading: {e}")

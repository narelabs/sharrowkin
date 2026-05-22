"""Automatic test generator.

Generates unit tests for:
- Functions and methods
- Classes
- Edge cases
- Error conditions
"""

import ast
import inspect
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


@dataclass
class TestCase:
    """A single test case."""
    name: str
    function_name: str
    inputs: Dict[str, Any]
    expected_output: Optional[Any]
    should_raise: Optional[str]  # Exception type if test should raise
    description: str


@dataclass
class TestSuite:
    """Collection of test cases for a module."""
    module_name: str
    test_cases: List[TestCase]
    setup_code: List[str]
    teardown_code: List[str]


class TestGenerator:
    """Generates unit tests automatically."""

    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    def generate_tests_for_file(self, file_path: Path) -> TestSuite:
        """Generate tests for all functions in a file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            TestSuite with generated tests
        """
        with open(file_path) as f:
            source = f.read()
        
        tree = ast.parse(source)
        
        test_cases = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Skip private functions and test functions
                if node.name.startswith("_") or node.name.startswith("test_"):
                    continue
                
                cases = self._generate_test_cases_for_function(node, source)
                test_cases.extend(cases)
        
        module_name = file_path.stem
        
        return TestSuite(
            module_name=module_name,
            test_cases=test_cases,
            setup_code=[f"from {module_name} import *"],
            teardown_code=[],
        )

    def _generate_test_cases_for_function(self, func_node: ast.FunctionDef, source: str) -> List[TestCase]:
        """Generate test cases for a function."""
        test_cases = []
        func_name = func_node.name
        
        # Extract function signature
        args = [arg.arg for arg in func_node.args.args if arg.arg != "self"]
        
        # Generate basic test case
        test_cases.append(TestCase(
            name=f"test_{func_name}_basic",
            function_name=func_name,
            inputs={arg: self._generate_sample_value(arg) for arg in args},
            expected_output=None,  # Would need execution to determine
            should_raise=None,
            description=f"Basic test for {func_name}",
        ))
        
        # Generate edge case tests
        if args:
            # Test with None values
            test_cases.append(TestCase(
                name=f"test_{func_name}_none_input",
                function_name=func_name,
                inputs={args[0]: None, **{arg: self._generate_sample_value(arg) for arg in args[1:]}},
                expected_output=None,
                should_raise="TypeError",
                description=f"Test {func_name} with None input",
            ))
            
            # Test with empty values
            if any("list" in arg or "dict" in arg or "str" in arg for arg in args):
                test_cases.append(TestCase(
                    name=f"test_{func_name}_empty_input",
                    function_name=func_name,
                    inputs={arg: self._generate_empty_value(arg) for arg in args},
                    expected_output=None,
                    should_raise=None,
                    description=f"Test {func_name} with empty input",
                ))
        
        # Check for error handling in function body
        has_try_except = any(isinstance(node, ast.Try) for node in ast.walk(func_node))
        if has_try_except:
            test_cases.append(TestCase(
                name=f"test_{func_name}_error_handling",
                function_name=func_name,
                inputs={arg: self._generate_invalid_value(arg) for arg in args},
                expected_output=None,
                should_raise=None,  # Function should handle error
                description=f"Test {func_name} error handling",
            ))
        
        return test_cases

    def _generate_sample_value(self, arg_name: str) -> Any:
        """Generate sample value based on argument name."""
        arg_lower = arg_name.lower()
        
        if "path" in arg_lower or "file" in arg_lower:
            return "test.txt"
        elif "name" in arg_lower:
            return "test_name"
        elif "count" in arg_lower or "num" in arg_lower or "size" in arg_lower:
            return 10
        elif "list" in arg_lower or "items" in arg_lower:
            return [1, 2, 3]
        elif "dict" in arg_lower or "map" in arg_lower:
            return {"key": "value"}
        elif "str" in arg_lower or "text" in arg_lower:
            return "test string"
        elif "bool" in arg_lower or "flag" in arg_lower:
            return True
        else:
            return 42  # Default numeric value

    def _generate_empty_value(self, arg_name: str) -> Any:
        """Generate empty value based on argument name."""
        arg_lower = arg_name.lower()
        
        if "list" in arg_lower or "items" in arg_lower:
            return []
        elif "dict" in arg_lower or "map" in arg_lower:
            return {}
        elif "str" in arg_lower or "text" in arg_lower or "name" in arg_lower:
            return ""
        else:
            return 0

    def _generate_invalid_value(self, arg_name: str) -> Any:
        """Generate invalid value to test error handling."""
        arg_lower = arg_name.lower()
        
        if "path" in arg_lower or "file" in arg_lower:
            return "/nonexistent/path.txt"
        elif "count" in arg_lower or "num" in arg_lower:
            return -1
        elif "list" in arg_lower:
            return "not a list"
        elif "dict" in arg_lower:
            return "not a dict"
        else:
            return None

    def write_test_file(self, suite: TestSuite, output_path: Path) -> None:
        """Write test suite to file.
        
        Args:
            suite: TestSuite to write
            output_path: Path to output test file
        """
        lines = [
            '"""Auto-generated tests."""',
            "",
            "import pytest",
            "",
        ]
        
        # Add setup code
        lines.extend(suite.setup_code)
        lines.append("")
        
        # Add test cases
        for test_case in suite.test_cases:
            lines.extend(self._format_test_case(test_case))
            lines.append("")
        
        output_path.write_text("\n".join(lines))

    def _format_test_case(self, test_case: TestCase) -> List[str]:
        """Format test case as Python code."""
        lines = [
            f"def {test_case.name}():",
            f'    """{test_case.description}"""',
        ]

        # Add test body
        if test_case.should_raise:
            lines.append("    with pytest.raises(Exception):")
            lines.append(f"        result = {test_case.function_name}(**{test_case.inputs!r})")
        else:
            lines.append(f"    result = {test_case.function_name}(**{test_case.inputs!r})")
            if test_case.expected_output is not None:
                lines.append(f"    assert result == {test_case.expected_output!r}")

        return lines
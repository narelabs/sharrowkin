"""Failure analysis for Stabilize phase to improve Reason phase."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FailureContext:
    """Context about a failure for learning."""
    iteration: int
    changed_files: list[str]
    error_output: str
    test_failures: int
    workspace_summary: str

    def to_prompt(self) -> str:
        """Convert failure context to LLM prompt."""
        return f"""
Previous attempt #{self.iteration} failed with {self.test_failures} test failures.

Error output:
{self.error_output[-2000:]}

Files modified: {', '.join(self.changed_files)}

Learn from this failure and propose a DIFFERENT approach. Do not repeat the same mistake.
"""


@dataclass
class FailureAnalysis:
    """Analysis result from FailureAnalyzer."""
    root_cause: str
    suggested_fix: str
    error_type: str
    confidence: float


class FailureAnalyzer:
    """Analyzes failures to improve reasoning."""

    def __init__(self):
        self.failure_patterns: dict[str, int] = {}

    def analyze(self, context: FailureContext) -> FailureAnalysis:
        """Analyze a failure and provide actionable insights."""

        # Extract error type
        error_type = self._extract_error_type(context.error_output)
        self.failure_patterns[error_type] = self.failure_patterns.get(error_type, 0) + 1

        # Analyze root cause
        root_cause = self._analyze_root_cause(context.error_output, error_type)

        # Generate suggested fix
        suggested_fix = self._generate_fix_suggestion(error_type, root_cause, context)

        # Calculate confidence based on error clarity
        confidence = self._calculate_confidence(context.error_output, error_type)

        return FailureAnalysis(
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            error_type=error_type,
            confidence=confidence
        )

    def _extract_error_type(self, error: str) -> str:
        """Extract error type from error message."""
        # Common Python error types
        error_types = [
            'SyntaxError', 'IndentationError', 'NameError', 'TypeError',
            'AttributeError', 'KeyError', 'ValueError', 'ImportError',
            'ModuleNotFoundError', 'FileNotFoundError', 'AssertionError',
            'IndexError', 'ZeroDivisionError', 'RuntimeError'
        ]

        for error_type in error_types:
            if error_type in error:
                return error_type

        # Check for test failures
        if 'FAILED' in error or 'failed' in error:
            return 'TestFailure'

        return 'UnknownError'

    def _analyze_root_cause(self, error_output: str, error_type: str) -> str:
        """Analyze the root cause of the error."""

        if error_type == 'ImportError' or error_type == 'ModuleNotFoundError':
            # Extract module name
            import re
            match = re.search(r"No module named ['\"]([^'\"]+)['\"]", error_output)
            if match:
                module = match.group(1)
                return f"Missing import: module '{module}' not found or not installed"
            return "Import error: required module not available"

        elif error_type == 'NameError':
            match = re.search(r"name ['\"]([^'\"]+)['\"] is not defined", error_output)
            if match:
                var = match.group(1)
                return f"Variable '{var}' used before definition or in wrong scope"
            return "Variable not defined in current scope"

        elif error_type == 'AttributeError':
            match = re.search(r"'([^']+)' object has no attribute '([^']+)'", error_output)
            if match:
                obj_type, attr = match.group(1), match.group(2)
                return f"Object of type '{obj_type}' doesn't have attribute '{attr}'"
            return "Attribute access error: object doesn't have the requested attribute"

        elif error_type == 'TypeError':
            if 'missing' in error_output and 'required positional argument' in error_output:
                return "Function called with wrong number of arguments"
            elif 'unsupported operand type' in error_output:
                return "Type mismatch in operation (e.g., adding string to int)"
            return "Type error: incompatible types used in operation"

        elif error_type == 'SyntaxError':
            return "Syntax error: invalid Python syntax in generated code"

        elif error_type == 'IndentationError':
            return "Indentation error: inconsistent use of tabs/spaces or wrong indentation level"

        elif error_type == 'TestFailure':
            if 'AssertionError' in error_output:
                return "Test assertion failed: expected value doesn't match actual value"
            return "Test failed: code behavior doesn't match test expectations"

        return f"Error of type {error_type} occurred"

    def _generate_fix_suggestion(self, error_type: str, root_cause: str, context: FailureContext) -> str:
        """Generate actionable fix suggestion."""

        if error_type == 'ImportError' or error_type == 'ModuleNotFoundError':
            return "Add missing import statement at the top of the file, or install required package"

        elif error_type == 'NameError':
            return "Define the variable before using it, or check if it's in the correct scope"

        elif error_type == 'AttributeError':
            return "Check object type and available attributes, or add the missing attribute/method"

        elif error_type == 'TypeError':
            if 'argument' in root_cause:
                return "Review function signature and ensure all required arguments are provided"
            return "Convert values to compatible types before operation"

        elif error_type == 'SyntaxError':
            return "Fix syntax error: check for missing colons, parentheses, or quotes"

        elif error_type == 'IndentationError':
            return "Fix indentation: use consistent spacing (4 spaces recommended)"

        elif error_type == 'TestFailure':
            return "Review test expectations and fix code logic to match expected behavior"

        return "Review error output and fix the underlying issue"

    def _calculate_confidence(self, error_output: str, error_type: str) -> float:
        """Calculate confidence in the analysis (0.0 to 1.0)."""

        # High confidence for well-known errors
        if error_type in ['ImportError', 'ModuleNotFoundError', 'NameError', 'SyntaxError']:
            return 0.9

        # Medium confidence for type errors
        if error_type in ['TypeError', 'AttributeError']:
            return 0.7

        # Lower confidence for test failures (need more context)
        if error_type == 'TestFailure':
            return 0.5

        # Low confidence for unknown errors
        return 0.3

    def analyze_failure(
        self,
        error: str,
        stack_trace: str,
        previous_attempt: str,
        diff: str,
        iteration: int,
        changed_files: list[str]
    ) -> FailureContext:
        """Legacy method for backward compatibility."""
        return FailureContext(
            iteration=iteration,
            changed_files=changed_files,
            error_output=f"{error}\n\n{stack_trace}",
            test_failures=1,
            workspace_summary=""
        )

    def get_failure_summary(self) -> str:
        """Get summary of failure patterns."""
        if not self.failure_patterns:
            return "No failures recorded yet."

        summary = "Failure patterns:\n"
        for error_type, count in sorted(self.failure_patterns.items(), key=lambda x: x[1], reverse=True):
            summary += f"  - {error_type}: {count} times\n"

        return summary

    def should_give_up(self, iteration: int, max_retries: int = 3) -> bool:
        """Determine if we should give up after too many failures."""
        return iteration >= max_retries


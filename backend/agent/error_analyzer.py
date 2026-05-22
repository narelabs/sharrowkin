"""Error analysis and classification for intelligent retry strategies.

Analyzes test failures and errors to determine root cause and suggest fixes.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import re


class ErrorType(Enum):
    """Types of errors that can occur during execution."""

    SYNTAX_ERROR = "syntax"
    IMPORT_ERROR = "import"
    TYPE_ERROR = "type"
    ATTRIBUTE_ERROR = "attribute"
    NAME_ERROR = "name"
    LOGIC_ERROR = "logic"
    TEST_FAILURE = "test"
    TIMEOUT = "timeout"
    DEPENDENCY_MISSING = "dependency"
    UNKNOWN = "unknown"


@dataclass
class ErrorAnalysis:
    """Result of error analysis."""

    error_type: ErrorType
    error_message: str
    file_path: Optional[str] = None
    line_number: Optional[int] = None

    # Suggested fix strategy
    fix_strategy: str = ""
    confidence: float = 0.0

    # Context
    code_snippet: Optional[str] = None
    stack_trace: Optional[str] = None


class ErrorAnalyzer:
    """Analyzes errors and suggests fix strategies."""

    def __init__(self):
        # Patterns for error classification
        self.patterns = {
            ErrorType.SYNTAX_ERROR: [
                r"SyntaxError",
                r"invalid syntax",
                r"unexpected EOF",
                r"IndentationError",
            ],
            ErrorType.IMPORT_ERROR: [
                r"ImportError",
                r"ModuleNotFoundError",
                r"cannot import name",
                r"No module named",
            ],
            ErrorType.TYPE_ERROR: [
                r"TypeError",
                r"expected .* got",
                r"takes .* positional argument",
            ],
            ErrorType.ATTRIBUTE_ERROR: [
                r"AttributeError",
                r"has no attribute",
                r"object has no attribute",
            ],
            ErrorType.NAME_ERROR: [
                r"NameError",
                r"name .* is not defined",
            ],
            ErrorType.TEST_FAILURE: [
                r"AssertionError",
                r"FAILED",
                r"test.*failed",
                r"Expected .* but got",
            ],
            ErrorType.TIMEOUT: [
                r"TimeoutError",
                r"timed out",
                r"timeout exceeded",
            ],
            ErrorType.DEPENDENCY_MISSING: [
                r"No such file or directory",
                r"FileNotFoundError",
                r"package .* not found",
            ],
        }

    def analyze(self, error_output: str, code_context: Optional[str] = None) -> ErrorAnalysis:
        """Analyze error output and determine type and fix strategy.

        Args:
            error_output: Error message or stack trace
            code_context: Optional code that caused the error

        Returns:
            ErrorAnalysis with classification and suggested fix
        """
        # Classify error type
        error_type = self._classify_error(error_output)

        # Extract file and line info
        file_path, line_number = self._extract_location(error_output)

        # Extract error message
        error_message = self._extract_message(error_output)

        # Determine fix strategy
        fix_strategy, confidence = self._suggest_fix(error_type, error_message, code_context)

        return ErrorAnalysis(
            error_type=error_type,
            error_message=error_message,
            file_path=file_path,
            line_number=line_number,
            fix_strategy=fix_strategy,
            confidence=confidence,
            code_snippet=code_context,
            stack_trace=error_output,
        )

    def _classify_error(self, error_output: str) -> ErrorType:
        """Classify error based on patterns."""
        for error_type, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, error_output, re.IGNORECASE):
                    return error_type

        # Check for logic errors (test failures without assertion)
        if "failed" in error_output.lower() or "error" in error_output.lower():
            return ErrorType.LOGIC_ERROR

        return ErrorType.UNKNOWN

    def _extract_location(self, error_output: str) -> tuple[Optional[str], Optional[int]]:
        """Extract file path and line number from error output."""
        # Pattern: File "path/to/file.py", line 42
        match = re.search(r'File "([^"]+)", line (\d+)', error_output)
        if match:
            return match.group(1), int(match.group(2))

        # Pattern: path/to/file.py:42
        match = re.search(r'([^\s]+\.py):(\d+)', error_output)
        if match:
            return match.group(1), int(match.group(2))

        return None, None

    def _extract_message(self, error_output: str) -> str:
        """Extract the main error message."""
        lines = error_output.strip().split('\n')

        # Last line usually contains the error
        if lines:
            return lines[-1].strip()

        return error_output[:200]  # Fallback to first 200 chars

    def _suggest_fix(
        self,
        error_type: ErrorType,
        error_message: str,
        code_context: Optional[str],
    ) -> tuple[str, float]:
        """Suggest fix strategy based on error type.

        Returns:
            (fix_strategy, confidence) tuple
        """
        strategies = {
            ErrorType.SYNTAX_ERROR: (
                "Fix syntax error: check for missing colons, parentheses, or indentation issues. "
                "Review the code at the error line and ensure proper Python syntax.",
                0.9
            ),
            ErrorType.IMPORT_ERROR: (
                "Fix import error: ensure the module is installed (pip install) or the import path is correct. "
                "Check if the module name is spelled correctly and exists in the project.",
                0.85
            ),
            ErrorType.TYPE_ERROR: (
                "Fix type error: check function arguments and return types. "
                "Ensure you're passing the correct number and types of arguments.",
                0.8
            ),
            ErrorType.ATTRIBUTE_ERROR: (
                "Fix attribute error: verify the object has the attribute you're accessing. "
                "Check for typos in attribute names or ensure the object is initialized properly.",
                0.8
            ),
            ErrorType.NAME_ERROR: (
                "Fix name error: ensure the variable is defined before use. "
                "Check for typos in variable names or missing imports.",
                0.85
            ),
            ErrorType.TEST_FAILURE: (
                "Fix test failure: review the test assertion and actual behavior. "
                "The logic may need adjustment to match expected behavior. Consider alternative approach.",
                0.7
            ),
            ErrorType.TIMEOUT: (
                "Fix timeout: optimize the code for better performance or increase timeout limit. "
                "Look for infinite loops or expensive operations.",
                0.6
            ),
            ErrorType.DEPENDENCY_MISSING: (
                "Fix missing dependency: install required packages or create missing files. "
                "Check requirements.txt or package.json for dependencies.",
                0.85
            ),
            ErrorType.LOGIC_ERROR: (
                "Fix logic error: review the algorithm and business logic. "
                "Consider a different approach or simplify the implementation.",
                0.5
            ),
            ErrorType.UNKNOWN: (
                "Unknown error type. Review the full error message and stack trace. "
                "Try a different approach or simplify the implementation.",
                0.3
            ),
        }

        return strategies.get(error_type, ("Review error and try alternative approach.", 0.4))

    def should_retry(self, analysis: ErrorAnalysis, attempt: int, max_attempts: int = 3) -> bool:
        """Determine if we should retry based on error type and attempt count.

        Args:
            analysis: Error analysis result
            attempt: Current attempt number (1-indexed)
            max_attempts: Maximum number of attempts

        Returns:
            True if should retry, False otherwise
        """
        if attempt >= max_attempts:
            return False

        # High-confidence fixes are worth retrying
        if analysis.confidence >= 0.8:
            return True

        # Syntax/import errors are usually fixable
        if analysis.error_type in [ErrorType.SYNTAX_ERROR, ErrorType.IMPORT_ERROR, ErrorType.NAME_ERROR]:
            return attempt < 2

        # Logic errors need different approach after 1 attempt
        if analysis.error_type in [ErrorType.LOGIC_ERROR, ErrorType.TEST_FAILURE]:
            return attempt < 2

        # Unknown errors - try once more
        if analysis.error_type == ErrorType.UNKNOWN:
            return attempt < 2

        return False

    def suggest_alternative_strategy(self, analysis: ErrorAnalysis) -> str:
        """Suggest an alternative strategy when retries fail.

        Args:
            analysis: Error analysis from failed attempts

        Returns:
            Alternative strategy description
        """
        if analysis.error_type in [ErrorType.LOGIC_ERROR, ErrorType.TEST_FAILURE]:
            return (
                "Try a fundamentally different approach: "
                "1) Simplify the implementation, "
                "2) Use a different algorithm or library, "
                "3) Break down into smaller steps"
            )

        if analysis.error_type == ErrorType.TIMEOUT:
            return (
                "Optimize for performance: "
                "1) Use more efficient data structures, "
                "2) Add caching, "
                "3) Reduce complexity"
            )

        if analysis.error_type in [ErrorType.IMPORT_ERROR, ErrorType.DEPENDENCY_MISSING]:
            return (
                "Check dependencies: "
                "1) Install missing packages, "
                "2) Use alternative library, "
                "3) Implement functionality without external dependency"
            )

        return (
            "Try alternative approach: "
            "1) Review requirements, "
            "2) Simplify implementation, "
            "3) Ask for clarification"
        )


if __name__ == "__main__":
    # Test error analyzer
    analyzer = ErrorAnalyzer()

    test_errors = [
        "File 'test.py', line 42\n    if x = 5:\n         ^\nSyntaxError: invalid syntax",
        "ModuleNotFoundError: No module named 'requests'",
        "AssertionError: Expected 5 but got 3",
    ]

    for error in test_errors:
        analysis = analyzer.analyze(error)
        print(f"\nError: {analysis.error_message}")
        print(f"Type: {analysis.error_type.value}")
        print(f"Fix: {analysis.fix_strategy}")
        print(f"Confidence: {analysis.confidence}")
        print(f"Should retry: {analyzer.should_retry(analysis, attempt=1)}")

"""Failure analysis for Stabilize phase to improve Reason phase."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class FailureContext:
    """Context about a failure for learning."""
    error_message: str
    stack_trace: str
    previous_attempt: str
    diff: str
    iteration: int
    changed_files: list[str]

    def to_prompt(self) -> str:
        """Convert failure context to LLM prompt."""
        return f"""
Previous attempt #{self.iteration} failed with error:

Error: {self.error_message}

Stack trace:
{self.stack_trace}

Previous approach:
{self.previous_attempt}

Changes that failed:
{self.diff}

Files modified: {', '.join(self.changed_files)}

Learn from this failure and propose a DIFFERENT approach. Do not repeat the same mistake.
"""


class FailureAnalyzer:
    """Analyzes failures to improve reasoning."""

    def __init__(self):
        self.failure_patterns: dict[str, int] = {}

    def analyze_failure(
        self,
        error: str,
        stack_trace: str,
        previous_attempt: str,
        diff: str,
        iteration: int,
        changed_files: list[str]
    ) -> FailureContext:
        """Analyze a failure and create context for learning."""

        # Track failure patterns
        error_type = self._extract_error_type(error)
        self.failure_patterns[error_type] = self.failure_patterns.get(error_type, 0) + 1

        return FailureContext(
            error_message=error,
            stack_trace=stack_trace,
            previous_attempt=previous_attempt,
            diff=diff,
            iteration=iteration,
            changed_files=changed_files
        )

    def _extract_error_type(self, error: str) -> str:
        """Extract error type from error message."""
        # Common Python error types
        error_types = [
            'SyntaxError', 'IndentationError', 'NameError', 'TypeError',
            'AttributeError', 'KeyError', 'ValueError', 'ImportError',
            'ModuleNotFoundError', 'FileNotFoundError'
        ]

        for error_type in error_types:
            if error_type in error:
                return error_type

        return 'UnknownError'

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

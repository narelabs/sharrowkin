"""Tests for core.tools module."""
import pytest
from pathlib import Path
from core.tools import (
    BLOCKED_COMMAND_TOKENS,
    SHELL_CONTROL_TOKENS,
    SymbolSummary,
)


def test_blocked_command_tokens():
    """Test that blocked command tokens are defined."""
    assert isinstance(BLOCKED_COMMAND_TOKENS, (list, tuple, set))
    assert len(BLOCKED_COMMAND_TOKENS) > 0


def test_shell_control_tokens():
    """Test that shell control tokens are defined."""
    assert isinstance(SHELL_CONTROL_TOKENS, (list, tuple, set))
    assert len(SHELL_CONTROL_TOKENS) > 0


def test_symbol_summary_creation():
    """Test SymbolSummary dataclass creation."""
    summary = SymbolSummary(kind="function", name="test_func")
    assert summary.kind == "function"
    assert summary.name == "test_func"
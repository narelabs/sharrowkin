"""Tests for analysis.code modules."""
import pytest
from analysis.code import CodeNodeType, CodeNode


def test_code_node_type_enum():
    """Test CodeNodeType enum values."""
    assert hasattr(CodeNodeType, "MODULE")
    assert hasattr(CodeNodeType, "CLASS")
    assert hasattr(CodeNodeType, "FUNCTION")
    assert hasattr(CodeNodeType, "METHOD")
    assert hasattr(CodeNodeType, "VARIABLE")
    assert hasattr(CodeNodeType, "CONSTANT")


def test_code_node_creation():
    """Test CodeNode dataclass creation."""
    node = CodeNode(
        id="test_node",
        type=CodeNodeType.FUNCTION,
        name="test_function",
        file_path="test.py",
        line_number=10,
    )
    assert node.id == "test_node"
    assert node.type == CodeNodeType.FUNCTION
    assert node.name == "test_function"
    assert node.file_path == "test.py"
    assert node.line_number == 10
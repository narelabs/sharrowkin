import pytest
from pathlib import Path
import ast

from analysis.code.semantic_graph import SemanticGraph, CodeNode, CodeNodeType


class TestSemanticGraph:
    """Test SemanticGraph builder."""

    def test_initialization(self):
        """Test graph initialization."""
        graph = SemanticGraph()
        assert graph is not None
        assert hasattr(graph, 'nodes')

    def test_add_node(self):
        """Test adding nodes to graph."""
        graph = SemanticGraph()
        node = CodeNode(
            id="test_func",
            name="test_func",
            type=CodeNodeType.FUNCTION,
            file_path=Path("test.py"),
            line_start=1,
            line_end=5
        )
        graph.add_node(node)
        assert len(graph.nodes) > 0

    def test_parse_python_file(self, temp_workspace):
        """Test parsing Python file into graph."""
        # Create test file
        test_file = temp_workspace / "test.py"
        test_file.write_text("""
def hello():
    print('world')

class TestClass:
    def method(self):
        pass
""")
        
        graph = SemanticGraph()
        graph.build_from_file(test_file)
        
        # Should have nodes for function and class
        assert len(graph.nodes) >= 2
        
        # Check node types
        node_types = [node.type for node in graph.nodes]
        assert CodeNodeType.FUNCTION in node_types
        assert CodeNodeType.CLASS in node_types


class TestCodeNode:
    """Test CodeNode dataclass."""

    def test_node_creation(self):
        """Test creating code node."""
        node = CodeNode(
            id="test_id",
            name="test_function",
            type=CodeNodeType.FUNCTION,
            file_path=Path("test.py"),
            line_start=10,
            line_end=20
        )
        assert node.name == "test_function"
        assert node.type == CodeNodeType.FUNCTION
        assert node.line_start == 10

    def test_node_with_metadata(self):
        """Test node with additional metadata."""
        node = CodeNode(
            id="test_id",
            name="test_class",
            type=CodeNodeType.CLASS,
            file_path=Path("test.py"),
            line_start=1,
            line_end=50,
            metadata={"docstring": "Test class", "complexity": 5}
        )
        assert node.metadata["docstring"] == "Test class"
        assert node.metadata["complexity"] == 5

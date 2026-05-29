"""Tests for semantic graph and code analysis."""
import pytest
from pathlib import Path
import tempfile

from analysis.code.semantic_graph import SemanticGraph, CodeNodeType
from analysis.code.dependency import DependencyAnalyzer
from analysis.code.patterns import PatternDetector


class TestSemanticGraph:
    """Tests for SemanticGraph."""

    @pytest.fixture
    def sample_python_file(self):
        """Create sample Python file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("""
class Calculator:
    def add(self, a, b):
        return a + b
    
    def multiply(self, a, b):
        return a * b

def main():
    calc = Calculator()
    result = calc.add(1, 2)
    print(result)
""")
            yield Path(f.name)

    def test_graph_creation(self, sample_python_file):
        """Test creating semantic graph from file."""
        graph = SemanticGraph()
        graph.add_file(sample_python_file)
        
        nodes = graph.get_all_nodes()
        assert len(nodes) > 0

    def test_graph_finds_classes(self, sample_python_file):
        """Test graph identifies classes."""
        graph = SemanticGraph()
        graph.add_file(sample_python_file)
        
        classes = graph.get_nodes_by_type(CodeNodeType.CLASS)
        assert len(classes) > 0
        assert any(node.name == "Calculator" for node in classes)

    def test_graph_finds_methods(self, sample_python_file):
        """Test graph identifies methods."""
        graph = SemanticGraph()
        graph.add_file(sample_python_file)
        
        methods = graph.get_nodes_by_type(CodeNodeType.METHOD)
        assert len(methods) >= 2
        method_names = [node.name for node in methods]
        assert "add" in method_names
        assert "multiply" in method_names

    def test_graph_finds_functions(self, sample_python_file):
        """Test graph identifies functions."""
        graph = SemanticGraph()
        graph.add_file(sample_python_file)
        
        functions = graph.get_nodes_by_type(CodeNodeType.FUNCTION)
        assert len(functions) > 0
        assert any(node.name == "main" for node in functions)


class TestDependencyAnalyzer:
    """Tests for DependencyAnalyzer."""

    @pytest.fixture
    def sample_files(self):
        """Create sample files with dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            
            (workspace / "module_a.py").write_text("""
import os
from pathlib import Path

def function_a():
    return Path.cwd()
""")
            
            (workspace / "module_b.py").write_text("""
from module_a import function_a

def function_b():
    return function_a()
""")
            
            yield workspace

    def test_analyze_imports(self, sample_files):
        """Test analyzing import dependencies."""
        analyzer = DependencyAnalyzer(workspace=sample_files)
        dependencies = analyzer.analyze()
        
        assert len(dependencies) > 0

    def test_detect_circular_dependencies(self, sample_files):
        """Test detecting circular dependencies."""
        # Create circular dependency
        (sample_files / "module_a.py").write_text("""
from module_b import function_b

def function_a():
    return function_b()
""")
        
        analyzer = DependencyAnalyzer(workspace=sample_files)
        circular = analyzer.find_circular_dependencies()
        
        # Should detect circular dependency
        assert len(circular) > 0


class TestPatternDetector:
    """Tests for PatternDetector."""

    def test_detect_singleton_pattern(self):
        """Test detecting Singleton pattern."""
        code = """
class Singleton:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
"""
        detector = PatternDetector()
        patterns = detector.analyze(code)
        
        assert "Singleton" in patterns

    def test_detect_factory_pattern(self):
        """Test detecting Factory pattern."""
        code = """
class ShapeFactory:
    @staticmethod
    def create_shape(shape_type):
        if shape_type == "circle":
            return Circle()
        elif shape_type == "square":
            return Square()
"""
        detector = PatternDetector()
        patterns = detector.analyze(code)
        
        assert "Factory" in patterns

    def test_detect_builder_pattern(self):
        """Test detecting Builder pattern."""
        code = """
class QueryBuilder:
    def __init__(self):
        self.query = ""

    def select(self, fields):
        self.query += f"SELECT {fields} "
        return self

    def from_table(self, table):
        self.query += f"FROM {table}"
        return self

    def build(self):
        return self.query
"""
        detector = PatternDetector()
        patterns = detector.analyze(code)

        assert "Builder" in patterns
"""Tests for Phase 3: Deep Code Understanding.

Tests the integration of:
- Context Linker (documentation, git history, cross-references)
- Data Flow Analyzer (variable tracking, flow paths, issues)
- Semantic Graph enhancements (enriched context)
"""

import ast
from pathlib import Path
import tempfile

from analysis import (
    SemanticGraph,
    SemanticGraphBuilder,
    CodeNode,
    CodeNodeType,
    ContextLinker,
    DataFlowAnalyzer,
)


def test_context_linker_basic():
    """Test basic context linking functionality."""
    # Create a simple semantic graph
    graph = SemanticGraph()

    # Add a module node
    module = CodeNode(
        id="test_module",
        name="test_module",
        node_type=CodeNodeType.MODULE,
        file_path="test_module.py",
    )
    graph.add_node(module)

    # Add a function node
    func = CodeNode(
        id="test_module.test_function",
        name="test_function",
        node_type=CodeNodeType.FUNCTION,
        file_path="test_module.py",
        line_number=10,
        docstring="Test function for context linking",
        parent_id="test_module",
        complexity=5,
    )
    graph.add_node(func)

    # Create context linker
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        linker = ContextLinker(graph, workspace)

        # Build context
        context = linker.build_context("test_module.test_function")

        assert context is not None
        assert context.node_id == "test_module.test_function"
        assert context.docstring == "Test function for context linking"

        # Get context summary
        summary = linker.get_context_summary("test_module.test_function")
        assert "test_module.test_function" in summary
        assert "Test function for context linking" in summary

    print("✓ Context linker basic test passed")


def test_data_flow_analyzer_basic():
    """Test basic data flow analysis."""
    # Sample function code
    source_code = """
def calculate_sum(a, b):
    result = a + b
    temp = result * 2
    return temp
"""

    # Create a code node
    node = CodeNode(
        id="test.calculate_sum",
        name="calculate_sum",
        node_type=CodeNodeType.FUNCTION,
        file_path="test.py",
        line_number=1,
        source_code=source_code,
    )

    # Analyze data flow
    analyzer = DataFlowAnalyzer()
    result = analyzer.analyze_function(node)

    assert "error" not in result
    assert result["total_variables"] >= 3  # a, b, result, temp
    assert result["flow_nodes"] > 0

    # Check for variable flow
    flow_nodes = analyzer.get_variable_flow("test.calculate_sum", "result")
    assert len(flow_nodes) > 0

    print("✓ Data flow analyzer basic test passed")


def test_data_flow_unused_variables():
    """Test detection of unused variables."""
    source_code = """
def test_function():
    used_var = 10
    unused_var = 20
    another_unused = 30
    return used_var
"""

    node = CodeNode(
        id="test.test_function",
        name="test_function",
        node_type=CodeNodeType.FUNCTION,
        source_code=source_code,
    )

    analyzer = DataFlowAnalyzer()
    result = analyzer.analyze_function(node)

    # Check for unused variable issues
    issues = result.get("issues", [])
    unused_issues = [i for i in issues if i["type"] == "unused"]

    assert len(unused_issues) >= 2  # unused_var and another_unused

    print("✓ Data flow unused variables test passed")


def test_data_flow_uninitialized_access():
    """Test detection of uninitialized variable access."""
    source_code = """
def test_function():
    result = uninitialized_var + 10
    return result
"""

    node = CodeNode(
        id="test.test_function",
        name="test_function",
        node_type=CodeNodeType.FUNCTION,
        source_code=source_code,
    )

    analyzer = DataFlowAnalyzer()
    result = analyzer.analyze_function(node)

    # Check for uninitialized access issues
    issues = result.get("issues", [])
    uninit_issues = [i for i in issues if i["type"] == "uninitialized"]

    assert len(uninit_issues) >= 1
    assert any("uninitialized_var" in i["message"] for i in uninit_issues)

    print("✓ Data flow uninitialized access test passed")


def test_semantic_graph_enriched_context():
    """Test enriched context from semantic graph."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create a test Python file
        test_file = workspace / "test_code.py"
        test_file.write_text("""
def complex_function(x, y):
    '''A complex function for testing.'''
    result = x + y
    temp = result * 2
    if temp > 10:
        temp = temp - 5
    return temp

def caller_function():
    return complex_function(5, 3)
""")

        # Build semantic graph
        graph = SemanticGraph(workspace / ".sharrowkin" / "semantic_graph")
        builder = SemanticGraphBuilder(graph)
        builder.build_from_file(test_file, "test_code")

        # Get enriched context
        enriched = graph.get_enriched_context("test_code.complex_function", workspace)

        assert "error" not in enriched
        assert enriched["name"] == "complex_function"
        assert enriched["type"] == "function"

        # Check for data flow analysis
        if "data_flow" in enriched:
            df = enriched["data_flow"]
            assert df["total_variables"] >= 3  # x, y, result, temp
            assert df["complexity_score"] > 0

        print("✓ Semantic graph enriched context test passed")


def test_change_impact_analysis():
    """Test change impact analysis."""
    graph = SemanticGraph()

    # Create a dependency chain: func_a -> func_b -> func_c
    func_a = CodeNode(
        id="module.func_a",
        name="func_a",
        node_type=CodeNodeType.FUNCTION,
        metadata={"calls": ["module.func_b"]},
    )

    func_b = CodeNode(
        id="module.func_b",
        name="func_b",
        node_type=CodeNodeType.FUNCTION,
        metadata={"calls": ["module.func_c"]},
    )

    func_c = CodeNode(
        id="module.func_c",
        name="func_c",
        node_type=CodeNodeType.FUNCTION,
        metadata={"calls": []},
    )

    graph.add_node(func_a)
    graph.add_node(func_b)
    graph.add_node(func_c)

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Analyze impact of changing func_c
        impact = graph.analyze_change_impact("module.func_c", workspace)

        assert "error" not in impact
        assert impact["node_id"] == "module.func_c"
        assert "direct_impact" in impact
        assert "risk_level" in impact

    print("✓ Change impact analysis test passed")


def test_find_related_code():
    """Test finding related code entities."""
    graph = SemanticGraph()

    # Create similar functions
    func1 = CodeNode(
        id="module.calculate_sum",
        name="calculate_sum",
        node_type=CodeNodeType.FUNCTION,
        signature="a, b",
        complexity=3,
    )

    func2 = CodeNode(
        id="module.calculate_product",
        name="calculate_product",
        node_type=CodeNodeType.FUNCTION,
        signature="a, b",
        complexity=3,
    )

    func3 = CodeNode(
        id="module.process_data",
        name="process_data",
        node_type=CodeNodeType.FUNCTION,
        signature="data",
        complexity=8,
    )

    graph.add_node(func1)
    graph.add_node(func2)
    graph.add_node(func3)

    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Find related code to calculate_sum
        related = graph.find_related_code("module.calculate_sum", workspace, max_results=5)

        # Should find calculate_product as similar (same signature, similar name)
        assert len(related) > 0

    print("✓ Find related code test passed")


def test_integration_with_agent():
    """Test Phase 3 integration with agent workflow."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)

        # Create a realistic test file
        test_file = workspace / "calculator.py"
        test_file.write_text("""
class Calculator:
    '''A simple calculator class.'''

    def __init__(self):
        self.history = []

    def add(self, a, b):
        '''Add two numbers.'''
        result = a + b
        self.history.append(('add', a, b, result))
        return result

    def multiply(self, a, b):
        '''Multiply two numbers.'''
        result = a * b
        self.history.append(('multiply', a, b, result))
        return result

    def get_history(self):
        '''Get calculation history.'''
        return self.history
""")

        # Build semantic graph (simulating agent's Observe phase)
        graph = SemanticGraph(workspace / ".sharrowkin" / "semantic_graph")
        builder = SemanticGraphBuilder(graph)
        builder.build_from_directory(workspace, recursive=False)

        # Verify graph was built
        assert len(graph.nodes) > 0

        # Get enriched context for a method
        enriched = graph.get_enriched_context("calculator.Calculator.add", workspace)

        if "error" not in enriched:
            assert enriched["name"] == "add"
            assert enriched["type"] == "method"

            # Should have data flow analysis
            if "data_flow" in enriched:
                assert enriched["data_flow"]["total_variables"] >= 2

        print("✓ Integration with agent test passed")


if __name__ == "__main__":
    print("\n=== Phase 3: Deep Code Understanding Tests ===\n")

    test_context_linker_basic()
    test_data_flow_analyzer_basic()
    test_data_flow_unused_variables()
    test_data_flow_uninitialized_access()
    test_semantic_graph_enriched_context()
    test_change_impact_analysis()
    test_find_related_code()
    test_integration_with_agent()

    print("\n✅ All Phase 3 tests passed!\n")

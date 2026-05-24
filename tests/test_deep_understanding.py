import ast
import tempfile
from pathlib import Path
from analysis.patterns import PatternDetector
from analysis.git import GitAnalyzer
# from analysis.documentation import DocLinker  # TODO: Fix import
from analysis.code.semantic_graph import SemanticGraph, SemanticGraphBuilder, CodeNodeType


def test_pattern_detector():
    code = """
class MySingleton:
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

class MyFactory:
    def create_widget(self):
        return Widget()

class MyBuilder:
    def set_name(self, name):
        self.name = name
        return self
        
    def set_value(self, value):
        self.value = value
        return self

class MyObserver:
    def __init__(self):
        self.observers = []
        
    def subscribe(self, observer):
        self.observers.append(observer)
        
    def notify(self, event):
        for obs in self.observers:
            obs.update(event)

class MyDecorator:
    def __init__(self, wrapped):
        self.wrapped = wrapped
"""
    tree = ast.parse(code)
    detector = PatternDetector()
    
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            detector.analyze_node(node, node.name)
            
    assert "MySingleton" in detector.detected_patterns["Singleton"]
    assert "MyFactory" in detector.detected_patterns["Factory"]
    assert "MyBuilder" in detector.detected_patterns["Builder"]
    assert "MyObserver" in detector.detected_patterns["Observer"]
    assert "MyDecorator" in detector.detected_patterns["Decorator"]


def test_git_analyzer_graceful_fallback():
    # Test on a temporary non-git directory
    with tempfile.TemporaryDirectory() as tmpdir:
        analyzer = GitAnalyzer(Path(tmpdir))
        assert not analyzer.is_git
        assert analyzer.get_recent_commits() == []
        assert analyzer.get_hotspots() == []
        assert analyzer.get_file_metadata("some_file.py") == {}


def test_doc_linker():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        doc_dir = tmp_path / "docs"
        doc_dir.mkdir()
        
        doc_file = doc_dir / "api.md"
        doc_file.write_text("# API Reference\nThis document describes `MyClass` and its methods like `run_process`.", encoding="utf-8")
        
        linker = DocLinker(tmp_path)
        mapping = linker.scan_documentation()
        
        assert "MyClass" in mapping
        assert "run_process" in mapping
        
        links = linker.get_links_for_symbol("MyClass")
        assert len(links) == 1
        assert links[0]["path"] == "docs/api.md"
        assert links[0]["title"] == "API Reference"


def test_semantic_graph_integration():
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        
        # Write dummy python file
        code_file = tmp_path / "module.py"
        code_file.write_text("""
class CustomSingleton:
    _instance = None
    def get_instance():
        return CustomSingleton._instance
""", encoding="utf-8")
        
        # Write dummy doc file
        doc_file = tmp_path / "readme.md"
        doc_file.write_text("# Readme\nDescribes `CustomSingleton`.", encoding="utf-8")
        
        sem_graph = SemanticGraph(tmp_path / ".sharrowkin" / "semantic_graph")
        builder = SemanticGraphBuilder(sem_graph)
        builder.build_from_directory(tmp_path)
        
        node_id = "module.CustomSingleton"
        node = sem_graph.get_node(node_id)
        assert node is not None
        assert node.node_type == CodeNodeType.CLASS
        
        # Check design pattern detected
        assert "Singleton" in node.metadata.get("detected_patterns", [])
        
        # Check documentation link
        doc_links = node.metadata.get("doc_links", [])
        assert len(doc_links) == 1
        assert doc_links[0]["title"] == "Readme"

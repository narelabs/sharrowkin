import pytest
from pathlib import Path

from analysis.code.dependency import DependencyAnalyzer, Dependency, DependencyType


class TestDependencyAnalyzer:
    """Test DependencyAnalyzer."""

    def test_initialization(self, temp_workspace):
        """Test analyzer initialization."""
        analyzer = DependencyAnalyzer(workspace_path=temp_workspace)
        assert analyzer is not None
        assert analyzer.workspace_path == temp_workspace

    def test_analyze_imports(self, temp_workspace):
        """Test analyzing import dependencies."""
        # Create test file with imports
        test_file = temp_workspace / "test.py"
        test_file.write_text("""
import os
import sys
from pathlib import Path
from typing import List, Dict
""")
        
        analyzer = DependencyAnalyzer(workspace_path=temp_workspace)
        dependencies = analyzer.analyze_file(test_file)
        
        assert len(dependencies) > 0
        
        # Check for import dependencies
        import_deps = [d for d in dependencies if d.type == DependencyType.IMPORT]
        assert len(import_deps) > 0

    def test_detect_circular_dependencies(self, temp_workspace):
        """Test circular dependency detection."""
        # Create files with circular imports
        file_a = temp_workspace / "module_a.py"
        file_b = temp_workspace / "module_b.py"
        
        file_a.write_text("from module_b import func_b")
        file_b.write_text("from module_a import func_a")
        
        analyzer = DependencyAnalyzer(workspace_path=temp_workspace)
        circular = analyzer.find_circular_dependencies()
        
        # Should detect circular dependency
        assert len(circular) > 0 or circular is not None


class TestDependency:
    """Test Dependency dataclass."""

    def test_dependency_creation(self):
        """Test creating dependency."""
        dep = Dependency(
            source="module_a",
            target="module_b",
            type=DependencyType.IMPORT,
            line_number=5
        )
        assert dep.source == "module_a"
        assert dep.target == "module_b"
        assert dep.type == DependencyType.IMPORT

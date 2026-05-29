import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.workspace_cache import WorkspaceCache, CachedWorkspace


class TestWorkspaceCache:
    """Test WorkspaceCache."""

    def test_initialization(self, temp_workspace):
        """Test cache initialization."""
        cache = WorkspaceCache(workspace_path=temp_workspace)
        assert cache is not None
        assert cache.workspace_path == temp_workspace

    def test_get_cached_workspace(self, temp_workspace, sample_cached_workspace):
        """Test getting cached workspace."""
        with patch('core.workspace_cache.WorkspaceCache._build_cache') as mock_build:
            mock_build.return_value = sample_cached_workspace
            
            cache = WorkspaceCache(workspace_path=temp_workspace)
            result = cache.get_cached_workspace()
            
            assert result is not None
            assert isinstance(result, CachedWorkspace)

    def test_invalidate_cache(self, temp_workspace):
        """Test cache invalidation."""
        cache = WorkspaceCache(workspace_path=temp_workspace)
        cache.invalidate()
        # Cache should be cleared
        assert cache._cache is None or not cache._cache


class TestCachedWorkspace:
    """Test CachedWorkspace dataclass."""

    def test_workspace_creation(self):
        """Test creating cached workspace."""
        workspace = CachedWorkspace(
            workspace_summary="Test summary",
            total_files=10,
            total_lines=500,
            complexity_avg=3.5,
            circular_dependencies=0,
            most_complex_functions=["func1", "func2"],
            semantic_insights="Insights here"
        )
        assert workspace.total_files == 10
        assert workspace.complexity_avg == 3.5
        assert len(workspace.most_complex_functions) == 2

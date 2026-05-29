import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from agent.phases.observe import ObserveModule
from agent.phases.recall import RecallModule
from agent.phases.reason import ReasonModule
from agent.phases.stabilize import StabilizeModule
from agent.phases.commit import CommitModule


@pytest.mark.asyncio
class TestObserveModule:
    """Test ObserveModule."""

    async def test_observe_workspace(self, temp_workspace, sample_cached_workspace):
        """Test workspace observation."""
        with patch('agent.phases.observe.DependencyAnalyzer') as mock_analyzer, \
             patch('agent.phases.observe.SemanticGraph') as mock_graph:
            
            mock_analyzer.return_value.analyze.return_value = []
            mock_graph.return_value.build.return_value = None
            
            module = ObserveModule(workspace_path=temp_workspace)
            result = await module.observe()
            
            assert result is not None
            assert isinstance(result, dict)


@pytest.mark.asyncio
class TestRecallModule:
    """Test RecallModule."""

    async def test_recall_memory(self, temp_workspace, mock_memory_bridge):
        """Test memory recall."""
        module = RecallModule(memory_bridge=mock_memory_bridge)
        result = await module.recall(query="test query")
        
        assert result is not None
        mock_memory_bridge.recall_structured.assert_called_once()


@pytest.mark.asyncio
class TestReasonModule:
    """Test ReasonModule."""

    async def test_reason_generates_patch(self, mock_llm_client):
        """Test reasoning generates a patch."""
        module = ReasonModule(llm_client=mock_llm_client)
        
        mock_llm_client.generate_patch.return_value = {
            "rationale": "Fix bug",
            "subtasks": ["Update file"],
            "files": {"test.py": "print('fixed')"},
            "commands": []
        }
        
        result = await module.reason(
            task="Fix the bug",
            context={"workspace": "test"}
        )
        
        assert result is not None
        assert "rationale" in result
        assert "files" in result


@pytest.mark.asyncio
class TestStabilizeModule:
    """Test StabilizeModule."""

    async def test_validate_python_syntax(self, temp_workspace):
        """Test Python syntax validation."""
        module = StabilizeModule(workspace_path=temp_workspace)
        
        # Valid Python code
        valid_code = "def hello():\n    print('world')"
        is_valid = await module._validate_syntax("test.py", valid_code)
        assert is_valid is True
        
        # Invalid Python code
        invalid_code = "def hello(\n    print('world')"
        is_valid = await module._validate_syntax("test.py", invalid_code)
        assert is_valid is False


@pytest.mark.asyncio
class TestCommitModule:
    """Test CommitModule."""

    async def test_commit_to_memory(self, mock_memory_bridge):
        """Test committing results to memory."""
        module = CommitModule(memory_bridge=mock_memory_bridge)
        
        await module.commit(
            task="Test task",
            result={"success": True},
            insights="Test insights"
        )
        
        # Verify memory bridge was called
        assert mock_memory_bridge.method_calls

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from agent.core import SharrowkinAgent, AgentRunState, FailureRecord
from agent.workspace_cache import CachedWorkspace


class TestAgentRunState:
    """Test AgentRunState dataclass."""

    def test_initialization(self):
        state = AgentRunState(
            task="Test task",
            workspace_path=Path("/test"),
            iteration=1
        )
        assert state.task == "Test task"
        assert state.iteration == 1
        assert state.failures == []

    def test_add_failure(self):
        state = AgentRunState(
            task="Test task",
            workspace_path=Path("/test"),
            iteration=1
        )
        failure = FailureRecord(
            iteration=1,
            changed_files=["test.py"],
            error="Test error",
            patch_diff="diff"
        )
        state.failures.append(failure)
        assert len(state.failures) == 1
        assert state.failures[0].error == "Test error"


class TestFailureRecord:
    """Test FailureRecord dataclass."""

    def test_initialization(self):
        record = FailureRecord(
            iteration=1,
            changed_files=["file1.py", "file2.py"],
            error="Syntax error",
            patch_diff="--- a/file1.py\n+++ b/file1.py"
        )
        assert record.iteration == 1
        assert len(record.changed_files) == 2
        assert "Syntax" in record.error


@pytest.mark.asyncio
class TestSharrowkinAgent:
    """Test SharrowkinAgent main class."""

    async def test_agent_initialization(self, temp_workspace, mock_llm_client, mock_memory_bridge):
        """Test agent can be initialized."""
        with patch('agent.core.GeminiClient', return_value=mock_llm_client), \
             patch('agent.core.MemoryBridge', return_value=mock_memory_bridge):
            agent = SharrowkinAgent(
                workspace_path=temp_workspace,
                llm_client=mock_llm_client,
                memory_bridge=mock_memory_bridge
            )
            assert agent.workspace_path == temp_workspace
            assert agent.llm_client == mock_llm_client

    async def test_run_with_simple_task(self, temp_workspace, mock_llm_client, mock_memory_bridge, sample_cached_workspace):
        """Test agent can run a simple task."""
        with patch('agent.core.GeminiClient', return_value=mock_llm_client), \
             patch('agent.core.MemoryBridge', return_value=mock_memory_bridge), \
             patch('agent.core.WorkspaceCache') as mock_cache:
            
            mock_cache.return_value.get_cached_workspace.return_value = sample_cached_workspace
            
            agent = SharrowkinAgent(
                workspace_path=temp_workspace,
                llm_client=mock_llm_client,
                memory_bridge=mock_memory_bridge
            )
            
            # Mock the phases
            with patch.object(agent, '_observe_phase', new_callable=AsyncMock) as mock_observe, \
                 patch.object(agent, '_recall_phase', new_callable=AsyncMock) as mock_recall, \
                 patch.object(agent, '_reason_phase', new_callable=AsyncMock) as mock_reason, \
                 patch.object(agent, '_stabilize_phase', new_callable=AsyncMock) as mock_stabilize, \
                 patch.object(agent, '_commit_phase', new_callable=AsyncMock) as mock_commit:
                
                mock_reason.return_value = {"files": {}, "commands": []}
                mock_stabilize.return_value = True
                
                # This would normally run the full cycle
                # For now just verify initialization works
                assert agent is not None

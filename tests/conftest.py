import pytest
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import tempfile
import shutil


@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_llm_client():
    """Mock GeminiClient for testing."""
    client = AsyncMock()
    client.generate_patch.return_value = {
        "rationale": "Test rationale",
        "subtasks": ["Task 1"],
        "files": {},
        "commands": []
    }
    return client


@pytest.fixture
def mock_memory_bridge():
    """Mock MemoryBridge for testing."""
    bridge = MagicMock()
    bridge.recall_structured.return_value = {
        "rld_context": "",
        "dsm_segments": [],
        "global_summary": ""
    }
    return bridge


@pytest.fixture
def sample_cached_workspace():
    """Sample CachedWorkspace for testing."""
    from agent.workspace_cache import CachedWorkspace
    return CachedWorkspace(
        workspace_summary="Test workspace",
        total_files=5,
        total_lines=100,
        complexity_avg=2.5,
        circular_dependencies=0,
        most_complex_functions=[],
        semantic_insights="Test insights"
    )


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

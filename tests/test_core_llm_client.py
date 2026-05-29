import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from core.llm.client import GeminiClient, GeneratedPatch


@pytest.mark.asyncio
class TestGeminiClient:
    """Test GeminiClient."""

    async def test_initialization(self):
        """Test client initialization."""
        with patch.dict('os.environ', {'GEMINI_API_KEY': 'test_key'}):
            client = GeminiClient(api_key='test_key')
            assert client is not None

    async def test_generate_patch(self):
        """Test patch generation."""
        with patch('core.llm.client.httpx.AsyncClient') as mock_client:
            mock_response = MagicMock()
            mock_response.json.return_value = {
                "candidates": [{
                    "content": {
                        "parts": [{
                            "text": json.dumps({
                                "rationale": "Test",
                                "subtasks": [],
                                "files": {},
                                "commands": []
                            })
                        }]
                    }
                }]
            }
            mock_response.raise_for_status = MagicMock()
            
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            client = GeminiClient(api_key='test_key')
            result = await client.generate_patch(
                task="Test task",
                context={"workspace": "test"}
            )
            
            assert result is not None
            assert "rationale" in result


class TestGeneratedPatch:
    """Test GeneratedPatch dataclass."""

    def test_patch_creation(self):
        """Test creating patch object."""
        patch = GeneratedPatch(
            rationale="Fix bug",
            subtasks=["Update file"],
            files={"test.py": "print('fixed')"},
            commands=["pytest"]
        )
        assert patch.rationale == "Fix bug"
        assert len(patch.subtasks) == 1
        assert "test.py" in patch.files
        assert len(patch.commands) == 1

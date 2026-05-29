"""Tests for LLM client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.llm.client import GeminiClient, repair_truncated_json


class TestGeminiClient:
    """Tests for GeminiClient."""

    @pytest.fixture
    def mock_httpx_client(self):
        """Mock httpx client."""
        with patch("core.llm.client.httpx.AsyncClient") as mock:
            yield mock

    @pytest.mark.asyncio
    async def test_generate_patch_success(self, mock_httpx_client):
        """Test successful patch generation."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {
                                "text": '{"rationale": "test", "files": {}, "commands": []}'
                            }
                        ]
                    }
                }
            ]
        }
        mock_httpx_client.return_value.__aenter__.return_value.post = AsyncMock(
            return_value=mock_response
        )

        client = GeminiClient(api_key="test_key")
        
        result = None
        async for chunk in client.generate_patch(
            task="Test task",
            workspace_context="Test context",
            memory_context="Test memory",
        ):
            result = chunk

        assert result is not None
        assert "rationale" in result

    @pytest.mark.asyncio
    async def test_generate_patch_retry_on_timeout(self, mock_httpx_client):
        """Test retry logic on timeout."""
        mock_httpx_client.return_value.__aenter__.return_value.post = AsyncMock(
            side_effect=TimeoutError("Request timeout")
        )

        client = GeminiClient(api_key="test_key", max_retries=2)

        with pytest.raises(Exception):
            async for _ in client.generate_patch(
                task="Test task",
                workspace_context="Test context",
                memory_context="Test memory",
            ):
                pass


class TestJSONRepair:
    """Tests for JSON repair functionality."""

    def test_repair_truncated_json_valid(self):
        """Test repair with valid JSON."""
        valid_json = '{"key": "value", "number": 42}'
        result = repair_truncated_json(valid_json)
        
        assert result["key"] == "value"
        assert result["number"] == 42

    def test_repair_truncated_json_missing_brace(self):
        """Test repair with missing closing brace."""
        truncated = '{"key": "value", "number": 42'
        result = repair_truncated_json(truncated)
        
        assert result["key"] == "value"
        assert result["number"] == 42

    def test_repair_truncated_json_missing_quote(self):
        """Test repair with missing closing quote."""
        truncated = '{"key": "value", "text": "incomplete'
        result = repair_truncated_json(truncated)
        
        assert result["key"] == "value"
        assert "text" in result

    def test_repair_truncated_json_nested(self):
        """Test repair with nested objects."""
        truncated = '{"outer": {"inner": "value"'
        result = repair_truncated_json(truncated)
        
        assert "outer" in result
        assert isinstance(result["outer"], dict)

    def test_repair_truncated_json_array(self):
        """Test repair with arrays."""
        truncated = '{"items": [1, 2, 3'
        result = repair_truncated_json(truncated)
        
        assert "items" in result
        assert isinstance(result["items"], list)

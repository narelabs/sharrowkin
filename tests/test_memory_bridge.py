import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

from memory.bridge import MemoryBridge


@pytest.mark.asyncio
class TestMemoryBridge:
    """Test MemoryBridge integration."""

    async def test_initialization(self):
        """Test MemoryBridge can be initialized."""
        with patch('memory.bridge.DynamicSegmentedMemory') as mock_dsm, \
             patch('memory.bridge.ReasoningLibrary') as mock_rld:
            
            bridge = MemoryBridge(
                dsm_path=Path("/tmp/dsm"),
                rld_path=Path("/tmp/rld")
            )
            assert bridge is not None

    async def test_recall_structured(self):
        """Test structured memory recall."""
        with patch('memory.bridge.DynamicSegmentedMemory') as mock_dsm, \
             patch('memory.bridge.ReasoningLibrary') as mock_rld:
            
            mock_dsm_instance = MagicMock()
            mock_dsm_instance.query.return_value = []
            mock_dsm.return_value = mock_dsm_instance
            
            mock_rld_instance = MagicMock()
            mock_rld_instance.activate_genes.return_value = []
            mock_rld.return_value = mock_rld_instance
            
            bridge = MemoryBridge(
                dsm_path=Path("/tmp/dsm"),
                rld_path=Path("/tmp/rld")
            )
            
            result = await bridge.recall_structured(
                query="test query",
                context={"task": "test"}
            )
            
            assert result is not None
            assert isinstance(result, dict)

    async def test_store_segment(self):
        """Test storing memory segment."""
        with patch('memory.bridge.DynamicSegmentedMemory') as mock_dsm, \
             patch('memory.bridge.ReasoningLibrary') as mock_rld:
            
            mock_dsm_instance = MagicMock()
            mock_dsm.return_value = mock_dsm_instance
            
            bridge = MemoryBridge(
                dsm_path=Path("/tmp/dsm"),
                rld_path=Path("/tmp/rld")
            )
            
            await bridge.store_segment(
                content="Test content",
                category="Test",
                metadata={"key": "value"}
            )
            
            # Verify DSM store was called
            assert mock_dsm_instance.method_calls

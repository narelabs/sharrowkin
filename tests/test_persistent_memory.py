"""Test Persistent Conversation Memory implementation."""

import pytest
from pathlib import Path
from backend.agent.core import SharrowkinAgent
from backend.memory import MemoryBridge


@pytest.mark.asyncio
async def test_conversation_saved_to_dsm(tmp_path):
    """Test that conversation messages are saved to DSM."""

    # Create agent
    agent = SharrowkinAgent()

    # Create memory bridge
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    memory = MemoryBridge(workspace)

    # Save a user message
    agent._save_conversation_to_dsm("user", "Привет, как дела?", memory)

    # Save an assistant message
    agent._save_conversation_to_dsm("assistant", "Отлично! Чем могу помочь?", memory)

    # Search for conversation in DSM
    results = memory.dsm.route("Привет", top_k=5)

    # Verify messages were saved
    assert len(results) > 0, "No conversation messages found in DSM"

    # Check that user message is in results
    user_found = any("user: Привет" in node.text for node in results)
    assert user_found, "User message not found in DSM"

    print(f"✅ Test passed: {len(results)} conversation nodes found in DSM")


@pytest.mark.asyncio
async def test_conversation_metadata(tmp_path):
    """Test that conversation metadata is correctly stored."""

    agent = SharrowkinAgent()
    workspace = tmp_path / "test_workspace"
    workspace.mkdir()
    memory = MemoryBridge(workspace)

    # Save message with metadata
    test_message = "Test message for metadata"
    agent._save_conversation_to_dsm("user", test_message, memory)

    # Search for the message
    results = memory.dsm.route(test_message, top_k=1)

    assert len(results) > 0, "Message not found in DSM"

    node = results[0]

    # Verify metadata
    assert "role" in node.metadata, "Role not in metadata"
    assert node.metadata["role"] == "user", "Role is incorrect"
    assert "timestamp" in node.metadata, "Timestamp not in metadata"
    assert "content_length" in node.metadata, "Content length not in metadata"

    print(f"✅ Test passed: Metadata correctly stored - {node.metadata}")


if __name__ == "__main__":
    import asyncio
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        print("Running test_conversation_saved_to_dsm...")
        asyncio.run(test_conversation_saved_to_dsm(Path(tmpdir)))

        print("\nRunning test_conversation_metadata...")
        asyncio.run(test_conversation_metadata(Path(tmpdir)))

        print("\n✅ All tests passed!")

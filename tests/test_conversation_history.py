"""Tests for ConversationHistory module."""

import pytest
import time
from pathlib import Path
import tempfile
import shutil

from memory.conversation import ConversationHistory, Message


@pytest.fixture
def temp_workspace():
    """Create temporary workspace for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


def test_message_creation():
    """Test Message dataclass creation."""
    msg = Message(
        role="user",
        content="test message",
        timestamp=time.time(),
        metadata={"key": "value"}
    )

    assert msg.role == "user"
    assert msg.content == "test message"
    assert msg.metadata["key"] == "value"


def test_message_to_dict():
    """Test Message serialization."""
    msg = Message(
        role="assistant",
        content="response",
        timestamp=123.456,
        metadata={}
    )

    data = msg.to_dict()
    assert data["role"] == "assistant"
    assert data["content"] == "response"
    assert data["timestamp"] == 123.456


def test_message_from_dict():
    """Test Message deserialization."""
    data = {
        "role": "user",
        "content": "hello",
        "timestamp": 789.012,
        "metadata": {"test": True}
    }

    msg = Message.from_dict(data)
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.metadata["test"] is True


def test_conversation_initialization(temp_workspace):
    """Test ConversationHistory initialization."""
    history = ConversationHistory(
        session_id="test_session",
        workspace=temp_workspace,
        max_messages=10,
        context_window=5
    )

    assert history.session_id == "test_session"
    assert history.max_messages == 10
    assert history.context_window == 5
    assert len(history) == 0


def test_add_message(temp_workspace):
    """Test adding messages to conversation."""
    history = ConversationHistory("test", temp_workspace)

    history.add_message("user", "Hello")
    assert len(history) == 1

    history.add_message("assistant", "Hi there")
    assert len(history) == 2

    messages = list(history.messages)
    assert messages[0].role == "user"
    assert messages[0].content == "Hello"
    assert messages[1].role == "assistant"
    assert messages[1].content == "Hi there"


def test_conversation_persistence(temp_workspace):
    """Test conversation persistence to disk."""
    session_id = "persist_test"

    # Create and populate conversation
    history1 = ConversationHistory(session_id, temp_workspace)
    history1.add_message("user", "test message 1")
    history1.add_message("assistant", "response 1")

    # Create new instance with same session_id
    history2 = ConversationHistory(session_id, temp_workspace)

    # Should load previous messages
    assert len(history2) == 2
    messages = list(history2.messages)
    assert messages[0].content == "test message 1"
    assert messages[1].content == "response 1"


def test_get_recent_context(temp_workspace):
    """Test getting recent messages."""
    history = ConversationHistory("test", temp_workspace, context_window=3)

    for i in range(5):
        history.add_message("user", f"message {i}")

    recent = history.get_recent_context(n=3)
    assert len(recent) == 3
    assert recent[-1].content == "message 4"


def test_get_context_string(temp_workspace):
    """Test formatting context as string."""
    history = ConversationHistory("test", temp_workspace)

    history.add_message("user", "Hello")
    history.add_message("assistant", "Hi", metadata={"tools_used": ["read", "write"]})

    context = history.get_context_string(n=2, include_metadata=True)

    assert "USER: Hello" in context
    assert "ASSISTANT: Hi" in context
    assert "Tools: read, write" in context


def test_search_messages(temp_workspace):
    """Test searching messages."""
    history = ConversationHistory("test", temp_workspace)

    history.add_message("user", "How do I fix the bug?")
    history.add_message("assistant", "Check the logs")
    history.add_message("user", "What about tests?")

    results = history.search_messages("bug", limit=2)
    assert len(results) >= 1
    assert any("bug" in msg.content.lower() for msg in results)


def test_get_summary(temp_workspace):
    """Test getting conversation summary."""
    history = ConversationHistory("test", temp_workspace)

    history.add_message("user", "message 1")
    time.sleep(0.1)
    history.add_message("assistant", "response 1")

    summary = history.get_summary()

    assert summary["total_messages"] == 2
    assert summary["user_messages"] == 1
    assert summary["assistant_messages"] == 1
    assert summary["duration_seconds"] > 0


def test_clear_conversation(temp_workspace):
    """Test clearing conversation."""
    history = ConversationHistory("test", temp_workspace)

    history.add_message("user", "test")
    assert len(history) == 1

    history.clear()
    assert len(history) == 0


def test_max_messages_limit(temp_workspace):
    """Test max_messages limit enforcement."""
    history = ConversationHistory("test", temp_workspace, max_messages=3)

    for i in range(5):
        history.add_message("user", f"message {i}")

    # Should only keep last 3 messages
    assert len(history) == 3
    messages = list(history.messages)
    assert messages[0].content == "message 2"
    assert messages[-1].content == "message 4"


def test_metadata_storage(temp_workspace):
    """Test storing metadata with messages."""
    history = ConversationHistory("test", temp_workspace)

    metadata = {
        "tools_used": ["read", "write", "execute"],
        "files_changed": ["file1.py", "file2.py"]
    }

    history.add_message("assistant", "Done", metadata=metadata)

    messages = list(history.messages)
    assert messages[0].metadata["tools_used"] == ["read", "write", "execute"]
    assert messages[0].metadata["files_changed"] == ["file1.py", "file2.py"]


def test_empty_conversation_summary(temp_workspace):
    """Test summary of empty conversation."""
    history = ConversationHistory("test", temp_workspace)

    summary = history.get_summary()

    assert summary["total_messages"] == 0
    assert summary["user_messages"] == 0
    assert summary["assistant_messages"] == 0


def test_conversation_repr(temp_workspace):
    """Test string representation."""
    history = ConversationHistory("test_session", temp_workspace)
    history.add_message("user", "test")

    repr_str = repr(history)
    assert "test_session" in repr_str
    assert "messages=1" in repr_str


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

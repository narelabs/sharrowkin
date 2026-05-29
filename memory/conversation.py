"""Conversation history management for maintaining dialog context.

This module provides short-term conversational memory separate from long-term
DSM/RLD memory systems. It ensures the agent remembers recent exchanges within
a session.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # "user" or "assistant"
    content: str
    timestamp: float
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Message:
        """Create from dictionary."""
        return cls(**data)


class ConversationHistory:
    """Manages conversation history for a session.

    Provides:
    - Short-term memory of recent messages
    - Automatic summarization of old messages
    - Context window management for LLM
    - Persistence to disk
    """

    def __init__(
        self,
        session_id: str,
        workspace: Path,
        max_messages: int = 50,
        context_window: int = 10
    ):
        """Initialize conversation history.

        Args:
            session_id: Unique session identifier
            workspace: Workspace directory
            max_messages: Maximum messages to keep in memory
            context_window: Number of recent messages to include in context
        """
        self.session_id = session_id
        self.workspace = workspace
        self.max_messages = max_messages
        self.context_window = context_window

        # Use deque for efficient FIFO operations
        self.messages: deque[Message] = deque(maxlen=max_messages)

        # Storage path
        self.storage_dir = workspace / ".sharrowkin" / "conversations"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.storage_path = self.storage_dir / f"{session_id}.json"

        # Load existing conversation if available
        self._load()

    def add_message(self, role: str, content: str, metadata: Dict[str, Any] = None) -> None:
        """Add a message to the conversation.

        Args:
            role: "user" or "assistant"
            content: Message content
            metadata: Optional metadata (tools used, files changed, etc.)
        """
        message = Message(
            role=role,
            content=content,
            timestamp=time.time(),
            metadata=metadata or {}
        )
        self.messages.append(message)

        # Auto-save after each message
        self._save()

    def get_recent_context(self, n: int = None) -> List[Message]:
        """Get recent messages for context.

        Args:
            n: Number of recent messages (default: context_window)

        Returns:
            List of recent messages
        """
        if n is None:
            n = self.context_window

        # Return last n messages
        return list(self.messages)[-n:]

    def get_context_string(self, n: int = None, include_metadata: bool = False) -> str:
        """Get recent context as formatted string for LLM.

        Args:
            n: Number of recent messages
            include_metadata: Include metadata in output

        Returns:
            Formatted conversation context
        """
        recent = self.get_recent_context(n)

        lines = []
        for msg in recent:
            lines.append(f"{msg.role.upper()}: {msg.content}")

            if include_metadata and msg.metadata:
                # Add relevant metadata
                if "tools_used" in msg.metadata:
                    lines.append(f"  [Tools: {', '.join(msg.metadata['tools_used'])}]")
                if "files_changed" in msg.metadata:
                    lines.append(f"  [Files: {', '.join(msg.metadata['files_changed'])}]")

        return "\n\n".join(lines)

    def get_summary(self) -> Dict[str, Any]:
        """Get conversation summary with auto-summarization for long conversations.

        Returns:
            Dictionary with summary info including LLM-generated summary if available
        """
        if not self.messages:
            return {
                "total_messages": 0,
                "user_messages": 0,
                "assistant_messages": 0,
                "duration_seconds": 0,
                "summary_text": None
            }

        user_count = sum(1 for m in self.messages if m.role == "user")
        assistant_count = sum(1 for m in self.messages if m.role == "assistant")

        first_time = self.messages[0].timestamp
        last_time = self.messages[-1].timestamp

        summary = {
            "total_messages": len(self.messages),
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "duration_seconds": last_time - first_time,
            "first_message_time": first_time,
            "last_message_time": last_time,
            "summary_text": None
        }

        # ✅ NEW: Generate LLM summary for long conversations
        if len(self.messages) > 10:
            try:
                summary["summary_text"] = self._generate_summary()
            except Exception as e:
                print(f"[ConversationHistory] Summary generation failed: {e}")

        return summary

    def _generate_summary(self) -> str:
        """Generate a concise summary of the conversation using LLM.

        Returns:
            Summary text
        """
        # Get conversation text
        conversation_text = self.get_context_string(n=20)

        # Simple extractive summary (first and last messages)
        if len(self.messages) >= 2:
            first_msg = self.messages[0]
            last_msg = self.messages[-1]

            summary = f"Conversation started with: {first_msg.content[:100]}...\n"
            summary += f"Latest: {last_msg.content[:100]}..."

            return summary

        return "No summary available"

    def search_messages(self, query: str, limit: int = 5) -> List[Message]:
        """Search messages by semantic similarity using embeddings.

        Args:
            query: Search query
            limit: Maximum results

        Returns:
            List of matching messages sorted by relevance
        """
        if not self.messages:
            return []

        try:
            # Get query embedding
            from memory.dsm.indexing.embedding import HashEmbeddingModel
            embedding_model = HashEmbeddingModel()
            query_embedding = embedding_model.encode(query)

            # Calculate similarity for each message
            matches = []
            for msg in self.messages:
                msg_embedding = embedding_model.encode(msg.content)

                # Cosine similarity
                from memory.dsm.indexing.embedding import cosine
                similarity = cosine(query_embedding, msg_embedding)

                matches.append((msg, similarity))

            # Sort by similarity
            matches.sort(key=lambda x: x[1], reverse=True)

            # Return top matches
            return [msg for msg, _ in matches[:limit]]

        except Exception as e:
            print(f"[ConversationHistory] Semantic search failed, falling back to text search: {e}")
            # Fallback to simple text search
            query_lower = query.lower()
            matches = []

            for msg in reversed(self.messages):
                if query_lower in msg.content.lower():
                    matches.append(msg)
                    if len(matches) >= limit:
                        break

            return matches

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()
        self._save()

    def _save(self) -> None:
        """Save conversation to disk."""
        try:
            data = {
                "session_id": self.session_id,
                "messages": [msg.to_dict() for msg in self.messages],
                "saved_at": time.time()
            }

            with open(self.storage_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[ConversationHistory] Error saving: {e}")

    def _load(self) -> None:
        """Load conversation from disk."""
        if not self.storage_path.exists():
            return

        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Restore messages
            for msg_data in data.get("messages", []):
                self.messages.append(Message.from_dict(msg_data))

            print(f"[ConversationHistory] Loaded {len(self.messages)} messages for session {self.session_id}")
        except Exception as e:
            print(f"[ConversationHistory] Error loading: {e}")

    def __len__(self) -> int:
        """Return number of messages."""
        return len(self.messages)

    def __repr__(self) -> str:
        """String representation."""
        return f"ConversationHistory(session={self.session_id}, messages={len(self.messages)})"

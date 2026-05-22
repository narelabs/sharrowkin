"""Conversation-aware context for custom tools.

Adapted from Google Antigravity SDK for Sharrowkin Agent.

ToolContext is injected into tools that opt in by declaring a
``ToolContext``-typed parameter. It provides conversation capabilities:
identity, idle state, message injection, and per-conversation state.

Example::

    from core.tool_system.tool_context import ToolContext

    def my_tool(query: str, ctx: ToolContext) -> str:
        \"\"\"Searches and records the query in conversation state.\"\"\"
        ctx.set_state("last_query", query)
        return f"Searching for {query}..."
"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from core.strategy.sharrowkin import SharrowkinConnection


class ToolContext:
    """Conversation-aware context injected into tools that request it.

    Wraps a Connection and provides conversation capabilities.
    Per-conversation state persists for the lifetime of the session.
    """

    def __init__(self, conn: "SharrowkinConnection") -> None:
        """Initializes the ToolContext.

        Args:
            conn: The active connection to the agent backend.
        """
        self._connection = conn
        self._state: dict[str, Any] = {}

    @property
    def conversation_id(self) -> str:
        """Returns the conversation identifier."""
        return self._connection.conversation_id

    @property
    def is_idle(self) -> bool:
        """Returns True if the connection is idle."""
        return self._connection.is_idle

    @property
    def workspace(self) -> str:
        """Returns the workspace path."""
        return self._connection.workspace

    async def send(self, message: str) -> None:
        """Sends a message into the agent conversation.

        This injects a notification into the conversation,
        allowing a tool to asynchronously push follow-up messages.

        Args:
            message: The message content to send.
        """
        # For Sharrowkin, we can add this to the steps queue
        from core import types
        import uuid

        step = types.Step(
            id=str(uuid.uuid4()),
            step_index=len(self._connection.history_steps),
            type=types.StepType.TEXT_RESPONSE,
            source=types.StepSource.SYSTEM,
            target=types.StepTarget.USER,
            status=types.StepStatus.DONE,
            content=message
        )
        await self._connection._steps_queue.put(step)

    def get_state(self, key: str, default: Any = None) -> Any:
        """Retrieves a value from the per-conversation state store.

        Args:
            key: The state key.
            default: Value returned when the key is absent.

        Returns:
            The stored value, or ``default`` if the key is not found.
        """
        return self._state.get(key, default)

    def set_state(self, key: str, value: Any) -> None:
        """Stores a value in the per-conversation state store.

        Args:
            key: The state key.
            value: The value to store.
        """
        self._state[key] = value

    def clear_state(self) -> None:
        """Clears all per-conversation state."""
        self._state.clear()

"""Base hook definitions for Sharrowkin Agent.

Extracted and adapted from Google Antigravity SDK.
"""

from __future__ import annotations

import abc
from typing import Any, Awaitable, Generic, TypeVar

from backend.core.types import HookResult, QuestionHookResult, ToolCall


# --- Contexts ---


class HookContext:
    """Base context for hooks to share state."""

    def __init__(self, parent: "HookContext | None" = None):
        self.parent = parent
        self._store: dict[str, Any] = {}

    def get(self, key: str, default: Any = None) -> Any:
        """Gets a value from the context or its parents."""
        if key in self._store:
            return self._store[key]
        if self.parent:
            return self.parent.get(key, default)
        return default

    def set(self, key: str, value: Any) -> None:
        """Sets a value in the local context."""
        self._store[key] = value


class SessionContext(HookContext):
    """Context scoped to an entire session."""

    def __init__(self):
        super().__init__(parent=None)


class TurnContext(HookContext):
    """Context scoped to a single turn."""

    def __init__(self, session_context: SessionContext):
        super().__init__(parent=session_context)


class OperationContext(HookContext):
    """Context scoped to a specific operation (e.g. tool call)."""

    def __init__(self, turn_context: TurnContext):
        super().__init__(parent=turn_context)


# --- Base Hook Types ---


T = TypeVar("T")
R = TypeVar("R")


class InspectHook(abc.ABC, Generic[T]):
    """Read-only, non-blocking hook for observability."""

    @abc.abstractmethod
    async def run(self, context: HookContext, data: T) -> None:
        """Runs the inspection hook.

        Args:
            context: The hook context.
            data: The data to inspect.
        """


class DecideHook(abc.ABC, Generic[T]):
    """Read-only, blocking hook for policy enforcement."""

    @abc.abstractmethod
    async def run(self, context: HookContext, data: T) -> HookResult:
        """Runs the decision hook.

        Args:
            context: The hook context.
            data: The data to decide on.

        Returns:
            HookResult indicating whether to allow or deny.
        """


class TransformHook(abc.ABC, Generic[T, R]):
    """Modifying, blocking hook for data transformation."""

    @abc.abstractmethod
    async def run(self, context: HookContext, data: T) -> R:
        """Runs the transformation hook.

        Args:
            context: The hook context.
            data: The data to transform.

        Returns:
            The transformed data.
        """


# --- Specific Hook Types ---


class PreToolCallDecideHook(DecideHook[ToolCall]):
    """Hook that runs before a tool call to approve or deny it."""


class PostToolCallHook(InspectHook[tuple[ToolCall, Any]]):
    """Hook that runs after a tool call completes."""


class OnToolErrorHook(TransformHook[tuple[ToolCall, Exception], str]):
    """Hook that runs when a tool call fails."""


class PreTurnHook(DecideHook[str]):
    """Hook that runs before a turn starts."""


class PostTurnHook(InspectHook[str]):
    """Hook that runs after a turn completes."""


class PrePhaseHook(DecideHook[str]):
    """Hook that runs before a phase starts (Observe, Recall, Reason, Stabilize, Commit)."""


class PostPhaseHook(InspectHook[str]):
    """Hook that runs after a phase completes."""


# --- Hook Type Union ---


Hook = (
    PreToolCallDecideHook
    | PostToolCallHook
    | OnToolErrorHook
    | PreTurnHook
    | PostTurnHook
    | PrePhaseHook
    | PostPhaseHook
)

"""Hook runner for dispatching hooks in Sharrowkin Agent.

Extracted and adapted from Google Antigravity SDK.
"""

from __future__ import annotations

import logging
from typing import Any

from core.types import HookResult, ToolCall
from core.hooks.base import (
    Hook,
    HookContext,
    SessionContext,
    TurnContext,
    OperationContext,
    PreToolCallDecideHook,
    PostToolCallHook,
    OnToolErrorHook,
    PreTurnHook,
    PostTurnHook,
    PrePhaseHook,
    PostPhaseHook,
)


_logger = logging.getLogger(__name__)


class HookRunner:
    """Manages and dispatches hooks throughout the agent lifecycle."""

    def __init__(self):
        self.pre_tool_call_decide_hooks: list[PreToolCallDecideHook] = []
        self.post_tool_call_hooks: list[PostToolCallHook] = []
        self.on_tool_error_hooks: list[OnToolErrorHook] = []
        self.pre_turn_hooks: list[PreTurnHook] = []
        self.post_turn_hooks: list[PostTurnHook] = []
        self.pre_phase_hooks: list[PrePhaseHook] = []
        self.post_phase_hooks: list[PostPhaseHook] = []

        self.session_context = SessionContext()

    def register_hook(self, hook: Hook) -> None:
        """Registers a hook by inferring its type.

        Args:
            hook: The hook to register.
        """
        if isinstance(hook, PreToolCallDecideHook):
            self.pre_tool_call_decide_hooks.append(hook)
        elif isinstance(hook, PostToolCallHook):
            self.post_tool_call_hooks.append(hook)
        elif isinstance(hook, OnToolErrorHook):
            self.on_tool_error_hooks.append(hook)
        elif isinstance(hook, PreTurnHook):
            self.pre_turn_hooks.append(hook)
        elif isinstance(hook, PostTurnHook):
            self.post_turn_hooks.append(hook)
        elif isinstance(hook, PrePhaseHook):
            self.pre_phase_hooks.append(hook)
        elif isinstance(hook, PostPhaseHook):
            self.post_phase_hooks.append(hook)
        else:
            _logger.warning(f"Unknown hook type: {type(hook)}")

    async def dispatch_pre_turn(
        self, prompt: str
    ) -> tuple[HookResult, TurnContext]:
        """Dispatches pre-turn hooks.

        Args:
            prompt: The user prompt.

        Returns:
            Tuple of (HookResult, TurnContext).
        """
        turn_context = TurnContext(self.session_context)

        for hook in self.pre_turn_hooks:
            try:
                result = await hook.run(turn_context, prompt)
                if not result.allow:
                    return result, turn_context
            except Exception as e:
                _logger.error(f"Pre-turn hook failed: {e}")
                return HookResult(allow=False, message=f"Hook error: {e}"), turn_context

        return HookResult(allow=True), turn_context

    async def dispatch_post_turn(
        self, turn_context: TurnContext, response: str
    ) -> None:
        """Dispatches post-turn hooks.

        Args:
            turn_context: The turn context.
            response: The agent response.
        """
        for hook in self.post_turn_hooks:
            try:
                await hook.run(turn_context, response)
            except Exception as e:
                _logger.error(f"Post-turn hook failed: {e}")

    async def dispatch_pre_tool_call(
        self, turn_context: TurnContext, tool_call: ToolCall
    ) -> tuple[HookResult, Any, OperationContext]:
        """Dispatches pre-tool-call decide hooks.

        Args:
            turn_context: The turn context.
            tool_call: The tool call to approve or deny.

        Returns:
            Tuple of (HookResult, data, OperationContext).
        """
        op_context = OperationContext(turn_context)

        for hook in self.pre_tool_call_decide_hooks:
            try:
                result = await hook.run(op_context, tool_call)
                if not result.allow:
                    return result, None, op_context
            except Exception as e:
                _logger.error(f"Pre-tool-call hook failed: {e}")
                # Fail-closed: deny on error
                return HookResult(allow=False, message=f"Hook error: {e}"), None, op_context

        return HookResult(allow=True), None, op_context

    async def dispatch_post_tool_call(
        self, op_context: OperationContext, tool_call: ToolCall, result: Any
    ) -> None:
        """Dispatches post-tool-call hooks.

        Args:
            op_context: The operation context.
            tool_call: The tool call that was executed.
            result: The result of the tool call.
        """
        for hook in self.post_tool_call_hooks:
            try:
                await hook.run(op_context, (tool_call, result))
            except Exception as e:
                _logger.error(f"Post-tool-call hook failed: {e}")

    async def dispatch_on_tool_error(
        self, op_context: OperationContext, tool_call: ToolCall, error: Exception
    ) -> str:
        """Dispatches on-tool-error hooks.

        Args:
            op_context: The operation context.
            tool_call: The tool call that failed.
            error: The exception that occurred.

        Returns:
            Transformed error message.
        """
        error_msg = str(error)

        for hook in self.on_tool_error_hooks:
            try:
                error_msg = await hook.run(op_context, (tool_call, error))
            except Exception as e:
                _logger.error(f"On-tool-error hook failed: {e}")

        return error_msg

    async def dispatch_pre_phase(
        self, turn_context: TurnContext, phase: str
    ) -> HookResult:
        """Dispatches pre-phase hooks.

        Args:
            turn_context: The turn context.
            phase: The phase name (Observe, Recall, Reason, Stabilize, Commit).

        Returns:
            HookResult indicating whether to allow the phase.
        """
        for hook in self.pre_phase_hooks:
            try:
                result = await hook.run(turn_context, phase)
                if not result.allow:
                    return result
            except Exception as e:
                _logger.error(f"Pre-phase hook failed: {e}")
                return HookResult(allow=False, message=f"Hook error: {e}")

        return HookResult(allow=True)

    async def dispatch_post_phase(
        self, turn_context: TurnContext, phase: str
    ) -> None:
        """Dispatches post-phase hooks.

        Args:
            turn_context: The turn context.
            phase: The phase name that completed.
        """
        for hook in self.post_phase_hooks:
            try:
                await hook.run(turn_context, phase)
            except Exception as e:
                _logger.error(f"Post-phase hook failed: {e}")

    async def dispatch_compaction(
        self, turn_context: TurnContext | None, data: dict[str, Any]
    ) -> None:
        """Dispatches compaction event (for observability).

        Args:
            turn_context: The turn context (may be None).
            data: Compaction data.
        """
        # For now, just log it
        _logger.info(f"Context compaction: {data.get('compaction', '')[:100]}")

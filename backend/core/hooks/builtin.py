"""Built-in hooks for Sharrowkin Agent."""

from __future__ import annotations

import logging
from typing import Any

from core.types import HookResult, ToolCall
from core.hooks.base import (
    HookContext,
    PreToolCallDecideHook,
    PostToolCallHook,
    OnToolErrorHook,
    PreTurnHook,
    PostTurnHook,
    PrePhaseHook,
    PostPhaseHook,
)


_logger = logging.getLogger(__name__)


class LoggingPreToolCallHook(PreToolCallDecideHook):
    """Logs all tool calls before execution."""

    async def run(self, context: HookContext, tool_call: ToolCall) -> HookResult:
        _logger.info(f"Tool call: {tool_call.name} with args: {tool_call.args}")
        return HookResult(allow=True)


class LoggingPostToolCallHook(PostToolCallHook):
    """Logs all tool call results."""

    async def run(self, context: HookContext, data: tuple[ToolCall, Any]) -> None:
        tool_call, result = data
        _logger.info(f"Tool result: {tool_call.name} -> {str(result)[:100]}")


class LoggingOnToolErrorHook(OnToolErrorHook):
    """Logs tool errors."""

    async def run(
        self, context: HookContext, data: tuple[ToolCall, Exception]
    ) -> str:
        tool_call, error = data
        _logger.error(f"Tool error: {tool_call.name} failed with {error}")
        return str(error)


class LoggingPreTurnHook(PreTurnHook):
    """Logs turn start."""

    async def run(self, context: HookContext, prompt: str) -> HookResult:
        _logger.info(f"Turn started: {prompt[:100]}")
        return HookResult(allow=True)


class LoggingPostTurnHook(PostTurnHook):
    """Logs turn completion."""

    async def run(self, context: HookContext, response: str) -> None:
        _logger.info(f"Turn completed: {response[:100]}")


class LoggingPrePhaseHook(PrePhaseHook):
    """Logs phase start."""

    async def run(self, context: HookContext, phase: str) -> HookResult:
        _logger.info(f"Phase started: {phase}")
        return HookResult(allow=True)


class LoggingPostPhaseHook(PostPhaseHook):
    """Logs phase completion."""

    async def run(self, context: HookContext, phase: str) -> None:
        _logger.info(f"Phase completed: {phase}")


def create_logging_hooks() -> list:
    """Creates a set of logging hooks for observability.

    Returns:
        List of logging hooks.
    """
    return [
        LoggingPreToolCallHook(),
        LoggingPostToolCallHook(),
        LoggingOnToolErrorHook(),
        LoggingPreTurnHook(),
        LoggingPostTurnHook(),
        LoggingPrePhaseHook(),
        LoggingPostPhaseHook(),
    ]

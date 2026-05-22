"""Policy system for tool call security in Sharrowkin Agent.

Extracted and adapted from Google Antigravity SDK.
"""

from __future__ import annotations

import dataclasses
import enum
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from core.types import HookResult, ToolCall
from core.hooks.base import PreToolCallDecideHook, HookContext


_logger = logging.getLogger(__name__)


# Predicate receives tool call args and returns whether policy applies
Predicate = Callable[..., bool | Awaitable[bool]]


class Decision(enum.Enum):
    """Outcome a policy can produce."""

    APPROVE = "APPROVE"
    DENY = "DENY"


@dataclasses.dataclass(frozen=True)
class Policy:
    """A single tool call policy rule.

    Attributes:
        tool: Tool name this policy targets, or "*" for all tools.
        decision: The outcome when this policy matches.
        when: Optional predicate on the tool call's arguments.
        name: Human-readable label used in logging and deny reasons.
    """

    tool: str
    decision: Decision
    when: Predicate | None = None
    name: str = ""


def allow(
    tool: str,
    *,
    when: Predicate | None = None,
    name: str = "",
) -> Policy:
    """Creates an APPROVE policy for `tool`.

    Args:
        tool: Tool name or "*" for all tools.
        when: Optional argument predicate.
        name: Human-readable label.

    Returns:
        A Policy with decision=APPROVE.
    """
    return Policy(tool=tool, decision=Decision.APPROVE, when=when, name=name)


def deny(
    tool: str,
    *,
    when: Predicate | None = None,
    name: str = "",
) -> Policy:
    """Creates a DENY policy for `tool`.

    Args:
        tool: Tool name or "*" for all tools.
        when: Optional argument predicate.
        name: Human-readable label.

    Returns:
        A Policy with decision=DENY.
    """
    return Policy(tool=tool, decision=Decision.DENY, when=when, name=name)


def allow_all() -> Policy:
    """Creates a policy that allows all tools."""
    return allow("*", name="allow_all")


def deny_all() -> Policy:
    """Creates a policy that denies all tools."""
    return deny("*", name="deny_all")


def confirm_run_command() -> list[Policy]:
    """Default policy: deny run_command, allow everything else."""
    return [
        deny("run_command", name="deny_run_command"),
        allow("*", name="allow_others"),
    ]


class PolicyEnforcer(PreToolCallDecideHook):
    """Hook that enforces a list of policies.

    Policies are evaluated in priority order:
    1. Specific Deny
    2. Specific Allow
    3. Wildcard Deny
    4. Wildcard Allow

    Within each level, first match wins.
    """

    def __init__(self, policies: list[Policy]):
        self.policies = self._sort_policies(policies)

    def _sort_policies(self, policies: list[Policy]) -> list[Policy]:
        """Sorts policies by priority."""
        specific_deny = []
        specific_allow = []
        wildcard_deny = []
        wildcard_allow = []

        for p in policies:
            is_wildcard = p.tool == "*"
            if p.decision == Decision.DENY:
                if is_wildcard:
                    wildcard_deny.append(p)
                else:
                    specific_deny.append(p)
            else:  # APPROVE
                if is_wildcard:
                    wildcard_allow.append(p)
                else:
                    specific_allow.append(p)

        return specific_deny + specific_allow + wildcard_deny + wildcard_allow

    async def run(self, context: HookContext, tool_call: ToolCall) -> HookResult:
        """Evaluates policies against the tool call.

        Args:
            context: The hook context.
            tool_call: The tool call to evaluate.

        Returns:
            HookResult indicating whether to allow or deny.
        """
        tool_name = str(tool_call.name)

        for policy in self.policies:
            # Check if policy matches tool name
            if policy.tool != "*" and policy.tool != tool_name:
                continue

            # Check predicate if present
            if policy.when:
                try:
                    if callable(policy.when):
                        result = policy.when(tool_call.args)
                        if isinstance(result, Awaitable):
                            result = await result
                        if not result:
                            continue
                except Exception as e:
                    # Fail-closed: predicate error means policy matches
                    _logger.error(f"Policy predicate failed: {e}")

            # Policy matches
            if policy.decision == Decision.DENY:
                reason = policy.name or f"Policy denied {tool_name}"
                _logger.info(f"Policy DENY: {reason}")
                return HookResult(allow=False, message=reason)
            else:
                _logger.debug(f"Policy ALLOW: {policy.name or tool_name}")
                return HookResult(allow=True)

        # No policy matched - default deny
        _logger.warning(f"No policy matched for {tool_name}, defaulting to DENY")
        return HookResult(allow=False, message="No matching policy")


def enforce(policies: list[Policy]) -> PolicyEnforcer:
    """Creates a PolicyEnforcer hook from a list of policies.

    Args:
        policies: List of Policy objects.

    Returns:
        A PolicyEnforcer hook.
    """
    return PolicyEnforcer(policies)


# --- Built-in policy helpers ---


def workspace_only(workspace_path: str) -> Predicate:
    """Predicate that checks if file path is within workspace.

    Args:
        workspace_path: The workspace directory path.

    Returns:
        A predicate function.
    """
    from pathlib import Path

    workspace = Path(workspace_path).resolve()

    def predicate(args: dict[str, Any]) -> bool:
        path_arg = args.get("path") or args.get("file_path") or args.get("Path")
        if not path_arg:
            return True  # No path arg, allow

        try:
            target = Path(path_arg).resolve()
            return workspace in target.parents or target == workspace
        except Exception:
            return False  # Invalid path, deny

    return predicate


def deny_dangerous_commands() -> list[Policy]:
    """Policies that deny dangerous shell commands.

    Returns:
        List of policies denying rm, sudo, curl, etc.
    """
    dangerous_tokens = {"rm", "sudo", "su", "chmod", "chown", "mkfs", "dd", "curl", "wget"}

    def has_dangerous_token(args: dict[str, Any]) -> bool:
        cmd = args.get("CommandLine") or args.get("command") or ""
        cmd_lower = cmd.lower()
        return any(token in cmd_lower for token in dangerous_tokens)

    return [
        deny("run_command", when=has_dangerous_token, name="deny_dangerous_commands"),
        allow("*"),
    ]

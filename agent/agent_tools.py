"""Tool definitions for the Sharrowkin ReAct tool-loop.

These are thin wrappers over :mod:`core.tools` that return a *string* result
suitable for an LLM ``tool_result`` block. The loop (``agent/tool_loop.py``)
executes them one at a time and feeds the returned string back to the model on
the next round — so the model always acts on real filesystem state instead of
guessing a whole patch in one shot.

Editing is split into two tools on purpose:

* ``write_file``  — create a new file or fully replace one.
* ``str_replace`` — surgical edit: replace an exact, *unique* snippet. It fails
  loudly if the snippet is missing or ambiguous, which forces the model to read
  the file first and prevents the "lazy rewrite that truncates the file" failure
  mode of the old one-shot patch generator.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.tools import (
    IGNORED_DIRS,
    TEXT_SUFFIXES,
    ProposedFileChange,
    apply_changes,
    detect_and_verify,
    list_files as _list_files,
    parse_python_summary,
    read_file as _read_file,
    run_git,
    run_pytest,
    run_terminal_command,
    safe_relative_path,
)

# Result strings are capped so a single tool call can't blow the context window.
MAX_TOOL_RESULT_CHARS = 16_000


def _clip(text: str, limit: int = MAX_TOOL_RESULT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n... [truncated {len(text) - limit} chars]"


@dataclass(slots=True)
class ToolOutcome:
    """Structured result of a single tool execution.

    ``content`` is the string fed back to the model. ``is_error`` marks
    failures so the loop can flag the ``tool_result`` accordingly. The
    remaining fields let the loop track real progress and emit UI events
    without re-parsing ``content``.
    """
    content: str
    is_error: bool = False
    changed_files: list[str] | None = None
    diff: str = ""
    is_completion: bool = False
    completion_summary: str = ""
    plan: list[dict] | None = None


class AgentToolbox:
    """Workspace-scoped registry of tools the model may call.

    One instance per run. ``execute(name, args)`` dispatches by name and never
    raises — every failure becomes a ``ToolOutcome(is_error=True)`` so a bad
    tool call degrades into feedback the model can recover from rather than
    crashing the loop.
    """

    def __init__(
        self,
        workspace: Path,
        *,
        gemini: Any = None,
        hook_runner: Any = None,
    ):
        self.workspace = workspace
        # Optional GeminiClient — only needed by spawn_subagent. Kept optional so
        # the toolbox stays constructible in tests and offline paths.
        self.gemini = gemini
        # Optional core.hooks.HookRunner — when present, every execute() passes
        # through pre/post/error hook dispatch (policy gating + observability).
        # When None the toolbox behaves exactly as before (fully back-compat).
        self.hook_runner = hook_runner
        self._turn_context = None
        if hook_runner is not None:
            try:
                from core.hooks.base import TurnContext
                self._turn_context = TurnContext(hook_runner.session_context)
            except Exception:
                self._turn_context = None
        # Latest plan recorded via update_plan, surfaced in the run summary.
        self.latest_plan: list[dict] = []
        # When True this is a restricted research sub-agent: mutating tools and
        # nested spawning are refused, and TOOL_SCHEMAS_SUBAGENT is advertised.
        self._subagent = False

    # Tools a restricted research sub-agent may NOT call.
    _SUBAGENT_FORBIDDEN = {"write_file", "str_replace", "run_command", "git", "spawn_subagent"}

    async def execute(self, name: str, args: dict) -> ToolOutcome:
        import asyncio

        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolOutcome(
                content=f"Unknown tool: '{name}'. Available tools: "
                + ", ".join(t["name"] for t in TOOL_SCHEMAS),
                is_error=True,
            )

        if self._subagent and name in self._SUBAGENT_FORBIDDEN:
            return ToolOutcome(
                content=f"Tool '{name}' is not available to a read-only research sub-agent.",
                is_error=True,
            )

        # --- pre-tool-call hook gating (policy) ---
        op_context = None
        if self.hook_runner is not None and self._turn_context is not None:
            try:
                from core.types import ToolCall
                tool_call = ToolCall(name=name, args=args)
                decision, _data, op_context = await self.hook_runner.dispatch_pre_tool_call(
                    self._turn_context, tool_call
                )
                if not decision.allow:
                    return ToolOutcome(
                        content=f"Blocked by policy: {decision.message or name}",
                        is_error=True,
                    )
            except Exception as exc:
                return ToolOutcome(content=f"Hook gating failed for '{name}': {exc}", is_error=True)

        try:
            outcome = await asyncio.to_thread(handler, args)
        except Exception as exc:  # pragma: no cover - defensive
            # Route through on-tool-error hooks for a transformed message.
            if self.hook_runner is not None and op_context is not None:
                try:
                    from core.types import ToolCall
                    msg = await self.hook_runner.dispatch_on_tool_error(
                        op_context, ToolCall(name=name, args=args), exc
                    )
                    return ToolOutcome(content=f"Tool '{name}' raised: {msg}", is_error=True)
                except Exception:
                    pass
            return ToolOutcome(content=f"Tool '{name}' raised: {exc}", is_error=True)

        # --- post-tool-call hook (observability) ---
        if self.hook_runner is not None and op_context is not None:
            try:
                from core.types import ToolCall
                await self.hook_runner.dispatch_post_tool_call(
                    op_context, ToolCall(name=name, args=args), outcome.content
                )
            except Exception:
                pass

        return outcome

    # --- read-only tools ---------------------------------------------------

    def _tool_read_file(self, args: dict) -> ToolOutcome:
        path = args.get("path", "")
        if not path:
            return ToolOutcome(content="read_file requires 'path'.", is_error=True)
        max_lines = int(args.get("max_lines", 500))
        content = _read_file(self.workspace, path, max_lines=max_lines)
        if content.startswith("ERROR:"):
            return ToolOutcome(content=content, is_error=True)
        # Number lines so str_replace targets are easy to reason about.
        numbered = "\n".join(
            f"{i + 1}\t{line}" for i, line in enumerate(content.splitlines())
        )
        return ToolOutcome(content=_clip(f"# {path}\n{numbered}"))

    def _tool_list_files(self, args: dict) -> ToolOutcome:
        subdir = args.get("path", "") or ""
        result = _list_files(self.workspace, subdir)
        if result.startswith("ERROR:"):
            return ToolOutcome(content=result, is_error=True)
        return ToolOutcome(content=_clip(result))

    def _tool_search_files(self, args: dict) -> ToolOutcome:
        pattern = args.get("pattern", "")
        if not pattern:
            return ToolOutcome(content="search_files requires 'pattern'.", is_error=True)
        glob = args.get("glob", "")
        matches = self._grep(pattern, glob)
        if not matches:
            return ToolOutcome(content=f"No matches for '{pattern}'.")
        return ToolOutcome(content=_clip("\n".join(matches)))

    def _grep(self, pattern: str, glob: str, max_results: int = 100) -> list[str]:
        import fnmatch
        import re

        try:
            rx = re.compile(pattern)
        except re.error:
            rx = re.compile(re.escape(pattern))

        results: list[str] = []
        for root, dirs, names in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for name in sorted(names):
                if glob and not fnmatch.fnmatch(name, glob):
                    continue
                fpath = Path(root) / name
                if fpath.suffix not in TEXT_SUFFIXES:
                    continue
                try:
                    if fpath.stat().st_size > 300_000:
                        continue
                    rel = fpath.relative_to(self.workspace).as_posix()
                    for lineno, line in enumerate(
                        fpath.read_text(encoding="utf-8", errors="replace").splitlines(),
                        start=1,
                    ):
                        if rx.search(line):
                            results.append(f"{rel}:{lineno}: {line.strip()[:200]}")
                            if len(results) >= max_results:
                                results.append(f"... [stopped at {max_results} matches]")
                                return results
                except Exception:
                    continue
        return results

    # --- mutating tools ----------------------------------------------------

    def _tool_write_file(self, args: dict) -> ToolOutcome:
        path = args.get("path", "")
        content = args.get("content")
        if not path or content is None:
            return ToolOutcome(
                content="write_file requires 'path' and 'content'.", is_error=True
            )
        try:
            safe_relative_path(self.workspace, path)
        except ValueError as exc:
            return ToolOutcome(content=str(exc), is_error=True)
        result = apply_changes(self.workspace, [ProposedFileChange(path=path, content=content)])
        if not result.changed_files:
            return ToolOutcome(
                content=f"No change: '{path}' already has this exact content.",
                diff=result.diff,
            )
        line_count = len(content.splitlines())
        return ToolOutcome(
            content=f"Wrote '{path}' ({line_count} lines).",
            changed_files=result.changed_files,
            diff=result.diff,
        )

    def _tool_str_replace(self, args: dict) -> ToolOutcome:
        path = args.get("path", "")
        old = args.get("old_string")
        new = args.get("new_string")
        if not path or old is None or new is None:
            return ToolOutcome(
                content="str_replace requires 'path', 'old_string', 'new_string'.",
                is_error=True,
            )
        try:
            target = safe_relative_path(self.workspace, path)
        except ValueError as exc:
            return ToolOutcome(content=str(exc), is_error=True)
        if not target.exists():
            return ToolOutcome(
                content=f"File not found: '{path}'. Use write_file to create it.",
                is_error=True,
            )

        source = target.read_text(encoding="utf-8", errors="replace")
        count = source.count(old)
        if count == 0:
            return ToolOutcome(
                content=(
                    f"old_string not found in '{path}'. Read the file again — the "
                    "snippet must match the current content exactly (whitespace included)."
                ),
                is_error=True,
            )
        if count > 1:
            return ToolOutcome(
                content=(
                    f"old_string is ambiguous in '{path}' ({count} matches). Include "
                    "more surrounding context so it matches exactly one location."
                ),
                is_error=True,
            )
        if old == new:
            return ToolOutcome(
                content="old_string and new_string are identical — nothing to do.",
                is_error=True,
            )

        updated = source.replace(old, new, 1)
        result = apply_changes(self.workspace, [ProposedFileChange(path=path, content=updated)])
        return ToolOutcome(
            content=f"Replaced 1 occurrence in '{path}'.",
            changed_files=result.changed_files,
            diff=result.diff,
        )

    def _tool_run_command(self, args: dict) -> ToolOutcome:
        command = args.get("command", "")
        if not command:
            return ToolOutcome(content="run_command requires 'command'.", is_error=True)
        timeout = int(args.get("timeout", 120))
        res = run_terminal_command(self.workspace, command, timeout_seconds=timeout)
        status = "OK" if res.success else f"FAILED (exit {res.exit_code})"
        body = _clip(res.output or "(no output)", 8000)
        return ToolOutcome(
            content=f"$ {command}\n[{status}]\n{body}",
            is_error=not res.success,
        )

    def _tool_run_tests(self, args: dict) -> ToolOutcome:
        res = run_pytest(self.workspace)
        status = "PASSED" if res.success else f"FAILED (exit {res.exit_code})"
        body = _clip(res.output or "(no output)", 8000)
        return ToolOutcome(
            content=f"[pytest {status}]\n{body}",
            is_error=not res.success,
        )

    def _tool_git(self, args: dict) -> ToolOutcome:
        """Run a whitelisted, local-only git subcommand."""
        sub = args.get("subcommand", "")
        if not sub:
            return ToolOutcome(content="git requires 'subcommand'.", is_error=True)
        extra = args.get("args", []) or []
        if isinstance(extra, str):
            extra = extra.split()
        git_args: list[str] = [sub]
        if sub == "commit":
            message = args.get("message", "")
            if not message:
                return ToolOutcome(content="git commit requires 'message'.", is_error=True)
            git_args += ["-m", message]
            git_args += [str(a) for a in extra]
        elif sub == "checkout":
            branch = args.get("branch", "")
            if branch:
                git_args += ["-b", str(branch)]
            else:
                git_args += [str(a) for a in extra]
        else:
            git_args += [str(a) for a in extra]

        res = run_git(self.workspace, git_args)
        status = "OK" if res.success else f"FAILED (exit {res.exit_code})"
        body = _clip(res.output or "(no output)", 8000)
        return ToolOutcome(
            content=f"$ git {' '.join(git_args)}\n[{status}]\n{body}",
            is_error=not res.success,
        )

    def _tool_find_symbol(self, args: dict) -> ToolOutcome:
        """Find a definition (class/function/method) by name across the workspace."""
        name = args.get("name", "")
        if not name:
            return ToolOutcome(content="find_symbol requires 'name'.", is_error=True)
        try:
            rx = re.compile(name)
        except re.error:
            rx = re.compile(re.escape(name))

        hits: list[str] = []
        for root, dirs, names in os.walk(self.workspace):
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS]
            for fname in sorted(names):
                if not fname.endswith(".py"):
                    continue
                fpath = Path(root) / fname
                try:
                    if fpath.stat().st_size > 300_000:
                        continue
                    rel = fpath.relative_to(self.workspace).as_posix()
                    source = fpath.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                summary = parse_python_summary(rel, source)
                for sym in summary.symbols:
                    if rx.search(sym.name):
                        sig = sym.signature or ""
                        hits.append(f"{rel}:{sym.line}: {sym.kind} {sym.name}{sig}")
                        if len(hits) >= 100:
                            hits.append("... [stopped at 100 matches]")
                            return ToolOutcome(content=_clip("\n".join(hits)))

        if not hits:
            # Fall back to a plain text search so the model still gets a lead.
            grep_hits = self._grep(name, "*.py")
            if grep_hits:
                return ToolOutcome(
                    content="No symbol definitions matched; text matches instead:\n"
                    + _clip("\n".join(grep_hits))
                )
            return ToolOutcome(content=f"No symbol or text match for '{name}'.")
        return ToolOutcome(content=_clip("\n".join(hits)))

    def _tool_verify(self, args: dict) -> ToolOutcome:
        """Auto-detect and run lint/typecheck/build checks."""
        res = detect_and_verify(self.workspace)
        status = "PASSED" if res.success else f"FAILED (exit {res.exit_code})"
        body = _clip(res.output or "(no output)", 8000)
        return ToolOutcome(content=f"[verify {status}]\n{body}", is_error=not res.success)

    def _tool_update_plan(self, args: dict) -> ToolOutcome:
        """Record the current step-by-step plan (Claude-Code-style todo list)."""
        steps = args.get("steps", []) or []
        normalized: list[dict] = []
        for i, s in enumerate(steps):
            if isinstance(s, dict):
                step = str(s.get("step") or s.get("title") or s.get("description") or "")
                stt = str(s.get("status", "pending"))
            else:
                step = str(s)
                stt = "pending"
            if step:
                # "title" is the key the UI renders (matches the TaskPlan
                # contract and the other emitter in core.py). "step" is kept for
                # the summary line and latest_plan consumers below.
                normalized.append({"id": str(i + 1), "title": step, "step": step, "status": stt})
        self.latest_plan = normalized
        done = sum(1 for s in normalized if s["status"] in ("done", "completed"))
        lines = [f"[{'x' if s['status'] in ('done', 'completed') else ' '}] {s['step']}" for s in normalized]
        return ToolOutcome(
            content=f"Plan updated ({done}/{len(normalized)} done):\n" + "\n".join(lines),
            plan=normalized,
        )

    def _tool_spawn_subagent(self, args: dict) -> ToolOutcome:
        """Delegate a focused, read-only research sub-task to a nested ToolLoop."""
        sub_task = args.get("task", "")
        if not sub_task:
            return ToolOutcome(content="spawn_subagent requires 'task'.", is_error=True)
        if self.gemini is None:
            return ToolOutcome(
                content="spawn_subagent unavailable: no LLM client configured.", is_error=True
            )
        focus = args.get("focus", "")
        import asyncio
        from agent.tool_loop import ToolLoop

        # Read-only sub-toolbox: no mutations, no nested spawning, no hooks.
        sub_toolbox = AgentToolbox(self.workspace, gemini=self.gemini)
        sub_toolbox._subagent = True  # marks restricted schema set
        loop = ToolLoop(self.gemini, sub_toolbox, max_steps=8, max_extensions=0)

        full_task = sub_task if not focus else f"{sub_task}\n\nFocus on: {focus}"

        async def _drive() -> None:
            async for _ in loop.run(full_task, "(read-only research sub-agent)"):
                pass

        try:
            loop_obj = asyncio.new_event_loop()
            try:
                loop_obj.run_until_complete(_drive())
            finally:
                loop_obj.close()
        except Exception as exc:
            return ToolOutcome(content=f"Subagent failed: {exc}", is_error=True)

        summary = loop.final_summary or "Subagent produced no summary."
        return ToolOutcome(content=_clip(f"[subagent result]\n{summary}", 8000))

    def _tool_attempt_completion(self, args: dict) -> ToolOutcome:
        summary = args.get("summary", "") or "Task completed."
        return ToolOutcome(
            content="Completion acknowledged.",
            is_completion=True,
            completion_summary=summary,
        )


# --- Tool schemas (provider-agnostic; client normalizes to Anthropic/OpenAI) --

TOOL_SCHEMAS: list[dict] = [
    {
        "name": "read_file",
        "description": (
            "Read a file from the workspace. Returns line-numbered content. "
            "ALWAYS read a file before editing it with str_replace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from workspace root."},
                "max_lines": {"type": "integer", "description": "Max lines to return (default 500)."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and folders in a workspace directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative subdirectory (empty = workspace root)."},
            },
            "required": [],
        },
    },
    {
        "name": "search_files",
        "description": (
            "Search file contents by regex across the workspace. Returns "
            "path:line: match. Use to locate symbols before reading."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Regex (or literal) to search for."},
                "glob": {"type": "string", "description": "Optional filename glob, e.g. '*.py'."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create a new file or completely replace an existing file's content. "
            "Provide the COMPLETE file content. For small edits to a large existing "
            "file, prefer str_replace."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from workspace root."},
                "content": {"type": "string", "description": "Complete new file content."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "str_replace",
        "description": (
            "Replace an exact, unique snippet in an existing file. old_string must "
            "match the current file content exactly (including whitespace) and occur "
            "exactly once. Read the file first to get the exact text."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative path from workspace root."},
                "old_string": {"type": "string", "description": "Exact snippet to replace (must be unique)."},
                "new_string": {"type": "string", "description": "Replacement text."},
            },
            "required": ["path", "old_string", "new_string"],
        },
    },
    {
        "name": "run_command",
        "description": (
            "Run a shell command in the workspace (build, lint, install, scripts). "
            "Destructive commands (rm, git, sudo, ...) are blocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Command line to execute."},
                "timeout": {"type": "integer", "description": "Timeout in seconds (default 120)."},
            },
            "required": ["command"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run the pytest suite in the workspace and return the result.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "find_symbol",
        "description": (
            "Find where a class/function/method is DEFINED by name (AST-based for "
            "Python). Returns path:line kind name signature. Prefer this over "
            "search_files when locating a definition — it skips false text matches."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Symbol name or regex to match against definitions."},
            },
            "required": ["name"],
        },
    },
    {
        "name": "verify",
        "description": (
            "Auto-detect and run the project's lint / typecheck / build checks "
            "(ruff, mypy, tsc, npm lint/build). Use alongside run_tests to validate "
            "changes beyond unit tests."
        ),
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "git",
        "description": (
            "Local-only git. subcommand is one of: status, diff, log, show, add, "
            "commit, branch, checkout, rev-parse, init. For commit pass 'message'. "
            "For a new branch use subcommand='checkout' with 'branch'. "
            "Network ops (push/pull/fetch) and destructive ops (reset/clean/rebase) "
            "are NOT available — a human pushes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "subcommand": {"type": "string", "description": "Allowed git subcommand."},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Extra args (e.g. ['README.md'] for add)."},
                "message": {"type": "string", "description": "Commit message (for subcommand='commit')."},
                "branch": {"type": "string", "description": "New branch name (for subcommand='checkout')."},
            },
            "required": ["subcommand"],
        },
    },
    {
        "name": "update_plan",
        "description": (
            "Record or update your step-by-step plan as a todo checklist. Call it "
            "early with the planned steps, then again to mark steps done as you go. "
            "Keeps the user informed and keeps you on track for multi-step tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "description": "Ordered steps.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "step": {"type": "string", "description": "What this step does."},
                            "status": {"type": "string", "description": "pending | in_progress | done"},
                        },
                        "required": ["step"],
                    },
                },
            },
            "required": ["steps"],
        },
    },
    {
        "name": "spawn_subagent",
        "description": (
            "Delegate a focused READ-ONLY research/exploration question to a nested "
            "sub-agent (e.g. 'where is auth handled and how does it flow?'). Returns "
            "the sub-agent's summary. The sub-agent cannot modify files. Use it to "
            "investigate a large area without filling your own context."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The research question / sub-task."},
                "focus": {"type": "string", "description": "Optional extra focus or constraints."},
            },
            "required": ["task"],
        },
    },
    {
        "name": "attempt_completion",
        "description": (
            "Call this ONLY when the task is fully done and verified. Provide a "
            "summary of what you did. This is the ONLY way to finish the task."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was accomplished, in the user's language."},
            },
            "required": ["summary"],
        },
    },
]

# Restricted read-only schema set advertised to research sub-agents (no
# mutation, no nested spawning). Mirrors AgentToolbox._SUBAGENT_FORBIDDEN.
_SUBAGENT_TOOL_NAMES = {"read_file", "list_files", "search_files", "find_symbol", "attempt_completion"}
TOOL_SCHEMAS_SUBAGENT: list[dict] = [t for t in TOOL_SCHEMAS if t["name"] in _SUBAGENT_TOOL_NAMES]

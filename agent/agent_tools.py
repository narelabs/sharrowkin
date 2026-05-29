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
from dataclasses import dataclass
from pathlib import Path

from core.tools import (
    IGNORED_DIRS,
    TEXT_SUFFIXES,
    ProposedFileChange,
    apply_changes,
    list_files as _list_files,
    read_file as _read_file,
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


class AgentToolbox:
    """Workspace-scoped registry of tools the model may call.

    One instance per run. ``execute(name, args)`` dispatches by name and never
    raises — every failure becomes a ``ToolOutcome(is_error=True)`` so a bad
    tool call degrades into feedback the model can recover from rather than
    crashing the loop.
    """

    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def execute(self, name: str, args: dict) -> ToolOutcome:
        import asyncio

        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            return ToolOutcome(
                content=f"Unknown tool: '{name}'. Available tools: "
                + ", ".join(t["name"] for t in TOOL_SCHEMAS),
                is_error=True,
            )
        try:
            return await asyncio.to_thread(handler, args)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolOutcome(content=f"Tool '{name}' raised: {exc}", is_error=True)

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

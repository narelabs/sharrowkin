"""ReAct tool-calling loop for the Sharrowkin agent.

This is the replacement for the old one-shot ``_reason`` → ``_stabilize`` block.
Instead of asking the model to emit one giant JSON patch (which it routinely
faked — claiming "done" while changing nothing), the loop runs the model
step-by-step:

    model picks ONE tool  →  we execute it for real  →  real result goes back
    →  model picks the next tool  →  ... until ``attempt_completion``.

Each tool call is its own request to the LLM, so the model always reacts to the
actual filesystem/test state. It cannot finish blind — completion only happens
after real tool results, and is rejected if a coding task changed zero files.

The loop is an async generator yielding the same event dicts the WebSocket
router/UI already understand (``phase_change``, ``tool_call``, ``log``,
``thinking``, ``diff``, ``content``). Final state (success, changed files,
summary, diff) is exposed as attributes after iteration completes.
"""

from __future__ import annotations

import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from core.llm.client import ChatTurn, GeminiClient
from agent.agent_tools import AgentToolbox, ToolOutcome, TOOL_SCHEMAS

# Tools that perform a real mutation — used to detect "claimed done but did
# nothing" on coding tasks.
_MUTATING_TOOLS = {"write_file", "str_replace", "run_command"}

TOOL_LOOP_SYSTEM_PROMPT = """You are Sharrowkin, an autonomous coding agent. You complete tasks by calling tools ONE AT A TIME and reacting to their real results.

# How you work
- Think briefly, then call exactly ONE tool per turn. Never describe a tool call in prose instead of making it.
- Inspect before you change: use list_files / search_files / read_file to understand the code BEFORE editing.
- Edit precisely: use str_replace for small edits to existing files (read the file first to get the exact snippet). Use write_file to create files or fully rewrite small ones.
- After changing code, verify it: run_tests or a relevant run_command. If something fails, read the error and fix the real cause — do not repeat the same failing change.
- When (and only when) the task is fully done and verified, call attempt_completion with a summary. attempt_completion is the ONLY way to finish.

# Rules
- Never claim something is done without having actually done it via a tool. The user sees the real file changes.
- One tool per turn. Wait for the result before the next step.
- Make safe assumptions and keep going; do not ask the user questions in headless mode.
- Preserve existing code and style. Provide COMPLETE content to write_file (no "...", no elisions).
- Answer summaries in the same language the user used."""


class ToolLoop:
    """Drives a single task to completion via iterative tool calls."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        toolbox: AgentToolbox,
        *,
        max_steps: int = 25,
        message_budget_chars: int = 180_000,
    ):
        self.gemini = gemini_client
        self.toolbox = toolbox
        self.max_steps = max_steps
        self.message_budget_chars = message_budget_chars

        # Populated as the loop runs; read by the agent after iteration.
        self.success: bool = False
        self.changed_files: list[str] = []
        self.final_summary: str = ""
        self.final_diff: str = ""
        self.steps_taken: int = 0
        self.tools_used: list[str] = []
        self.actions: list[str] = []
        self.messages: list[dict] = []

    # --- event helpers (shapes match agent/core.py legacy emitters) --------

    @staticmethod
    def _phase(name: str, status: str) -> dict:
        return {"type": "phase_change", "phase": name.lower(), "status": status}

    @staticmethod
    def _log(level: str, message: str) -> dict:
        return {"type": "log", "level": level, "message": message}

    @staticmethod
    def _thinking(text: str) -> dict:
        return {"type": "thinking", "content": text}

    # Result text shown in the UI's expandable "Response" block. Larger than the
    # one-line `detail`, but still capped so a single event can't bloat the
    # WebSocket payload or the browser DOM.
    UI_RESULT_CHARS = 4_000

    @staticmethod
    def _tool_call(
        tool: str,
        *,
        status: str = "done",
        target: str = "",
        detail: str = "",
        lines_changed: int = 0,
        duration_ms: int = 0,
        args: dict | None = None,
        result: str = "",
    ) -> dict:
        return {
            "type": "tool_call",
            "tool": tool,
            "status": status,
            "target": target,
            "detail": detail,
            "lines_changed": lines_changed,
            "duration_ms": duration_ms,
            # Full structured input and (capped) output so the UI can render
            # Arguments / Response blocks like a proper tool-call card.
            "args": args or {},
            "result": result[:ToolLoop.UI_RESULT_CHARS] if result else "",
        }

    # --- main loop ---------------------------------------------------------

    async def run(
        self,
        task: str,
        initial_context: str,
        *,
        ui_delays_enabled: bool = False,
    ) -> AsyncIterator[dict[str, Any]]:
        """Run the task. Yields UI events; sets result attrs when done."""
        first_user = (
            f"# Task\n{task}\n\n"
            f"# Workspace context\n{initial_context}\n\n"
            "Begin by inspecting whatever you need, then make the changes and verify them. "
            "Call attempt_completion only when the task is genuinely finished."
        )
        self.messages = [{"role": "user", "content": first_user}]

        changed: set[str] = set()
        consecutive_no_tool = 0

        yield self._phase("Reason", "active")

        for step in range(1, self.max_steps + 1):
            self.steps_taken = step
            yield self._log("info", f"Step {step} — analyzing and deciding the next action")

            try:
                turn: ChatTurn = await self.gemini.chat_with_tools(
                    messages=self.messages,
                    tools=TOOL_SCHEMAS,
                    system=TOOL_LOOP_SYSTEM_PROMPT,
                )
            except Exception as exc:
                yield self._log("error", f"Could not reach the language model: {exc}")
                self.success = False
                self.final_summary = f"The language model was unavailable: {exc}"
                yield self._phase("Reason", "error")
                return

            # Record the assistant turn verbatim to keep the tool protocol valid.
            self._append_assistant(turn)

            if turn.text:
                yield self._thinking(turn.text)

            # --- no tool call: nudge, then give up if it persists ---
            if not turn.tool_calls:
                consecutive_no_tool += 1
                if consecutive_no_tool >= 2:
                    # Model is just talking. Treat its text as the answer.
                    self.final_summary = turn.text or "No actionable output."
                    self.success = bool(changed) or not _looks_like_coding(task)
                    yield self._log("info", "Finished — no further actions needed")
                    break
                self._append_user_text(
                    "You did not call a tool. Either call a tool to make progress, "
                    "or call attempt_completion if the task is genuinely done."
                )
                continue
            consecutive_no_tool = 0

            # --- execute tool calls (usually one) ---
            tool_results = []
            completion: ToolOutcome | None = None
            for call in turn.tool_calls:
                self.tools_used.append(call.name)
                target = call.args.get("path") or call.args.get("command") or call.args.get("pattern") or ""
                yield self._tool_call(call.name, status="running", target=str(target)[:200], args=call.args)

                t0 = time.monotonic()
                outcome = await self.toolbox.execute(call.name, call.args)
                dur_ms = int((time.monotonic() - t0) * 1000)

                if outcome.is_completion:
                    completion = outcome
                    tool_results.append((call, ToolOutcome(content="Completion acknowledged.")))
                    yield self._tool_call(call.name, status="done", target="", detail="Task finished", duration_ms=dur_ms)
                    continue

                status = "error" if outcome.is_error else "done"
                detail = outcome.content.splitlines()[0][:160] if outcome.content else ""
                lines_changed = 0
                if outcome.changed_files:
                    changed.update(outcome.changed_files)
                    lines_changed = len(call.args.get("content", "").splitlines())
                    self.actions.append(f"{call.name}: {', '.join(outcome.changed_files)}")
                    if outcome.diff:
                        yield {"type": "diff", "diff": outcome.diff, "files": outcome.changed_files}
                else:
                    self.actions.append(f"{call.name}: {str(target)[:80]}")

                yield self._tool_call(
                    call.name, status=status, target=str(target)[:200],
                    detail=detail, lines_changed=lines_changed, duration_ms=dur_ms,
                    args=call.args, result=outcome.content,
                )
                if outcome.is_error:
                    yield self._log("warning", f"{_friendly_tool(call.name)} reported an issue: {detail}")
                tool_results.append((call, outcome))

            # Feed real results back for the next round.
            self._append_tool_results(turn, tool_results)

            # --- handle completion ---
            if completion is not None:
                if _looks_like_coding(task) and not changed:
                    # Model tried to finish without doing anything. Reject once.
                    self._append_user_text(
                        "You called attempt_completion but no files were changed and no "
                        "commands were run. Do the actual work first (edit files, run "
                        "tests), then call attempt_completion."
                    )
                    yield self._log("warning", "The task isn't done yet — continuing to work on it")
                    continue
                self.success = True
                self.final_summary = completion.completion_summary
                yield self._log("success", "Task completed successfully")
                break

            self._trim_messages()
        else:
            # max_steps exhausted without attempt_completion
            self.success = bool(changed)
            if not self.final_summary:
                self.final_summary = (
                    f"Reached the step limit ({self.max_steps}) without explicit completion. "
                    f"Changed {len(changed)} file(s)."
                )
            yield self._log("warning", f"Reached the step limit ({self.max_steps} steps) — wrapping up")

        self.changed_files = sorted(changed)
        # Dedup tools_used preserving order
        self.tools_used = list(dict.fromkeys(self.tools_used))
        yield self._phase("Reason", "done")

    # --- message protocol helpers -----------------------------------------

    def _append_assistant(self, turn: ChatTurn) -> None:
        if turn.api_format == "anthropic":
            content = turn.raw_assistant_content
            if not content:
                content = [{"type": "text", "text": turn.text or ""}]
            self.messages.append({"role": "assistant", "content": content})
        else:  # openai
            msg = turn.raw_assistant_content
            if isinstance(msg, dict) and msg.get("role"):
                self.messages.append(msg)
            else:
                self.messages.append({"role": "assistant", "content": turn.text or ""})

    def _append_tool_results(self, turn: ChatTurn, results: list[tuple]) -> None:
        if turn.api_format == "anthropic":
            blocks = []
            for call, outcome in results:
                block = {
                    "type": "tool_result",
                    "tool_use_id": call.id,
                    "content": outcome.content,
                }
                if outcome.is_error:
                    block["is_error"] = True
                blocks.append(block)
            self.messages.append({"role": "user", "content": blocks})
        else:  # openai: one tool message per call
            for call, outcome in results:
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": outcome.content,
                })

    def _append_user_text(self, text: str) -> None:
        self.messages.append({"role": "user", "content": text})

    def _trim_messages(self) -> None:
        """Drop oldest rounds (keeping the task message) if over budget.

        Trims in whole rounds from the front so we never strip a tool_result
        away from its assistant tool_use (which would break the protocol).
        """
        total = sum(len(str(m.get("content", ""))) for m in self.messages)
        if total <= self.message_budget_chars or len(self.messages) <= 5:
            return
        head = self.messages[:1]  # original task
        tail = self.messages[1:]
        # Drop from the front of tail until under budget, but only at a
        # boundary that starts with an assistant message (start of a round).
        while tail and sum(len(str(m.get("content", ""))) for m in head + tail) > self.message_budget_chars:
            # remove the first round: an assistant msg + following tool/user msgs
            tail.pop(0)
            while tail and tail[0].get("role") in ("tool", "user") and not _is_plain_user(tail[0]):
                tail.pop(0)
        self.messages = head + tail


def _looks_like_coding(task: str) -> bool:
    t = task.lower()
    keywords = (
        "созда", "напиш", "исправ", "добав", "удали", "измени", "сделай",
        "рефактор", "запус", "установ", "обнов", "почини", "fix", "create",
        "add", "write", "implement", "refactor", "build", "delete", "remove",
        "change", "update", "run", "install", "debug",
    )
    return any(k in t for k in keywords)


def _is_plain_user(msg: dict) -> bool:
    """True for a normal user text message (not an Anthropic tool_result block)."""
    if msg.get("role") != "user":
        return False
    content = msg.get("content")
    return isinstance(content, str)


_FRIENDLY_TOOL_NAMES = {
    "read_file": "Reading a file",
    "list_files": "Listing files",
    "search_files": "Searching the code",
    "write_file": "Writing a file",
    "str_replace": "Editing a file",
    "run_command": "Running a command",
    "run_tests": "Running the tests",
    "attempt_completion": "Finishing up",
}


def _friendly_tool(name: str) -> str:
    """Human-readable label for a tool, for user-facing log lines."""
    return _FRIENDLY_TOOL_NAMES.get(name, name.replace("_", " ").capitalize())


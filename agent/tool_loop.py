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
from agent.agent_tools import AgentToolbox, ToolOutcome, TOOL_SCHEMAS, TOOL_SCHEMAS_SUBAGENT

# Tools that perform a real mutation — used to detect "claimed done but did
# nothing" on coding tasks. `git` counts only for commit (handled below), but
# listing it here means a commit-only task is correctly seen as real work.
_MUTATING_TOOLS = {"write_file", "str_replace", "run_command", "git"}

TOOL_LOOP_SYSTEM_PROMPT = """You are Sharrowkin, an autonomous coding agent. You complete tasks by calling tools ONE AT A TIME and reacting to their real results.

# How you work
- Think briefly, then call exactly ONE tool per turn. Never describe a tool call in prose instead of making it.
- For any multi-step task, call update_plan FIRST with your planned steps, then update it (mark steps done) as you progress. Skip this only for trivial one-step tasks.
- Inspect before you change: use list_files / search_files / read_file to understand the code BEFORE editing. To locate where a class/function is DEFINED, prefer find_symbol over search_files.
- For a large investigation you don't need to do yourself, use spawn_subagent to delegate a focused read-only research question and get back a summary.
- Edit precisely: use str_replace for small edits to existing files (read the file first to get the exact snippet). Use write_file to create files or fully rewrite small ones.
- After changing code, verify it: run_tests for unit tests, and verify for lint/typecheck/build. If something fails, read the error and fix the real cause — do not repeat the same failing change.
- Version control is available via the git tool (local only): stage with add, then commit with a message. Create a branch with subcommand=checkout + branch. push/pull are NOT available — a human handles publishing.
- When (and only when) the task is fully done and verified, call attempt_completion with a summary. attempt_completion is the ONLY way to finish.

# Scope discipline — do ONLY what was asked
- Do exactly what the task asks, nothing more. Make the SMALLEST change that fully satisfies it.
- Do NOT rewrite, replace, or "improve" existing working files unless the task explicitly asks for it. A small fix does not justify rebuilding a module.
- Never delete or overwrite a working file to replace it with your own version unless explicitly requested. Prefer str_replace on the existing file over write_file that clobbers it.
- Do not add new features, files, abstractions, dependencies, or "upgrades" that were not requested.
- If the task is genuinely ambiguous about scope, make the conservative minimal choice and state your assumption in the completion summary — do not expand scope to be safe.

# Workspace
- All tools (read_file, write_file, run_command, …) already run from the workspace root: {workspace}
- Use paths RELATIVE to that root. Never `cd` into another directory, and never prepend `cd <path> &&` to a command — commands already execute at the root. Doing so points you at the wrong folder.

# Showing visual results (Preview)
- The Agent Computer has a live Preview browser. When you start a web/dev server, the user sees the running site there automatically.
- The server URL printed to the terminal (http://localhost:PORT or http://127.0.0.1:PORT) is auto-detected and opened in the Preview tab. So to SHOW a web result, START A SERVER and let its URL print — do NOT just open a raw .html file or print a file path.
- For static HTML/CSS/JS, serve the folder: `python -m http.server PORT` (pick a stable port like 5500). For a framework, use its dev server (`npm run dev`, vite, next dev). Keep the server running; do not kill it before completing.
- After the server is up and its URL has printed, the preview is visible — proceed to verify/finish rather than re-launching it.

# Rules
- Never claim something is done without having actually done it via a tool. The user sees the real file changes.
- One tool per turn. Wait for the result before the next step.
- Make safe assumptions and keep going; do not ask the user questions in headless mode.
- Preserve existing code and style. Provide COMPLETE content to write_file (no "...", no elisions).
- Answer summaries in the same language the user used."""


def build_system_prompt(workspace: str | Path) -> str:
    """Fill the workspace root into the system prompt so the model knows where
    its tools operate and never tries to cd elsewhere."""
    return TOOL_LOOP_SYSTEM_PROMPT.replace("{workspace}", str(workspace))


class ToolLoop:
    """Drives a single task to completion via iterative tool calls."""

    def __init__(
        self,
        gemini_client: GeminiClient,
        toolbox: AgentToolbox,
        *,
        max_steps: int = 25,
        max_extensions: int = 4,
        message_budget_chars: int = 180_000,
    ):
        self.gemini = gemini_client
        self.toolbox = toolbox
        self.max_steps = max_steps
        # When the step budget runs out without an explicit completion, the loop
        # auto-grants another batch of `max_steps` instead of quitting — up to
        # this many times. Hard ceiling = max_steps * (1 + max_extensions).
        self.max_extensions = max_extensions
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

    # System instruction for the dedicated reasoning request. This is OUR own
    # prompt-driven "thinking" — a separate generate_text call through our
    # system — NOT the model's native reasoning/extended-thinking mode.
    THINKING_SYSTEM = (
        "You are the inner reasoning voice of Sharrowkin, an autonomous coding agent. "
        "Given a task and workspace context, think out loud in first person about how you "
        "will approach it: what you need to inspect, the likely steps, and risks to watch. "
        "Be concrete and reference the actual task. 3-6 short sentences, no headings, no lists, "
        "no code. Do not solve the task yet — only plan your approach. "
        "Reply in the same language the task is written in."
    )
    THINKING_MAX_CHARS = 1_200

    async def _generate_thinking(self, task: str, context: str) -> str:
        """Produce reasoning text via a dedicated request in our system.

        Returns "" on any failure (non-fatal — the loop proceeds either way).
        This deliberately uses generate_text (a plain prompt->text call routed
        through our omniroute) instead of the model's native thinking mode.
        """
        if not getattr(self.gemini, "configured", False):
            return ""
        prompt = (
            f"# Task\n{task}\n\n"
            f"# Workspace context\n{context[:4000]}\n\n"
            "Think through your approach before acting."
        )
        try:
            text = await self.gemini.generate_text(prompt, system_instruction=self.THINKING_SYSTEM)
        except Exception:
            return ""
        return (text or "").strip()[:self.THINKING_MAX_CHARS]

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

        # System prompt carries the workspace root so the model uses relative
        # paths and never cd's into the wrong directory.
        system_prompt = build_system_prompt(self.toolbox.workspace)

        changed: set[str] = set()
        did_real_work = False  # mutation OR successful git commit
        consecutive_no_tool = 0
        finished = False  # set when the model genuinely completes or stops

        # Research sub-agents get a restricted, read-only tool set.
        active_tools = TOOL_SCHEMAS_SUBAGENT if getattr(self.toolbox, "_subagent", False) else TOOL_SCHEMAS

        yield self._phase("Reason", "active")

        # Dedicated, prompt-driven "thinking": a separate request in our system
        # that plans the approach before any tool runs. This replaces relying on
        # the model's incidental preamble (turn.text) as the only reasoning.
        thinking = await self._generate_thinking(task, initial_context)
        if thinking:
            yield self._thinking(thinking)

        # Outer loop grants additional step-batches when the budget runs out
        # without an explicit completion, so the agent keeps working instead of
        # stopping at the limit. Bounded by max_extensions as a safety ceiling.
        step = 0
        extensions_used = 0
        while True:
            batch_end = self.max_steps * (extensions_used + 1)
            while step < batch_end:
                step += 1
                self.steps_taken = step
                yield self._log("info", f"Step {step} — analyzing and deciding the next action")

                try:
                    turn: ChatTurn = await self.gemini.chat_with_tools(
                        messages=self.messages,
                        tools=active_tools,
                        system=system_prompt,
                    )
                except Exception as exc:
                    yield self._log("error", f"Could not reach the language model: {exc}")
                    self.success = False
                    self.final_summary = f"The language model was unavailable: {exc}"
                    yield self._phase("Reason", "error")
                    return

                # Record the assistant turn verbatim to keep the tool protocol valid.
                self._append_assistant(turn)

                # NOTE: we no longer surface turn.text as "thinking" — reasoning
                # comes from the dedicated _generate_thinking request (our system),
                # not the model's incidental tool-call preamble. turn.text is still
                # used below as the final answer when the model stops calling tools.

                # --- no tool call: nudge, then give up if it persists ---
                if not turn.tool_calls:
                    consecutive_no_tool += 1
                    if consecutive_no_tool >= 2:
                        # Model is just talking. Treat its text as the answer.
                        self.final_summary = turn.text or "No actionable output."
                        self.success = bool(changed) or not _looks_like_coding(task)
                        yield self._log("info", "Finished — no further actions needed")
                        finished = True
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
                        did_real_work = True
                        lines_changed = len(call.args.get("content", "").splitlines())
                        self.actions.append(f"{call.name}: {', '.join(outcome.changed_files)}")
                        if outcome.diff:
                            yield {"type": "diff", "diff": outcome.diff, "files": outcome.changed_files}
                    else:
                        self.actions.append(f"{call.name}: {str(target)[:80]}")

                    # A successful git commit counts as real work even though it
                    # reports no changed_files (the files were staged earlier).
                    if call.name == "git" and not outcome.is_error and call.args.get("subcommand") == "commit":
                        did_real_work = True

                    # Surface an updated plan to the UI (reuses the task_plan event).
                    if call.name == "update_plan" and outcome.plan is not None:
                        yield {"type": "task_plan", "plan": outcome.plan}

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
                    if _looks_like_coding(task) and not did_real_work:
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
                    finished = True
                    break

                self._trim_messages()

            if finished:
                break

            # Step budget for this batch exhausted without completion.
            if extensions_used < self.max_extensions:
                extensions_used += 1
                yield self._log(
                    "info",
                    f"Hit the {batch_end}-step checkpoint — extending and continuing "
                    f"({extensions_used}/{self.max_extensions})",
                )
                # Nudge the model to push toward completion in the next batch.
                self._append_user_text(
                    f"You've taken {step} steps without calling attempt_completion. "
                    "Keep going: focus on what's left, finish the remaining work, and "
                    "call attempt_completion as soon as the task is genuinely done. "
                    "If you're stuck, change approach rather than repeating the same action."
                )
                self._trim_messages()
                continue

            # All extensions used — wrap up.
            self.success = did_real_work or not _looks_like_coding(task)
            if not self.final_summary:
                self.final_summary = (
                    f"Reached the extended step limit ({batch_end}) without explicit "
                    f"completion. Changed {len(changed)} file(s)."
                )
            yield self._log("warning", f"Reached the step limit ({batch_end} steps) — wrapping up")
            break

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
    "find_symbol": "Finding a symbol",
    "write_file": "Writing a file",
    "str_replace": "Editing a file",
    "run_command": "Running a command",
    "run_tests": "Running the tests",
    "verify": "Verifying (lint/type/build)",
    "git": "Running git",
    "update_plan": "Updating the plan",
    "spawn_subagent": "Delegating to a sub-agent",
    "attempt_completion": "Finishing up",
}


def _friendly_tool(name: str) -> str:
    """Human-readable label for a tool, for user-facing log lines."""
    return _FRIENDLY_TOOL_NAMES.get(name, name.replace("_", " ").capitalize())


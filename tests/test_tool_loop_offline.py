"""Offline test of the ReAct ToolLoop with a scripted (mock) LLM.

Verifies the core promise: the loop executes tools for real (files actually
appear on disk), feeds results back, and only finishes via attempt_completion —
and rejects a completion that changed nothing on a coding task.

Run: python tests/test_tool_loop_offline.py
"""

import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.llm.client import ChatTurn, ToolCallRequest, GeminiClient
from agent.agent_tools import AgentToolbox
from agent.tool_loop import ToolLoop


class ScriptedClient:
    """Returns a pre-baked sequence of ChatTurns, ignoring the prompt."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0
        self.last_system = None  # captures the system prompt of the latest call

    async def chat_with_tools(self, messages, tools, system, **kwargs):
        self.last_system = system
        turn = self._turns[min(self.calls, len(self._turns) - 1)]
        self.calls += 1
        return turn


def _assistant_blocks(text, calls):
    blocks = []
    if text:
        blocks.append({"type": "text", "text": text})
    for c in calls:
        blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.args})
    return blocks


def _turn(text, calls):
    return ChatTurn(
        text=text,
        tool_calls=calls,
        raw_assistant_content=_assistant_blocks(text, calls),
        stop_reason="tool_use" if calls else "end_turn",
        api_format="anthropic",
    )


async def test_happy_path():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        script = [
            _turn("I'll create the file.", [
                ToolCallRequest(id="c1", name="write_file",
                                args={"path": "hello.py", "content": "def hello():\n    return 'hi'\n"})
            ]),
            _turn("Now verify it exists.", [
                ToolCallRequest(id="c2", name="read_file", args={"path": "hello.py"})
            ]),
            _turn("Done.", [
                ToolCallRequest(id="c3", name="attempt_completion",
                                args={"summary": "Created hello.py with a hello() function."})
            ]),
        ]
        client = ScriptedClient(script)
        loop = ToolLoop(client, AgentToolbox(ws), max_steps=10)
        events = [e async for e in loop.run("создай файл hello.py с функцией hello", "(empty)")]

        assert (ws / "hello.py").exists(), "file was NOT created on disk"
        assert loop.success, "loop should report success"
        assert "hello.py" in loop.changed_files, f"changed_files wrong: {loop.changed_files}"
        assert "hello" in loop.final_summary.lower()
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert any(e["tool"] == "write_file" for e in tool_events)
        # The workspace root must be injected into the system prompt, and the
        # scope-discipline section must be present.
        assert str(ws) in client.last_system, "workspace path not injected into system prompt"
        assert "Scope discipline" in client.last_system, "scope-discipline section missing from prompt"
        print(f"  happy_path: OK — file created, {len(events)} events, {loop.steps_taken} steps")


async def test_rejects_empty_completion():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        # Tries to finish immediately without doing anything → must be rejected,
        # then actually does the work on the retry.
        script = [
            _turn("All done!", [
                ToolCallRequest(id="c1", name="attempt_completion",
                                args={"summary": "Done (but did nothing)."})
            ]),
            _turn("Okay, doing the work now.", [
                ToolCallRequest(id="c2", name="write_file",
                                args={"path": "real.py", "content": "x = 1\n"})
            ]),
            _turn("Now done.", [
                ToolCallRequest(id="c3", name="attempt_completion",
                                args={"summary": "Created real.py."})
            ]),
        ]
        client = ScriptedClient(script)
        loop = ToolLoop(client, AgentToolbox(ws), max_steps=10)
        events = [e async for e in loop.run("создай файл real.py", "(empty)")]

        assert (ws / "real.py").exists(), "real work was never done"
        assert loop.success
        warnings = [e for e in events if e.get("type") == "log" and e.get("level") == "warning"]
        assert any("task isn't done yet" in e["message"].lower() for e in warnings), \
            "empty completion was not rejected"
        print(f"  rejects_empty_completion: OK — empty completion rejected then real work done")


async def test_str_replace_requires_match():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "f.py").write_text("a = 1\nb = 2\n", encoding="utf-8")
        tb = AgentToolbox(ws)
        miss = await tb.execute("str_replace", {"path": "f.py", "old_string": "zzz", "new_string": "q"})
        assert miss.is_error and "not found" in miss.content.lower()
        ok = await tb.execute("str_replace", {"path": "f.py", "old_string": "a = 1", "new_string": "a = 99"})
        assert not ok.is_error and ok.changed_files == ["f.py"]
        assert (ws / "f.py").read_text(encoding="utf-8") == "a = 99\nb = 2\n"
        print("  str_replace_requires_match: OK — miss rejected, unique match applied")


async def test_auto_extends_past_step_limit():
    """The loop must keep working past max_steps (auto-extend) instead of
    stopping, and finish when attempt_completion finally arrives."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        tb = AgentToolbox(ws)

        # A long run of read_file calls (never completing) that exceeds the
        # first step batch, then a real edit + completion.
        keep_busy = [
            _turn("checking", [
                ToolCallRequest(id=f"r{i}", name="read_file", args={"path": "nope.txt"})
            ])
            for i in range(7)
        ]
        finish = [
            _turn("now editing", [
                ToolCallRequest(id="w", name="write_file",
                                args={"path": "out.txt", "content": "done\n"})
            ]),
            _turn("", [
                ToolCallRequest(id="done", name="attempt_completion",
                                args={"completion_summary": "Finished after extension."})
            ]),
        ]
        client = ScriptedClient(keep_busy + finish)
        # Tiny batch so we cross the limit quickly; allow extensions.
        loop = ToolLoop(client, tb, max_steps=3, max_extensions=4)

        extended = False
        async for ev in loop.run(task="explain the project", initial_context=""):
            if ev.get("type") == "log" and "extending and continuing" in ev.get("message", ""):
                extended = True

        assert extended, "loop should have logged an extension past the step limit"
        assert loop.success, "loop should succeed once completion arrives"
        assert loop.steps_taken > 3, f"expected to run past first batch, got {loop.steps_taken}"
        assert (ws / "out.txt").exists(), "the post-extension edit should have happened"
        print(f"  auto_extends_past_step_limit: OK — ran {loop.steps_taken} steps, extended, then completed")


async def test_intent_triage():
    """Retrospective/meta questions must route to conversational (answered from
    history), never to the informational repo-scan cycle. Real coding and
    analysis requests must keep their classification."""
    client = GeminiClient(api_key=None)  # unconfigured: heuristics short-circuit

    retrospective = [
        "а что ты сделал",
        "что ты сделал?",
        "what did you do",
        "what changed?",
        "что было сделано",
    ]
    for q in retrospective:
        intent = await client.classify_intent(q)
        assert intent["is_conversational"] is True, f"{q!r} should be conversational, got {intent}"
        assert intent["is_informational"] is False, f"{q!r} must NOT trigger info scan, got {intent}"

    # A genuine analysis request stays informational.
    info = await client.classify_intent("изучи проект и объясни архитектуру")
    assert info["is_informational"] is True and not info["is_conversational"], f"info misrouted: {info}"

    # A genuine coding request is neither conversational nor informational.
    coding = await client.classify_intent("создай файл hello.py с функцией hello")
    assert not coding["is_conversational"] and not coding["is_informational"], f"coding misrouted: {coding}"

    await client.close()
    print("  intent_triage: OK — retrospective->chat, analysis->info, coding->task")


async def main():
    print("Running ToolLoop offline tests...")
    await test_happy_path()
    await test_rejects_empty_completion()
    await test_str_replace_requires_match()
    await test_auto_extends_past_step_limit()
    await test_intent_triage()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

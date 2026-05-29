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

from core.llm.client import ChatTurn, ToolCallRequest
from agent.agent_tools import AgentToolbox
from agent.tool_loop import ToolLoop


class ScriptedClient:
    """Returns a pre-baked sequence of ChatTurns, ignoring the prompt."""

    def __init__(self, turns):
        self._turns = list(turns)
        self.calls = 0

    async def chat_with_tools(self, messages, tools, system, **kwargs):
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
        loop = ToolLoop(ScriptedClient(script), AgentToolbox(ws), max_steps=10)
        events = [e async for e in loop.run("создай файл hello.py с функцией hello", "(empty)")]

        assert (ws / "hello.py").exists(), "file was NOT created on disk"
        assert loop.success, "loop should report success"
        assert "hello.py" in loop.changed_files, f"changed_files wrong: {loop.changed_files}"
        assert "hello" in loop.final_summary.lower()
        tool_events = [e for e in events if e.get("type") == "tool_call"]
        assert any(e["tool"] == "write_file" for e in tool_events)
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


async def main():
    print("Running ToolLoop offline tests...")
    await test_happy_path()
    await test_rejects_empty_completion()
    await test_str_replace_requires_match()
    print("ALL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

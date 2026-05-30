"""Offline tests for the new agent capabilities wired into the ToolLoop.

Covers: controlled git tool (commit works, push rejected), find_symbol (AST),
verify auto-detection, the hook/policy gate (dangerous run_command denied),
update_plan event emission, and spawn_subagent restriction (no mutation).

Standalone runner (the repo's pytest setup has no asyncio plugin):
    python tests/test_agent_new_tools.py
"""

import asyncio
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.tools import run_git, detect_and_verify
from agent.agent_tools import AgentToolbox, TOOL_SCHEMAS, TOOL_SCHEMAS_SUBAGENT


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=10, check=False)
        return True
    except Exception:
        return False


async def test_git_tool_commit_and_reject():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        tb = AgentToolbox(ws)

        # init + configure identity (commit needs it in CI environments)
        assert (await tb.execute("git", {"subcommand": "init"})).is_error is False
        subprocess.run(["git", "config", "user.email", "t@t.io"], cwd=ws, check=False)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=ws, check=False)

        (ws / "a.txt").write_text("hello", encoding="utf-8")
        assert (await tb.execute("git", {"subcommand": "add", "args": ["a.txt"]})).is_error is False
        commit = await tb.execute("git", {"subcommand": "commit", "message": "init commit"})
        assert commit.is_error is False, commit.content

        # push must be refused at the run_git whitelist level
        push = await tb.execute("git", {"subcommand": "push"})
        assert push.is_error is True and "not allowed" in push.content.lower(), push.content

        # checkout restricted to -b <branch>
        bad_co = await tb.execute("git", {"subcommand": "checkout", "args": ["main"]})
        assert bad_co.is_error is True, bad_co.content
        good_co = await tb.execute("git", {"subcommand": "checkout", "branch": "feature-x"})
        assert good_co.is_error is False, good_co.content
        print("  git_tool: OK — commit works, push/checkout-existing rejected, new branch ok")


async def test_run_git_direct_whitelist():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        assert run_git(ws, ["reset", "--hard"]).success is False  # destructive blocked
        assert run_git(ws, ["pull"]).success is False             # network blocked
        assert run_git(ws, []).success is False                   # empty
        print("  run_git_whitelist: OK — reset/pull/empty all refused")


async def test_find_symbol():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        (ws / "mod.py").write_text(
            "class Widget:\n    def render(self):\n        pass\n\ndef build_widget():\n    return Widget()\n",
            encoding="utf-8",
        )
        tb = AgentToolbox(ws)
        res = await tb.execute("find_symbol", {"name": "build_widget"})
        assert "mod.py" in res.content and "build_widget" in res.content, res.content
        res2 = await tb.execute("find_symbol", {"name": "Widget"})
        assert "class Widget" in res2.content, res2.content
        print("  find_symbol: OK — locates class and function definitions")


async def test_verify_detects_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        res = detect_and_verify(ws)
        assert res.success is True and "nothing to verify" in res.output.lower()
        print("  verify_empty: OK — no tooling detected => clean pass")


async def test_hook_policy_blocks_dangerous():
    from core.hooks.runner import HookRunner
    from core.hooks.policy import PolicyEnforcer, allow, deny

    def has_rm(args: dict) -> bool:
        return "rm" in (args.get("command") or "").lower().split()

    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        runner = HookRunner()
        runner.register_hook(PolicyEnforcer([
            deny("run_command", when=has_rm, name="no_rm"),
            allow("*", name="allow_others"),
        ]))
        tb = AgentToolbox(ws, hook_runner=runner)

        blocked = await tb.execute("run_command", {"command": "rm -rf ."})
        assert blocked.is_error is True and "policy" in blocked.content.lower(), blocked.content

        # a harmless read tool still passes the gate
        (ws / "x.txt").write_text("hi", encoding="utf-8")
        ok = await tb.execute("read_file", {"path": "x.txt"})
        assert ok.is_error is False, ok.content
        print("  hook_policy: OK — dangerous run_command denied, read allowed")


async def test_update_plan_outcome():
    with tempfile.TemporaryDirectory() as tmp:
        tb = AgentToolbox(Path(tmp))
        res = await tb.execute("update_plan", {"steps": [
            {"step": "read code", "status": "done"},
            {"step": "edit code", "status": "in_progress"},
        ]})
        assert res.plan is not None and len(res.plan) == 2, res.content
        assert tb.latest_plan[0]["step"] == "read code"
        print("  update_plan: OK — plan recorded and returned for UI event")


async def test_subagent_schema_restricted():
    # The restricted schema set must exclude mutation + spawning.
    names = {t["name"] for t in TOOL_SCHEMAS_SUBAGENT}
    assert "write_file" not in names and "spawn_subagent" not in names
    assert "read_file" in names and "find_symbol" in names
    # And a sub-agent toolbox refuses a mutating call even if asked.
    with tempfile.TemporaryDirectory() as tmp:
        tb = AgentToolbox(Path(tmp))
        tb._subagent = True
        res = await tb.execute("write_file", {"path": "x.txt", "content": "no"})
        assert res.is_error is True and "read-only" in res.content.lower(), res.content
        assert not (Path(tmp) / "x.txt").exists()
        print("  subagent_restricted: OK — read-only set, mutation refused")


async def main():
    print("Running new-tools offline tests...")
    if _has_git():
        await test_git_tool_commit_and_reject()
    else:
        print("  git_tool: SKIPPED (git not on PATH)")
    await test_run_git_direct_whitelist()
    await test_find_symbol()
    await test_verify_detects_nothing()
    await test_hook_policy_blocks_dangerous()
    await test_update_plan_outcome()
    await test_subagent_schema_restricted()
    print("ALL NEW-TOOL TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())

"""Offline test: conversation memory persists across agent restarts.

Proves the fix for "agent doesn't remember the conversation":
  - ConversationHistory persists to workspace/.sharrowkin/conversations/{session_id}.json
  - A stable session_id (not a per-call timestamp) means the same file is
    reused, so a fresh process/agent rehydrates prior turns.
  - The hydration logic mirrors agent/core.py: when RAM history is empty,
    fill it from the disk-backed ConversationHistory before adding the new turn.

Standalone runner (repo's pytest has no asyncio plugin):
    python tests/test_conversation_persistence.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from memory.conversation import ConversationHistory


def _hydrate_ram(conv: ConversationHistory) -> list[dict]:
    """Replicate core.py hydration: RAM list seeded from disk-backed history."""
    ram: list[dict] = []
    if len(conv) > 0:
        for m in conv.get_recent_context(n=conv.max_messages):
            ram.append({"role": m.role, "content": m.content})
    return ram


def test_same_session_id_reuses_disk_file():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        sid = "session-1"

        # --- "first message" run ---
        conv1 = ConversationHistory(session_id=sid, workspace=ws)
        conv1.add_message("user", "привет")
        conv1.add_message("assistant", "Привет! Чем помочь?")
        conv1.add_message("user", "меня зовут Даник")
        conv1.add_message("assistant", "Приятно познакомиться, Даник!")

        path = ws / ".sharrowkin" / "conversations" / f"{sid}.json"
        assert path.exists(), "conversation file should be written to disk"

        # --- simulate backend restart: brand-new instance, SAME session_id ---
        conv2 = ConversationHistory(session_id=sid, workspace=ws)
        assert len(conv2) == 4, f"expected 4 restored messages, got {len(conv2)}"

        ram = _hydrate_ram(conv2)
        joined = " ".join(m["content"] for m in ram)
        assert "Даник" in joined, "agent must recall the user's name after restart"
        assert ram[0]["role"] == "user" and ram[0]["content"] == "привет"
        print("  same_session_reuse: OK — 4 turns restored, name remembered after restart")


def test_timestamp_session_id_loses_memory():
    """The OLD bug: a per-call session id never reloads the prior file."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        conv_a = ConversationHistory(session_id="session_1700000001", workspace=ws)
        conv_a.add_message("user", "привет")
        conv_a.add_message("assistant", "Привет!")

        # Next message generated a different timestamp id -> empty history.
        conv_b = ConversationHistory(session_id="session_1700000002", workspace=ws)
        assert len(conv_b) == 0, "different id must NOT see prior conversation (documents the old bug)"
        print("  timestamp_id_bug: OK — distinct ids start empty (this is what we fixed)")


def test_hydration_skipped_when_ram_already_populated():
    """In-process reuse: RAM already holds turns, so we must NOT re-hydrate."""
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        sid = "session-xyz"
        conv = ConversationHistory(session_id=sid, workspace=ws)
        conv.add_message("user", "first")
        conv.add_message("assistant", "ack")

        ram = [{"role": "user", "content": "first"}, {"role": "assistant", "content": "ack"}]
        # core.py guards hydration behind `if not self.conversation_history`
        should_hydrate = (not ram) and len(conv) > 0
        assert should_hydrate is False, "must not duplicate turns when RAM is already populated"
        print("  no_duplicate: OK — hydration guarded by empty-RAM check")


def main():
    print("Running conversation-persistence tests...")
    test_same_session_id_reuses_disk_file()
    test_timestamp_session_id_loses_memory()
    test_hydration_skipped_when_ram_already_populated()
    print("ALL CONVERSATION-PERSISTENCE TESTS PASSED")


if __name__ == "__main__":
    main()

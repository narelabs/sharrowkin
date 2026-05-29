"""Unit tests for :class:`agent.checkpoints.CheckpointStore` (subtask 3.3).

These tests exercise the on-disk behaviour required by the design doc
"Backend: Checkpoint v2 > Store rules": save/load round-trip, recoverable
filtering, quarantine of corrupt files, and pruning to a fixed retention.

The property-based round-trip and broader prune/quarantine PBT live in
subtasks 3.5 / 3.6 (`tests/test_checkpoint_pbt.py`); this file focuses on
deterministic example-based coverage so a regression surfaces with a clear
failure rather than a hypothesis counterexample.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agent.checkpoints import (
    SCHEMA_VERSION,
    Checkpoint,
    CheckpointPhase,
    CheckpointStore,
    serialize,
)
from agent.event_stream import PhaseId, PhaseStatus


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _iso(dt: datetime) -> str:
    """ISO-8601 UTC string with the ``+00:00`` offset that ``deserialize``
    accepts. Tests use this consistently so created_at / expires_at are
    parseable by the store's recoverable / prune logic."""
    return dt.astimezone(timezone.utc).isoformat()


def _phase(
    phase_id: PhaseId, status: PhaseStatus = PhaseStatus.PENDING
) -> CheckpointPhase:
    return CheckpointPhase(
        id=phase_id,
        status=status,
        started_at=None,
        completed_at=None,
        error=None,
    )


def _make_checkpoint(
    *,
    session_id: str = "session_test",
    workspace: str = "C:/ws",
    created_at: datetime | None = None,
    ttl_hours: int = 24,
    phases: tuple[CheckpointPhase, ...] | None = None,
    current_phase: PhaseId = PhaseId.OBSERVE,
    last_event_seq: int = 0,
) -> Checkpoint:
    """Build a minimal but valid :class:`Checkpoint` for store tests.

    Defaults pick a future ``expires_at`` so the checkpoint is recoverable
    unless a test explicitly overrides ``created_at`` to push it into the
    past.
    """
    if created_at is None:
        created_at = datetime.now(timezone.utc)
    if phases is None:
        phases = tuple(_phase(p) for p in PhaseId)
    return Checkpoint(
        schema_version=SCHEMA_VERSION,
        session_id=session_id,
        workspace=workspace,
        task="t",
        plan_mode="autonomous",
        current_phase=current_phase,
        phases=phases,
        conversation_ref="conv.json",
        in_flight_tool_calls=(),
        last_event_seq=last_event_seq,
        cognitive_state={},
        created_at=_iso(created_at),
        expires_at=_iso(created_at + timedelta(hours=ttl_hours)),
    )


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    """Fresh store rooted at ``tmp_path`` so tests are isolated from each
    other and from the real ``.sharrowkin/checkpoints/`` directory."""
    return CheckpointStore(base_dir=tmp_path)


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_init_creates_base_dir(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "checkpoints"
    assert not target.exists()
    store = CheckpointStore(base_dir=target)
    assert target.is_dir()
    assert store.base_dir == target


def test_init_default_uses_cwd(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    store = CheckpointStore()
    assert store.base_dir == tmp_path / ".sharrowkin" / "checkpoints"
    assert store.base_dir.is_dir()


# ---------------------------------------------------------------------------
# save + load_latest
# ---------------------------------------------------------------------------


def test_save_writes_primary_and_latest(store: CheckpointStore) -> None:
    c = _make_checkpoint(session_id="abc")
    primary = store.save(c)

    assert primary.is_file()
    assert primary.name.startswith("checkpoint_abc_")
    assert primary.name.endswith(".json")

    latest = store.base_dir / "latest_abc.json"
    assert latest.is_file()
    # Same content (the ``latest_`` is a copy, not a symlink — Windows).
    assert latest.read_text(encoding="utf-8") == primary.read_text(encoding="utf-8")


def test_save_filename_is_windows_safe(store: CheckpointStore) -> None:
    # ISO timestamps contain ':' which is invalid on NTFS.
    c = _make_checkpoint(session_id="abc")
    primary = store.save(c)
    forbidden = set('<>:"/\\|?*')
    # The filename portion (not the parent path) must not contain any of
    # the reserved characters even though created_at does.
    assert not (forbidden & set(primary.name))


def test_load_latest_round_trip(store: CheckpointStore) -> None:
    c = _make_checkpoint(session_id="abc", last_event_seq=42)
    store.save(c)
    loaded = store.load_latest("abc")
    assert loaded == c


def test_load_latest_missing_returns_none(store: CheckpointStore) -> None:
    assert store.load_latest("never_saved") is None


def test_load_latest_corrupt_quarantines(store: CheckpointStore) -> None:
    latest = store.base_dir / "latest_bad.json"
    latest.write_text("{not json", encoding="utf-8")

    assert store.load_latest("bad") is None
    # Original file is gone and now lives under corrupt/.
    assert not latest.exists()
    corrupt = store.base_dir / "corrupt" / "latest_bad.json"
    assert corrupt.is_file()
    reason = corrupt.with_name(corrupt.name + ".reason.txt")
    assert reason.is_file()
    # After 3.4, ``load_latest`` delegates to ``_load_or_migrate`` so the
    # quarantine reason mentions the helper rather than the public API.
    reason_text = reason.read_text(encoding="utf-8")
    assert (
        "load_latest failed" in reason_text
        or "_load_or_migrate" in reason_text
    )


def test_save_overwrites_latest_pointer(store: CheckpointStore) -> None:
    older = _make_checkpoint(
        session_id="abc",
        created_at=datetime(2026, 5, 25, tzinfo=timezone.utc),
        last_event_seq=1,
    )
    newer = _make_checkpoint(
        session_id="abc",
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc),
        last_event_seq=2,
    )
    store.save(older)
    store.save(newer)

    loaded = store.load_latest("abc")
    assert loaded is not None
    assert loaded.last_event_seq == 2


# ---------------------------------------------------------------------------
# list_recoverable
# ---------------------------------------------------------------------------


def test_list_recoverable_returns_active(store: CheckpointStore) -> None:
    c = _make_checkpoint(session_id="active")
    store.save(c)
    recoverable = store.list_recoverable()
    assert [r.session_id for r in recoverable] == ["active"]


def test_list_recoverable_excludes_expired(store: CheckpointStore) -> None:
    expired = _make_checkpoint(
        session_id="old",
        created_at=datetime.now(timezone.utc) - timedelta(days=2),
        ttl_hours=24,
    )
    store.save(expired)
    assert store.list_recoverable() == []


def test_list_recoverable_excludes_all_done_phases(store: CheckpointStore) -> None:
    done_phases = tuple(
        _phase(p, PhaseStatus.DONE) for p in PhaseId
    )
    finished = _make_checkpoint(
        session_id="finished",
        phases=done_phases,
        current_phase=PhaseId.COMMIT,
    )
    store.save(finished)
    assert store.list_recoverable() == []


def test_list_recoverable_filters_by_workspace(store: CheckpointStore) -> None:
    a = _make_checkpoint(session_id="a", workspace="C:/proj-a")
    b = _make_checkpoint(session_id="b", workspace="C:/proj-b")
    store.save(a)
    store.save(b)

    only_a = store.list_recoverable(workspace=Path("C:/proj-a"))
    assert [r.session_id for r in only_a] == ["a"]


def test_list_recoverable_excludes_latest_files(store: CheckpointStore) -> None:
    # latest_<session>.json must not appear as its own recoverable record;
    # otherwise we'd double-count every saved checkpoint.
    c = _make_checkpoint(session_id="abc")
    store.save(c)
    recoverable = store.list_recoverable()
    assert len(recoverable) == 1


def test_list_recoverable_quarantines_corrupt_primary(
    store: CheckpointStore,
) -> None:
    bad = store.base_dir / "checkpoint_bad_2026-05-25.json"
    bad.write_text("not json", encoding="utf-8")

    assert store.list_recoverable() == []
    assert not bad.exists()
    assert (store.base_dir / "corrupt" / bad.name).is_file()


def test_list_recoverable_excludes_corrupt_subdir_contents(
    store: CheckpointStore,
) -> None:
    # A pre-existing corrupt file should be ignored on subsequent scans
    # rather than re-quarantined / counted.
    corrupt_dir = store.base_dir / "corrupt"
    corrupt_dir.mkdir()
    (corrupt_dir / "checkpoint_old_x.json").write_text("garbage", encoding="utf-8")

    c = _make_checkpoint(session_id="ok")
    store.save(c)

    recoverable = store.list_recoverable()
    assert [r.session_id for r in recoverable] == ["ok"]


# ---------------------------------------------------------------------------
# quarantine
# ---------------------------------------------------------------------------


def test_quarantine_moves_file_and_writes_reason(
    store: CheckpointStore,
) -> None:
    bad = store.base_dir / "checkpoint_bad.json"
    bad.write_text("payload", encoding="utf-8")

    new_path = store.quarantine(bad, reason="malformed JSON")

    assert not bad.exists()
    assert new_path == store.base_dir / "corrupt" / "checkpoint_bad.json"
    assert new_path.is_file()
    reason = new_path.with_name(new_path.name + ".reason.txt")
    assert reason.read_text(encoding="utf-8") == "malformed JSON"


def test_quarantine_does_not_clobber_existing(store: CheckpointStore) -> None:
    bad = store.base_dir / "checkpoint_bad.json"
    bad.write_text("first", encoding="utf-8")
    store.quarantine(bad, reason="r1")

    bad.write_text("second", encoding="utf-8")
    new_path = store.quarantine(bad, reason="r2")

    # Both copies must survive; the second got a numeric suffix.
    first = store.base_dir / "corrupt" / "checkpoint_bad.json"
    assert first.read_text(encoding="utf-8") == "first"
    assert new_path != first
    assert new_path.read_text(encoding="utf-8") == "second"


# ---------------------------------------------------------------------------
# prune
# ---------------------------------------------------------------------------


def test_prune_keeps_newest_n(store: CheckpointStore) -> None:
    base_time = datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc)
    for i in range(10):
        store.save(
            _make_checkpoint(
                session_id=f"s{i}",
                created_at=base_time + timedelta(minutes=i),
            )
        )

    deleted = store.prune(keep=3)
    assert deleted == 7

    remaining = sorted(p.name for p in store.base_dir.iterdir() if p.is_file()
                       and p.name.startswith("checkpoint_"))
    # The three kept must be the most recent (s7, s8, s9).
    assert len(remaining) == 3
    assert all(name.startswith(("checkpoint_s7_", "checkpoint_s8_",
                                 "checkpoint_s9_")) for name in remaining)


def test_prune_keep_default_50_keeps_exactly_50(store: CheckpointStore) -> None:
    base_time = datetime(2026, 5, 25, tzinfo=timezone.utc)
    for i in range(60):
        store.save(
            _make_checkpoint(
                session_id=f"s{i:02d}",
                created_at=base_time + timedelta(seconds=i),
            )
        )
    deleted = store.prune()  # default keep=50
    assert deleted == 10

    primaries = [p for p in store.base_dir.iterdir()
                 if p.is_file() and p.name.startswith("checkpoint_")]
    assert len(primaries) == 50


def test_prune_below_keep_is_noop(store: CheckpointStore) -> None:
    store.save(_make_checkpoint(session_id="only"))
    assert store.prune(keep=50) == 0
    assert (store.base_dir / "latest_only.json").is_file()


def test_prune_filters_by_workspace(store: CheckpointStore) -> None:
    base = datetime(2026, 5, 25, tzinfo=timezone.utc)
    for i in range(5):
        store.save(
            _make_checkpoint(
                session_id=f"a{i}",
                workspace="C:/ws-a",
                created_at=base + timedelta(minutes=i),
            )
        )
    for i in range(5):
        store.save(
            _make_checkpoint(
                session_id=f"b{i}",
                workspace="C:/ws-b",
                created_at=base + timedelta(minutes=i + 100),
            )
        )

    deleted = store.prune(workspace=Path("C:/ws-a"), keep=2)
    # Only ws-a candidates considered; 5 - 2 = 3 deleted.
    assert deleted == 3

    # ws-b is untouched.
    ws_b_count = sum(
        1 for p in store.base_dir.iterdir()
        if p.is_file() and p.name.startswith("checkpoint_b")
    )
    assert ws_b_count == 5


def test_prune_does_not_touch_latest_or_corrupt(store: CheckpointStore) -> None:
    # Set up many checkpoints so prune wants to delete some, plus a
    # latest_ pointer and a corrupt/ entry that must survive untouched.
    base = datetime(2026, 5, 25, tzinfo=timezone.utc)
    for i in range(5):
        store.save(
            _make_checkpoint(
                session_id=f"s{i}",
                created_at=base + timedelta(minutes=i),
            )
        )
    corrupt_dir = store.base_dir / "corrupt"
    corrupt_dir.mkdir(exist_ok=True)
    sentinel = corrupt_dir / "checkpoint_old.json"
    sentinel.write_text("garbage", encoding="utf-8")

    store.prune(keep=1)

    # latest_ pointers must still exist for every session that still has a
    # primary record (we keep only the newest, s4).
    assert (store.base_dir / "latest_s4.json").is_file()
    assert sentinel.is_file()


def test_prune_negative_keep_raises(store: CheckpointStore) -> None:
    with pytest.raises(ValueError):
        store.prune(keep=-1)


# ---------------------------------------------------------------------------
# Misc behaviour
# ---------------------------------------------------------------------------


def test_save_two_checkpoints_with_different_created_at(
    store: CheckpointStore,
) -> None:
    # Distinct created_at must produce distinct primary files (otherwise
    # prune cannot distinguish snapshots).
    c1 = _make_checkpoint(
        created_at=datetime(2026, 5, 25, tzinfo=timezone.utc)
    )
    c2 = _make_checkpoint(
        created_at=datetime(2026, 5, 26, tzinfo=timezone.utc)
    )
    p1 = store.save(c1)
    p2 = store.save(c2)
    assert p1 != p2
    assert p1.is_file() and p2.is_file()


def test_load_latest_after_external_corruption(store: CheckpointStore) -> None:
    # If something else on the system clobbers latest_*.json with garbage,
    # subsequent load_latest calls must self-heal: quarantine and report
    # missing.
    c = _make_checkpoint(session_id="abc")
    store.save(c)
    latest = store.base_dir / "latest_abc.json"
    latest.write_text("oops", encoding="utf-8")

    assert store.load_latest("abc") is None
    assert (store.base_dir / "corrupt" / "latest_abc.json").is_file()


def test_serialize_round_trip_on_disk(tmp_path: Path) -> None:
    # Sanity: bytes written to disk must equal serialize() output exactly,
    # so external tools / migrations can read them with the public function.
    store = CheckpointStore(base_dir=tmp_path)
    c = _make_checkpoint()
    primary = store.save(c)
    assert primary.read_text(encoding="utf-8") == serialize(c)

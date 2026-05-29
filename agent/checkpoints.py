"""Checkpoint v2: typed snapshot of agent run-state for crash recovery.

This module implements the public types described in the design document
(``.kiro/specs/ui-and-agent-stabilization/design.md``, section
"Backend: Checkpoint v2 > Format"). It is split across several subtasks
(3.1 - 3.6); this file currently covers:

* **3.1 (this commit)** introduces the dataclass surface used by every
  later piece:

  - :data:`SCHEMA_VERSION` — current on-disk format version (``2``).
  - :class:`ToolCallSnapshot` — frozen record of a tool invocation that was
    in-flight when the checkpoint was taken, including its ``idempotency_key``
    so resume can dedupe replays of mutating tools.
  - :class:`CheckpointPhase` — frozen record of a single phase entry
    (``id``, ``status`` and timing) used to rebuild the Phase_Timeline after
    resume.
  - :class:`Checkpoint` — top-level frozen aggregate persisted under
    ``.sharrowkin/checkpoints/`` after every completed phase and at most
    every 60 seconds (see Req 7.1, design "Store rules").

* Subsequent subtasks add :func:`serialize` / :func:`deserialize` (3.2),
  :class:`CheckpointStore` with ``save`` / ``load_latest`` /
  ``list_recoverable`` / ``quarantine`` / ``prune`` (3.3), legacy migration
  (3.4) and property-based round-trip + store invariant tests (3.5, 3.6).

All dataclasses use ``slots=True, frozen=True``: instances are compact
(``__slots__`` saves the per-instance dict) and immutable, so a
:class:`Checkpoint` can be safely shared across the resume code path,
the WebSocket replay path and tests without defensive copies.

Field-level rationale:
    * ``ToolCallSnapshot.status`` is typed as ``ToolCallStatus | str`` rather
      than just the enum because checkpoints are written as JSON and read
      back across processes — keeping the raw string form portable lets the
      deserializer (subtask 3.2) round-trip even if the enum gains values
      between versions.
    * ``Checkpoint.phases`` and ``Checkpoint.in_flight_tool_calls`` are tuples
      (not lists) to keep the aggregate hashable and to make accidental
      mutation impossible after construction.
    * ``Checkpoint.conversation_ref`` is the **path** to the matching
      ``.sharrowkin/conversations/session_*.json`` rather than the embedded
      conversation, so checkpoints stay small and the conversation log
      remains the single source of truth for message history.
    * ``Checkpoint.cognitive_state`` is an opaque ``dict[str, Any]`` snapshot
      of cognitive primitives (``dim``, ``energy_ledger``, ``attractors``);
      its precise shape is owned by the cognitive subsystem and only needs to
      survive JSON round-trip here.

References:
    Design: ``.kiro/specs/ui-and-agent-stabilization/design.md`` section
    "Backend: Checkpoint v2 > Format".
    Requirements: 7.2 (typed Checkpoint v2 record).
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from agent.event_stream import PhaseId, PhaseStatus, ToolCallStatus


# =============================================================================
# Schema version
# =============================================================================

#: On-disk format version for Checkpoint v2 files.
#:
#: Bumped from the legacy unversioned format (see ``migrate_legacy`` in
#: subtask 3.4) to ``2``. The deserializer rejects unknown versions; legacy
#: files (no ``schema_version`` key) are migrated rather than read directly.
SCHEMA_VERSION: int = 2


# =============================================================================
# Dataclasses
# =============================================================================


@dataclass(slots=True, frozen=True)
class ToolCallSnapshot:
    """Frozen record of one tool invocation captured in a checkpoint.

    A snapshot is recorded for every tool call that has been started but not
    yet observed as ``done`` / ``error`` at checkpoint time, so resume can:

    * skip tools that already completed (matched by ``idempotency_key``), and
    * surface still-running tools to the UI as ``tool_call(running)`` again
      after replay.

    Attributes:
        tool_id: Stable per-call identifier (matches the ``tool_id`` field of
            the corresponding ``tool_call`` event).
        name: Tool name as registered with the agent (e.g. ``"run_pytest"``).
        status: Lifecycle status. Typed as ``ToolCallStatus | str`` so a
            checkpoint loaded from disk can hold the raw string value even
            when the enum has drifted between versions; new code should pass
            a :class:`ToolCallStatus` and let serialization down-convert.
        started_at: ISO-8601 UTC timestamp of the ``tool_call(running)``
            event, or ``None`` if not yet started.
        completed_at: ISO-8601 UTC timestamp of the terminal event
            (``done`` / ``error``), or ``None`` while still running.
        error: Error message captured on failure, or ``None`` on success or
            while running.
        idempotency_key: Deterministic key derived from
            ``(tool_name, normalized_args, run_id)`` (Req 2.1). Used by resume
            to detect "already executed" mutating tools and avoid double
            side effects.
    """

    tool_id: str
    name: str
    status: ToolCallStatus | str
    started_at: str | None
    completed_at: str | None
    error: str | None
    idempotency_key: str | None


@dataclass(slots=True, frozen=True)
class CheckpointPhase:
    """Frozen record of a single phase entry in the checkpoint.

    Mirrors the per-phase row used by the UI Phase_Timeline; on resume the
    store reconstructs the timeline directly from
    :attr:`Checkpoint.phases` without replaying the event log.

    Attributes:
        id: Canonical phase identifier (one of the five-stage cycle).
        status: Lifecycle status of this phase at checkpoint time.
        started_at: ISO-8601 UTC timestamp when the phase entered ``running``,
            or ``None`` if it never started.
        completed_at: ISO-8601 UTC timestamp when the phase reached a
            terminal status (``done`` / ``error`` / ``skipped``), or ``None``
            while still pending or running.
        error: Error message if ``status == PhaseStatus.ERROR``, else
            ``None``.
    """

    id: PhaseId
    status: PhaseStatus
    started_at: str | None
    completed_at: str | None
    error: str | None


@dataclass(slots=True, frozen=True)
class Checkpoint:
    """Top-level immutable snapshot of an agent run-state.

    Persisted under ``.sharrowkin/checkpoints/checkpoint_<session>_<ts>.json``
    after every completed phase and at most every 60 seconds. A checkpoint
    is considered ``recoverable`` while ``expires_at > now`` and
    ``current_phase`` is not the terminal ``commit:done`` state (the resume
    eligibility logic lives in :class:`CheckpointStore.list_recoverable`,
    subtask 3.3).

    The aggregate is intentionally flat and JSON-friendly: tuples instead of
    lists for collections, ISO-8601 strings for timestamps, and an opaque
    ``cognitive_state`` dict the cognitive subsystem owns. This lets
    :func:`serialize` (subtask 3.2) be a pure function over standard JSON
    types with stable, sorted-key output.

    Attributes:
        schema_version: Format version, must equal :data:`SCHEMA_VERSION`
            for any newly written checkpoint. Older files go through
            ``migrate_legacy`` (subtask 3.4).
        session_id: Owning session id; one session may produce many
            checkpoints, identified by their ``created_at`` timestamp.
        workspace: Absolute path to the workspace this run targets.
        task: User-supplied task description that drove this run.
        plan_mode: Planning mode in effect (e.g. ``"autonomous"``).
        current_phase: The phase the agent was executing (or about to
            execute) at checkpoint time.
        phases: Per-phase rows in canonical order
            (Observe → Recall → Reason → Stabilize → Commit). A tuple so the
            checkpoint stays hashable and immutable.
        conversation_ref: Path (relative to the workspace) of the matching
            ``conversations/session_*.json`` log. The conversation itself is
            **not** embedded — keeping the checkpoint small and the log as
            the single source of truth.
        in_flight_tool_calls: Snapshots of tool calls that were started but
            not observed as terminal at checkpoint time. Empty tuple is
            normal during idle phases.
        last_event_seq: Highest ``seq`` from the Event_Stream that this
            checkpoint reflects. Resume continues with ``seq + 1``.
        cognitive_state: Opaque snapshot of cognitive primitives
            (``dim``, ``energy_ledger``, ``attractors`` snapshot per the
            design doc). The structure is owned by the cognitive subsystem;
            this layer only requires JSON round-trip.
        created_at: ISO-8601 UTC timestamp the checkpoint was produced.
        expires_at: ISO-8601 UTC timestamp ``created_at + 24h`` after which
            the checkpoint is no longer eligible for resume.
    """

    schema_version: int
    session_id: str
    workspace: str
    task: str
    plan_mode: str
    current_phase: PhaseId
    phases: tuple[CheckpointPhase, ...]
    conversation_ref: str
    in_flight_tool_calls: tuple[ToolCallSnapshot, ...]
    last_event_seq: int
    cognitive_state: dict[str, Any]
    created_at: str
    expires_at: str


__all__ = [
    "SCHEMA_VERSION",
    "ToolCallSnapshot",
    "CheckpointPhase",
    "Checkpoint",
    "serialize",
    "deserialize",
    "migrate_legacy",
    "CheckpointStore",
]


# =============================================================================
# Serialization (subtask 3.2)
# =============================================================================


def _enum_to_value(value: Any) -> Any:
    """Reduce an :class:`Enum` member to its underlying ``.value``.

    Pass-through for non-enum inputs so this is safe to apply to fields that
    may hold either an enum or a raw string (e.g. ``ToolCallSnapshot.status``,
    which is typed ``ToolCallStatus | str`` to survive enum drift across
    versions).
    """

    if isinstance(value, Enum):
        return value.value
    return value


def serialize(c: Checkpoint) -> str:
    """Serialize a :class:`Checkpoint` to canonical JSON.

    The output is:

    * ``sort_keys=True`` so byte output is stable for any structurally equal
      input (required for the round-trip property in Req 13.3 and for
      content-addressable storage / diffing).
    * ``indent=2`` so checkpoint files are human-inspectable on disk.
    * ``ensure_ascii=False`` so non-ASCII task descriptions survive verbatim
      rather than being escaped.

    All :class:`Enum` members (``PhaseId``, ``PhaseStatus``,
    ``ToolCallStatus``) are emitted as their ``.value`` strings; tuples
    become JSON arrays. ``ToolCallSnapshot.status`` is normalized to a string
    even when stored as the raw enum, which makes
    ``deserialize(serialize(c)) == c`` exact regardless of which form the
    caller used to construct the snapshot.

    Args:
        c: The checkpoint to serialize. Must be a fully-constructed
            :class:`Checkpoint`; partial dicts are not accepted.

    Returns:
        JSON text suitable for direct write to
        ``.sharrowkin/checkpoints/*.json``.
    """

    payload = asdict(c)

    # ``asdict`` already converts the nested dataclasses and turns the tuple
    # fields into lists, which is what JSON wants. The remaining work is
    # collapsing enums to their string values.
    payload["current_phase"] = _enum_to_value(c.current_phase)

    payload["phases"] = [
        {
            "id": _enum_to_value(p.id),
            "status": _enum_to_value(p.status),
            "started_at": p.started_at,
            "completed_at": p.completed_at,
            "error": p.error,
        }
        for p in c.phases
    ]

    payload["in_flight_tool_calls"] = [
        {
            "tool_id": t.tool_id,
            "name": t.name,
            "status": _enum_to_value(t.status),
            "started_at": t.started_at,
            "completed_at": t.completed_at,
            "error": t.error,
            "idempotency_key": t.idempotency_key,
        }
        for t in c.in_flight_tool_calls
    ]

    return json.dumps(payload, sort_keys=True, indent=2, ensure_ascii=False)


# =============================================================================
# Deserialization (subtask 3.2)
# =============================================================================


# Required top-level keys; missing any of these is a hard error rather than a
# silent default, because a checkpoint with a hole cannot safely drive resume.
_REQUIRED_KEYS: frozenset[str] = frozenset(
    {
        "schema_version",
        "session_id",
        "workspace",
        "task",
        "plan_mode",
        "current_phase",
        "phases",
        "conversation_ref",
        "in_flight_tool_calls",
        "last_event_seq",
        "cognitive_state",
        "created_at",
        "expires_at",
    }
)

_REQUIRED_PHASE_KEYS: frozenset[str] = frozenset(
    {"id", "status", "started_at", "completed_at", "error"}
)

_REQUIRED_TOOL_CALL_KEYS: frozenset[str] = frozenset(
    {
        "tool_id",
        "name",
        "status",
        "started_at",
        "completed_at",
        "error",
        "idempotency_key",
    }
)


def _coerce_tool_call_status(raw: Any) -> ToolCallStatus | str:
    """Convert a stored status string back to :class:`ToolCallStatus` if known.

    Strings matching a current enum value become the enum (so equality with a
    freshly-constructed snapshot holds). Strings that do not match — possibly
    written by a newer agent version — are preserved verbatim, which is what
    the ``ToolCallStatus | str`` field type promises.
    """

    if isinstance(raw, str):
        try:
            return ToolCallStatus(raw)
        except ValueError:
            return raw
    raise ValueError(f"tool call status must be a string, got {type(raw).__name__}")


def _build_phase(raw: dict[str, Any]) -> CheckpointPhase:
    missing = _REQUIRED_PHASE_KEYS - raw.keys()
    if missing:
        raise ValueError(f"checkpoint phase missing required keys: {sorted(missing)}")
    try:
        phase_id = PhaseId(raw["id"])
    except ValueError as exc:
        raise ValueError(f"unknown phase id: {raw['id']!r}") from exc
    try:
        status = PhaseStatus(raw["status"])
    except ValueError as exc:
        raise ValueError(f"unknown phase status: {raw['status']!r}") from exc
    return CheckpointPhase(
        id=phase_id,
        status=status,
        started_at=raw["started_at"],
        completed_at=raw["completed_at"],
        error=raw["error"],
    )


def _build_tool_call(raw: dict[str, Any]) -> ToolCallSnapshot:
    missing = _REQUIRED_TOOL_CALL_KEYS - raw.keys()
    if missing:
        raise ValueError(
            f"checkpoint tool call missing required keys: {sorted(missing)}"
        )
    return ToolCallSnapshot(
        tool_id=raw["tool_id"],
        name=raw["name"],
        status=_coerce_tool_call_status(raw["status"]),
        started_at=raw["started_at"],
        completed_at=raw["completed_at"],
        error=raw["error"],
        idempotency_key=raw["idempotency_key"],
    )


def deserialize(raw: str) -> Checkpoint:
    """Parse JSON text back into a :class:`Checkpoint`.

    Inverse of :func:`serialize`: the round-trip identity
    ``deserialize(serialize(c)) == c`` holds for every valid checkpoint
    (Req 13.3). To make that exact, lists are restored as tuples for
    ``phases`` and ``in_flight_tool_calls``, and known enum string values are
    converted back to :class:`PhaseId` / :class:`PhaseStatus` /
    :class:`ToolCallStatus` members. Unknown ``ToolCallStatus`` strings are
    preserved verbatim (``ToolCallStatus | str`` field), so a checkpoint
    written by a newer agent revision is still loadable here.

    Args:
        raw: JSON text produced by :func:`serialize`, or a structurally
            equivalent payload.

    Returns:
        Fully-typed :class:`Checkpoint`.

    Raises:
        ValueError: If the payload is not a JSON object, ``schema_version``
            does not equal :data:`SCHEMA_VERSION`, a required field is
            missing, or a known-enum field carries an unknown value.
            Legacy checkpoints (no ``schema_version``) are not handled here;
            they go through ``migrate_legacy`` (subtask 3.4) first.
    """

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"checkpoint is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(
            f"checkpoint root must be a JSON object, got {type(payload).__name__}"
        )

    missing = _REQUIRED_KEYS - payload.keys()
    if missing:
        raise ValueError(f"checkpoint missing required keys: {sorted(missing)}")

    schema_version = payload["schema_version"]
    if schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"unsupported checkpoint schema_version: {schema_version!r} "
            f"(expected {SCHEMA_VERSION})"
        )

    try:
        current_phase = PhaseId(payload["current_phase"])
    except ValueError as exc:
        raise ValueError(
            f"unknown current_phase: {payload['current_phase']!r}"
        ) from exc

    raw_phases = payload["phases"]
    if not isinstance(raw_phases, list):
        raise ValueError("checkpoint 'phases' must be a JSON array")
    phases = tuple(_build_phase(p) for p in raw_phases)

    raw_tool_calls = payload["in_flight_tool_calls"]
    if not isinstance(raw_tool_calls, list):
        raise ValueError("checkpoint 'in_flight_tool_calls' must be a JSON array")
    in_flight_tool_calls = tuple(_build_tool_call(t) for t in raw_tool_calls)

    cognitive_state = payload["cognitive_state"]
    if not isinstance(cognitive_state, dict):
        raise ValueError("checkpoint 'cognitive_state' must be a JSON object")

    return Checkpoint(
        schema_version=schema_version,
        session_id=payload["session_id"],
        workspace=payload["workspace"],
        task=payload["task"],
        plan_mode=payload["plan_mode"],
        current_phase=current_phase,
        phases=phases,
        conversation_ref=payload["conversation_ref"],
        in_flight_tool_calls=in_flight_tool_calls,
        last_event_seq=payload["last_event_seq"],
        cognitive_state=cognitive_state,
        created_at=payload["created_at"],
        expires_at=payload["expires_at"],
    )


# =============================================================================
# Legacy migration (subtask 3.4)
# =============================================================================


#: How long after migration the resulting checkpoint stays "recoverable".
#: Mirrors the standard 24h TTL described in the design doc; legacy files
#: do not carry an ``expires_at``, so we synthesize one from "now" rather
#: than the original wall-clock timestamp (which may be well past 24h ago
#: by the time migration runs).
_LEGACY_TTL: timedelta = timedelta(hours=24)


def _legacy_now_iso() -> str:
    """ISO-8601 UTC timestamp for the moment migration runs.

    Wrapped in a helper so tests can monkey-patch a single call site if
    deterministic timestamps are needed; production code uses the wall
    clock. The trailing ``+00:00`` suffix matches the format produced
    elsewhere in the system (``datetime.isoformat`` on a tz-aware UTC
    datetime).
    """

    return _now_utc().isoformat()


def _coerce_legacy_phase_id(raw: Any) -> PhaseId:
    """Best-effort conversion of a legacy phase indicator to :class:`PhaseId`.

    Accepts:

    * A string matching a current :class:`PhaseId` value (case-insensitive),
      e.g. ``"observe"`` or ``"OBSERVE"``.
    * Any other value falls back to :data:`PhaseId.OBSERVE`, which is the
      canonical "start of cycle" phase — safer than picking ``COMMIT`` and
      accidentally signalling a finished run during resume.
    """

    if isinstance(raw, str):
        try:
            return PhaseId(raw.lower())
        except ValueError:
            pass
    return PhaseId.OBSERVE


def _coerce_legacy_phase_status(raw: Any) -> PhaseStatus:
    """Best-effort conversion of a legacy phase status to :class:`PhaseStatus`.

    Unknown / missing values map to :data:`PhaseStatus.PENDING` so the
    canonical five-row timeline is rebuildable even when the legacy file
    only carried a single phase indicator.
    """

    if isinstance(raw, str):
        try:
            return PhaseStatus(raw.lower())
        except ValueError:
            pass
    return PhaseStatus.PENDING


def _build_legacy_phases(
    raw_dict: dict[str, Any],
    current_phase: PhaseId,
) -> tuple[CheckpointPhase, ...]:
    """Rebuild the canonical 5-phase timeline from a legacy payload.

    Strategy:

    * If the legacy payload carries a recognizable ``phases`` list with the
      same shape as v2 entries, reuse those values where they map cleanly,
      and fill missing phases with ``PENDING``.
    * Otherwise fall back to "all phases ``PENDING``" — the design doc
      explicitly accepts this as the migration default. We do **not** try
      to retroactively mark phases ``DONE`` based on ``current_phase``,
      because the legacy format never recorded successful phase transitions
      and assuming completion would risk skipping work on resume.
    """

    by_id: dict[PhaseId, CheckpointPhase] = {}
    raw_phases = raw_dict.get("phases")
    if isinstance(raw_phases, list):
        for entry in raw_phases:
            if not isinstance(entry, dict):
                continue
            phase_id = _coerce_legacy_phase_id(entry.get("id") or entry.get("phase"))
            status = _coerce_legacy_phase_status(
                entry.get("status") or entry.get("state")
            )
            by_id[phase_id] = CheckpointPhase(
                id=phase_id,
                status=status,
                started_at=entry.get("started_at"),
                completed_at=entry.get("completed_at"),
                error=entry.get("error"),
            )

    # Canonical order, with any value supplied by the legacy file taking
    # precedence over the synthesized ``PENDING`` default.
    ordered: list[CheckpointPhase] = []
    for phase_id in PhaseId:
        if phase_id in by_id:
            ordered.append(by_id[phase_id])
        else:
            ordered.append(
                CheckpointPhase(
                    id=phase_id,
                    status=PhaseStatus.PENDING,
                    started_at=None,
                    completed_at=None,
                    error=None,
                )
            )
    return tuple(ordered)


def _build_legacy_tool_calls(raw_dict: dict[str, Any]) -> tuple[ToolCallSnapshot, ...]:
    """Rebuild ``in_flight_tool_calls`` from a legacy payload.

    Legacy checkpoints predate the in-flight snapshot model, so the common
    case is "no tool-call data at all" → empty tuple. Where a list is
    present and entries are shaped roughly like v2 snapshots, we map
    field-by-field with safe defaults.
    """

    raw_calls = raw_dict.get("in_flight_tool_calls")
    if not isinstance(raw_calls, list):
        return ()
    snapshots: list[ToolCallSnapshot] = []
    for entry in raw_calls:
        if not isinstance(entry, dict):
            continue
        status_raw = entry.get("status", "running")
        try:
            status: ToolCallStatus | str = ToolCallStatus(status_raw)
        except ValueError:
            status = str(status_raw)
        snapshots.append(
            ToolCallSnapshot(
                tool_id=str(entry.get("tool_id", "")),
                name=str(entry.get("name", "")),
                status=status,
                started_at=entry.get("started_at"),
                completed_at=entry.get("completed_at"),
                error=entry.get("error"),
                idempotency_key=entry.get("idempotency_key"),
            )
        )
    return tuple(snapshots)


def migrate_legacy(raw_dict: dict[str, Any]) -> Checkpoint:
    """Convert a legacy unversioned checkpoint payload into a v2 :class:`Checkpoint`.

    Legacy detection is purely structural: a checkpoint is "legacy" iff it
    has no ``schema_version`` key. This matches the design rule
    "Legacy формат … определяется по отсутствию ключа ``schema_version``"
    (Req 7.6, design "Backend: Checkpoint v2 > Store rules") and makes
    migration a pure function over the parsed JSON object — no filesystem
    access, no ambient state — so it can be unit-tested with synthetic
    payloads as well as the real ``.sharrowkin/checkpoints/checkpoint_default_*.json``
    fixtures.

    Field mapping (legacy → v2), with all defaults documented inline:

    * ``session_id`` → ``session_id`` (default ``"default"``).
    * ``workspace`` → ``workspace`` (default ``"."``).
    * ``task`` → ``task`` (default ``""``).
    * ``plan_mode`` → ``plan_mode`` (default ``"autonomous"``).
    * ``current_phase`` / ``phase`` → ``current_phase`` (default
      :data:`PhaseId.OBSERVE`).
    * ``phases`` → reconstructed via :func:`_build_legacy_phases` so the
      canonical five-phase timeline is always present.
    * ``conversation_ref`` → ``conversation_ref`` (default ``""``).
    * ``in_flight_tool_calls`` → reconstructed via
      :func:`_build_legacy_tool_calls` (default empty tuple).
    * ``last_event_seq`` / ``seq`` → ``last_event_seq`` (default ``0``).
    * ``cognitive_state`` → ``cognitive_state`` (default ``{}``).
    * ``created_at`` → ``created_at`` (default current UTC ISO-8601).
    * ``expires_at`` → ``expires_at`` (default ``now + 24h`` ISO-8601).

    The function does **not** write to disk; persisting the migrated copy
    back over the legacy file is the responsibility of the calling store
    (see :meth:`CheckpointStore._load_or_migrate`), which keeps this
    function pure and side-effect free for testing.

    Args:
        raw_dict: Parsed JSON object read from a legacy checkpoint file.
            Must be a ``dict`` — callers that have only the raw JSON text
            should ``json.loads`` first.

    Returns:
        Fully-typed v2 :class:`Checkpoint` ready for :func:`serialize`.

    Raises:
        ValueError: If ``raw_dict`` is not a mapping, if it carries a
            ``schema_version`` equal to :data:`SCHEMA_VERSION` (it is
            already v2 — the caller should use :func:`deserialize`
            instead), or if it carries an unsupported non-default
            ``schema_version``.
    """

    if not isinstance(raw_dict, dict):
        raise ValueError(
            f"legacy checkpoint must be a JSON object, got {type(raw_dict).__name__}"
        )

    if "schema_version" in raw_dict:
        version = raw_dict["schema_version"]
        if version == SCHEMA_VERSION:
            raise ValueError("not a legacy checkpoint")
        raise ValueError(
            f"unsupported version: {version!r} (expected legacy / no "
            f"schema_version, or {SCHEMA_VERSION})"
        )

    session_id = str(raw_dict.get("session_id") or "default")
    workspace = str(raw_dict.get("workspace") or ".")
    task = str(raw_dict.get("task") or "")
    plan_mode = str(raw_dict.get("plan_mode") or "autonomous")

    current_phase = _coerce_legacy_phase_id(
        raw_dict.get("current_phase") or raw_dict.get("phase")
    )
    phases = _build_legacy_phases(raw_dict, current_phase)
    in_flight_tool_calls = _build_legacy_tool_calls(raw_dict)

    conversation_ref = str(raw_dict.get("conversation_ref") or "")

    raw_seq = raw_dict.get("last_event_seq", raw_dict.get("seq", 0))
    try:
        last_event_seq = int(raw_seq)
    except (TypeError, ValueError):
        last_event_seq = 0

    cognitive_state_raw = raw_dict.get("cognitive_state")
    cognitive_state: dict[str, Any] = (
        dict(cognitive_state_raw) if isinstance(cognitive_state_raw, dict) else {}
    )

    created_at = raw_dict.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        created_at = _legacy_now_iso()

    expires_at = raw_dict.get("expires_at")
    if not isinstance(expires_at, str) or not expires_at:
        expires_at = (_now_utc() + _LEGACY_TTL).isoformat()

    return Checkpoint(
        schema_version=SCHEMA_VERSION,
        session_id=session_id,
        workspace=workspace,
        task=task,
        plan_mode=plan_mode,
        current_phase=current_phase,
        phases=phases,
        conversation_ref=conversation_ref,
        in_flight_tool_calls=in_flight_tool_calls,
        last_event_seq=last_event_seq,
        cognitive_state=cognitive_state,
        created_at=created_at,
        expires_at=expires_at,
    )


# =============================================================================
# Checkpoint store (subtask 3.3)
# =============================================================================


#: Default base directory (resolved relative to cwd) for the on-disk checkpoint
#: layout. Mirrors the design doc "Backend: Checkpoint v2 > Store rules":
#: ``.sharrowkin/checkpoints/`` with a ``corrupt/`` subdirectory for files that
#: failed to deserialize and per-session ``latest_<session>.json`` pointers.
_DEFAULT_BASE_DIR: Path = Path(".sharrowkin") / "checkpoints"

#: Subdirectory within :data:`_DEFAULT_BASE_DIR` where corrupt files are
#: relocated by :meth:`CheckpointStore.quarantine`.
_CORRUPT_SUBDIR: str = "corrupt"

#: Characters that are unsafe in filenames on Windows (NTFS forbids these in
#: any filename) plus the path separators. The ISO-8601 timestamps used for
#: ``Checkpoint.created_at`` contain ``:``, which alone is enough to make a
#: file unwritable on Windows; the broader set keeps us safe across platforms.
_UNSAFE_FILENAME_CHARS: str = '<>:"/\\|?*'


def _safe_filename_part(value: str) -> str:
    """Replace filesystem-unsafe characters with ``-``.

    Used to embed an ISO-8601 timestamp into a checkpoint filename while
    staying compatible with Windows path rules (the platform constraint
    called out in the task description for this subtask). Whitespace is
    collapsed to ``_`` so the resulting name has no spaces.
    """

    cleaned: list[str] = []
    for ch in value:
        if ch in _UNSAFE_FILENAME_CHARS:
            cleaned.append("-")
        elif ch.isspace():
            cleaned.append("_")
        else:
            cleaned.append(ch)
    return "".join(cleaned)


def _now_utc() -> datetime:
    """Return the current UTC time.

    Wrapped in a helper so tests / future patches can monkey-patch a single
    call site if deterministic behaviour is needed; production code uses the
    real wall clock.
    """

    return datetime.now(timezone.utc)


def _parse_iso8601(value: str) -> datetime | None:
    """Best-effort parse of an ISO-8601 string used in checkpoint timestamps.

    Returns ``None`` on failure rather than raising — callers ( ``recoverable``
    filtering, ``prune`` sort key) treat unparseable timestamps as "fall back
    to file mtime", which is the documented behaviour for ``prune``.
    """

    if not isinstance(value, str) or not value:
        return None
    # ``fromisoformat`` accepts ``...+00:00`` natively; normalize the common
    # ``Z`` suffix used elsewhere in the system.
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


class CheckpointStore:
    """On-disk store for :class:`Checkpoint` records.

    Layout under :attr:`base_dir` (default ``.sharrowkin/checkpoints/``):

    * ``checkpoint_<session>_<created_at_safe>.json`` — primary record, one
      per :meth:`save` call.
    * ``latest_<session>.json`` — copy (not a symlink, for Windows
      compatibility — see task notes) of the most recent checkpoint for each
      session, used for fast :meth:`load_latest` reads.
    * ``corrupt/<filename>`` — files that failed to deserialize, moved here
      by :meth:`quarantine` together with a ``<filename>.reason.txt`` sibling
      describing why.

    The store is intentionally stateless beyond ``base_dir``; every operation
    re-scans the directory. That keeps it safe to use from multiple
    processes (the agent process writes; the API process may read for the
    ``GET /api/agent/sessions/recoverable`` endpoint, see task 7.4) without
    cache-coherency concerns.

    Migration of legacy unversioned files is **not** done here — that lives
    in :func:`migrate_legacy` (subtask 3.4) and is invoked by the caller
    before passing a :class:`Checkpoint` to :meth:`save`.
    """

    # ---- Construction --------------------------------------------------

    def __init__(self, base_dir: Path | None = None) -> None:
        """Initialize the store and ensure the base directory exists.

        Args:
            base_dir: Directory where checkpoint files live. ``None`` (the
                default) resolves :data:`_DEFAULT_BASE_DIR` relative to the
                current working directory, which matches how every other
                Sharrowkin component locates ``.sharrowkin/`` artifacts. A
                supplied path is used as-is so tests can pass a ``tmp_path``
                fixture without monkey-patching cwd.

        The constructor creates the directory (``parents=True``,
        ``exist_ok=True``) so callers do not need to bootstrap anything; the
        ``corrupt/`` subdirectory is created lazily on first
        :meth:`quarantine` to avoid leaving an empty directory on
        well-behaved systems.
        """

        if base_dir is None:
            base_dir = Path.cwd() / _DEFAULT_BASE_DIR
        self._base_dir: Path = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ---- Public API ----------------------------------------------------

    @property
    def base_dir(self) -> Path:
        """Resolved base directory used by this store instance."""

        return self._base_dir

    def save(self, c: Checkpoint) -> Path:
        """Persist a checkpoint and refresh the per-session ``latest_`` copy.

        Writes two files on every call:

        1. The primary record at
           ``<base_dir>/checkpoint_<session_id>_<created_at_safe>.json``,
           where ``<created_at_safe>`` is :attr:`Checkpoint.created_at` with
           filename-unsafe characters replaced. Distinct ``created_at``
           timestamps yield distinct primary files, matching the design
           rule that one session may produce many checkpoints over time.
        2. ``<base_dir>/latest_<session_id>.json`` — a **copy** of the same
           bytes, not a symlink, because :meth:`load_latest` must work on
           Windows where ``os.symlink`` requires elevated privileges.

        Args:
            c: Fully-constructed :class:`Checkpoint` to persist. The caller
                is responsible for migrating legacy payloads first
                (subtask 3.4).

        Returns:
            Absolute path to the primary checkpoint file. The ``latest_``
            companion is intentionally not returned; it is a derived view.
        """

        raw = serialize(c)
        safe_ts = _safe_filename_part(c.created_at)
        primary = self._base_dir / f"checkpoint_{c.session_id}_{safe_ts}.json"
        primary.write_text(raw, encoding="utf-8")

        # Two-step write for the ``latest_`` pointer so a crash mid-write
        # cannot leave an empty file behind that would later look like a
        # corrupt checkpoint to ``load_latest``.
        latest = self._base_dir / f"latest_{c.session_id}.json"
        tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
        tmp_latest.write_text(raw, encoding="utf-8")
        # ``Path.replace`` is atomic on POSIX and does an atomic rename on
        # Windows when the destination is on the same volume, which is
        # always the case here.
        tmp_latest.replace(latest)

        return primary

    def load_latest(self, session_id: str) -> Checkpoint | None:
        """Read the most recent checkpoint for ``session_id``.

        Returns ``None`` if there is no ``latest_<session_id>.json`` for the
        session (fresh agent / never wrote a checkpoint) **or** the file
        cannot be deserialized (and is not a recoverable legacy payload).
        In the latter case the file is moved to ``corrupt/`` via
        :meth:`quarantine` so subsequent reads do not keep stumbling over
        the same corruption — this matches the design rule "Битые файлы
        переезжают в ``.sharrowkin/checkpoints/corrupt/``".

        Legacy unversioned files (no ``schema_version`` key) are migrated
        transparently by :meth:`_load_or_migrate`: the v2 representation is
        returned to the caller and a v2 copy is written back over the same
        path so the next read is a plain :func:`deserialize` (Req 7.6).

        Args:
            session_id: Session identifier whose latest snapshot we want.

        Returns:
            The deserialized :class:`Checkpoint`, or ``None`` if missing or
            corrupt.
        """

        latest = self._base_dir / f"latest_{session_id}.json"
        if not latest.is_file():
            return None
        return self._load_or_migrate(latest)

    def list_recoverable(
        self, workspace: Path | None = None
    ) -> list[Checkpoint]:
        """Return checkpoints eligible for resume.

        Eligibility rules (Req 7.3, design "Store rules"):

        * The file matches the primary pattern ``checkpoint_*.json`` —
          ``latest_*`` pointers and anything under ``corrupt/`` are excluded
          so each logical checkpoint is considered exactly once.
        * It deserializes successfully. Files that do not are quarantined
          and skipped (so ``list_recoverable`` is also a self-healing scan).
        * ``expires_at`` parses and is strictly greater than ``now`` (UTC).
          Expired checkpoints are not eligible even if the run is otherwise
          incomplete; the design treats them as stale.
        * The run is not fully finished. We approximate this with
          "not all phases have ``status == DONE``": as soon as every phase
          row has reached ``done``, the run is effectively over and resume
          would be a no-op. This is the simplification described in the
          task wording.

        Args:
            workspace: When provided, only checkpoints whose
                :attr:`Checkpoint.workspace` equals this path string (after
                ``str``) are returned. Used by the API layer to filter the
                ``GET /api/agent/sessions/recoverable`` response to the
                workspace currently open in the IDE.

        Returns:
            List of recoverable checkpoints, in arbitrary order. Callers
            that want a specific ordering (e.g. newest first) should sort
            on :attr:`Checkpoint.created_at` themselves.
        """

        results: list[Checkpoint] = []
        now = _now_utc()
        workspace_key = (
            _workspace_key(workspace) if workspace is not None else None
        )

        for path in self._iter_primary_files():
            checkpoint = self._load_or_migrate(path)
            if checkpoint is None:
                continue

            if (
                workspace_key is not None
                and _workspace_key(checkpoint.workspace) != workspace_key
            ):
                continue

            expires_at = _parse_iso8601(checkpoint.expires_at)
            if expires_at is None or expires_at <= now:
                continue

            # "All phases done" → run is over, not a resume candidate.
            if checkpoint.phases and all(
                p.status == PhaseStatus.DONE for p in checkpoint.phases
            ):
                continue

            results.append(checkpoint)

        return results

    def quarantine(self, path: Path, reason: str) -> Path:
        """Move a corrupt checkpoint file into ``corrupt/`` for post-mortem.

        Beside the relocated file we write ``<filename>.reason.txt`` so an
        operator inspecting ``corrupt/`` later can tell *why* a particular
        snapshot was rejected without re-running the deserializer.

        If a file with the same name already exists under ``corrupt/`` (for
        example because the same session keeps writing the same bad latest
        pointer over multiple restarts), a ``-<n>`` suffix is appended so
        the original record is preserved rather than overwritten.

        Args:
            path: Path to the file to quarantine. Need not be inside
                :attr:`base_dir` — this method handles arbitrary inputs so
                the caller (e.g. :meth:`load_latest`) does not have to
                resolve paths first.
            reason: Human-readable explanation written to the sidecar
                ``.reason.txt`` file. Typically the ``str(exc)`` of the
                exception that triggered quarantine.

        Returns:
            Final path of the moved file inside the ``corrupt/`` directory.
        """

        corrupt_dir = self._base_dir / _CORRUPT_SUBDIR
        corrupt_dir.mkdir(parents=True, exist_ok=True)

        target = corrupt_dir / path.name
        # Avoid clobbering pre-existing quarantined files; pick the first
        # free ``<stem>-<n><suffix>``.
        if target.exists():
            stem, suffix = target.stem, target.suffix
            counter = 1
            while True:
                candidate = corrupt_dir / f"{stem}-{counter}{suffix}"
                if not candidate.exists():
                    target = candidate
                    break
                counter += 1

        # ``shutil.move`` works across volumes (falls back to copy+delete);
        # ``Path.replace`` would fail in that situation. The file may also
        # have been removed underneath us; treat that as already-quarantined
        # and just write the reason sidecar.
        if path.exists():
            shutil.move(str(path), str(target))

        reason_path = target.with_name(target.name + ".reason.txt")
        try:
            reason_path.write_text(reason, encoding="utf-8")
        except OSError:
            # Sidecar is best-effort; do not fail quarantine if it cannot be
            # written (e.g. permission issue on a read-only filesystem).
            pass

        return target

    def prune(
        self, workspace: Path | None = None, keep: int = 50
    ) -> int:
        """Delete oldest primary checkpoints beyond ``keep``.

        Mirrors the design rule "при создании нового checkpoint считаем все
        файлы для текущего workspace, отсортированные по ``created_at``, и
        удаляем старше 50-го" (Req 7.7). This method is idempotent — running
        it twice in a row deletes files only on the first call.

        Sort key:

        * Preferred: :attr:`Checkpoint.created_at` parsed via ISO-8601, so
          chronological order across machines/timezones is consistent.
        * Fallback: file mtime, used when a file cannot be deserialized
          (e.g. mid-write or partial corruption). The fallback ensures
          ``prune`` never silently skips files just because they could not
          be parsed; pairing this with quarantine on read keeps the
          directory eventually consistent.

        Args:
            workspace: When provided, only checkpoints whose ``workspace``
                field matches are considered (and only those are eligible
                for deletion). Useful when one ``.sharrowkin/`` directory
                serves multiple projects.
            keep: Number of newest checkpoints to retain. Must be ``>= 0``.

        Returns:
            Number of files deleted. Latest-pointer files (``latest_*``)
            and quarantined files (``corrupt/``) are never touched.
        """

        if keep < 0:
            raise ValueError(f"keep must be non-negative, got {keep}")

        workspace_key = (
            _workspace_key(workspace) if workspace is not None else None
        )

        # ``(sort_key, path)`` pairs. ``sort_key`` is a string for parseable
        # ISO timestamps (lexicographic order matches chronological order),
        # otherwise a float of file mtime. We tag with a kind prefix so
        # parseable and unparseable entries sort consistently relative to
        # each other (parseable timestamps always win as "newer" when they
        # share an instant — they carry more information).
        candidates: list[tuple[tuple[int, float | str], Path]] = []
        for path in self._iter_primary_files():
            try:
                raw = path.read_text(encoding="utf-8")
                checkpoint = deserialize(raw)
            except (OSError, ValueError):
                checkpoint = None

            if checkpoint is not None:
                if (
                    workspace_key is not None
                    and _workspace_key(checkpoint.workspace) != workspace_key
                ):
                    continue
                parsed = _parse_iso8601(checkpoint.created_at)
                if parsed is not None:
                    sort_key: tuple[int, float | str] = (
                        1,
                        parsed.isoformat(),
                    )
                else:
                    sort_key = (0, _safe_mtime(path))
            else:
                # Cannot read the file — if a workspace filter is active we
                # cannot prove this file belongs to that workspace, so we
                # must skip it. Without a filter we still consider it for
                # pruning so corrupt files do not perpetually consume slots.
                if workspace_key is not None:
                    continue
                sort_key = (0, _safe_mtime(path))

            candidates.append((sort_key, path))

        # Sort newest-last so that ``[-keep:]`` selects the most recent.
        candidates.sort(key=lambda pair: pair[0])

        if keep >= len(candidates):
            return 0

        to_delete = candidates[: len(candidates) - keep]
        deleted = 0
        for _, path in to_delete:
            try:
                path.unlink()
                deleted += 1
            except FileNotFoundError:
                # Already gone (concurrent prune from another process); not
                # an error.
                continue
            except OSError:
                # Do not abort the whole prune on one stuck file; just skip.
                continue
        return deleted

    # ---- Internal helpers ---------------------------------------------

    def _load_or_migrate(self, path: Path) -> Checkpoint | None:
        """Read a checkpoint file, migrating legacy payloads in place.

        Resolution order:

        1. Attempt :func:`deserialize` directly. Success path for any v2
           file already on disk — returned as-is.
        2. If deserialization fails *only* because the payload is missing
           ``schema_version`` (i.e. it is a legacy unversioned record),
           parse the JSON, run :func:`migrate_legacy`, write the v2
           serialization back over the same path so the next read is a
           plain ``deserialize``, and return the migrated checkpoint
           (Req 7.6, design "Backend: Checkpoint v2 > Store rules").
        3. For any other failure (invalid JSON, unsupported non-default
           ``schema_version``, OS error, migration error), the file is
           quarantined via :meth:`quarantine` and ``None`` is returned —
           same behaviour as a corrupt v2 file.

        The "write migrated copy back" step is done via
        :meth:`Path.replace` of a ``.tmp`` sibling so a crash mid-write
        cannot leave the file half-overwritten and unreadable. If the
        write itself fails (read-only filesystem, permission error), the
        in-memory migrated :class:`Checkpoint` is still returned — losing
        the cache write is preferable to refusing to resume.

        Args:
            path: Concrete file to read. Both ``latest_*`` pointers and
                primary records flow through here, since both shapes can
                be either v2 or legacy on disk.

        Returns:
            A :class:`Checkpoint` if the file is readable as v2 or
            migratable from legacy, otherwise ``None`` (file already
            quarantined).
        """

        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            self.quarantine(path, f"_load_or_migrate read failed: {exc}")
            return None

        # Fast path: already v2.
        try:
            return deserialize(raw_text)
        except ValueError:
            # Fall through to legacy detection below. We deliberately do
            # not catch the wider ``Exception`` — anything other than a
            # schema/JSON ValueError is a bug in deserialize and should
            # surface.
            pass

        # Either legacy (no ``schema_version``) or genuinely corrupt.
        try:
            payload = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            self.quarantine(path, f"_load_or_migrate invalid JSON: {exc}")
            return None

        if not isinstance(payload, dict):
            self.quarantine(
                path,
                "_load_or_migrate root is not a JSON object: "
                f"{type(payload).__name__}",
            )
            return None

        if "schema_version" in payload:
            # Present but not equal to SCHEMA_VERSION — unsupported version,
            # not a legacy payload. Treat as corrupt.
            self.quarantine(
                path,
                f"_load_or_migrate unsupported schema_version: "
                f"{payload['schema_version']!r}",
            )
            return None

        try:
            migrated = migrate_legacy(payload)
        except ValueError as exc:
            self.quarantine(path, f"_load_or_migrate migration failed: {exc}")
            return None

        # Persist the migrated v2 form back over the same path so we never
        # re-do the migration on the next read. Best-effort: failure here
        # is logged into the file's parent only via the resulting
        # exception flow, and we still return ``migrated`` to the caller.
        try:
            new_raw = serialize(migrated)
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(new_raw, encoding="utf-8")
            tmp.replace(path)
        except OSError:
            # Read-only filesystem or transient write error — keep going
            # with the in-memory result.
            pass

        return migrated

    def _iter_primary_files(self) -> list[Path]:
        """Return all ``checkpoint_*.json`` primary records.

        Excludes:

        * ``latest_*.json`` pointers (handled separately by
          :meth:`load_latest` / :meth:`save`).
        * Anything under the ``corrupt/`` subdirectory — those have already
          been triaged and must not be reconsidered as live checkpoints.
        * Temporary write files (``.tmp``).

        Returned as a list rather than a generator so the directory handle
        is closed before callers begin doing potentially-mutating work
        (delete, move) on the entries.
        """

        if not self._base_dir.is_dir():
            return []
        results: list[Path] = []
        corrupt_dir = self._base_dir / _CORRUPT_SUBDIR
        for entry in self._base_dir.iterdir():
            if not entry.is_file():
                continue
            name = entry.name
            if not name.startswith("checkpoint_") or not name.endswith(".json"):
                continue
            # ``Path.iterdir`` does not recurse, but be defensive: explicitly
            # skip anything that resolved into the corrupt directory just in
            # case symlinks or junctions are involved.
            try:
                if corrupt_dir in entry.resolve().parents:
                    continue
            except OSError:
                # ``resolve()`` can fail on broken symlinks; treat such
                # entries as not-our-files and skip.
                continue
            results.append(entry)
        return results


def _safe_mtime(path: Path) -> float:
    """File mtime, or ``0.0`` if the file cannot be stat'd.

    Used as the fallback sort key in :meth:`CheckpointStore.prune` when a
    checkpoint's ``created_at`` cannot be parsed. Returning ``0.0`` rather
    than raising lets such files sort to the front (oldest) so they are
    pruned first, which is the desired behaviour for unreadable artifacts.
    """

    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _workspace_key(value: str | Path) -> str:
    """Normalize a workspace identifier for equality comparison.

    Checkpoints stored on disk may use either ``/`` or ``\\`` separators
    depending on which OS produced them, so we collapse both to ``/`` and
    strip a trailing separator before comparison. This makes
    ``Path("C:/proj")``, ``"C:/proj"``, ``"C:\\proj"`` and ``"C:/proj/"``
    all equivalent — which matches user intent when filtering by the
    workspace currently open in the IDE.
    """

    raw = str(value).replace("\\", "/")
    if raw.endswith("/") and len(raw) > 1:
        raw = raw.rstrip("/")
    return raw

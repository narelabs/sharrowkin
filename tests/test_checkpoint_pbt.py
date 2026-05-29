"""Property-based round-trip tests for ``agent.checkpoints``.

Covers task 3.5 of spec ``ui-and-agent-stabilization``:

* **Property 3 (Round-trip):** ``deserialize(serialize(c)) == c`` holds for
  every valid :class:`Checkpoint`. This is the headline contract from the
  design doc — the resume code path reads back exactly what the run-loop
  wrote, with no field drift.
* **Idempotent serialization:** ``serialize(deserialize(serialize(c)))``
  equals ``serialize(c)`` byte-for-byte. Combined with the round-trip
  property this proves the on-disk form is canonical (sorted keys, stable
  enum encoding) so checkpoint files are diffable across machines.
* **Output is valid JSON:** ``serialize(c)`` always produces parseable JSON
  with a top-level object. This guards against a regression where someone
  swaps ``json.dumps`` for a non-JSON encoder; without it, the round-trip
  alone could pass via a custom format.

The strategies are intentionally narrow:

* Timestamps are derived from a bounded integer epoch via
  ``datetime.fromtimestamp(...).isoformat()``, which guarantees well-formed
  ISO-8601 output without depending on platform-specific datetime ranges.
* Strings are non-empty, printable Unicode, capped at 64 characters — long
  enough to exercise UTF-8 paths but short enough to keep the example
  budget useful.
* ``cognitive_state`` is restricted to JSON-safe primitives (``None``,
  ``bool``, finite numbers, strings) so round-trip equality is bit-exact;
  the cognitive subsystem owns the actual shape and only requires JSON
  survivability here.
* ``Checkpoint.phases`` always contains all five phases in canonical
  ``PhaseId`` order — that is the structural invariant the rest of the
  system relies on. Per-phase status and timestamps are randomised
  independently.
* ``schema_version`` is fixed to :data:`SCHEMA_VERSION`; mismatched
  versions are tested directly in the unit tests for ``deserialize`` rather
  than here, where they would only generate uninteresting failures.

Validates: Requirements 13.3, Property 3
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from agent.checkpoints import (
    SCHEMA_VERSION,
    Checkpoint,
    CheckpointPhase,
    ToolCallSnapshot,
    deserialize,
    serialize,
)
from agent.event_stream import PhaseId, PhaseStatus, ToolCallStatus


# ---------------------------------------------------------------------------
# Primitive strategies
# ---------------------------------------------------------------------------

# Bounded epoch range: 1970-01-01 .. 2100-01-01. Wide enough to surface any
# year-formatting issues, narrow enough to avoid platform-specific overflow
# in ``datetime.fromtimestamp`` on Windows.
_EPOCH_MIN: int = 0
_EPOCH_MAX: int = 4_102_444_800


def _iso_from_epoch(seconds: int) -> str:
    """Convert a UTC epoch second to an ISO-8601 string.

    Centralised so every timestamp in the test corpus uses the same format
    (with ``+00:00`` offset). The deserializer accepts any ISO-8601 input,
    so we deliberately pick the form that exercises both ``datetime`` and
    JSON encoding paths.
    """

    return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()


iso_timestamps: st.SearchStrategy[str] = st.integers(
    min_value=_EPOCH_MIN, max_value=_EPOCH_MAX
).map(_iso_from_epoch)

iso_timestamps_or_none: st.SearchStrategy[str | None] = st.one_of(
    st.none(), iso_timestamps
)

# Printable Unicode, no surrogates (those break JSON), capped to 64 chars.
# The blacklist on category ``Cs`` (Surrogate) is what stops Hypothesis from
# producing lone surrogate halves that ``json.dumps`` would refuse to encode.
non_empty_text: st.SearchStrategy[str] = st.text(
    alphabet=st.characters(
        blacklist_categories=("Cs",),
        min_codepoint=32,
        max_codepoint=0x10FFFF,
    ),
    min_size=1,
    max_size=64,
)

optional_text: st.SearchStrategy[str | None] = st.one_of(st.none(), non_empty_text)


# ---------------------------------------------------------------------------
# ToolCallSnapshot strategy
# ---------------------------------------------------------------------------

# Stick to the enum values for ``status``: free strings would also survive
# the round-trip (``ToolCallSnapshot.status`` is typed ``ToolCallStatus | str``
# precisely for that reason), but they are tested in the dedicated unit
# tests for ``_coerce_tool_call_status``. The enum-only path mirrors how
# real agent code constructs snapshots.
tool_call_statuses: st.SearchStrategy[ToolCallStatus] = st.sampled_from(
    list(ToolCallStatus)
)

tool_call_snapshots: st.SearchStrategy[ToolCallSnapshot] = st.builds(
    ToolCallSnapshot,
    tool_id=non_empty_text,
    name=non_empty_text,
    status=tool_call_statuses,
    started_at=iso_timestamps_or_none,
    completed_at=iso_timestamps_or_none,
    error=optional_text,
    idempotency_key=optional_text,
)


# ---------------------------------------------------------------------------
# CheckpointPhase strategy (per-phase, pinned id)
# ---------------------------------------------------------------------------

phase_statuses: st.SearchStrategy[PhaseStatus] = st.sampled_from(list(PhaseStatus))


def _phase_for(phase_id: PhaseId) -> st.SearchStrategy[CheckpointPhase]:
    """Strategy producing a :class:`CheckpointPhase` pinned to ``phase_id``.

    Used by :func:`checkpoints` to assemble the canonical 5-tuple of phases
    in :data:`PhaseId` declaration order. Pinning the id (rather than
    sampling it) guarantees the structural invariant
    ``[p.id for p in c.phases] == list(PhaseId)`` without needing a
    rejection filter.
    """

    return st.builds(
        CheckpointPhase,
        id=st.just(phase_id),
        status=phase_statuses,
        started_at=iso_timestamps_or_none,
        completed_at=iso_timestamps_or_none,
        error=optional_text,
    )


# ---------------------------------------------------------------------------
# cognitive_state strategy
# ---------------------------------------------------------------------------

# JSON-safe primitives only. Floats are constrained to finite IEEE-754
# values; ``allow_nan=False, allow_infinity=False`` keeps us inside the
# JSON spec where ``json.dumps(..., allow_nan=False)`` would refuse anyway.
# Integer width is capped at 32 bits to stay well clear of any platform-
# specific JSON int handling, even though Python's ``json`` is unbounded.
json_primitives: st.SearchStrategy[object] = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(2**31), max_value=2**31 - 1),
    st.floats(allow_nan=False, allow_infinity=False, width=64),
    non_empty_text,
)

cognitive_states: st.SearchStrategy[dict[str, object]] = st.dictionaries(
    keys=non_empty_text,
    values=json_primitives,
    max_size=5,
)


# ---------------------------------------------------------------------------
# Top-level Checkpoint strategy
# ---------------------------------------------------------------------------


@st.composite
def checkpoints(draw: st.DrawFn) -> Checkpoint:
    """Generate a valid :class:`Checkpoint` with all five phases in canonical order.

    The strategy fixes ``schema_version`` to :data:`SCHEMA_VERSION` because
    that is the only version the deserializer accepts; mismatched-version
    handling has dedicated unit tests. Every other field is drawn
    independently:

    * ``phases``: 5-tuple in :data:`PhaseId` declaration order with random
      per-phase status and timestamps.
    * ``current_phase``: any of the five (not constrained to match a
      "running" entry, since the deserializer treats the field as opaque).
    * ``in_flight_tool_calls``: 0..4 snapshots — empty is the common case
      during idle phases, larger counts exercise tuple round-tripping.
    * ``cognitive_state``: small dict of JSON primitives.
    * ``created_at`` / ``expires_at``: independently drawn ISO-8601
      strings; the deserializer does not validate the relationship between
      them, that is the store's job.
    """

    phases = tuple(draw(_phase_for(pid)) for pid in PhaseId)

    return Checkpoint(
        schema_version=SCHEMA_VERSION,
        session_id=draw(non_empty_text),
        workspace=draw(non_empty_text),
        task=draw(non_empty_text),
        plan_mode=draw(non_empty_text),
        current_phase=draw(st.sampled_from(list(PhaseId))),
        phases=phases,
        # ``conversation_ref`` may be empty per the legacy migration path
        # (default ``""``), so the strategy permits empty strings here.
        conversation_ref=draw(st.text(max_size=64)),
        in_flight_tool_calls=tuple(
            draw(st.lists(tool_call_snapshots, max_size=4))
        ),
        last_event_seq=draw(st.integers(min_value=0, max_value=2**31 - 1)),
        cognitive_state=draw(cognitive_states),
        created_at=draw(iso_timestamps),
        expires_at=draw(iso_timestamps),
    )


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------


@given(c=checkpoints())
@settings(deadline=None, max_examples=50)
def test_serialize_deserialize_roundtrip(c: Checkpoint) -> None:
    """``deserialize(serialize(c)) == c`` for every valid :class:`Checkpoint`.

    This is the headline property from the design doc: the resume path must
    reconstruct the exact run-state that was persisted, with all enum
    fields, tuple shapes and nested dataclasses intact.

    Validates: Requirements 13.3, Property 3
    """

    restored = deserialize(serialize(c))
    assert restored == c


@given(c=checkpoints())
@settings(deadline=None, max_examples=50)
def test_serialize_is_idempotent(c: Checkpoint) -> None:
    """``serialize(deserialize(serialize(c))) == serialize(c)`` byte-for-byte.

    Combined with the round-trip property, this proves the encoding is
    canonical: no information is lost on either leg, and the second
    encode produces exactly the same bytes as the first. Sorted JSON keys
    and stable enum-value encoding are the load-bearing parts here.

    Validates: Requirements 13.3, Property 3
    """

    raw = serialize(c)
    again = serialize(deserialize(raw))
    assert again == raw


@given(c=checkpoints())
@settings(deadline=None, max_examples=50)
def test_serialize_emits_valid_json(c: Checkpoint) -> None:
    """``serialize(c)`` always emits text parseable as a JSON object.

    Guards against a future regression where the encoder is swapped for a
    non-JSON format that still happens to round-trip; checkpoint files are
    contractually JSON so external tooling (jq, log shippers, the API
    layer) can read them without a custom parser.

    Validates: Requirements 13.3, Property 3
    """

    raw = serialize(c)
    payload = json.loads(raw)
    assert isinstance(payload, dict)
    assert payload["schema_version"] == SCHEMA_VERSION

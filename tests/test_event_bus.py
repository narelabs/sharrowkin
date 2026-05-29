"""Unit tests for ``agent.event_stream.EventBus``.

Covers task 1.3 of spec ``ui-and-agent-stabilization``:

* monotonic per-session ``seq`` allocation across mixed helper / generic emits,
* payload validation: passing the wrong payload model produces a
  ``schema_violation`` log instead of throwing,
* unknown ``type`` via :meth:`EventBus.emit` produces a ``schema_violation`` log
  with ``code="schema_violation"`` and ``rejected_type`` in details,
* envelope shape: ``v=1``, ``session_id`` pass-through, ``seq`` is the assigned
  monotonic number, ``ts`` is ISO-8601, ``payload`` is a JSON-compatible dict,
* empty ``session_id`` raises :class:`ValueError` from the constructor,
* helper-specific tests for ``phase_change``, ``status``, ``thinking``,
  ``tool_call``, ``log``, ``heartbeat``, ``agent_complete``: a malformed
  argument falls through to a ``schema_violation`` log without raising,
* concurrency: two concurrent emits never produce duplicate or out-of-order
  ``seq`` numbers.

Validates: Requirements 8.1, 8.2, 13.4
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Mapping

import pytest

from agent.event_stream import (
    AgentOutcome,
    AgentStatus,
    EventBus,
    LogLevel,
    PhaseChangePayload,
    PhaseId,
    PhaseStatus,
    SCHEMA_VERSION,
    ToolCallStatus,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class RecordingSink:
    """Async sink that records every envelope it receives.

    Mirrors the contract of ``EventSink`` (an async callable taking a JSON-
    compatible mapping) so it can be passed directly to ``EventBus(...)``.
    """

    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []

    async def __call__(self, envelope: Mapping[str, Any]) -> None:
        # Copy so later mutations by the caller (none expected) cannot affect
        # the recorded snapshot.
        self.envelopes.append(dict(envelope))


_ISO_8601_Z = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


def _assert_envelope_shape(
    envelope: Mapping[str, Any],
    *,
    session_id: str,
    seq: int,
    type_: str,
) -> None:
    """Assert the basic invariants every envelope must satisfy."""

    assert envelope["v"] == SCHEMA_VERSION
    assert envelope["v"] == 1
    assert envelope["session_id"] == session_id
    assert envelope["seq"] == seq
    assert envelope["type"] == type_

    ts = envelope["ts"]
    assert isinstance(ts, str)
    assert _ISO_8601_Z.match(ts), f"ts is not ISO-8601: {ts!r}"
    # Must round-trip through datetime.fromisoformat (Z normalized).
    candidate = ts.replace("Z", "+00:00") if ts.endswith("Z") else ts
    datetime.fromisoformat(candidate)

    payload = envelope["payload"]
    assert isinstance(payload, dict)
    # JSON-compatible: round-trip via json.dumps/loads should not raise.
    assert json.loads(json.dumps(payload)) == payload


def _last_log(envelopes: list[dict[str, Any]]) -> dict[str, Any]:
    for env in reversed(envelopes):
        if env["type"] == "log":
            return env
    raise AssertionError("no log envelope found")


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestEventBusConstructor:
    """Constructor preconditions."""

    def test_empty_session_id_raises(self) -> None:
        async def sink(_: Mapping[str, Any]) -> None:  # pragma: no cover - unused
            return None

        with pytest.raises(ValueError):
            EventBus("", sink)

    def test_session_id_property_is_fixed(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_xyz", sink)
        assert bus.session_id == "session_xyz"
        assert bus.next_seq == 0


# ---------------------------------------------------------------------------
# Monotonic seq + envelope shape
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestMonotonicSeqAndEnvelope:
    """``seq`` is monotonic across all emits and envelopes have the right shape."""

    async def test_seq_is_monotonic_across_helpers_and_emit(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_mono", sink)

        await bus.phase_change(PhaseId.OBSERVE, PhaseStatus.RUNNING)
        await bus.status(AgentStatus.RUNNING, message="kicked off")
        await bus.thinking("partial 1", delta=True)
        await bus.tool_call("tool-1", "run_pytest", ToolCallStatus.RUNNING)
        await bus.log(LogLevel.INFO, "tool started", code="tool_started")
        await bus.heartbeat()
        await bus.emit(
            "phase_change",
            {"phase": "recall", "status": "running"},
        )
        await bus.agent_complete(AgentOutcome.DONE, runtime_ms=1234)

        assert len(sink.envelopes) == 8
        seqs = [env["seq"] for env in sink.envelopes]
        assert seqs == list(range(8))
        assert bus.next_seq == 8

        for i, env in enumerate(sink.envelopes):
            _assert_envelope_shape(
                env, session_id="session_mono", seq=i, type_=env["type"]
            )

    async def test_envelope_shape_for_phase_change(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_shape", sink)

        await bus.phase_change(
            PhaseId.REASON, PhaseStatus.DONE, reason="finished"
        )

        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        _assert_envelope_shape(
            env, session_id="session_shape", seq=0, type_="phase_change"
        )
        # Payload is a plain dict with the right enum string values.
        assert env["payload"] == {
            "phase": "reason",
            "status": "done",
            "reason": "finished",
        }

    async def test_seq_does_not_advance_on_validation_failure_then_logs(self) -> None:
        """Schema violation produces a log; ``seq`` is still consumed by the log."""

        sink = RecordingSink()
        bus = EventBus("session_seqv", sink)

        await bus.phase_change(PhaseId.OBSERVE, PhaseStatus.RUNNING)
        # Invalid payload -> falls through to a ``log`` event.
        await bus.emit("phase_change", {"phase": "not_a_phase", "status": "running"})
        await bus.phase_change(PhaseId.OBSERVE, PhaseStatus.DONE)

        assert len(sink.envelopes) == 3
        assert [e["seq"] for e in sink.envelopes] == [0, 1, 2]
        assert sink.envelopes[1]["type"] == "log"
        assert sink.envelopes[1]["payload"]["code"] == "schema_violation"


# ---------------------------------------------------------------------------
# Payload validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPayloadValidation:
    """Validation errors are converted to ``schema_violation`` logs, not raises."""

    async def test_unknown_type_emits_schema_violation_log(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_unknown", sink)

        await bus.emit("definitely_not_a_real_type", {"foo": "bar"})

        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        _assert_envelope_shape(
            env, session_id="session_unknown", seq=0, type_="log"
        )
        payload = env["payload"]
        assert payload["level"] == "error"
        assert payload["code"] == "schema_violation"
        assert payload["details"]["rejected_type"] == "definitely_not_a_real_type"
        assert payload["details"]["error"] == "KeyError"

    async def test_wrong_payload_model_class_emits_schema_violation(self) -> None:
        """Passing a payload model that does not match ``type`` is rejected."""

        sink = RecordingSink()
        bus = EventBus("session_wrong_cls", sink)

        # Build a valid PhaseChangePayload, then submit it under "status" type.
        wrong = PhaseChangePayload(phase=PhaseId.OBSERVE, status=PhaseStatus.RUNNING)
        await bus.emit("status", wrong)

        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        assert env["type"] == "log"
        assert env["payload"]["code"] == "schema_violation"
        assert env["payload"]["details"]["rejected_type"] == "status"
        assert env["payload"]["details"]["error"] == "TypeError"

    async def test_invalid_payload_dict_emits_schema_violation(self) -> None:
        """Missing required field -> ``ValidationError`` -> log, no raise."""

        sink = RecordingSink()
        bus = EventBus("session_invalid_dict", sink)

        # ``phase_change`` requires both ``phase`` and ``status``; omit ``status``.
        await bus.emit("phase_change", {"phase": "observe"})

        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        assert env["type"] == "log"
        assert env["payload"]["code"] == "schema_violation"
        assert env["payload"]["details"]["rejected_type"] == "phase_change"
        # pydantic raises ValidationError, the bus captures the class name.
        assert env["payload"]["details"]["error"] == "ValidationError"

    async def test_extra_fields_are_rejected_as_schema_violation(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_extra", sink)

        await bus.emit(
            "heartbeat",
            {"agent_alive": True, "unexpected": "field"},
        )

        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        assert env["type"] == "log"
        assert env["payload"]["code"] == "schema_violation"
        assert env["payload"]["details"]["rejected_type"] == "heartbeat"


# ---------------------------------------------------------------------------
# Helpers degrade gracefully on bad arguments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHelpersDegradeOnBadArguments:
    """Each typed helper falls through to ``schema_violation`` cleanly."""

    async def _expect_schema_violation(
        self,
        sink: RecordingSink,
        *,
        rejected_type: str,
    ) -> None:
        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        assert env["type"] == "log"
        assert env["payload"]["code"] == "schema_violation"
        assert env["payload"]["level"] == "error"
        assert env["payload"]["details"]["rejected_type"] == rejected_type

    async def test_phase_change_with_bogus_phase(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_phase", sink)

        await bus.phase_change("nonsense_phase", PhaseStatus.RUNNING)

        await self._expect_schema_violation(sink, rejected_type="phase_change")

    async def test_status_with_bogus_status(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_status", sink)

        await bus.status("not_a_status")

        await self._expect_schema_violation(sink, rejected_type="status")

    async def test_thinking_with_non_string_text(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_thinking", sink)

        # text=None is invalid (must be ``str``).
        await bus.thinking(None)  # type: ignore[arg-type]

        await self._expect_schema_violation(sink, rejected_type="thinking")

    async def test_tool_call_with_bogus_status(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_tool", sink)

        await bus.tool_call("tool-1", "run_pytest", "not_a_tool_status")

        await self._expect_schema_violation(sink, rejected_type="tool_call")

    async def test_log_with_bogus_level(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_log", sink)

        await bus.log("not_a_level", "something happened")

        await self._expect_schema_violation(sink, rejected_type="log")

    async def test_heartbeat_with_bogus_alive(self) -> None:
        """``agent_alive`` is typed as ``bool``; pydantic strict on extras only.

        Pydantic v2 coerces many values to bool, so we instead force a failure
        by going through the generic ``emit`` to assert the log path. The
        helper itself, however, is verified to succeed normally below.
        """

        sink = RecordingSink()
        bus = EventBus("session_h_hb", sink)

        # Non-bool, non-coercible value triggers a ValidationError.
        await bus.emit("heartbeat", {"agent_alive": object()})

        await self._expect_schema_violation(sink, rejected_type="heartbeat")

    async def test_heartbeat_helper_normal_path(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_hb_ok", sink)

        await bus.heartbeat()

        assert len(sink.envelopes) == 1
        env = sink.envelopes[0]
        _assert_envelope_shape(
            env, session_id="session_h_hb_ok", seq=0, type_="heartbeat"
        )
        assert env["payload"] == {"agent_alive": True}

    async def test_agent_complete_with_bogus_outcome(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_complete", sink)

        await bus.agent_complete("not_an_outcome", runtime_ms=10)

        await self._expect_schema_violation(sink, rejected_type="agent_complete")

    async def test_agent_complete_with_negative_runtime(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_h_neg_rt", sink)

        # ``runtime_ms`` is NonNegativeInt; -1 must be rejected.
        await bus.agent_complete(AgentOutcome.DONE, runtime_ms=-1)

        await self._expect_schema_violation(sink, rejected_type="agent_complete")


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConcurrency:
    """Concurrent emits must not interleave seq allocation."""

    async def test_concurrent_emits_have_unique_ordered_seqs(self) -> None:
        sink = RecordingSink()
        bus = EventBus("session_concurrent", sink)

        # Mix helpers and generic emits, all scheduled concurrently.
        async def helper_phase(i: int) -> None:
            status = PhaseStatus.RUNNING if i % 2 == 0 else PhaseStatus.DONE
            await bus.phase_change(PhaseId.OBSERVE, status, reason=f"r{i}")

        async def helper_thinking(i: int) -> None:
            await bus.thinking(f"chunk-{i}", delta=True)

        async def generic(i: int) -> None:
            await bus.emit("heartbeat", {"agent_alive": True})

        tasks = []
        n = 30
        for i in range(n):
            if i % 3 == 0:
                tasks.append(asyncio.create_task(helper_phase(i)))
            elif i % 3 == 1:
                tasks.append(asyncio.create_task(helper_thinking(i)))
            else:
                tasks.append(asyncio.create_task(generic(i)))

        await asyncio.gather(*tasks)

        assert len(sink.envelopes) == n
        seqs = [env["seq"] for env in sink.envelopes]

        # Unique and exactly the contiguous 0..n-1 set.
        assert len(set(seqs)) == n
        assert sorted(seqs) == list(range(n))
        # Sink received them in seq order (lock guarantees it).
        assert seqs == list(range(n))
        assert bus.next_seq == n

    async def test_seq_continues_monotonic_after_schema_violation(self) -> None:
        """Even when violations interleave with valid events, seq stays unique."""

        sink = RecordingSink()
        bus = EventBus("session_mixed", sink)

        async def good() -> None:
            await bus.phase_change(PhaseId.OBSERVE, PhaseStatus.RUNNING)

        async def bad_unknown() -> None:
            await bus.emit("nope", {"x": 1})

        async def bad_payload() -> None:
            await bus.emit("phase_change", {"phase": "nope", "status": "running"})

        tasks = [
            asyncio.create_task(good()),
            asyncio.create_task(bad_unknown()),
            asyncio.create_task(good()),
            asyncio.create_task(bad_payload()),
            asyncio.create_task(good()),
        ]
        await asyncio.gather(*tasks)

        # Each call produced exactly one envelope (good -> phase_change,
        # bad -> log).
        assert len(sink.envelopes) == 5
        seqs = [env["seq"] for env in sink.envelopes]
        assert sorted(seqs) == [0, 1, 2, 3, 4]
        assert bus.next_seq == 5

        # Exactly two of them are schema_violation logs.
        violations = [
            e for e in sink.envelopes
            if e["type"] == "log" and e["payload"]["code"] == "schema_violation"
        ]
        assert len(violations) == 2

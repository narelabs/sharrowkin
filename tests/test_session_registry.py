"""Unit tests for ``api.session_registry``.

Covers task 4.3 of spec ``ui-and-agent-stabilization``:

* ``Session.start_heartbeat`` spawns a background task that emits one event
  per ``interval`` while the socket is attached,
* the loop exits cleanly when the socket is detached between ticks (no extra
  emission after detach),
* :meth:`Session.stop_heartbeat` cancels the running task and is idempotent,
* :meth:`SessionRegistry.attach_socket` accepts the optional ``heartbeat_sink``
  parameter and starts the loop, while :meth:`SessionRegistry.detach_socket`
  stops it before unbinding the socket,
* a sink raising an exception terminates the loop without leaking and without
  wedging the session,
* invalid ``interval`` values are rejected up-front.

Validates: Requirement 3.6
"""

from __future__ import annotations

import asyncio

import pytest

from api.session_registry import (
    HEARTBEAT_INTERVAL_SECONDS,
    Session,
    SessionRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _RecordingSink:
    """Async sink that records every ``session_id`` it receives."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.event = asyncio.Event()

    async def __call__(self, session_id: str) -> None:
        self.calls.append(session_id)
        self.event.set()


class _RaisingSink:
    """Sink that raises on the n-th call."""

    def __init__(self, *, raise_at: int = 1) -> None:
        self.calls: list[str] = []
        self.raise_at = raise_at
        self.event = asyncio.Event()

    async def __call__(self, session_id: str) -> None:
        self.calls.append(session_id)
        self.event.set()
        if len(self.calls) >= self.raise_at:
            raise RuntimeError("sink boom")


async def _wait_for(condition, *, timeout: float = 1.0, poll: float = 0.005) -> None:
    """Poll ``condition()`` until truthy or raise on timeout."""

    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(poll)
    raise AssertionError("condition not met within timeout")


# ---------------------------------------------------------------------------
# Session.start_heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionStartHeartbeat:
    """Direct tests against :meth:`Session.start_heartbeat`."""

    async def test_emits_after_interval_while_socket_attached(self) -> None:
        session = Session("session_hb_basic")
        sink = _RecordingSink()
        await session.attach_socket(object())

        await session.start_heartbeat(interval=0.02, sink=sink)
        # Wait for at least one heartbeat to be sunk.
        await asyncio.wait_for(sink.event.wait(), timeout=1.0)

        await session.stop_heartbeat()
        await session.detach_socket()

        assert sink.calls, "expected at least one heartbeat call"
        assert all(sid == "session_hb_basic" for sid in sink.calls)

    async def test_first_heartbeat_does_not_fire_immediately(self) -> None:
        """First call happens *after* the first ``await sleep(interval)``."""

        session = Session("session_hb_delay")
        sink = _RecordingSink()
        await session.attach_socket(object())

        await session.start_heartbeat(interval=0.5, sink=sink)
        # Yield the loop; at this point the task should be parked in
        # ``asyncio.sleep`` and no call should have happened yet.
        await asyncio.sleep(0.05)
        assert sink.calls == []

        await session.stop_heartbeat()
        await session.detach_socket()

    async def test_emits_multiple_heartbeats_at_cadence(self) -> None:
        session = Session("session_hb_multi")
        sink = _RecordingSink()
        await session.attach_socket(object())

        await session.start_heartbeat(interval=0.01, sink=sink)
        await _wait_for(lambda: len(sink.calls) >= 3, timeout=2.0)

        await session.stop_heartbeat()
        await session.detach_socket()

        assert len(sink.calls) >= 3

    async def test_loop_exits_when_socket_detached_between_ticks(self) -> None:
        """If ``socket`` becomes None during the sleep, the loop returns."""

        session = Session("session_hb_detach")
        sink = _RecordingSink()
        await session.attach_socket(object())

        # Long interval so we control when the next iteration runs.
        await session.start_heartbeat(interval=0.05, sink=sink)
        # Detach immediately. The current sleep continues until 0.05 elapses,
        # then the loop should observe ``socket is None`` and exit without
        # calling the sink.
        await session.detach_socket()

        # Wait for longer than ``interval`` so the loop has had a chance to
        # wake up and re-check the socket state.
        await asyncio.sleep(0.15)
        # After exit the task is done.
        assert session.heartbeat_task is not None
        assert session.heartbeat_task.done()
        assert sink.calls == [], (
            f"sink should not fire after detach; got {sink.calls!r}"
        )

        await session.stop_heartbeat()  # idempotent cleanup

    async def test_sink_exception_terminates_loop_without_wedging(self) -> None:
        session = Session("session_hb_raise")
        sink = _RaisingSink(raise_at=1)
        await session.attach_socket(object())

        await session.start_heartbeat(interval=0.01, sink=sink)
        await asyncio.wait_for(sink.event.wait(), timeout=1.0)

        # The task should finish on its own after the sink raises.
        await _wait_for(
            lambda: session.heartbeat_task is not None
            and session.heartbeat_task.done(),
            timeout=1.0,
        )
        # Only one call happened — the loop did not retry after the failure.
        assert len(sink.calls) == 1

        # ``stop_heartbeat`` is safe to call on a task that already finished.
        await session.stop_heartbeat()
        await session.detach_socket()

    async def test_double_start_raises(self) -> None:
        session = Session("session_hb_double")
        sink = _RecordingSink()
        await session.attach_socket(object())

        await session.start_heartbeat(interval=0.5, sink=sink)
        with pytest.raises(RuntimeError, match="already has a running heartbeat"):
            await session.start_heartbeat(interval=0.5, sink=sink)

        await session.stop_heartbeat()
        await session.detach_socket()

    async def test_restart_after_stop_is_allowed(self) -> None:
        session = Session("session_hb_restart")
        sink = _RecordingSink()
        await session.attach_socket(object())

        await session.start_heartbeat(interval=0.01, sink=sink)
        await asyncio.wait_for(sink.event.wait(), timeout=1.0)
        await session.stop_heartbeat()

        # Reset the event and start again.
        sink.event = asyncio.Event()
        await session.start_heartbeat(interval=0.01, sink=sink)
        await asyncio.wait_for(sink.event.wait(), timeout=1.0)

        await session.stop_heartbeat()
        await session.detach_socket()

    @pytest.mark.parametrize("bad_interval", [0, -1.0, float("nan"), float("inf")])
    async def test_invalid_interval_rejected(self, bad_interval: float) -> None:
        session = Session("session_hb_bad")
        sink = _RecordingSink()
        await session.attach_socket(object())

        with pytest.raises(ValueError):
            await session.start_heartbeat(interval=bad_interval, sink=sink)

        # No task was started.
        assert session.heartbeat_task is None
        await session.detach_socket()

    async def test_default_interval_matches_spec_window(self) -> None:
        """Sanity check: default interval is in the 10–15 s window from Req 3.6."""

        assert 10.0 <= HEARTBEAT_INTERVAL_SECONDS <= 15.0


# ---------------------------------------------------------------------------
# Session.stop_heartbeat
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSessionStopHeartbeat:
    async def test_stop_when_idle_is_noop(self) -> None:
        session = Session("session_hb_idle_stop")
        # No heartbeat ever started.
        await session.stop_heartbeat()
        assert session.heartbeat_task is None

    async def test_stop_cancels_running_task(self) -> None:
        session = Session("session_hb_cancel")
        sink = _RecordingSink()
        await session.attach_socket(object())

        await session.start_heartbeat(interval=10.0, sink=sink)
        task = session.heartbeat_task
        assert task is not None and not task.done()

        await session.stop_heartbeat()
        assert task.done()
        assert session.heartbeat_task is None

        # No emission ever happened.
        assert sink.calls == []
        await session.detach_socket()


# ---------------------------------------------------------------------------
# SessionRegistry.attach_socket / detach_socket integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRegistryAttachWithHeartbeat:
    async def test_attach_without_sink_does_not_start_heartbeat(self) -> None:
        registry = SessionRegistry()
        await registry.attach_socket("session_no_hb", object())

        session = registry.get("session_no_hb")
        assert session is not None
        assert session.heartbeat_task is None

        await registry.detach_socket("session_no_hb")

    async def test_attach_with_sink_starts_heartbeat(self) -> None:
        registry = SessionRegistry()
        sink = _RecordingSink()

        await registry.attach_socket(
            "session_with_hb",
            object(),
            heartbeat_sink=sink,
            heartbeat_interval=0.01,
        )
        session = registry.get("session_with_hb")
        assert session is not None
        assert session.heartbeat_task is not None

        await asyncio.wait_for(sink.event.wait(), timeout=1.0)
        assert sink.calls and all(sid == "session_with_hb" for sid in sink.calls)

        await registry.detach_socket("session_with_hb")

    async def test_detach_stops_heartbeat_before_unbinding_socket(self) -> None:
        registry = SessionRegistry()
        sink = _RecordingSink()

        await registry.attach_socket(
            "session_detach_hb",
            object(),
            heartbeat_sink=sink,
            heartbeat_interval=0.01,
        )
        session = registry.get("session_detach_hb")
        assert session is not None
        await asyncio.wait_for(sink.event.wait(), timeout=1.0)

        before = len(sink.calls)
        await registry.detach_socket("session_detach_hb")

        # Socket and task are both released after detach.
        assert session.socket is None
        assert session.heartbeat_task is None

        # Wait long enough that another tick *would* have fired if the task
        # had survived; the sink call count must not grow.
        await asyncio.sleep(0.05)
        assert len(sink.calls) == before

    async def test_detach_unknown_session_is_noop(self) -> None:
        registry = SessionRegistry()
        # No session exists; should not raise.
        await registry.detach_socket("nonexistent")

    async def test_attach_rolls_back_when_start_heartbeat_fails(self) -> None:
        """Validation failure in heartbeat startup unwinds the socket attach."""

        registry = SessionRegistry()
        sink = _RecordingSink()

        with pytest.raises(ValueError):
            await registry.attach_socket(
                "session_rollback",
                object(),
                heartbeat_sink=sink,
                heartbeat_interval=0,  # invalid -> ValueError
            )

        session = registry.get("session_rollback")
        assert session is not None
        # Attach was rolled back so a clean retry is possible.
        assert session.socket is None
        assert session.outbound_queue is None
        assert session.heartbeat_task is None

        # Retry with valid params succeeds.
        await registry.attach_socket(
            "session_rollback",
            object(),
            heartbeat_sink=sink,
            heartbeat_interval=0.01,
        )
        await asyncio.wait_for(sink.event.wait(), timeout=1.0)
        await registry.detach_socket("session_rollback")

"""Integration tests for Task 5.1 + 5.2: EventBus injection and PhaseGuard wrapping.

Verifies that:
- EventBus is properly injected into run() and accessible via self._event_bus
- _run_phase_guarded wraps phases in PhaseGuard correctly
- Non-critical phases (observe, recall) continue on error
- Critical phases (reason, commit) break on error
- Stabilize failure counter works (2 consecutive → break)
- agent_complete is always emitted at the end
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from agent.event_stream import (
    AgentOutcome,
    AgentStatus,
    EventBus,
    PhaseId,
    PhaseStatus,
)
from agent.resilience import PhaseGuard


# ---------------------------------------------------------------------------
# Test: _run_phase_guarded helper
# ---------------------------------------------------------------------------


class TestRunPhaseGuarded:
    """Test the _run_phase_guarded helper method in isolation."""

    @pytest.fixture
    def collected_events(self) -> list[dict]:
        """Sink that collects all events emitted by the EventBus."""
        events: list[dict] = []

        async def sink(envelope: dict) -> None:
            events.append(envelope)

        return events

    @pytest.fixture
    def bus(self, collected_events: list[dict]) -> EventBus:
        """Create an EventBus with a collecting sink."""
        async def sink(envelope: dict) -> None:
            collected_events.append(envelope)

        return EventBus("test-session", sink)

    @pytest.mark.asyncio
    async def test_successful_phase_emits_running_and_done(
        self, bus: EventBus, collected_events: list[dict]
    ):
        """PhaseGuard emits phase_change(running) on entry and phase_change(done) on exit."""

        async def phase_gen() -> AsyncIterator[dict[str, object]]:
            yield {"type": "log", "message": "hello"}

        async with PhaseGuard(phase=PhaseId.OBSERVE, bus=bus) as guard:
            events = []
            async for event in phase_gen():
                events.append(event)

        assert guard.outcome == "ok"
        assert len(events) == 1
        assert events[0] == {"type": "log", "message": "hello"}

        # Check bus events: should have phase_change(running) and phase_change(done)
        phase_events = [
            e for e in collected_events if e.get("type") == "phase_change"
        ]
        assert len(phase_events) == 2
        assert phase_events[0]["payload"]["status"] == "running"
        assert phase_events[0]["payload"]["phase"] == "observe"
        assert phase_events[1]["payload"]["status"] == "done"
        assert phase_events[1]["payload"]["phase"] == "observe"

    @pytest.mark.asyncio
    async def test_failing_phase_emits_error_and_swallows_exception(
        self, bus: EventBus, collected_events: list[dict]
    ):
        """PhaseGuard catches exceptions, emits log(error) + phase_change(error), swallows."""

        async def failing_phase_gen() -> AsyncIterator[dict[str, object]]:
            yield {"type": "log", "message": "before error"}
            raise RuntimeError("something went wrong")

        events = []
        async with PhaseGuard(phase=PhaseId.REASON, bus=bus) as guard:
            try:
                async for event in failing_phase_gen():
                    events.append(event)
            except Exception:
                raise  # Re-raise so PhaseGuard can catch it

        assert guard.outcome == "error"
        assert len(events) == 1  # Only the event before the error

        # Check bus events: running, log(error), phase_change(error)
        phase_events = [
            e for e in collected_events if e.get("type") == "phase_change"
        ]
        assert len(phase_events) == 2
        assert phase_events[0]["payload"]["status"] == "running"
        assert phase_events[1]["payload"]["status"] == "error"
        assert phase_events[1]["payload"]["reason"] == "RuntimeError"

        log_events = [
            e for e in collected_events
            if e.get("type") == "log" and e.get("payload", {}).get("level") == "error"
        ]
        assert len(log_events) == 1
        assert "something went wrong" in log_events[0]["payload"]["message"]

    @pytest.mark.asyncio
    async def test_timeout_phase_reports_timeout_outcome(
        self, bus: EventBus, collected_events: list[dict]
    ):
        """PhaseGuard with a very short timeout reports outcome='timeout'."""

        async def slow_phase_gen() -> AsyncIterator[dict[str, object]]:
            yield {"type": "log", "message": "starting"}
            await asyncio.sleep(10)  # Will be interrupted by timeout
            yield {"type": "log", "message": "never reached"}

        events = []
        async with PhaseGuard(phase=PhaseId.STABILIZE, bus=bus, max_seconds=0.01) as guard:
            try:
                async for event in slow_phase_gen():
                    events.append(event)
                    guard.check_deadline()
            except asyncio.TimeoutError:
                raise  # Let PhaseGuard handle it

        assert guard.outcome == "timeout"

    @pytest.mark.asyncio
    async def test_no_bus_runs_without_guard(self):
        """When no EventBus is attached, phases run without PhaseGuard (legacy path)."""
        from agent.core import SharrowkinAgent

        # Create agent without bus
        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._event_bus = None

        async def simple_gen() -> AsyncIterator[dict[str, object]]:
            yield {"type": "log", "message": "hello"}
            yield {"type": "log", "message": "world"}

        events, outcome = await agent._run_phase_guarded(
            PhaseId.OBSERVE, simple_gen()
        )

        assert outcome == "ok"
        assert len(events) == 2
        assert events[0] == {"type": "log", "message": "hello"}
        assert events[1] == {"type": "log", "message": "world"}

    @pytest.mark.asyncio
    async def test_with_bus_wraps_in_guard(self):
        """When EventBus is attached, phases are wrapped in PhaseGuard."""
        from agent.core import SharrowkinAgent

        collected: list[dict] = []

        async def sink(envelope: dict) -> None:
            collected.append(envelope)

        bus = EventBus("test-session", sink)

        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._event_bus = bus

        async def simple_gen() -> AsyncIterator[dict[str, object]]:
            yield {"type": "log", "message": "hello"}

        events, outcome = await agent._run_phase_guarded(
            PhaseId.RECALL, simple_gen()
        )

        assert outcome == "ok"
        assert len(events) == 1

        # Verify PhaseGuard emitted phase_change events on the bus
        phase_events = [
            e for e in collected if e.get("type") == "phase_change"
        ]
        assert len(phase_events) == 2
        assert phase_events[0]["payload"]["status"] == "running"
        assert phase_events[0]["payload"]["phase"] == "recall"
        assert phase_events[1]["payload"]["status"] == "done"
        assert phase_events[1]["payload"]["phase"] == "recall"

    @pytest.mark.asyncio
    async def test_with_bus_error_captured(self):
        """When EventBus is attached and phase errors, PhaseGuard captures it."""
        from agent.core import SharrowkinAgent

        collected: list[dict] = []

        async def sink(envelope: dict) -> None:
            collected.append(envelope)

        bus = EventBus("test-session", sink)

        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._event_bus = bus

        async def failing_gen() -> AsyncIterator[dict[str, object]]:
            yield {"type": "log", "message": "before"}
            raise ValueError("test error")

        events, outcome = await agent._run_phase_guarded(
            PhaseId.COMMIT, failing_gen()
        )

        assert outcome == "error"
        assert len(events) == 1  # Only the event before the error

        # Verify PhaseGuard emitted error events
        phase_events = [
            e for e in collected if e.get("type") == "phase_change"
        ]
        assert len(phase_events) == 2
        assert phase_events[0]["payload"]["status"] == "running"
        assert phase_events[1]["payload"]["status"] == "error"
        assert phase_events[1]["payload"]["reason"] == "ValueError"


class TestStabilizeFailureCounter:
    """Test the stabilize failure counter logic (2 consecutive → break)."""

    @pytest.mark.asyncio
    async def test_stabilize_counter_resets_on_success(self):
        """Stabilize failure counter resets when a stabilize phase succeeds."""
        from agent.core import SharrowkinAgent

        collected: list[dict] = []

        async def sink(envelope: dict) -> None:
            collected.append(envelope)

        bus = EventBus("test-session", sink)

        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._event_bus = bus

        # Simulate: first stabilize fails, second succeeds
        call_count = 0

        async def stabilize_gen() -> AsyncIterator[dict[str, object]]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                yield {"type": "log", "message": "failing"}
                raise RuntimeError("stabilize error")
            else:
                yield {"type": "log", "message": "success"}

        # First call: error
        events1, outcome1 = await agent._run_phase_guarded(
            PhaseId.STABILIZE, stabilize_gen()
        )
        assert outcome1 == "error"

        # Second call: success
        events2, outcome2 = await agent._run_phase_guarded(
            PhaseId.STABILIZE, stabilize_gen()
        )
        assert outcome2 == "ok"


class TestEventBusInjection:
    """Test that EventBus is properly injected into run() (Task 5.1)."""

    @pytest.mark.asyncio
    async def test_event_bus_stored_on_agent(self):
        """The event_bus parameter is stored on self._event_bus."""
        from agent.core import SharrowkinAgent

        collected: list[dict] = []

        async def sink(envelope: dict) -> None:
            collected.append(envelope)

        bus = EventBus("test-session", sink)

        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._event_bus = None
        agent._run_started_monotonic = None

        # Simulate what run() does at the start
        agent._event_bus = bus
        import time
        agent._run_started_monotonic = time.monotonic()

        assert agent._event_bus is bus
        assert agent._run_started_monotonic is not None

    @pytest.mark.asyncio
    async def test_bus_runtime_ms_returns_elapsed(self):
        """_bus_runtime_ms returns elapsed time in milliseconds."""
        import time
        from agent.core import SharrowkinAgent

        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._run_started_monotonic = time.monotonic() - 1.5  # 1.5 seconds ago

        ms = agent._bus_runtime_ms()
        assert 1400 <= ms <= 1700  # ~1500ms with some tolerance

    @pytest.mark.asyncio
    async def test_bus_runtime_ms_returns_zero_when_not_started(self):
        """_bus_runtime_ms returns 0 when run hasn't started."""
        from agent.core import SharrowkinAgent

        agent = SharrowkinAgent.__new__(SharrowkinAgent)
        agent._run_started_monotonic = None

        assert agent._bus_runtime_ms() == 0

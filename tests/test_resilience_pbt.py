"""Property-based tests for ``agent.resilience``.

Covers task 2.6 of spec ``ui-and-agent-stabilization``:

* **Property 4 (Retry bound):** :func:`agent.resilience.retry_async` invokes
  ``fn`` no more than :attr:`RetryPolicy.max_attempts` times and finishes
  within the analytic upper bound on cumulative jittered backoff.
* **Property 5 (Phase wall-clock bound):** :class:`agent.resilience.PhaseGuard`
  always exits the ``async with`` block within ``max_seconds + ε`` and emits
  exactly one terminal :class:`PhaseStatus` event.
* **Property 6 (Process survival):** No exception escapes a
  :class:`PhaseGuard` block, regardless of the exception type raised inside
  it; the guard reports a definite ``outcome`` instead.

The tests use a real :class:`agent.event_stream.EventBus` wired to a no-op
recording sink so :class:`PhaseGuard`'s ``phase_change`` / ``log`` traffic
exercises the real validation path. Hypothesis is used to randomise the
:class:`RetryPolicy` parameters and the exception payloads.

Validates: Requirements 13.2, Property 4, Property 5, Property 6
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Mapping

import pytest
from hypothesis import given, settings, strategies as st

from agent.event_stream import EventBus, PhaseId, PhaseStatus
from agent.resilience import (
    PermanentError,
    PhaseGuard,
    RetryPolicy,
    TransientError,
    retry_async,
)


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------


class _NoopSink:
    """Async sink that silently records every envelope it receives.

    Mirrors :class:`agent.event_stream.EventSink` (an async callable that
    accepts a JSON-compatible mapping). Recording is incidental — the tests
    only need a sink that completes successfully so :class:`PhaseGuard` can
    emit its lifecycle events through a real :class:`EventBus`.
    """

    def __init__(self) -> None:
        self.envelopes: list[dict[str, Any]] = []

    async def __call__(self, envelope: Mapping[str, Any]) -> None:
        self.envelopes.append(dict(envelope))


def _make_bus(session_id: str = "pbt-session") -> tuple[EventBus, _NoopSink]:
    """Return a fresh :class:`EventBus` paired with its recording sink."""

    sink = _NoopSink()
    return EventBus(session_id, sink), sink


# Policy parameters chosen so the wall-clock cost of every example stays well
# under one second even for ``max_attempts=10`` with maximal delays — the
# total per-example budget is bounded by
# ``(max_attempts - 1) * max_delay * (1 + jitter) ≈ 9 * 0.01 * 2 = 0.18 s``.
_retry_policies = st.builds(
    RetryPolicy,
    max_attempts=st.integers(min_value=1, max_value=10),
    base_delay=st.floats(min_value=0.0, max_value=0.001, allow_nan=False, allow_infinity=False),
    max_delay=st.floats(min_value=0.0, max_value=0.01, allow_nan=False, allow_infinity=False),
    jitter=st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False),
)


# Slack we allow on top of the analytic time bound to absorb event-loop
# scheduling, GC and Windows clock granularity. The design doc speaks of
# "max_seconds + ε" without pinning ε; 1.0 s is generous enough for CI.
_TIME_EPSILON = 1.0


# ---------------------------------------------------------------------------
# Property 4: retry_async respects max_attempts and the analytic time bound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@given(policy=_retry_policies)
@settings(deadline=None, max_examples=30)
async def test_retry_async_attempts_equals_max_attempts(policy: RetryPolicy) -> None:
    """``retry_async`` invokes ``fn`` exactly ``max_attempts`` times on transient failure.

    Validates: Requirements 13.2, Property 4
    """

    calls = 0

    async def always_transient() -> None:
        nonlocal calls
        calls += 1
        raise TransientError("boom")

    with pytest.raises(TransientError):
        await retry_async(always_transient, policy=policy)

    assert calls == policy.max_attempts


@pytest.mark.asyncio
@given(policy=_retry_policies)
@settings(deadline=None, max_examples=30)
async def test_retry_async_time_upper_bound(policy: RetryPolicy) -> None:
    """Wall-clock cost of ``retry_async`` stays under the analytic upper bound.

    The cumulative sleep between ``max_attempts`` attempts is at most
    ``(max_attempts - 1) * max_delay * (1 + jitter)``; a fixed ``ε`` covers
    fn() invocation cost and event-loop scheduling jitter.

    Validates: Requirements 13.2, Property 4
    """

    async def always_transient() -> None:
        raise TransientError("boom")

    upper_bound = (policy.max_attempts - 1) * policy.max_delay * (1.0 + policy.jitter)

    started = time.monotonic()
    with pytest.raises(TransientError):
        await retry_async(always_transient, policy=policy)
    elapsed = time.monotonic() - started

    assert elapsed <= upper_bound + _TIME_EPSILON, (
        f"retry_async took {elapsed:.4f}s for policy={policy}, "
        f"expected ≤ {upper_bound:.4f}s + {_TIME_EPSILON}s"
    )


@pytest.mark.asyncio
@given(policy=_retry_policies)
@settings(deadline=None, max_examples=30)
async def test_retry_async_permanent_short_circuits(policy: RetryPolicy) -> None:
    """A permanent failure surfaces immediately after a single ``fn`` call.

    Validates: Requirements 13.2, Property 4
    """

    calls = 0

    async def always_permanent() -> None:
        nonlocal calls
        calls += 1
        raise PermanentError("nope")

    with pytest.raises(PermanentError):
        await retry_async(always_permanent, policy=policy)

    assert calls == 1


# ---------------------------------------------------------------------------
# Property 5: PhaseGuard wall-clock bound
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@given(max_seconds=st.floats(min_value=0.01, max_value=0.1, allow_nan=False, allow_infinity=False))
@settings(deadline=None, max_examples=20)
async def test_phase_guard_exits_within_max_seconds(max_seconds: float) -> None:
    """``PhaseGuard`` always returns within ``max_seconds + ε`` even when the body loops.

    The body sleeps in sub-millisecond increments and calls
    ``guard.check_deadline()`` between sleeps; once the budget is exhausted
    the helper raises :class:`asyncio.TimeoutError` which the guard captures
    and translates into ``outcome="timeout"``.

    Validates: Requirements 13.2, Property 5
    """

    bus, _sink = _make_bus()

    started = time.monotonic()
    async with PhaseGuard(phase=PhaseId.OBSERVE, bus=bus, max_seconds=max_seconds) as guard:
        # Spin until the deadline check fires. The sleep is short enough
        # that we cross the deadline on a sub-millisecond grid, so the
        # observed elapsed time is dominated by ``max_seconds`` itself.
        while True:
            await asyncio.sleep(0.0005)
            guard.check_deadline()
    elapsed = time.monotonic() - started

    assert guard.outcome == "timeout"
    assert elapsed <= max_seconds + _TIME_EPSILON, (
        f"PhaseGuard took {elapsed:.4f}s for max_seconds={max_seconds:.4f}s, "
        f"expected ≤ max_seconds + {_TIME_EPSILON}s"
    )


# ---------------------------------------------------------------------------
# Property 6: PhaseGuard swallows every non-cancellation exception
# ---------------------------------------------------------------------------


# Exception classes the guard is contractually required to swallow. The list
# spans both stdlib types and the resilience-layer hierarchy. We exclude
# ``asyncio.CancelledError`` because the guard intentionally re-raises it.
_swallowable_excs: list[type[BaseException]] = [
    ValueError,
    RuntimeError,
    KeyError,
    IndexError,
    TransientError,
    PermanentError,
    TimeoutError,  # asyncio.TimeoutError is the same class on 3.11+
]


@pytest.mark.asyncio
@given(exc_cls=st.sampled_from(_swallowable_excs))
@settings(deadline=None, max_examples=30)
async def test_phase_guard_swallows_arbitrary_exceptions(
    exc_cls: type[BaseException],
) -> None:
    """No non-cancellation exception escapes a :class:`PhaseGuard` block.

    For :class:`asyncio.TimeoutError` (a.k.a. ``TimeoutError`` on Python 3.11+)
    the guard reports ``outcome="timeout"``; for every other type it reports
    ``outcome="error"``. In both cases the surrounding ``async with`` returns
    normally and the run-loop can read :attr:`PhaseGuard.outcome` instead of
    catching the exception itself.

    Validates: Requirements 13.2, Property 6
    """

    bus, sink = _make_bus()

    # The body raises eagerly; the guard must capture and translate the
    # exception. We deliberately do not wrap this in pytest.raises — the
    # contract is that nothing escapes the with-block.
    async with PhaseGuard(phase=PhaseId.REASON, bus=bus, max_seconds=10.0) as guard:
        if exc_cls is KeyError:
            # KeyError stringifies its arg in quotes — pass a benign payload.
            raise exc_cls("missing")
        raise exc_cls("payload")

    expected_outcome = "timeout" if issubclass(exc_cls, asyncio.TimeoutError) else "error"
    assert guard.outcome == expected_outcome

    # Sanity: the guard emitted exactly one terminal phase_change with the
    # matching status, proving the lifecycle event stream is also intact.
    terminal_events = [
        env
        for env in sink.envelopes
        if env["type"] == "phase_change"
        and env["payload"]["status"] == PhaseStatus.ERROR.value
    ]
    assert len(terminal_events) == 1
    if expected_outcome == "timeout":
        assert terminal_events[0]["payload"]["reason"] == "phase_timeout"

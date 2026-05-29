"""Resilience_Layer: retry, timeout and degrade primitives for the agent.

This module implements the public API described in the design document
(``.kiro/specs/ui-and-agent-stabilization/design.md``, section
"Backend: Resilience_Layer"). It is split across several subtasks (2.1 - 2.5):

* **2.1** introduces the type system used by every other piece:
  the :class:`TransientError` / :class:`PermanentError` exception hierarchy,
  the :class:`RetryPolicy` dataclass and the :func:`default_classify`
  function which decides whether a given exception should be retried.
* **2.2** adds :func:`retry_async` — an async retry helper
  with exponential backoff + symmetric jitter that is safe across task
  cancellation (``asyncio.CancelledError`` always propagates).
* **2.3** adds :func:`with_timeout` — an :func:`asyncio.wait_for`
  wrapper that guarantees inner-task cancellation on timeout and supports an
  optional sync-or-async fallback callback (Requirement 6.7).
* **2.4** adds :class:`PhaseGuard` — an async context manager
  that brackets one phase of :class:`agent.core.SharrowkinAgent.run` with
  ``phase_change(running)`` / ``phase_change(done|error)`` events, swallows
  any exception so the main loop sees a clean :attr:`PhaseGuard.outcome`, and
  records elapsed time so callers can enforce the 600 s wall-clock bound
  (Requirements 6.1, 6.2, 6.7).
* **2.5 (this commit)** adds :func:`degrade_on_error` — a thin wrapper that
  runs a memory-system call (DSM, RLD, TraceMemory, ConversationHistory) and,
  on any non-cancellation failure, emits a structured ``log(warning)`` with a
  caller-supplied code and returns a pre-built fallback value so the agent
  can keep going in a degraded in-memory mode (Requirement 6.6).

The classifier purposefully treats any unknown exception as **permanent**:
retrying an unclassified failure is dangerous (it may have side effects or
hide a real bug), so we surface it immediately and let the caller decide.

References:
    Design: ``.kiro/specs/ui-and-agent-stabilization/design.md`` (section
    "Backend: Resilience_Layer", Public API).
    Requirements: 6.3 (retry policy for transient LLM/HTTP failures).
"""

from __future__ import annotations

import asyncio
import inspect
import random
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Literal, TypeVar, Union

from agent.event_stream import EventBus, LogLevel, PhaseId, PhaseStatus

# ---------------------------------------------------------------------------
# Optional dependency: httpx
# ---------------------------------------------------------------------------
#
# ``httpx`` is the transport used by the LLM client, but the resilience layer
# itself must be importable without it (e.g. in unit tests that monkeypatch
# the network stack, or in environments where the LLM is mocked entirely).
# We try to import it once and fall back to ``None`` if it is unavailable;
# :func:`default_classify` checks for ``None`` before doing any ``isinstance``.
try:  # pragma: no cover - exercised implicitly by tests with/without httpx
    import httpx as _httpx
except ImportError:  # pragma: no cover - defensive, httpx is normally present
    _httpx = None  # type: ignore[assignment]


# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class TransientError(Exception):
    """Failure that is expected to recover on its own.

    Raise this (or let :func:`default_classify` infer it from a known
    network/HTTP exception) when the call should be retried under the active
    :class:`RetryPolicy`. Examples: network timeouts, HTTP 429 / 5xx, transient
    DNS failures.
    """


class PermanentError(Exception):
    """Failure that will not recover by simply retrying.

    Raise this when the call must surface immediately to the caller without
    further attempts. Examples: HTTP 4xx (except 408/425/429), validation
    errors, programming errors.
    """


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class RetryPolicy:
    """Parameters controlling :func:`retry_async`.

    Attributes:
        max_attempts: Total number of attempts, including the initial call.
            ``max_attempts=1`` disables retrying. Must be ``>= 1``.
        base_delay: Delay in seconds before the second attempt. The delay for
            attempt ``n`` (``1``-indexed) is
            ``min(max_delay, base_delay * 2 ** (n - 1))``.
        max_delay: Upper bound on the per-attempt delay in seconds, applied
            after the exponential growth and before jitter.
        jitter: Symmetric multiplicative jitter in ``[0, 1]``. The actual
            sleep is sampled uniformly from
            ``delay * (1 - jitter) .. delay * (1 + jitter)``.

    The defaults match Requirement 6.3 / design doc: 3 attempts, 1 s base,
    30 s cap, ±25 % jitter.
    """

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    jitter: float = 0.25


# ---------------------------------------------------------------------------
# Default classifier
# ---------------------------------------------------------------------------


# HTTP status codes that we treat as transient. 408 (Request Timeout),
# 425 (Too Early), 429 (Too Many Requests) and the 5xx family.
_TRANSIENT_HTTP_STATUS: frozenset[int] = frozenset({408, 425, 429, 500, 502, 503, 504})


def default_classify(exc: BaseException) -> bool:
    """Return ``True`` if ``exc`` should be retried, ``False`` otherwise.

    Classification rules, in order:

    1. Explicit :class:`TransientError` / :class:`PermanentError` wins over
       everything else - callers can force the decision by raising one of
       these.
    2. ``httpx`` network-level errors (timeouts, connection / read errors)
       are transient. We probe ``httpx`` lazily so the module loads even
       when ``httpx`` is not installed.
    3. ``httpx.HTTPStatusError`` is transient iff the response status code
       is in :data:`_TRANSIENT_HTTP_STATUS`; any other 4xx (or unexpected
       code) is permanent.
    4. Anything else defaults to **permanent**: an unknown failure mode is
       not safely retryable.

    The function never raises - if classification fails for any reason we
    fall through to ``False``.
    """

    # 1. Explicit hierarchy wins.
    if isinstance(exc, TransientError):
        return True
    if isinstance(exc, PermanentError):
        return False

    # 2 + 3. httpx-specific handling, only if httpx is importable.
    if _httpx is not None:
        # Network-level errors: TimeoutException covers Read/Connect/Write/Pool
        # timeouts via inheritance, but we list the concrete subclasses
        # explicitly so the contract is obvious from the source.
        transient_httpx_excs: tuple[type[BaseException], ...] = (
            _httpx.TimeoutException,
            _httpx.ReadTimeout,
            _httpx.ConnectTimeout,
            _httpx.WriteTimeout,
            _httpx.PoolTimeout,
            _httpx.ReadError,
            _httpx.ConnectError,
        )
        if isinstance(exc, transient_httpx_excs):
            return True

        # HTTP status errors: classify by response.status_code.
        if isinstance(exc, _httpx.HTTPStatusError):
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if isinstance(status_code, int):
                return status_code in _TRANSIENT_HTTP_STATUS
            # No status code attached: treat as permanent rather than
            # silently retrying an opaque failure.
            return False

    # 4. Unknown exception type -> permanent (do not retry blindly).
    return False


# ---------------------------------------------------------------------------
# retry_async
# ---------------------------------------------------------------------------


T = TypeVar("T")


def _compute_backoff(
    attempt: int,
    policy: RetryPolicy,
    rng: random.Random,
) -> float:
    """Return the (jittered) sleep duration before the next attempt.

    ``attempt`` is the 1-indexed number of the attempt that *just failed*.
    The base delay before attempt ``attempt + 1`` is

        ``min(policy.max_delay, policy.base_delay * 2 ** (attempt - 1))``

    plus a symmetric multiplicative jitter sampled uniformly from
    ``[delay * (1 - jitter), delay * (1 + jitter)]``. The result is clamped
    to a non-negative value so a misconfigured ``jitter > 1`` cannot produce
    a negative sleep.
    """

    exponent = max(0, attempt - 1)
    raw_delay = policy.base_delay * (2 ** exponent)
    delay = min(policy.max_delay, raw_delay)
    if policy.jitter > 0.0:
        spread = delay * policy.jitter
        delay = rng.uniform(delay - spread, delay + spread)
    return max(0.0, delay)


async def retry_async(
    fn: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy = RetryPolicy(),
    classify: Callable[[BaseException], bool] = default_classify,
) -> T:
    """Retry an async callable with exponential backoff and symmetric jitter.

    The function calls ``await fn()`` up to ``policy.max_attempts`` times.
    Between attempts ``n`` and ``n + 1`` it sleeps for

        ``min(policy.max_delay, policy.base_delay * 2 ** (n - 1))``

    multiplied by a uniform jitter factor in
    ``[1 - policy.jitter, 1 + policy.jitter]``.

    Args:
        fn: A zero-argument async callable that performs the work. Each
            attempt invokes ``fn()`` afresh, so the caller is responsible
            for any per-attempt setup (e.g. building a fresh request).
        policy: The :class:`RetryPolicy` to apply. Defaults to the policy
            mandated by Requirement 6.3 (3 attempts, 1 s base, 30 s cap,
            ±25 % jitter).
        classify: Predicate that maps an exception to ``True`` (transient,
            keep retrying) or ``False`` (permanent, re-raise immediately).
            Defaults to :func:`default_classify`.

    Returns:
        The value returned by the first successful ``fn()`` call.

    Raises:
        BaseException: The last exception raised by ``fn`` is re-raised
            once attempts are exhausted, or immediately if ``classify``
            marks it as permanent.
        asyncio.CancelledError: Always propagates without being retried
            or swallowed, so cooperative cancellation remains correct.

    The implementation is cancellation-safe: an ``asyncio.CancelledError``
    raised either from inside ``fn`` or from the inter-attempt sleep is
    re-raised immediately and never classified as transient.
    """

    if policy.max_attempts < 1:
        raise ValueError("RetryPolicy.max_attempts must be >= 1")

    rng = random.Random()
    last_exc: BaseException | None = None

    for attempt in range(1, policy.max_attempts + 1):
        try:
            return await fn()
        except asyncio.CancelledError:
            # Cooperative cancellation must always win — do not retry,
            # do not classify, do not swallow.
            raise
        except BaseException as exc:  # noqa: BLE001 - intentional broad catch
            last_exc = exc
            # Permanent failure: surface immediately without sleeping.
            if not classify(exc):
                raise
            # Transient failure: if no attempts remain, surface as-is.
            if attempt >= policy.max_attempts:
                raise
            # Otherwise back off and try again.
            delay = _compute_backoff(attempt, policy, rng)
            try:
                await asyncio.sleep(delay)
            except asyncio.CancelledError:
                raise

    # The loop above always either returns or raises. This line is purely
    # defensive (e.g. against a future refactor that breaks the invariant)
    # and is unreachable in practice.
    assert last_exc is not None  # pragma: no cover
    raise last_exc  # pragma: no cover


__all__ = [
    "TransientError",
    "PermanentError",
    "RetryPolicy",
    "default_classify",
    "retry_async",
    "with_timeout",
    "PhaseGuard",
    "degrade_on_error",
]


# ---------------------------------------------------------------------------
# with_timeout
# ---------------------------------------------------------------------------


# Type alias for the optional fallback callable. ``on_timeout`` may be a
# regular function returning a value (or ``None``) or an async function whose
# coroutine resolves to a value (or ``None``). The return type is intentionally
# ``Any`` because the fallback is free to substitute a degraded result of a
# different shape than the primary path; callers that need stronger typing can
# wrap :func:`with_timeout` with their own typed helper.
_OnTimeout = Union[
    Callable[[], Any],
    Callable[[], Awaitable[Any]],
]


async def with_timeout(
    fn: Callable[[], Awaitable[T]],
    *,
    seconds: float,
    on_timeout: _OnTimeout | None = None,
) -> T | Any:
    """Run an async callable under a timeout, with optional fallback.

    The function awaits ``fn()`` inside :func:`asyncio.wait_for` with the
    given ``seconds`` budget. If the budget is exceeded:

    * When ``on_timeout`` is ``None``, the original :class:`asyncio.TimeoutError`
      propagates to the caller.
    * When ``on_timeout`` is provided, it is invoked (sync or async). Its
      return value, if any, becomes the result of :func:`with_timeout`. If
      ``on_timeout`` itself raises, that exception propagates instead.

    :func:`asyncio.wait_for` already cancels the underlying task on timeout
    and waits for that cancellation to be observed before re-raising
    ``TimeoutError``. This contract is what we rely on for the "guaranteed
    cancellation" requirement (Req 6.7): when this coroutine returns or
    raises, the inner task is no longer running. We do not double-cancel or
    second-guess that behaviour - doing so would race with ``wait_for``'s own
    cleanup and could swallow exceptions.

    Args:
        fn: A zero-argument async callable. Each call to :func:`with_timeout`
            invokes ``fn()`` exactly once; the caller owns any setup logic.
        seconds: Timeout budget in seconds. Non-positive values cause the
            underlying call to be cancelled almost immediately, matching the
            semantics of :func:`asyncio.wait_for`.
        on_timeout: Optional fallback invoked when the budget is exceeded.
            May be sync or async. Its return value, if any, is returned by
            :func:`with_timeout`; if it returns ``None`` we still return that
            ``None`` to give callers an explicit "no value" signal.

    Returns:
        The value returned by ``fn()`` if it completes within ``seconds``,
        otherwise the value returned by ``on_timeout`` (if provided).

    Raises:
        asyncio.TimeoutError: If the budget is exceeded and no
            ``on_timeout`` callback is supplied.
        asyncio.CancelledError: Always propagates without being swallowed,
            so cooperative cancellation of the outer task remains correct.
        BaseException: Any exception raised by ``fn`` (within the budget)
            or by ``on_timeout`` is propagated unchanged.
    """

    try:
        return await asyncio.wait_for(fn(), timeout=seconds)
    except asyncio.CancelledError:
        # Cooperative cancellation of the *outer* task must always win.
        # ``asyncio.wait_for`` has already cancelled the inner task and
        # awaited its teardown by the time this branch runs.
        raise
    except asyncio.TimeoutError:
        # The inner task has been cancelled and awaited by ``wait_for``;
        # we now have the option to substitute a fallback value.
        if on_timeout is None:
            raise
        result = on_timeout()
        if inspect.isawaitable(result):
            result = await result
        return result


# ---------------------------------------------------------------------------
# PhaseGuard
# ---------------------------------------------------------------------------


#: Lifecycle outcomes reported by :attr:`PhaseGuard.outcome`. The guard starts
#: in ``"pending"`` and moves to exactly one terminal value during ``__aexit__``.
PhaseOutcome = Literal["pending", "ok", "error", "timeout"]


class PhaseGuard:
    """Bracket one cognitive-cycle phase with start/end events and error capture.

    A :class:`PhaseGuard` is the context manager used by
    :class:`agent.core.SharrowkinAgent.run` to wrap each of the five phases
    (``observe``, ``recall``, ``reason``, ``stabilize``, ``commit``). It owns
    three concerns that the design doc keeps together for a reason:

    1. **Lifecycle events.** On entry it emits
       ``phase_change(phase, status=RUNNING)`` so the UI Phase_Timeline lights
       up immediately. On exit it emits exactly one terminal
       ``phase_change(phase, status=DONE|ERROR)`` so the timeline never gets
       stuck in the running state. (Req 6.1, 6.2.)
    2. **Exception isolation.** Any exception raised inside the ``async with``
       block (other than :class:`asyncio.CancelledError`) is captured, turned
       into a structured ``log(error)`` plus
       ``phase_change(error, reason=<exception_type>)`` and then *swallowed*.
       The main run-loop reads :attr:`outcome` to decide policy (skip,
       retry the stabilize phase, abort the run, ...) instead of catching
       exceptions itself. ``CancelledError`` always propagates so cooperative
       cancellation of the outer task remains correct. (Req 6.2.)
    3. **Wall-clock bound.** The phase is supposed to complete within
       ``max_seconds`` (default 600 s, per Req 6.7). The actual hard
       enforcement happens at the call site by wrapping the phase body in
       :func:`with_timeout` (or :func:`asyncio.wait_for`); when that wrapper
       times out, ``PhaseGuard`` recognises the resulting
       :class:`asyncio.TimeoutError` and reports
       ``outcome="timeout"`` with ``reason="phase_timeout"`` instead of the
       generic exception class name. The guard itself also exposes
       :meth:`check_deadline`, a cheap helper callers may invoke between
       sub-steps to fail fast if the budget is exhausted.

    Attributes:
        phase: The :class:`PhaseId` this guard is bracketing.
        bus: The :class:`EventBus` used to emit lifecycle events.
        max_seconds: Wall-clock budget for the phase, in seconds.
        outcome: One of :data:`PhaseOutcome`. ``"pending"`` while the guard is
            active or before entry, then exactly one of ``"ok"`` / ``"error"``
            / ``"timeout"`` after :meth:`__aexit__` returns. The main loop is
            expected to read this attribute and apply phase policy.
        started_at_monotonic: :func:`time.monotonic` reading captured on
            entry; ``None`` before entry. Useful to compute elapsed time from
            inside the phase body.

    Example:
        >>> async def observe(state, bus, guard):
        ...     # ... do work, optionally call guard.check_deadline()
        ...     return None
        >>> async with PhaseGuard(phase=PhaseId.OBSERVE, bus=bus) as guard:
        ...     await observe(state, bus, guard)
        >>> if guard.outcome == "error":
        ...     ...  # apply phase policy

    The implementation deliberately does not start its own
    :func:`asyncio.wait_for` around the body: the body is supplied by the
    caller, can call into ``await`` at arbitrary granularity, and the proper
    place to enforce a hard timeout is at the call site that owns the
    coroutine. Doing it here would also make ``PhaseGuard`` a non-trivial
    task scheduler that races with the caller's own cancellation logic.
    """

    __slots__ = (
        "phase",
        "bus",
        "max_seconds",
        "outcome",
        "started_at_monotonic",
        "_entered",
    )

    def __init__(
        self,
        *,
        phase: PhaseId,
        bus: EventBus,
        max_seconds: float = 600.0,
    ) -> None:
        if max_seconds <= 0:
            raise ValueError("PhaseGuard.max_seconds must be > 0")
        self.phase: PhaseId = phase
        self.bus: EventBus = bus
        self.max_seconds: float = max_seconds
        self.outcome: PhaseOutcome = "pending"
        self.started_at_monotonic: float | None = None
        self._entered: bool = False

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def elapsed(self) -> float:
        """Seconds since :meth:`__aenter__`. Returns ``0.0`` before entry."""

        if self.started_at_monotonic is None:
            return 0.0
        return max(0.0, time.monotonic() - self.started_at_monotonic)

    def check_deadline(self) -> None:
        """Raise :class:`asyncio.TimeoutError` if the wall-clock budget is gone.

        Cheap helper that phase implementations may sprinkle between
        sub-steps. The raised :class:`asyncio.TimeoutError` is caught by
        :meth:`__aexit__` and translated into ``outcome="timeout"`` with
        ``reason="phase_timeout"``, so the resulting event stream looks the
        same regardless of whether the timeout was detected by an outer
        :func:`with_timeout` wrapper or by an inner deadline check.
        """

        if self.elapsed > self.max_seconds:
            raise asyncio.TimeoutError(
                f"phase {self.phase.value!r} exceeded "
                f"{self.max_seconds:.0f}s budget"
            )

    # ------------------------------------------------------------------
    # Async context manager protocol
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "PhaseGuard":
        if self._entered:
            raise RuntimeError("PhaseGuard is not re-entrant")
        self._entered = True
        self.started_at_monotonic = time.monotonic()
        self.outcome = "pending"
        # Emit the running event before yielding control. If the bus itself
        # raises (e.g. transport failure), we propagate that out: failing to
        # signal the start of a phase is a hard environmental error and the
        # caller has not yet executed any phase work, so there is nothing to
        # roll back.
        await self.bus.phase_change(self.phase, PhaseStatus.RUNNING)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        # Cooperative cancellation always wins. Do not swallow, do not log,
        # do not emit a terminal phase_change: the run-loop is being torn
        # down and any further bus traffic could race with shutdown.
        if exc is not None and isinstance(exc, asyncio.CancelledError):
            self.outcome = "error"
            return False

        if exc is None:
            # Normal exit: phase completed within its budget.
            self.outcome = "ok"
            try:
                await self.bus.phase_change(self.phase, PhaseStatus.DONE)
            except asyncio.CancelledError:
                # Cancellation during the terminal emit: surface it.
                raise
            except Exception:  # noqa: BLE001 - defensive, do not mask
                # If the bus fails on the success path we cannot recover the
                # missed event from inside the guard. Re-raise so the caller
                # learns that the transport is broken; the phase body itself
                # already finished cleanly.
                raise
            return False

        # Exception path: classify, log, emit terminal event, swallow.
        is_timeout = isinstance(exc, asyncio.TimeoutError)
        self.outcome = "timeout" if is_timeout else "error"
        reason = "phase_timeout" if is_timeout else (
            exc_type.__name__ if exc_type is not None else exc.__class__.__name__
        )
        message = str(exc) if str(exc) else reason

        # Emit a structured log first so diagnostics always have the raw
        # exception details, even if the subsequent phase_change fails.
        # We catch and discard secondary failures from the bus here: the
        # primary exception has already been recorded in ``self.outcome``,
        # and the run-loop's job is to act on that outcome rather than
        # discover transport problems through ``__aexit__``.
        try:
            await self.bus.log(
                LogLevel.ERROR,
                f"phase {self.phase.value!r} failed: {message}",
                code="phase_exception",
                phase=self.phase,
                details={
                    "exception_type": exc.__class__.__name__,
                    "message": message[:1000],
                    "elapsed_seconds": round(self.elapsed, 3),
                    "max_seconds": self.max_seconds,
                },
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - defensive, swallow secondary
            pass

        try:
            await self.bus.phase_change(
                self.phase,
                PhaseStatus.ERROR,
                reason=reason,
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - defensive, swallow secondary
            pass

        # Suppress the original exception so the run-loop can read
        # ``self.outcome`` and decide policy without writing its own
        # ``try/except`` around every phase invocation.
        return True


# ---------------------------------------------------------------------------
# degrade_on_error
# ---------------------------------------------------------------------------


async def degrade_on_error(
    fn: Callable[[], Awaitable[T]],
    fallback: T,
    *,
    code: str,
    bus: EventBus | None = None,
) -> T:
    """Run a memory-system call and degrade to ``fallback`` on failure.

    This is the primitive used to wrap every call into the agent's optional
    memory subsystems — DSM, RLD, TraceMemory and ConversationHistory — so
    that a failure in one of them never aborts the cognitive cycle. The
    agent simply continues with a degraded in-memory result and emits a
    diagnostic ``log(warning)`` so operators can see when memory is
    misbehaving (Requirement 6.6, design doc "Phase loop policy" table).

    Behavior:
        * Awaits ``fn()`` once. On success the result is returned unchanged.
        * On any exception **other than** :class:`asyncio.CancelledError`:
            - if ``bus`` is provided, emits a single
              ``log(level=warning, code=code, message=...,
              details={"exception_type": ...})`` event;
            - returns ``fallback`` to the caller.
        * :class:`asyncio.CancelledError` always propagates so cooperative
          cancellation of the outer task remains correct.

    The function never re-raises a non-cancellation exception: callers rely
    on the returned value being usable as a drop-in replacement for ``fn()``
    output. If emitting the diagnostic ``log`` event itself raises (e.g. the
    bus transport is broken), that secondary failure is swallowed — the
    primary purpose of this helper is to keep the agent loop running, and
    surfacing a transport error here would defeat that.

    Args:
        fn: A zero-argument async callable that performs a memory-system
            access. It is invoked exactly once per call to
            :func:`degrade_on_error`; the caller owns any setup logic.
        fallback: Value returned when ``fn()`` raises a non-cancellation
            exception. Typically an empty container (``[]``, ``{}``,
            ``""``) or a sentinel that downstream code recognises as
            "no memory available".
        code: Stable, machine-readable identifier for the failure category
            (e.g. ``"dsm_recall_failed"``, ``"trace_memory_unavailable"``).
            Surfaces in the emitted ``log`` event under ``payload.code``.
        bus: Optional :class:`EventBus`. When ``None``, the helper degrades
            silently — useful for unit tests or call sites that have no
            session context. When provided, a structured warning is
            emitted before the fallback is returned.

    Returns:
        The value produced by ``fn()`` on success, or ``fallback`` if
        ``fn()`` raised a non-cancellation exception.

    Raises:
        asyncio.CancelledError: Always propagates without being swallowed,
            so cooperative cancellation of the outer task remains correct.
    """

    try:
        return await fn()
    except asyncio.CancelledError:
        # Cooperative cancellation must always win — do not log, do not
        # substitute a fallback.
        raise
    except BaseException as exc:  # noqa: BLE001 - intentional broad catch
        if bus is not None:
            try:
                await bus.log(
                    LogLevel.WARNING,
                    f"memory call degraded ({code}): {exc.__class__.__name__}",
                    code=code,
                    details={"exception_type": exc.__class__.__name__},
                )
            except asyncio.CancelledError:
                # Cancellation during the diagnostic emit must propagate.
                raise
            except Exception:  # noqa: BLE001 - defensive, swallow secondary
                # The bus failed to deliver our warning. The primary job of
                # this helper is to keep the agent loop running, so we
                # silently move on to the fallback rather than raising.
                pass
        return fallback

"""Per-session state registry: ring buffer of recent events + ``next_seq``.

This module owns the in-memory state for the agent's WebSocket sessions. It is
the boundary between the agent's :class:`agent.event_stream.EventBus` and the
WebSocket transport in ``api/routers/agent.py``: the bus emits envelopes into
the registry, the registry stores them in a per-session ring buffer (1024
recent events), and the WebSocket layer consumes either live or replayed
events through it.

Subtask 4.5 (this revision) closes the loop on resume by persisting every
envelope to ``.sharrowkin/runs/<session>/events.jsonl`` in append-only form
the moment it lands in the ring buffer, so ``resume(last_seq)`` can serve
clients whose ``last_seq`` is already older than the in-memory window.
Cold-path replay merges the persisted log with whatever the buffer still
remembers and (optionally) a Checkpoint v2 — the disk log is what makes the
cold path actually recoverable without a checkpoint.

Subtask 4.2 added the ``attach_socket`` / ``detach_socket`` primitives and the
**lossless** outbound event queue used by the WebSocket sender task. The queue
is **unbounded** by design: requirement 11.2 is explicit that backpressure
must never drop events. Bounded-queue + ``put_nowait``-with-drop semantics are
therefore prohibited here. A slow WebSocket consumer instead causes the queue
to grow; the in-memory ring buffer (``RING_BUFFER_CAPACITY = 1024``) remains
the bounded recent-events store used for replay, independent of this transport
queue.

Subtask 4.3 (this revision) adds a per-session ``heartbeat`` background task
that emits a ``heartbeat`` event every ``HEARTBEAT_INTERVAL_SECONDS`` (12 s by
default, in the 10–15 s window mandated by Requirement 3.6) while a socket is
attached. The task is owned by :class:`Session` and is started/stopped by
:meth:`SessionRegistry.attach_socket` / :meth:`SessionRegistry.detach_socket`
respectively. The actual envelope construction is delegated to a caller-
supplied ``heartbeat_sink`` callable so this module stays free of an
:class:`agent.event_stream.EventBus` import — full integration with the bus
happens in task 7 (router refactor).

References:
    Design doc: ``.kiro/specs/ui-and-agent-stabilization/design.md`` (sections
    "SessionRegistry" and "Sequencing & resume").
    Requirements: 3.4, 3.6, 7.4, 8.2, 11.2.
"""

from __future__ import annotations

import asyncio
import collections
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Mapping

if TYPE_CHECKING:
    # Imported under ``TYPE_CHECKING`` to avoid a runtime dependency on
    # :mod:`agent.checkpoints` from this transport-layer module. The
    # checkpoint store is supplied by the caller (the WebSocket router) via
    # duck typing — we only call ``load_latest`` on it — and the dataclass
    # fields below survive at runtime thanks to
    # ``from __future__ import annotations``.
    from agent.checkpoints import Checkpoint, CheckpointStore


__all__ = ["HeartbeatSink", "ReplayResult", "Session", "SessionRegistry"]


#: Module logger for the silent-failure paths (e.g. JSONL append errors). The
#: design forbids raising from the persistence path because the in-memory
#: ring buffer already has the envelope and remains the authoritative source
#: for live and warm-replay traffic; the disk log is best-effort durability
#: for cold replay only. Failures are surfaced via ``logger.warning`` so they
#: are visible in operator logs without breaking event delivery.
logger = logging.getLogger(__name__)


#: Default root for per-session persisted event logs. Each session's events
#: are appended to ``<runs_dir>/<session_id>/events.jsonl``. The default of
#: ``.sharrowkin/runs`` matches Requirement 3.4 and the wider repo
#: convention (``.sharrowkin/checkpoints``, ``.sharrowkin/conversations``,
#: ...). Callers can override per-registry via :class:`SessionRegistry`'s
#: constructor argument; tests typically point this at a ``tmp_path``.
_DEFAULT_RUNS_DIR: Path = Path(".sharrowkin") / "runs"


#: Type alias for the heartbeat sink callable: ``async (session_id) -> None``.
#: The session knows nothing about :class:`agent.event_stream.EventBus`; the
#: caller provides this callable to bridge the registry to the bus. See
#: :meth:`Session.start_heartbeat` for the full contract.
HeartbeatSink = Callable[[str], Awaitable[None]]


#: Default heartbeat interval. Requirement 3.6 mandates 10–15 s; 12 s sits in
#: the middle of that window and matches the watchdog budget on the UI client
#: (45 s, ~3.75x the interval). Callers can override per-session via
#: :meth:`SessionRegistry.attach_socket`.
HEARTBEAT_INTERVAL_SECONDS: float = 12.0


#: Capacity of the per-session in-memory ring buffer of recent events. Older
#: events are evicted automatically by :class:`collections.deque`. Replays
#: requesting a ``last_seq`` older than what is still in the buffer must be
#: served from the persisted event log on disk (subtask 4.5).
RING_BUFFER_CAPACITY: int = 1024


# =============================================================================
# Replay result (subtask 4.4)
# =============================================================================


@dataclass(frozen=True)
class ReplayResult:
    """Outcome of a :meth:`SessionRegistry.resume` call.

    Returned to the WebSocket router so it can decide what to send to the
    client and whether to feed cognitive state back into the agent. The
    fields together cover the three resume paths described in the design
    doc (section "Sequencing & resume"):

    * **Warm path** — the requested ``last_seq`` is still in the in-memory
      ring buffer. ``mode == "resume"``, ``recoverable=True``, ``events`` is
      the tail of envelopes the client missed (``seq > last_seq``,
      monotonic), ``checkpoint`` is ``None``.
    * **Cold path** — ``last_seq`` is older than what the ring buffer still
      remembers, or no in-memory session exists at all. ``mode == "resume"``;
      ``events`` is the merged, deduplicated tail from the persisted JSONL
      log (``runs_dir/<session_id>/events.jsonl``) and the in-memory ring,
      sorted by ``seq``. ``checkpoint`` is the latest checkpoint loaded
      from the supplied store, or ``None``. ``recoverable`` is ``True``
      whenever ``events`` is non-empty or ``checkpoint`` is non-``None`` —
      both signal that the caller has something useful for the client.
    * **New session** — no in-memory session, no disk log, no checkpoint.
      ``mode == "new"``, ``recoverable=False``, ``events == []``,
      ``next_seq == 0``, ``checkpoint is None``. The session has been
      created so the caller can immediately
      :meth:`SessionRegistry.attach_socket` and start streaming.

    The dataclass is ``frozen`` so callers cannot accidentally mutate the
    structure between the registry returning it and the router consuming
    it. ``events`` is a list (not tuple) because the router will commonly
    iterate-and-send rather than hash; consumers MUST treat it as
    read-only.

    Attributes:
        mode: ``"new"`` only when a brand-new session was just created and
            there was nothing to replay — otherwise ``"resume"``.
        recoverable: ``True`` iff resume can produce a coherent client
            state, either from the in-memory ring buffer, the persisted
            JSONL event log, or a checkpoint loaded from disk. ``False``
            signals that the client should fall back to a clean start (the
            design's "session_info {recoverable: false}" path).
        events: Envelopes with ``seq > last_seq`` that the registry can
            replay, in ascending ``seq`` order. May be empty when the
            session is brand-new or when ``last_seq`` already matches the
            most recent emitted ``seq``. On the cold path the list is
            merged from the persisted JSONL log and the in-memory ring,
            deduplicated by ``seq``.
        next_seq: The :attr:`Session.next_seq` of the (now-existing)
            session. The router uses this to know what value the next live
            event will carry — useful when stitching replay output with
            live emission or when reporting back to the UI in
            ``session_info``.
        checkpoint: Optional :class:`Checkpoint` loaded from a supplied
            :class:`CheckpointStore` when ``last_seq`` is too old for the
            ring buffer or no in-memory session exists. The router and
            agent code consume ``checkpoint.cognitive_state`` /
            ``checkpoint.phases`` to rebuild runtime state; this module
            never inspects those fields itself.
    """

    mode: Literal["new", "resume"]
    recoverable: bool
    events: list[dict[str, Any]]
    next_seq: int
    checkpoint: "Checkpoint | None"


class Session:
    """Per-session state container.

    A :class:`Session` owns the monotonic ``next_seq`` counter that the
    :class:`agent.event_stream.EventBus` reads from when stamping outgoing
    envelopes, and a bounded ring buffer of the most recent events emitted on
    the session's channel.

    Attributes:
        session_id: Stable identifier of the session, immutable for the
            lifetime of the object. Matches the ``session_id`` field of every
            envelope stored in the buffer.
        workspace: Optional filesystem root associated with the session. May
            be ``None`` for sessions created before a workspace is selected
            (e.g. while the user is still picking a repository).

    The ``next_seq`` and ``events`` accessors are read-only. Mutation goes
    through :meth:`append_event` so the two stay in sync.

    Socket attachment (subtask 4.2):
        :meth:`attach_socket` and :meth:`detach_socket` bind a single live
        WebSocket to the session for the duration of one connect/disconnect
        cycle. While a socket is attached, :meth:`enqueue_event` also pushes
        the envelope into :attr:`outbound_queue` so a sender task can forward
        it to the wire. The queue is **unbounded** — see the module docstring
        and Requirement 11.2 for the rationale.

    Heartbeat (subtask 4.3):
        :meth:`start_heartbeat` spawns a background asyncio task that emits a
        ``heartbeat`` event every ``interval`` seconds (default
        :data:`HEARTBEAT_INTERVAL_SECONDS`) by awaiting the caller-supplied
        ``sink`` with ``self.session_id``. The task exits cleanly when the
        socket is detached (``self.socket is None``) or when
        :meth:`stop_heartbeat` cancels it. The session never imports
        :class:`agent.event_stream.EventBus`; envelope construction is the
        sink's responsibility. See Requirement 3.6.
    """

    __slots__ = (
        "session_id",
        "workspace",
        "runs_dir",
        "_next_seq",
        "_events",
        "socket",
        "outbound_queue",
        "socket_lock",
        "heartbeat_task",
    )

    def __init__(
        self,
        session_id: str,
        *,
        workspace: Path | None = None,
        runs_dir: Path | None = None,
    ) -> None:
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self.session_id: str = session_id
        self.workspace: Path | None = workspace
        #: Root directory under which the persisted event log is written, or
        #: ``None`` to disable disk persistence (the default for ad-hoc
        #: ``Session`` instances created in tests). When set, every envelope
        #: passing through :meth:`enqueue_event` is appended to
        #: ``runs_dir/<session_id>/events.jsonl`` so a future cold-path
        #: ``resume`` can recover events that have already aged out of the
        #: ring buffer (Requirement 3.4 / 7.4).
        self.runs_dir: Path | None = runs_dir
        self._next_seq: int = 0
        self._events: collections.deque[dict[str, Any]] = collections.deque(
            maxlen=RING_BUFFER_CAPACITY
        )
        #: The currently attached WebSocket (or any duck-typed transport).
        #: ``None`` means the session is detached and any outbound events are
        #: only buffered in the ring for future replay. Typed as ``Any`` so the
        #: registry stays free of a hard FastAPI/Starlette import.
        self.socket: Any | None = None
        #: Outbound queue for the WebSocket sender task. Populated only while a
        #: socket is attached; ``None`` when detached so accidental enqueues
        #: from background tasks turn into a clean no-op rather than leaking
        #: into a stale queue. Created **without ``maxsize``** (unbounded) —
        #: design forbids dropping events under backpressure.
        self.outbound_queue: asyncio.Queue[dict[str, Any]] | None = None
        #: Serializes :meth:`attach_socket` / :meth:`detach_socket` so two
        #: concurrent connect attempts cannot both observe ``socket is None``
        #: and end up bound to the same session.
        self.socket_lock: asyncio.Lock = asyncio.Lock()
        #: Background heartbeat task (subtask 4.3). ``None`` when no heartbeat
        #: is running. Owned exclusively by :meth:`start_heartbeat` /
        #: :meth:`stop_heartbeat`; external code must not cancel or replace
        #: it directly.
        self.heartbeat_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Read-only views
    # ------------------------------------------------------------------

    @property
    def next_seq(self) -> int:
        """The next ``seq`` value that the :class:`EventBus` will stamp.

        Starts at ``0`` and advances to ``max(seq) + 1`` for the highest
        ``seq`` ever stored via :meth:`append_event`. Exposed as a property so
        callers cannot mutate it directly — the only legal way to advance it
        is by appending a stamped envelope through :meth:`append_event`.
        """

        return self._next_seq

    @property
    def events(self) -> collections.deque[dict[str, Any]]:
        """Read-only view of the in-memory ring buffer.

        Returns the underlying :class:`collections.deque` for zero-copy
        iteration; callers MUST NOT mutate it. The buffer holds at most
        :data:`RING_BUFFER_CAPACITY` (1024) most recent envelopes; older ones
        are evicted automatically.
        """

        return self._events

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def append_event(self, envelope: Mapping[str, Any]) -> None:
        """Store a fully-stamped envelope in the ring buffer.

        The :class:`agent.event_stream.EventBus` is responsible for stamping
        ``seq``, ``ts`` and the rest of the envelope before handing it to the
        registry. This method only stores the envelope and keeps
        :attr:`next_seq` consistent: after the call, ``next_seq`` is at least
        ``envelope["seq"] + 1``.

        Args:
            envelope: A JSON-compatible mapping with at minimum a non-negative
                integer ``seq`` field. The mapping is stored as a plain
                ``dict`` shallow copy so later mutations by the caller cannot
                corrupt the buffer.

        Raises:
            ValueError: ``seq`` is missing, not an ``int`` or negative.
        """

        seq = envelope.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise ValueError(
                f"envelope must carry a non-negative int seq, got {seq!r}"
            )

        self._events.append(dict(envelope))
        if seq >= self._next_seq:
            self._next_seq = seq + 1

    # ------------------------------------------------------------------
    # Socket lifecycle (subtask 4.2)
    # ------------------------------------------------------------------

    async def attach_socket(self, socket: Any) -> None:
        """Bind a live transport to the session and create the outbound queue.

        Exactly one socket may be attached at a time. The caller (typically
        the ``/api/agent/ws`` route handler) is expected to spawn a sender
        task that consumes :attr:`outbound_queue` and forwards events to the
        wire; that task is owned by the route handler, not by the session.

        Args:
            socket: Any object that the route handler will use to send events
                (a Starlette/FastAPI ``WebSocket`` in production, a stub in
                tests). Stored as :attr:`socket` for the route handler's
                reference; this module does not call any methods on it.

        Raises:
            RuntimeError: a socket is already attached. The route handler
                must :meth:`detach_socket` first (e.g. on the previous
                connection's ``WebSocketDisconnect``) before reattaching.
        """

        async with self.socket_lock:
            if self.socket is not None:
                raise RuntimeError(
                    f"session {self.session_id!r} already has an attached socket; "
                    "detach the previous socket before attaching a new one"
                )
            # Unbounded by design — Requirement 11.2 forbids dropping events
            # under backpressure. A slow consumer pays in memory, not in lost
            # events. The ring buffer remains the bounded recent-events store
            # used for replay (see :data:`RING_BUFFER_CAPACITY`).
            self.outbound_queue = asyncio.Queue()
            self.socket = socket

    async def detach_socket(self) -> None:
        """Unbind the current transport. Safe to call when already detached.

        Sets :attr:`socket` and :attr:`outbound_queue` back to ``None``. The
        ring buffer of recent events is preserved so a future ``resume`` can
        replay missed events. Background tasks owned by the session
        (heartbeat, agent run) are intentionally **not** cancelled here —
        Requirement 3.6 says the session keeps running while the UI is
        disconnected; cancellation is handled at a higher level when the
        session itself is torn down (subtask 4.3 onward).
        """

        async with self.socket_lock:
            # Drop references to the queue first so any enqueue racing with
            # detach observes ``outbound_queue is None`` and falls back to the
            # ring-buffer-only path. We do not drain remaining items: their
            # consumer (the sender task) is gone, and the events are still in
            # the ring buffer for a subsequent resume.
            self.outbound_queue = None
            self.socket = None

    async def enqueue_event(self, envelope: Mapping[str, Any]) -> None:
        """Record an envelope in the ring buffer and, if attached, queue it.

        This is the single entry point that :class:`SessionRegistry.deliver`
        and the WebSocket router use when an event needs to reach the client.
        Whether or not a socket is attached, the envelope is appended to the
        ring buffer so a future ``resume`` can replay it. When a socket is
        attached, the same envelope is also pushed onto
        :attr:`outbound_queue` for the sender task to forward.

        ``put_nowait`` is safe here precisely because the queue is unbounded:
        it never raises :class:`asyncio.QueueFull`. We do not use bounded
        ``put_nowait``-with-drop semantics — Requirement 11.2 is explicit
        that backpressure must be lossless.

        Args:
            envelope: A fully-stamped envelope (``seq`` already assigned by
                the bus). Same shape constraints as :meth:`append_event`.
        """

        self.append_event(envelope)
        # Persist to disk (best-effort) before queuing for the wire so a
        # crash between ``put_nowait`` and the actual flush still leaves a
        # recoverable trail in ``events.jsonl``. Failures are swallowed —
        # the ring buffer already holds the envelope and the WebSocket
        # sender task does not depend on disk persistence (Req 3.4 / 7.4).
        self.append_to_event_log(dict(envelope))
        # Snapshot the queue reference under the lock-free fast path so a
        # concurrent detach cannot null it out between the check and the put.
        queue = self.outbound_queue
        if queue is not None:
            queue.put_nowait(dict(envelope))

    # ------------------------------------------------------------------
    # Persisted event log (subtask 4.5)
    # ------------------------------------------------------------------

    def event_log_path(self) -> Path | None:
        """Return the JSONL log path for this session, or ``None`` if disabled.

        The path is ``<runs_dir>/<session_id>/events.jsonl``. ``None`` is
        returned when no ``runs_dir`` was configured (typically a bare
        :class:`Session` constructed by tests that do not exercise disk
        persistence). Callers can use ``is None`` as a feature flag without
        touching the filesystem.
        """

        if self.runs_dir is None:
            return None
        return self.runs_dir / self.session_id / "events.jsonl"

    def append_to_event_log(self, envelope: Mapping[str, Any]) -> None:
        """Append a single envelope as one JSON line to the persisted log.

        Best-effort durability: the ring buffer already has the envelope at
        this point and is the authoritative source for live and warm-replay
        traffic, so any :class:`OSError` (disk full, permission denied,
        path conflict, …) is logged at warning level and swallowed instead
        of being raised. The disk log is consulted only on the cold-replay
        path, where missing entries simply degrade resume back to the
        in-memory tail (and the optional checkpoint).

        The envelope is serialized with ``ensure_ascii=False`` and written
        in a single ``write`` call followed by a newline so a partial line
        on truncation is still detectable (the JSON parser will reject the
        trailing fragment) and so the file remains a valid JSONL stream.
        Concurrent appends from a single event loop are naturally
        serialized — :meth:`enqueue_event` is the only caller and runs on
        the same loop as the bus.

        Args:
            envelope: A fully-stamped envelope. Same shape as the entries
                in :attr:`events`. Must be JSON-serializable; non-JSON
                values cause a :class:`TypeError` from :func:`json.dumps`,
                which is treated like any other persistence failure (logged
                and swallowed) so a misconfigured emission cannot wedge the
                live channel.
        """

        log_path = self.event_log_path()
        if log_path is None:
            return
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(envelope, ensure_ascii=False)
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
        except OSError as exc:
            # Disk-side failure: log and move on. The ring buffer remains
            # the source of truth for the live channel.
            logger.warning(
                "session %s: failed to append to event log %s: %s",
                self.session_id,
                log_path,
                exc,
            )
        except (TypeError, ValueError) as exc:
            # Non-JSON envelope or malformed data: surface in logs but do
            # not raise — emission must not be blocked by persistence.
            logger.warning(
                "session %s: failed to serialize envelope for event log: %s",
                self.session_id,
                exc,
            )

    def read_event_log(self, since_seq: int) -> list[dict[str, Any]]:
        """Read persisted envelopes with ``seq > since_seq`` from disk.

        Used by :meth:`SessionRegistry.resume` on the cold path to fill the
        gap between ``last_seq`` and the buffer's oldest entry. Returns an
        empty list when no log exists for this session (either ``runs_dir``
        is unset or the file has not been created yet) — the caller treats
        that as "nothing recoverable from disk" and proceeds with whatever
        the ring buffer / checkpoint can offer.

        Malformed JSONL lines are skipped with a warning rather than
        aborting the read: an interrupted append may leave a partial last
        line, and we want the rest of the log to remain replayable. Lines
        without a non-negative integer ``seq`` field are likewise skipped.

        Args:
            since_seq: Only envelopes with ``seq > since_seq`` are returned.
                Pass a negative value (e.g. ``-1``) to read the entire log.

        Returns:
            Envelopes in the order they appear on disk. Sorting and
            deduplication relative to the in-memory buffer is the caller's
            responsibility (see :meth:`SessionRegistry.resume`).
        """

        log_path = self.event_log_path()
        if log_path is None or not log_path.exists():
            return []

        events: list[dict[str, Any]] = []
        try:
            with log_path.open("r", encoding="utf-8") as handle:
                for line_no, raw in enumerate(handle, start=1):
                    line = raw.strip()
                    if not line:
                        continue
                    try:
                        envelope = json.loads(line)
                    except json.JSONDecodeError:
                        # Partial / corrupted line — most often the trailing
                        # fragment of an interrupted append. Skip and keep
                        # going; do not block recovery on log integrity.
                        logger.warning(
                            "session %s: malformed JSONL line %d in %s, skipping",
                            self.session_id,
                            line_no,
                            log_path,
                        )
                        continue
                    if not isinstance(envelope, dict):
                        continue
                    seq = envelope.get("seq")
                    if (
                        not isinstance(seq, int)
                        or isinstance(seq, bool)
                        or seq < 0
                    ):
                        continue
                    if seq > since_seq:
                        events.append(envelope)
        except OSError as exc:
            logger.warning(
                "session %s: failed to read event log %s: %s",
                self.session_id,
                log_path,
                exc,
            )
            return []
        return events

    # ------------------------------------------------------------------
    # Heartbeat lifecycle (subtask 4.3)
    # ------------------------------------------------------------------

    async def start_heartbeat(
        self,
        *,
        interval: float = HEARTBEAT_INTERVAL_SECONDS,
        sink: HeartbeatSink,
    ) -> None:
        """Start the background heartbeat task.

        Spawns an :class:`asyncio.Task` that loops while a socket is attached.
        Each iteration sleeps for ``interval`` seconds and then awaits
        ``sink(self.session_id)`` to emit a single ``heartbeat`` event. The
        sink is responsible for building the actual envelope (typically by
        calling ``EventBus.heartbeat()``); this method only drives the cadence
        and lifecycle.

        The loop exits — without raising — when:

        * :attr:`socket` is ``None`` at the start of an iteration (i.e. the
          socket was detached between ticks),
        * the task is cancelled via :meth:`stop_heartbeat` (or because the
          event loop is shutting down),
        * the sink itself raises: the exception is suppressed and the loop
          terminates so a misbehaving sink cannot wedge the session. The
          caller (the WebSocket router) is expected to log such failures
          through its own diagnostics path before they reach this method.

        Args:
            interval: Seconds between heartbeats. Must be a positive finite
                number; the design doc and Requirement 3.6 mandate the
                10–15 s window, so this is the recommended range, but the
                method does not hard-enforce it (tests may use shorter
                intervals).
            sink: Async callable ``(session_id) -> None`` that emits the
                heartbeat event. The callable is invoked **after** the sleep
                so the first heartbeat fires one ``interval`` after the
                socket attaches, not immediately — this avoids piling a
                heartbeat on top of the initial ``session_info`` burst.

        Raises:
            ValueError: ``interval`` is not strictly positive or finite.
            RuntimeError: a heartbeat task is already running for this
                session. Callers must :meth:`stop_heartbeat` first.
        """

        if not (interval > 0) or interval != interval or interval == float("inf"):
            # Reject NaN, +inf, zero, negative values up-front — an
            # ``asyncio.sleep`` with these would either spin or hang forever.
            raise ValueError(
                f"interval must be a positive finite number of seconds, got {interval!r}"
            )
        if self.heartbeat_task is not None and not self.heartbeat_task.done():
            raise RuntimeError(
                f"session {self.session_id!r} already has a running heartbeat task; "
                "stop_heartbeat() before starting a new one"
            )

        async def _loop() -> None:
            try:
                while True:
                    await asyncio.sleep(interval)
                    # Re-check the socket *after* the sleep: if the session
                    # was detached while we were waiting, we must not emit
                    # another heartbeat (Requirement 3.6: heartbeats only
                    # fire while the channel is open).
                    if self.socket is None:
                        return
                    try:
                        await sink(self.session_id)
                    except asyncio.CancelledError:
                        # Cancellation propagates to the outer ``except`` so
                        # the task ends promptly without a stray emission.
                        raise
                    except Exception:
                        # A misbehaving sink must not wedge the session.
                        # Exit the loop; the route handler owns its own
                        # error reporting via diagnostics. Re-attaching the
                        # socket will spawn a fresh heartbeat task.
                        return
            except asyncio.CancelledError:
                # Standard cooperative-cancel exit; do not re-raise so
                # callers awaiting the task on detach see a clean finish.
                return

        self.heartbeat_task = asyncio.create_task(
            _loop(),
            name=f"session-heartbeat:{self.session_id}",
        )

    async def stop_heartbeat(self) -> None:
        """Cancel the heartbeat task if one is running. Safe when idle.

        Awaits the task to finish so the caller can rely on no further
        heartbeat envelopes being enqueued after this method returns. A
        completed task is left as-is; only running tasks are cancelled.
        Cancellation is suppressed (the task's ``CancelledError`` is caught
        by :meth:`start_heartbeat`'s loop), so this method never raises.
        """

        task = self.heartbeat_task
        if task is None:
            return
        if not task.done():
            task.cancel()
            # Wait for the task to acknowledge cancellation. The inner loop
            # swallows ``CancelledError``, so we should not see it here, but
            # we still guard against bare-cancellation propagation if the
            # task was cancelled before the ``try`` block was entered.
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.heartbeat_task = None


class SessionRegistry:
    """In-memory registry of active :class:`Session` objects.

    The registry is the single owner of session state inside the API process.
    Mutating operations (``get_or_create``) are serialized through an
    :class:`asyncio.Lock` so two concurrent WebSocket connects for the same
    ``session_id`` cannot race and create duplicate :class:`Session`
    instances.

    Read-only operations (:meth:`get`, :meth:`list_sessions`) are lock-free —
    Python's ``dict`` reads are atomic with respect to other reads under the
    GIL, and a stale snapshot is acceptable for these callers (they only need
    a consistent view at the moment of the call).

    Subsequent subtasks (4.3–4.5) attach heartbeat tasks and replay/resume
    logic to this same registry without changing the surface introduced here.
    """

    def __init__(self, *, runs_dir: Path | None = None) -> None:
        self._sessions: dict[str, Session] = {}
        self._lock: asyncio.Lock = asyncio.Lock()
        #: Root directory under which per-session ``events.jsonl`` files are
        #: written. Resolved eagerly to an absolute path against the current
        #: working directory so a later ``os.chdir`` cannot retarget existing
        #: sessions to a different on-disk location. ``None`` is never
        #: stored — callers that pass ``None`` (the default) get the repo-
        #: standard ``./.sharrowkin/runs/`` resolved once at construction
        #: time.
        self.runs_dir: Path = (
            Path(runs_dir) if runs_dir is not None else (Path.cwd() / _DEFAULT_RUNS_DIR)
        )

    async def get_or_create(
        self,
        session_id: str,
        *,
        workspace: Path | None = None,
    ) -> Session:
        """Return the existing session or create a fresh one.

        Args:
            session_id: Stable session identifier. Must be non-empty.
            workspace: Optional workspace path to associate with a freshly
                created session. Ignored when an existing session is
                returned — its workspace is preserved as-is so callers cannot
                accidentally rebind a running session to a different
                directory.

        Returns:
            The existing :class:`Session` if one is already registered for
            ``session_id``, otherwise a newly created and registered one.
        """

        if not session_id:
            raise ValueError("session_id must be a non-empty string")

        async with self._lock:
            existing = self._sessions.get(session_id)
            if existing is not None:
                return existing
            session = Session(
                session_id=session_id,
                workspace=workspace,
                runs_dir=self.runs_dir,
            )
            self._sessions[session_id] = session
            return session

    def get(self, session_id: str) -> Session | None:
        """Return the session for ``session_id`` if registered, else ``None``.

        This is a read-only lookup; it does not create a new session and does
        not need the lock.
        """

        return self._sessions.get(session_id)

    def list_sessions(self) -> list[str]:
        """Return a snapshot of currently registered session ids.

        The returned list is a copy and is safe to iterate without holding the
        registry lock. Insertion/eviction concurrent with the call may not be
        reflected, which is acceptable for diagnostic and admin callers.
        """

        return list(self._sessions.keys())

    # ------------------------------------------------------------------
    # Socket lifecycle (subtask 4.2 / 4.3)
    # ------------------------------------------------------------------

    async def attach_socket(
        self,
        session_id: str,
        socket: Any,
        *,
        heartbeat_sink: HeartbeatSink | None = None,
        heartbeat_interval: float = HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        """Attach a transport to ``session_id``, creating the session if new.

        Thin wrapper around :meth:`Session.attach_socket` that also ensures
        the session exists. Workspace is left ``None`` if the session is
        being created here — callers that already know the workspace should
        call :meth:`get_or_create` first.

        When ``heartbeat_sink`` is supplied (subtask 4.3), a background
        heartbeat task is started after the attach succeeds. The sink is the
        bridge between the registry and the
        :class:`agent.event_stream.EventBus`: the registry passes only
        ``session_id`` and the sink builds and emits the envelope. The task
        is automatically cancelled by :meth:`detach_socket` before the
        socket reference is cleared, so callers do not have to manage its
        lifetime explicitly.

        Args:
            session_id: Target session id. Created if not yet registered.
            socket: Transport object to bind. See
                :meth:`Session.attach_socket`.
            heartbeat_sink: Optional async ``(session_id) -> None`` callable.
                ``None`` (default) keeps the legacy behaviour of subtask 4.2:
                no heartbeat is emitted from this session. Integration with
                the WebSocket router happens in task 7.
            heartbeat_interval: Seconds between heartbeats when the sink is
                provided. Defaults to :data:`HEARTBEAT_INTERVAL_SECONDS`
                (12 s, in the 10–15 s window from Requirement 3.6).

        Raises:
            RuntimeError: forwarded from :meth:`Session.attach_socket` when
                a socket is already attached to ``session_id``.
        """

        session = await self.get_or_create(session_id)
        await session.attach_socket(socket)
        if heartbeat_sink is not None:
            try:
                await session.start_heartbeat(
                    interval=heartbeat_interval, sink=heartbeat_sink
                )
            except Exception:
                # Roll back the attach so the session does not end up with
                # a live socket but no heartbeat — the caller can retry
                # cleanly. ``detach_socket`` is no-op-safe if start_heartbeat
                # never created the task.
                await session.detach_socket()
                raise

    async def detach_socket(self, session_id: str) -> None:
        """Detach the transport from ``session_id``. No-op if unknown.

        Stops the heartbeat task first (subtask 4.3) so no further heartbeat
        envelopes can be enqueued for a socket that is already going away,
        then unbinds the socket and clears the outbound queue. Detaching an
        unknown session is intentionally not an error: the WebSocket router
        calls this from a ``finally`` block and we do not want a missing-
        session race (e.g. teardown ordering on shutdown) to mask the
        original disconnect reason.
        """

        session = self._sessions.get(session_id)
        if session is None:
            return
        await session.stop_heartbeat()
        await session.detach_socket()

    async def deliver(
        self, session_id: str, envelope: Mapping[str, Any]
    ) -> None:
        """Deliver an envelope to ``session_id`` (ring buffer + outbound queue).

        Creates the session lazily if it does not exist yet so the
        :class:`agent.event_stream.EventBus` can emit the very first
        ``session_info`` event without a separate registration step. The
        envelope is stored in the ring buffer regardless of socket state and
        queued for the sender task only when a socket is attached.
        """

        session = await self.get_or_create(session_id)
        await session.enqueue_event(envelope)

    # ------------------------------------------------------------------
    # Resume (subtask 4.4 / 4.5)
    # ------------------------------------------------------------------

    async def resume(
        self,
        session_id: str,
        last_seq: int,
        *,
        checkpoint_store: "CheckpointStore | None" = None,
    ) -> ReplayResult:
        """Resolve a client-side ``resume`` request into a :class:`ReplayResult`.

        Implements the three resume paths described in the design doc
        (section "Sequencing & resume"):

        * **Warm replay (in-memory)** — when an :class:`Session` exists for
          ``session_id`` and ``last_seq + 1`` is still ≥ the oldest ``seq``
          in the ring buffer, all envelopes with ``seq > last_seq`` are
          returned directly. ``checkpoint`` is left ``None`` because the
          buffer alone is sufficient for a coherent UI replay.
        * **Cold replay (disk + checkpoint fallback)** — when the buffer's
          oldest ``seq`` is already greater than ``last_seq + 1`` (or the
          session does not exist in memory at all), the in-memory tail is
          no longer enough to bridge the gap. The persisted JSONL log
          (``runs_dir/<session_id>/events.jsonl``) is read and merged with
          whatever the buffer still has, deduplicated by ``seq`` (disk
          version preferred for stability across restarts, since the buffer
          may be empty after a crash). If a ``checkpoint_store`` is
          supplied, the latest checkpoint is also loaded so the agent's
          cognitive state can be restored on top of the replayed events.
          ``recoverable`` is ``True`` whenever the merged event tail is
          non-empty *or* a checkpoint is available — both signals mean the
          caller has something useful to send to the UI (Req 3.4 / 7.4).
        * **No in-memory session, no disk log, no checkpoint** — a clean
          session is created and ``ReplayResult(mode="new",
          recoverable=False, ...)`` is returned so the WebSocket router can
          answer ``session_info {mode: "new"}`` to the UI.

        Args:
            session_id: Stable session identifier from the client's
                ``resume`` message. Must be non-empty.
            last_seq: Highest ``seq`` the client has already applied.
                Negative values (e.g. ``-1`` for "I have nothing yet") are
                treated as "before any event" — every event with
                ``seq > last_seq`` is replayed.
            checkpoint_store: Optional :class:`CheckpointStore` used to
                recover cognitive state on the cold path. ``None`` keeps
                the resume disk-only: cold replays still benefit from the
                persisted JSONL log even without a checkpoint.

        Returns:
            A :class:`ReplayResult` describing the outcome. The session
            referenced by ``session_id`` is guaranteed to exist in the
            registry on return — even in the ``mode="new"`` branch — so
            the caller can immediately :meth:`attach_socket` afterwards.

        Raises:
            ValueError: ``session_id`` is empty.
        """

        if not session_id:
            raise ValueError("session_id must be a non-empty string")

        session = self.get(session_id)

        # Warm path: the in-memory ring still covers ``last_seq + 1``. We
        # do not touch the disk log here — the buffer is authoritative for
        # everything it still holds, and avoiding the read keeps the hot
        # resume path allocation-light.
        if session is not None and len(session.events) > 0:
            oldest_seq = session.events[0]["seq"]
            if last_seq + 1 >= oldest_seq:
                events = [
                    dict(envelope)
                    for envelope in session.events
                    if envelope["seq"] > last_seq
                ]
                return ReplayResult(
                    mode="resume",
                    recoverable=True,
                    events=events,
                    next_seq=session.next_seq,
                    checkpoint=None,
                )

        # Cold path: either no session in memory, an empty buffer (e.g.
        # right after a process restart), or ``last_seq`` is older than
        # what the ring buffer remembers. Merge the persisted JSONL log
        # with whatever the buffer still has and load a checkpoint if one
        # is available. The session is materialised first so
        # ``read_event_log`` can see the configured ``runs_dir`` and so
        # the caller can ``attach_socket`` immediately on return.
        checkpoint = (
            checkpoint_store.load_latest(session_id)
            if checkpoint_store is not None
            else None
        )
        workspace: Path | None = None
        if (
            session is None
            and checkpoint is not None
            and checkpoint.workspace
        ):
            # Materialise with the workspace recorded in the checkpoint so
            # downstream code paths see the same workspace the agent was
            # running against before the crash.
            workspace = Path(checkpoint.workspace)
        session = await self.get_or_create(session_id, workspace=workspace)

        # Disk events first so they can act as the deduplication anchor
        # across restarts: after a process bounce the buffer is empty,
        # while the JSONL log retains everything ever emitted.
        disk_events = session.read_event_log(since_seq=last_seq)
        memory_events = [
            dict(envelope)
            for envelope in session.events
            if envelope["seq"] > last_seq
        ]

        # Dedupe by ``seq`` — disk wins for any collision so the replay is
        # stable across cold/warm boundaries (the disk record was written
        # synchronously the first time the envelope passed through
        # ``enqueue_event``, before any in-memory mutation could shadow it).
        merged: dict[int, dict[str, Any]] = {}
        for envelope in memory_events:
            seq = envelope.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
                merged[seq] = envelope
        for envelope in disk_events:
            seq = envelope.get("seq")
            if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
                merged[seq] = envelope
        combined_events = [merged[seq] for seq in sorted(merged)]

        # If the disk log carries envelopes whose ``seq`` is at or beyond
        # the live ``next_seq`` (e.g. after a crash that lost the in-memory
        # counter), advance the counter so subsequent live emissions do
        # not collide with the replayed tail.
        if combined_events:
            highest_seq = combined_events[-1]["seq"]
            if highest_seq + 1 > session.next_seq:
                # ``Session._next_seq`` is private but this module owns it;
                # advancing it keeps :class:`EventBus`'s next stamp aligned
                # with what the client has already applied.
                session._next_seq = highest_seq + 1

        recoverable = bool(combined_events) or checkpoint is not None
        if not recoverable:
            # Truly nothing to recover: empty buffer, empty disk log, no
            # checkpoint. Behave like a brand-new session so the UI can
            # render a clean start.
            return ReplayResult(
                mode="new",
                recoverable=False,
                events=[],
                next_seq=session.next_seq,
                checkpoint=None,
            )

        return ReplayResult(
            mode="resume",
            recoverable=True,
            events=combined_events,
            next_seq=session.next_seq,
            checkpoint=checkpoint,
        )

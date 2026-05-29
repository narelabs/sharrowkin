"""Event_Stream contract: envelope, payloads, canonical enums and EventBus.

This module defines the wire-level schema between the agent backend and the UI
client. Every event emitted by the agent is wrapped into an :class:`EventEnvelope`
with a fixed schema version (``v=1``), monotonic ``seq`` per session, ISO-8601
timestamp and a typed ``payload``.

It also exposes :class:`EventBus`, the single object responsible for:

* allocating monotonic per-session ``seq`` numbers,
* validating each payload against its pydantic model before emission,
* building the envelope (with ``v``, ``session_id``, ``seq``, ``ts``) and
  passing the JSON-compatible ``dict`` to an injected async ``sink``,
* providing typed helpers (``phase_change``, ``status``, ``thinking``,
  ``tool_call``, ``log``, ``heartbeat``, ``agent_complete``, ...) for the rest
  of the agent so phases never construct envelopes by hand.

The schema is the single source of truth shared with the UI side
(``ui/lib/agent-stream/schema.ts``), so any change here must be mirrored there.

References:
    Design doc: ``.kiro/specs/ui-and-agent-stabilization/design.md`` (section
    "Event_Stream contract" and "Components and Interfaces > Backend").
    Requirements: 8.1, 8.2, 8.3, 8.6, 8.7, 13.4.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Any, Awaitable, Callable, Literal, Mapping, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    NonNegativeInt,
    ValidationError,
    field_validator,
)


# =============================================================================
# Schema version
# =============================================================================

#: Current schema version. The envelope ``v`` field MUST equal this value.
#: A bump invalidates older clients and requires explicit migration on both
#: backend and UI sides.
SCHEMA_VERSION: int = 1


# =============================================================================
# Canonical enums
# =============================================================================


class PhaseId(str, Enum):
    """Canonical phase identifier (lowercase).

    Mirrors the five-stage cognitive cycle of :class:`agent.core.SharrowkinAgent`.
    """

    OBSERVE = "observe"
    RECALL = "recall"
    REASON = "reason"
    STABILIZE = "stabilize"
    COMMIT = "commit"


class PhaseStatus(str, Enum):
    """Lifecycle status of a single phase."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


class AgentStatus(str, Enum):
    """Top-level agent status surfaced in the UI Status_Indicator.

    Values are kept aligned with the UI type
    (``ui/components/chat/agent-status-badge.tsx``) so a backend value can be
    rendered without translation.
    """

    IDLE = "idle"
    CONNECTING = "connecting"
    RUNNING = "running"
    THINKING = "thinking"
    STABILIZING = "stabilizing"
    DONE = "done"
    ERROR = "error"
    STOPPED = "stopped"


class LogLevel(str, Enum):
    """Severity for structured ``log`` events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class ToolCallStatus(str, Enum):
    """Lifecycle status of a tool invocation."""

    RUNNING = "running"
    DONE = "done"
    ERROR = "error"


class TaskStatus(str, Enum):
    """Status of a node in the UI task plan."""

    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    ERROR = "error"
    SKIPPED = "skipped"


class AgentOutcome(str, Enum):
    """Terminal outcome reported by ``agent_complete``."""

    DONE = "done"
    ERROR = "error"
    STOPPED = "stopped"


class SessionMode(str, Enum):
    """Mode of a ``session_info`` event."""

    NEW = "new"
    RESUME = "resume"


# =============================================================================
# Shared building blocks
# =============================================================================


class _Payload(BaseModel):
    """Base class for every event payload model.

    Forbids unknown fields so contract drift is detected eagerly. Allows enums
    to be supplied as their string values when constructed from JSON.
    """

    model_config = ConfigDict(
        extra="forbid",
        use_enum_values=False,
        validate_assignment=True,
        frozen=True,
    )


class RepoRef(_Payload):
    """Reference to a single repository surfaced to the user for selection."""

    id: str
    name: str
    full_name: str
    description: str = ""
    language: str = ""
    private: bool = False
    url: str
    stars: int | None = None


# =============================================================================
# Payload models (one per event type)
# =============================================================================


class SessionInfoPayload(_Payload):
    """Payload for ``session_info``.

    Emitted on session start (``mode=new``) or after a successful resume
    (``mode=resume``). ``last_seq`` and ``recoverable`` are only meaningful for
    resume.
    """

    mode: SessionMode
    last_seq: NonNegativeInt | None = None
    recoverable: bool | None = None


class PhaseChangePayload(_Payload):
    """Payload for ``phase_change``: a phase entered, finished, or errored."""

    phase: PhaseId
    status: PhaseStatus
    reason: str | None = None


class StatusPayload(_Payload):
    """Payload for ``status``: global Status_Indicator update."""

    status: AgentStatus
    message: str | None = None
    runtime_ms: NonNegativeInt | None = None


class ThinkingPayload(_Payload):
    """Payload for ``thinking``: live reasoning stream.

    ``delta=True`` means ``text`` is an incremental chunk to be appended; ``False``
    means it replaces the current buffer.
    """

    text: str
    delta: bool = True


class ContentPayload(_Payload):
    """Payload for ``content``: assistant content (final or streaming)."""

    text: str
    done: bool = False


class ToolCallPayload(_Payload):
    """Payload for ``tool_call``: a tool invocation lifecycle event."""

    tool_id: str
    name: str
    status: ToolCallStatus
    error: str | None = None


class ToolActivityPayload(_Payload):
    """Payload for ``tool_activity``: progress signal from a running tool."""

    tool_id: str
    progress: float | None = Field(default=None, ge=0.0, le=1.0)
    target: str | None = None


class TaskUpdatePayload(_Payload):
    """Payload for ``task_update``: status update for a task plan node."""

    task_id: str
    status: TaskStatus
    parent_id: str | None = None


class LogPayload(_Payload):
    """Payload for ``log``: structured diagnostic message."""

    level: LogLevel
    message: str
    code: str | None = None
    phase: PhaseId | None = None
    details: dict[str, Any] | None = None


class ErrorPayload(_Payload):
    """Payload for ``error``: an interrupting error."""

    code: str
    message: str
    phase: PhaseId | None = None
    recoverable: bool = False


class HeartbeatPayload(_Payload):
    """Payload for ``heartbeat``: liveness signal on an open channel."""

    agent_alive: bool = True


class AgentCompletePayload(_Payload):
    """Payload for ``agent_complete``: terminal event of a Run_Session."""

    outcome: AgentOutcome
    runtime_ms: NonNegativeInt


class RepoSelectorPayload(_Payload):
    """Payload for ``repo_selector``: UI prompt with a list of repositories."""

    repos: list[RepoRef]
    prompt: str


# =============================================================================
# Discriminated envelopes (one wrapper per ``type`` literal)
# =============================================================================


class _EnvelopeBase(BaseModel):
    """Common envelope fields.

    Fields:
        v: Schema version, must equal :data:`SCHEMA_VERSION` (currently ``1``).
        type: Event type literal (set by each concrete subclass).
        session_id: Owning session id; events for different sessions never mix.
        seq: Monotonically increasing 0-based sequence number within ``session_id``.
        ts: ISO-8601 UTC timestamp (with ``Z`` suffix).
        payload: Strongly-typed payload model.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        frozen=True,
    )

    v: Literal[1] = SCHEMA_VERSION  # type: ignore[assignment]
    session_id: str = Field(min_length=1)
    seq: NonNegativeInt
    ts: str

    @field_validator("ts")
    @classmethod
    def _validate_ts(cls, value: str) -> str:
        """Accept any ISO-8601 string parseable by :func:`datetime.fromisoformat`.

        ``Z`` suffix is normalized to ``+00:00`` for parsing only; the original
        string is preserved so round-trip serialization is stable.
        """

        candidate = value.replace("Z", "+00:00") if value.endswith("Z") else value
        try:
            datetime.fromisoformat(candidate)
        except ValueError as exc:  # pragma: no cover - re-raised with context
            raise ValueError(f"ts is not a valid ISO-8601 timestamp: {value!r}") from exc
        return value


class SessionInfoEvent(_EnvelopeBase):
    type: Literal["session_info"] = "session_info"
    payload: SessionInfoPayload


class PhaseChangeEvent(_EnvelopeBase):
    type: Literal["phase_change"] = "phase_change"
    payload: PhaseChangePayload


class StatusEvent(_EnvelopeBase):
    type: Literal["status"] = "status"
    payload: StatusPayload


class ThinkingEvent(_EnvelopeBase):
    type: Literal["thinking"] = "thinking"
    payload: ThinkingPayload


class ContentEvent(_EnvelopeBase):
    type: Literal["content"] = "content"
    payload: ContentPayload


class ToolCallEvent(_EnvelopeBase):
    type: Literal["tool_call"] = "tool_call"
    payload: ToolCallPayload


class ToolActivityEvent(_EnvelopeBase):
    type: Literal["tool_activity"] = "tool_activity"
    payload: ToolActivityPayload


class TaskUpdateEvent(_EnvelopeBase):
    type: Literal["task_update"] = "task_update"
    payload: TaskUpdatePayload


class LogEvent(_EnvelopeBase):
    type: Literal["log"] = "log"
    payload: LogPayload


class ErrorEvent(_EnvelopeBase):
    type: Literal["error"] = "error"
    payload: ErrorPayload


class HeartbeatEvent(_EnvelopeBase):
    type: Literal["heartbeat"] = "heartbeat"
    payload: HeartbeatPayload


class AgentCompleteEvent(_EnvelopeBase):
    type: Literal["agent_complete"] = "agent_complete"
    payload: AgentCompletePayload


class RepoSelectorEvent(_EnvelopeBase):
    type: Literal["repo_selector"] = "repo_selector"
    payload: RepoSelectorPayload


#: Discriminated union of all valid envelopes. Use :data:`EventEnvelope` to
#: parse an arbitrary inbound event without knowing its ``type`` upfront::
#:
#:     from pydantic import TypeAdapter
#:     adapter = TypeAdapter(EventEnvelope)
#:     event = adapter.validate_python(raw_dict)
EventEnvelope = Annotated[
    Union[
        SessionInfoEvent,
        PhaseChangeEvent,
        StatusEvent,
        ThinkingEvent,
        ContentEvent,
        ToolCallEvent,
        ToolActivityEvent,
        TaskUpdateEvent,
        LogEvent,
        ErrorEvent,
        HeartbeatEvent,
        AgentCompleteEvent,
        RepoSelectorEvent,
    ],
    Field(discriminator="type"),
]


# =============================================================================
# Helpers
# =============================================================================


def utcnow_iso() -> str:
    """Return current UTC time as an ISO-8601 string with ``Z`` suffix.

    Convenience helper for ``ts`` field construction. Kept here so backend
    and tests share the same formatting and round-trip rules.
    """

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# =============================================================================
# EventBus
# =============================================================================


#: Async sink signature accepted by :class:`EventBus`. The sink receives a
#: JSON-compatible ``dict`` (already validated against the event schema) and is
#: expected to forward it to the underlying transport (WebSocket, in-process
#: queue, file log, ...).
EventSink = Callable[[Mapping[str, Any]], Awaitable[None]]


#: Lookup table mapping a ``type`` literal to its (payload, envelope) classes.
#: Defined after all classes so the references resolve at module load time.
_EVENT_REGISTRY: dict[str, tuple[type[_Payload], type[_EnvelopeBase]]] = {
    "session_info": (SessionInfoPayload, SessionInfoEvent),
    "phase_change": (PhaseChangePayload, PhaseChangeEvent),
    "status": (StatusPayload, StatusEvent),
    "thinking": (ThinkingPayload, ThinkingEvent),
    "content": (ContentPayload, ContentEvent),
    "tool_call": (ToolCallPayload, ToolCallEvent),
    "tool_activity": (ToolActivityPayload, ToolActivityEvent),
    "task_update": (TaskUpdatePayload, TaskUpdateEvent),
    "log": (LogPayload, LogEvent),
    "error": (ErrorPayload, ErrorEvent),
    "heartbeat": (HeartbeatPayload, HeartbeatEvent),
    "agent_complete": (AgentCompletePayload, AgentCompleteEvent),
    "repo_selector": (RepoSelectorPayload, RepoSelectorEvent),
}


class EventBus:
    """Sequencing and emission boundary between agent code and a transport sink.

    Responsibilities:
        * Allocate per-session monotonic ``seq`` numbers (0-based).
        * Validate every payload against its canonical pydantic model.
        * Build the envelope (``v=1``, ``session_id``, ``seq``, ``ts``, ``payload``).
        * Serialize the envelope to a JSON-compatible ``dict`` and pass it to
          the injected async ``sink`` (typically ``WebSocket.send_json``).
        * Convert any schema violation inside helpers into a ``log`` event of
          level ``error`` with ``code="schema_violation"`` instead of raising
          (Req 13.4).

    The bus is single-session: callers create one :class:`EventBus` per
    ``session_id``. Allocation of ``seq`` and delivery to the ``sink`` are
    serialized through an internal :class:`asyncio.Lock` so concurrent
    callers cannot reorder events on the wire.

    Attributes:
        session_id: Owning session identifier (non-empty).
        next_seq: The next ``seq`` number that will be allocated. After the
            bus has emitted ``n`` events successfully, ``next_seq == n``.

    Example:
        >>> async def sink(envelope): print(envelope)  # doctest: +SKIP
        >>> bus = EventBus("session_abc", sink)        # doctest: +SKIP
        >>> await bus.phase_change(PhaseId.OBSERVE, PhaseStatus.RUNNING)
    """

    def __init__(self, session_id: str, sink: EventSink) -> None:
        if not session_id:
            raise ValueError("session_id must be a non-empty string")
        self._session_id = session_id
        self._sink = sink
        self._seq = 0
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public read-only state
    # ------------------------------------------------------------------

    @property
    def session_id(self) -> str:
        """Owning session id, fixed for the lifetime of the bus."""

        return self._session_id

    @property
    def next_seq(self) -> int:
        """The next ``seq`` value that will be assigned on the next emit.

        Read-only; advances by one per successful emission (including the
        synthetic ``log`` event produced by a schema violation).
        """

        return self._seq

    # ------------------------------------------------------------------
    # Generic emit
    # ------------------------------------------------------------------

    async def emit(
        self,
        type: str,
        payload: Mapping[str, Any] | _Payload,
    ) -> None:
        """Validate, sequence and dispatch an event.

        Args:
            type: Canonical event type literal (e.g. ``"phase_change"``).
            payload: Either a mapping of payload fields or an already-built
                payload model instance of the matching class.

        Behavior:
            * On success the envelope is sent to the sink with the next
              available ``seq``.
            * On any schema violation (unknown ``type``, wrong payload class,
              ``ValidationError``) a ``log`` event of level ``error`` with
              ``code="schema_violation"`` is emitted instead. The original
              event is dropped.
            * Sink errors are **not** caught here — transport failures
              propagate to the caller so they can be handled by the
              ``SessionRegistry`` / WebSocket layer.
        """

        try:
            envelope_dict = self._build_envelope(type, payload)
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            await self._emit_schema_violation(type, exc)
            return

        await self._dispatch(envelope_dict)

    def _build_envelope(
        self,
        type: str,
        payload: Mapping[str, Any] | _Payload,
    ) -> dict[str, Any]:
        """Validate the payload and return a JSON-compatible envelope dict.

        The ``seq`` field is set to a placeholder ``0`` here; the real value
        is stamped under the lock in :meth:`_dispatch` so sequencing matches
        the order events reach the sink.
        """

        if type not in _EVENT_REGISTRY:
            raise KeyError(f"unknown event type: {type!r}")
        payload_cls, envelope_cls = _EVENT_REGISTRY[type]

        if isinstance(payload, _Payload):
            if not isinstance(payload, payload_cls):
                raise TypeError(
                    f"payload for type {type!r} must be {payload_cls.__name__}, "
                    f"got {payload.__class__.__name__}"
                )
            payload_model = payload
        else:
            payload_model = payload_cls.model_validate(dict(payload))

        envelope = envelope_cls(
            session_id=self._session_id,
            seq=0,
            ts=utcnow_iso(),
            payload=payload_model,
        )
        return envelope.model_dump(mode="json")

    async def _dispatch(self, envelope_dict: dict[str, Any]) -> None:
        """Allocate the next seq, stamp it, and forward to the sink.

        Held under :attr:`_lock` so concurrent emits cannot interleave the
        ``allocate seq → send`` pair, which would let the sink see events in a
        different order than their seq numbers.
        """

        async with self._lock:
            envelope_dict["seq"] = self._seq
            self._seq += 1
            await self._sink(envelope_dict)

    async def _emit_schema_violation(
        self,
        original_type: str,
        exc: BaseException,
    ) -> None:
        """Emit a controlled ``log`` event describing a schema violation.

        The replacement payload is built from values we fully control, so it
        cannot itself fail validation. Any sink error is allowed to propagate
        — that is a transport problem, not a schema one.
        """

        details: dict[str, Any] = {
            "rejected_type": original_type,
            "error": exc.__class__.__name__,
        }
        try:
            details["error_message"] = str(exc)[:1000]
        except Exception:  # pragma: no cover - defensive, str() should not fail
            details["error_message"] = "<unrepresentable>"

        log_payload = LogPayload(
            level=LogLevel.ERROR,
            message=f"schema violation while emitting {original_type!r}",
            code="schema_violation",
            phase=None,
            details=details,
        )
        envelope = LogEvent(
            session_id=self._session_id,
            seq=0,
            ts=utcnow_iso(),
            payload=log_payload,
        )
        await self._dispatch(envelope.model_dump(mode="json"))

    # ------------------------------------------------------------------
    # Typed helpers (one per common event type)
    #
    # All helpers route through :meth:`emit`, so they share the same
    # validation, sequencing and schema-violation fallback semantics.
    # Enum arguments may be passed as the enum itself or as its string value.
    # ------------------------------------------------------------------

    async def phase_change(
        self,
        phase: PhaseId | str,
        status: PhaseStatus | str,
        *,
        reason: str | None = None,
    ) -> None:
        """Emit ``phase_change``: a phase entered, finished, or errored."""

        await self.emit(
            "phase_change",
            {"phase": phase, "status": status, "reason": reason},
        )

    async def status(
        self,
        status: AgentStatus | str,
        *,
        message: str | None = None,
        runtime_ms: int | None = None,
    ) -> None:
        """Emit ``status``: top-level Status_Indicator update."""

        await self.emit(
            "status",
            {"status": status, "message": message, "runtime_ms": runtime_ms},
        )

    async def thinking(self, text: str, *, delta: bool = True) -> None:
        """Emit ``thinking``: incremental (``delta=True``) or full reasoning text."""

        await self.emit("thinking", {"text": text, "delta": delta})

    async def tool_call(
        self,
        tool_id: str,
        name: str,
        status: ToolCallStatus | str,
        *,
        error: str | None = None,
    ) -> None:
        """Emit ``tool_call``: a tool invocation lifecycle event."""

        await self.emit(
            "tool_call",
            {"tool_id": tool_id, "name": name, "status": status, "error": error},
        )

    async def log(
        self,
        level: LogLevel | str,
        message: str,
        *,
        code: str | None = None,
        phase: PhaseId | str | None = None,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Emit ``log``: structured diagnostic message."""

        await self.emit(
            "log",
            {
                "level": level,
                "message": message,
                "code": code,
                "phase": phase,
                "details": dict(details) if details is not None else None,
            },
        )

    async def heartbeat(self, *, agent_alive: bool = True) -> None:
        """Emit ``heartbeat``: periodic liveness signal on an open channel."""

        await self.emit("heartbeat", {"agent_alive": agent_alive})

    async def agent_complete(
        self,
        outcome: AgentOutcome | str,
        runtime_ms: int,
    ) -> None:
        """Emit ``agent_complete``: terminal event of a Run_Session."""

        await self.emit(
            "agent_complete",
            {"outcome": outcome, "runtime_ms": runtime_ms},
        )


__all__ = [
    "SCHEMA_VERSION",
    # Enums
    "PhaseId",
    "PhaseStatus",
    "AgentStatus",
    "LogLevel",
    "ToolCallStatus",
    "TaskStatus",
    "AgentOutcome",
    "SessionMode",
    # Building blocks
    "RepoRef",
    # Payloads
    "SessionInfoPayload",
    "PhaseChangePayload",
    "StatusPayload",
    "ThinkingPayload",
    "ContentPayload",
    "ToolCallPayload",
    "ToolActivityPayload",
    "TaskUpdatePayload",
    "LogPayload",
    "ErrorPayload",
    "HeartbeatPayload",
    "AgentCompletePayload",
    "RepoSelectorPayload",
    # Envelopes
    "SessionInfoEvent",
    "PhaseChangeEvent",
    "StatusEvent",
    "ThinkingEvent",
    "ContentEvent",
    "ToolCallEvent",
    "ToolActivityEvent",
    "TaskUpdateEvent",
    "LogEvent",
    "ErrorEvent",
    "HeartbeatEvent",
    "AgentCompleteEvent",
    "RepoSelectorEvent",
    "EventEnvelope",
    # Helpers
    "utcnow_iso",
    # Bus
    "EventSink",
    "EventBus",
]

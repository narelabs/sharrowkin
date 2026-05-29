/**
 * TypeScript types mirroring the backend event_stream.py contract.
 *
 * This file is the single source of truth for the UI side of the Event_Stream
 * protocol. Any change to `agent/event_stream.py` must be reflected here.
 *
 * Requirements: 8.1, 8.5
 */

// =============================================================================
// Canonical enums
// =============================================================================

export type PhaseId = "observe" | "recall" | "reason" | "stabilize" | "commit"
export type PhaseStatus = "pending" | "running" | "done" | "error" | "skipped"
export type AgentStatus = "idle" | "connecting" | "running" | "thinking" | "stabilizing" | "done" | "error" | "stopped"
export type ConnectionState = "online" | "reconnecting" | "offline"
export type LogLevel = "debug" | "info" | "warning" | "error"
export type ToolCallStatus = "running" | "done" | "error"
export type TaskStatus = "pending" | "running" | "done" | "error" | "skipped"
export type AgentOutcome = "done" | "error" | "stopped"
export type SessionMode = "new" | "resume"

// =============================================================================
// Event envelope
// =============================================================================

export interface AgentEvent<T extends string = string, P = unknown> {
  v: 1
  type: T
  session_id: string
  seq: number
  ts: string
  payload: P
}

// =============================================================================
// Payload types
// =============================================================================

export interface SessionInfoPayload {
  mode: SessionMode
  last_seq?: number | null
  recoverable?: boolean | null
}

export interface PhaseChangePayload {
  phase: PhaseId
  status: PhaseStatus
  reason?: string | null
}

export interface StatusPayload {
  status: AgentStatus
  message?: string | null
  runtime_ms?: number | null
}

export interface ThinkingPayload {
  text: string
  delta: boolean
}

export interface ContentPayload {
  text: string
  done: boolean
}

export interface ToolCallPayload {
  tool_id: string
  name: string
  status: ToolCallStatus
  error?: string | null
}

export interface ToolActivityPayload {
  tool_id: string
  progress?: number | null
  target?: string | null
}

export interface TaskUpdatePayload {
  task_id: string
  status: TaskStatus
  parent_id?: string | null
}

export interface LogPayload {
  level: LogLevel
  message: string
  code?: string | null
  phase?: PhaseId | null
  details?: Record<string, unknown> | null
}

export interface ErrorPayload {
  code: string
  message: string
  phase?: PhaseId | null
  recoverable: boolean
}

export interface HeartbeatPayload {
  agent_alive: boolean
}

export interface AgentCompletePayload {
  outcome: AgentOutcome
  runtime_ms: number
}

export interface RepoRef {
  id: string
  name: string
  full_name: string
  description?: string
  language?: string
  private?: boolean
  url: string
  stars?: number | null
}

export interface RepoSelectorPayload {
  repos: RepoRef[]
  prompt: string
}

// =============================================================================
// Typed event aliases
// =============================================================================

export type SessionInfoEvent = AgentEvent<"session_info", SessionInfoPayload>
export type PhaseChangeEvent = AgentEvent<"phase_change", PhaseChangePayload>
export type StatusEvent = AgentEvent<"status", StatusPayload>
export type ThinkingEvent = AgentEvent<"thinking", ThinkingPayload>
export type ContentEvent = AgentEvent<"content", ContentPayload>
export type ToolCallEvent = AgentEvent<"tool_call", ToolCallPayload>
export type ToolActivityEvent = AgentEvent<"tool_activity", ToolActivityPayload>
export type TaskUpdateEvent = AgentEvent<"task_update", TaskUpdatePayload>
export type LogEvent = AgentEvent<"log", LogPayload>
export type ErrorEvent = AgentEvent<"error", ErrorPayload>
export type HeartbeatEvent = AgentEvent<"heartbeat", HeartbeatPayload>
export type AgentCompleteEvent = AgentEvent<"agent_complete", AgentCompletePayload>
export type RepoSelectorEvent = AgentEvent<"repo_selector", RepoSelectorPayload>

export type AnyAgentEvent =
  | SessionInfoEvent
  | PhaseChangeEvent
  | StatusEvent
  | ThinkingEvent
  | ContentEvent
  | ToolCallEvent
  | ToolActivityEvent
  | TaskUpdateEvent
  | LogEvent
  | ErrorEvent
  | HeartbeatEvent
  | AgentCompleteEvent
  | RepoSelectorEvent

// =============================================================================
// Store state types
// =============================================================================

export interface PhaseEntry {
  id: PhaseId
  status: PhaseStatus
  startedAt?: string
  completedAt?: string
  description?: string
  errorReason?: string
}

export interface ToolActivity {
  id: string
  name: string
  status: "queued" | "running" | "done" | "error"
  message?: string
  target?: string
  startedAt: string
  completedAt?: string
  errorMessage?: string
}

export interface TelemetryEntry {
  id: string
  ts: string
  level: "debug" | "info" | "warning" | "error"
  source: "agent" | "ui" | "schema" | "socket"
  code?: string
  phase?: PhaseId
  message: string
  details?: Record<string, unknown>
}

export interface SessionState {
  sessionId: string | null
  status: AgentStatus
  message?: string
  startedAt?: string
  updatedAt?: string
  runtimeMs?: number
  phases: Record<PhaseId, PhaseEntry>
  lastSeq: number
  connection: ConnectionState
  reconnectAttempt: number
  diagnostics: TelemetryEntry[]
  diagnosticsUnread: number
  thinking: string
  toolActivity: ToolActivity[]
}

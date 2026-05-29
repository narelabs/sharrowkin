/**
 * Zod schemas for the Event_Stream protocol, synchronized with the pydantic
 * models in `agent/event_stream.py`.
 *
 * Uses `z.discriminatedUnion("type", [...])` for the top-level event envelope.
 * Exports a `parseEvent(raw: unknown)` function that returns the parsed event
 * or null (logging parse errors to console).
 *
 * Requirements: 8.5, 13.4
 */

import { z } from "zod"
import type { AnyAgentEvent } from "./types"

// =============================================================================
// Shared enums / scalars
// =============================================================================

const PhaseIdSchema = z.enum(["observe", "recall", "reason", "stabilize", "commit"])
const PhaseStatusSchema = z.enum(["pending", "running", "done", "error", "skipped"])
const AgentStatusSchema = z.enum(["idle", "connecting", "running", "thinking", "stabilizing", "done", "error", "stopped"])
const LogLevelSchema = z.enum(["debug", "info", "warning", "error"])
const ToolCallStatusSchema = z.enum(["running", "done", "error"])
const TaskStatusSchema = z.enum(["pending", "running", "done", "error", "skipped"])
const AgentOutcomeSchema = z.enum(["done", "error", "stopped"])
const SessionModeSchema = z.enum(["new", "resume"])

// =============================================================================
// Payload schemas
// =============================================================================

const SessionInfoPayloadSchema = z.object({
  mode: SessionModeSchema,
  last_seq: z.number().int().nonnegative().nullish(),
  recoverable: z.boolean().nullish(),
})

const PhaseChangePayloadSchema = z.object({
  phase: PhaseIdSchema,
  status: PhaseStatusSchema,
  reason: z.string().nullish(),
})

const StatusPayloadSchema = z.object({
  status: AgentStatusSchema,
  message: z.string().nullish(),
  runtime_ms: z.number().int().nonnegative().nullish(),
})

const ThinkingPayloadSchema = z.object({
  text: z.string(),
  delta: z.boolean().default(true),
})

const ContentPayloadSchema = z.object({
  text: z.string(),
  done: z.boolean().default(false),
})

const ToolCallPayloadSchema = z.object({
  tool_id: z.string(),
  name: z.string(),
  status: ToolCallStatusSchema,
  error: z.string().nullish(),
})

const ToolActivityPayloadSchema = z.object({
  tool_id: z.string(),
  progress: z.number().min(0).max(1).nullish(),
  target: z.string().nullish(),
})

const TaskUpdatePayloadSchema = z.object({
  task_id: z.string(),
  status: TaskStatusSchema,
  parent_id: z.string().nullish(),
})

const LogPayloadSchema = z.object({
  level: LogLevelSchema,
  message: z.string(),
  code: z.string().nullish(),
  phase: PhaseIdSchema.nullish(),
  details: z.record(z.unknown()).nullish(),
})

const ErrorPayloadSchema = z.object({
  code: z.string(),
  message: z.string(),
  phase: PhaseIdSchema.nullish(),
  recoverable: z.boolean().default(false),
})

const HeartbeatPayloadSchema = z.object({
  agent_alive: z.boolean().default(true),
})

const AgentCompletePayloadSchema = z.object({
  outcome: AgentOutcomeSchema,
  runtime_ms: z.number().int().nonnegative(),
})

const RepoRefSchema = z.object({
  id: z.string(),
  name: z.string(),
  full_name: z.string(),
  description: z.string().default(""),
  language: z.string().default(""),
  private: z.boolean().default(false),
  url: z.string(),
  stars: z.number().int().nullish(),
})

const RepoSelectorPayloadSchema = z.object({
  repos: z.array(RepoRefSchema),
  prompt: z.string(),
})

// =============================================================================
// Envelope schemas (one per event type, for discriminated union)
// =============================================================================

const envelopeBase = {
  v: z.literal(1),
  session_id: z.string().min(1),
  seq: z.number().int().nonnegative(),
  ts: z.string().min(1),
} as const

const SessionInfoEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("session_info"),
  payload: SessionInfoPayloadSchema,
})

const PhaseChangeEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("phase_change"),
  payload: PhaseChangePayloadSchema,
})

const StatusEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("status"),
  payload: StatusPayloadSchema,
})

const ThinkingEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("thinking"),
  payload: ThinkingPayloadSchema,
})

const ContentEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("content"),
  payload: ContentPayloadSchema,
})

const ToolCallEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("tool_call"),
  payload: ToolCallPayloadSchema,
})

const ToolActivityEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("tool_activity"),
  payload: ToolActivityPayloadSchema,
})

const TaskUpdateEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("task_update"),
  payload: TaskUpdatePayloadSchema,
})

const LogEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("log"),
  payload: LogPayloadSchema,
})

const ErrorEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("error"),
  payload: ErrorPayloadSchema,
})

const HeartbeatEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("heartbeat"),
  payload: HeartbeatPayloadSchema,
})

const AgentCompleteEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("agent_complete"),
  payload: AgentCompletePayloadSchema,
})

const RepoSelectorEventSchema = z.object({
  ...envelopeBase,
  type: z.literal("repo_selector"),
  payload: RepoSelectorPayloadSchema,
})

// =============================================================================
// Discriminated union
// =============================================================================

export const AgentEventSchema = z.discriminatedUnion("type", [
  SessionInfoEventSchema,
  PhaseChangeEventSchema,
  StatusEventSchema,
  ThinkingEventSchema,
  ContentEventSchema,
  ToolCallEventSchema,
  ToolActivityEventSchema,
  TaskUpdateEventSchema,
  LogEventSchema,
  ErrorEventSchema,
  HeartbeatEventSchema,
  AgentCompleteEventSchema,
  RepoSelectorEventSchema,
])

// =============================================================================
// Public API
// =============================================================================

/**
 * Parse a raw event (from WebSocket JSON) into a typed AgentEvent.
 * Returns null if parsing fails, logging the error to console.
 */
export function parseEvent(raw: unknown): AnyAgentEvent | null {
  const result = AgentEventSchema.safeParse(raw)
  if (result.success) {
    return result.data as AnyAgentEvent
  }
  console.error("[agent-stream/schema] Failed to parse event:", result.error.format(), raw)
  return null
}

// Export individual schemas for testing
export {
  SessionInfoEventSchema,
  PhaseChangeEventSchema,
  StatusEventSchema,
  ThinkingEventSchema,
  ContentEventSchema,
  ToolCallEventSchema,
  ToolActivityEventSchema,
  TaskUpdateEventSchema,
  LogEventSchema,
  ErrorEventSchema,
  HeartbeatEventSchema,
  AgentCompleteEventSchema,
  RepoSelectorEventSchema,
  PhaseIdSchema,
  PhaseStatusSchema,
  AgentStatusSchema,
}

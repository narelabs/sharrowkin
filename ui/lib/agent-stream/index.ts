/**
 * Agent Event_Stream client library.
 *
 * Re-exports types, schema validation, the session store, and socket client.
 */

export * from "./types"
export { AgentEventSchema, parseEvent } from "./schema"
export {
  createAgentSessionStore,
  selectPhases,
  selectStatus,
  selectConnection,
  selectDiagnostics,
  selectThinking,
  selectToolActivity,
} from "./store"
export type { AgentSessionStore } from "./store"
export { AgentSocketClient } from "./socket-client"
export type { ConnectInput } from "./socket-client"

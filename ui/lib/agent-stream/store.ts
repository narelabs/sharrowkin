/**
 * AgentSessionStore — single source of truth for agent session state.
 *
 * Implements a simple external store pattern compatible with `useSyncExternalStore`.
 * Consumes events from the Event_Stream and maintains the canonical session state.
 *
 * Requirements: 1.2, 1.3, 1.4, 1.6, 1.7, 2.1, 2.4, 2.6, 9.3, 11.4
 */

import type {
  AgentEvent,
  AgentStatus,
  ConnectionState,
  PhaseEntry,
  PhaseId,
  SessionState,
  TelemetryEntry,
  ToolActivity,
} from "./types"

// =============================================================================
// Constants
// =============================================================================

const CANONICAL_PHASES: PhaseId[] = ["observe", "recall", "reason", "stabilize", "commit"]
const THINKING_MAX_CHARS = 500
const DIAGNOSTICS_MAX = 100
const PERSIST_DEBOUNCE_MS = 100

// =============================================================================
// Helpers
// =============================================================================

function createInitialPhases(): Record<PhaseId, PhaseEntry> {
  return Object.fromEntries(
    CANONICAL_PHASES.map((id) => [id, { id, status: "pending" as const }])
  ) as Record<PhaseId, PhaseEntry>
}

function createInitialState(): SessionState {
  return {
    sessionId: null,
    status: "idle",
    message: undefined,
    startedAt: undefined,
    updatedAt: undefined,
    runtimeMs: undefined,
    phases: createInitialPhases(),
    lastSeq: -1,
    connection: "online",
    reconnectAttempt: 0,
    diagnostics: [],
    diagnosticsUnread: 0,
    thinking: "",
    toolActivity: [],
  }
}

function generateId(): string {
  return Math.random().toString(36).slice(2, 10) + Date.now().toString(36)
}

function storageKey(sessionId: string): string {
  return `sharrowkin.session.${sessionId}`
}

// =============================================================================
// Persistence helpers
// =============================================================================

interface PersistedState {
  phases: Record<PhaseId, PhaseEntry>
  status: AgentStatus
  sessionId: string | null
  lastSeq: number
  runtimeMs?: number
}

function tryLoadFromStorage(sessionId: string): Partial<SessionState> | null {
  if (typeof window === "undefined") return null
  try {
    const raw = localStorage.getItem(storageKey(sessionId))
    if (!raw) return null
    const parsed: PersistedState = JSON.parse(raw)
    return {
      phases: parsed.phases,
      status: parsed.status,
      sessionId: parsed.sessionId,
      lastSeq: parsed.lastSeq,
      runtimeMs: parsed.runtimeMs,
    }
  } catch {
    return null
  }
}

function persistToStorage(state: SessionState): void {
  if (typeof window === "undefined") return
  if (!state.sessionId) return
  try {
    const persisted: PersistedState = {
      phases: state.phases,
      status: state.status,
      sessionId: state.sessionId,
      lastSeq: state.lastSeq,
      runtimeMs: state.runtimeMs,
    }
    localStorage.setItem(storageKey(state.sessionId), JSON.stringify(persisted))
  } catch {
    // localStorage may be full or unavailable — silently ignore
  }
}

// =============================================================================
// Reducer logic
// =============================================================================

function applyEventToState(state: SessionState, event: AgentEvent): SessionState {
  const next = { ...state }
  next.lastSeq = Math.max(next.lastSeq, event.seq)
  next.updatedAt = event.ts

  switch (event.type) {
    case "session_info": {
      const payload = event.payload as { mode: string; last_seq?: number | null; recoverable?: boolean | null }
      if (payload.mode === "new") {
        next.phases = createInitialPhases()
        next.sessionId = event.session_id
        next.status = "running"
        next.startedAt = event.ts
        next.thinking = ""
        next.toolActivity = []
        next.diagnostics = []
        next.diagnosticsUnread = 0
        next.runtimeMs = undefined
      } else {
        // resume — keep existing phases, update sessionId
        next.sessionId = event.session_id
      }
      break
    }

    case "phase_change": {
      const payload = event.payload as { phase: string; status: string; reason?: string | null }
      const phaseId = payload.phase as PhaseId
      if (!CANONICAL_PHASES.includes(phaseId)) {
        // Unknown phase → push to diagnostics, no-op on phases
        next.diagnostics = pushDiagnostic(next.diagnostics, {
          id: generateId(),
          ts: event.ts,
          level: "warning",
          source: "agent",
          message: `Unknown phase "${payload.phase}" received in phase_change event`,
          phase: undefined,
        })
        next.diagnosticsUnread = next.diagnosticsUnread + 1
        break
      }
      const existingPhase = next.phases[phaseId]
      const newPhaseEntry: PhaseEntry = {
        ...existingPhase,
        id: phaseId,
        status: payload.status as PhaseEntry["status"],
      }
      if (payload.status === "running") {
        newPhaseEntry.startedAt = event.ts
      }
      if (payload.status === "done" || payload.status === "error" || payload.status === "skipped") {
        newPhaseEntry.completedAt = event.ts
      }
      if (payload.status === "error" && payload.reason) {
        newPhaseEntry.errorReason = payload.reason
      }
      next.phases = { ...next.phases, [phaseId]: newPhaseEntry }
      break
    }

    case "status": {
      const payload = event.payload as { status: string; message?: string | null; runtime_ms?: number | null }
      // Error stickiness: once status is "error", it cannot go back to "done"
      // Only resetSession clears it
      if (next.status === "error" && payload.status === "done") {
        break
      }
      next.status = payload.status as AgentStatus
      if (payload.message !== undefined && payload.message !== null) {
        next.message = payload.message
      }
      if (payload.runtime_ms !== undefined && payload.runtime_ms !== null) {
        next.runtimeMs = payload.runtime_ms
      }
      break
    }

    case "thinking": {
      const payload = event.payload as { text: string; delta: boolean }
      if (payload.delta) {
        // Append and keep last THINKING_MAX_CHARS characters (ring buffer)
        const combined = next.thinking + payload.text
        next.thinking = combined.length > THINKING_MAX_CHARS
          ? combined.slice(combined.length - THINKING_MAX_CHARS)
          : combined
      } else {
        // Replace mode
        next.thinking = payload.text.length > THINKING_MAX_CHARS
          ? payload.text.slice(payload.text.length - THINKING_MAX_CHARS)
          : payload.text
      }
      break
    }

    case "tool_call": {
      const payload = event.payload as { tool_id: string; name: string; status: string; error?: string | null }
      const existingIdx = next.toolActivity.findIndex((t) => t.id === payload.tool_id)
      const toolEntry: ToolActivity = {
        id: payload.tool_id,
        name: payload.name,
        status: payload.status as ToolActivity["status"],
        startedAt: event.ts,
        ...(payload.error ? { errorMessage: payload.error } : {}),
      }
      if (payload.status === "done" || payload.status === "error") {
        toolEntry.completedAt = event.ts
      }
      if (existingIdx >= 0) {
        // Upsert: preserve startedAt from original entry
        const existing = next.toolActivity[existingIdx]
        toolEntry.startedAt = existing.startedAt
        const newActivity = [...next.toolActivity]
        newActivity[existingIdx] = toolEntry
        next.toolActivity = newActivity
      } else {
        next.toolActivity = [...next.toolActivity, toolEntry]
      }
      break
    }

    case "log": {
      const payload = event.payload as { level: string; message: string; code?: string | null; phase?: string | null; details?: Record<string, unknown> | null }
      // Only push warning/error to diagnostics ring buffer
      if (payload.level === "warning" || payload.level === "error") {
        next.diagnostics = pushDiagnostic(next.diagnostics, {
          id: generateId(),
          ts: event.ts,
          level: payload.level as TelemetryEntry["level"],
          source: "agent",
          code: payload.code ?? undefined,
          phase: payload.phase as PhaseId | undefined,
          message: payload.message,
          details: payload.details ?? undefined,
        })
        next.diagnosticsUnread = next.diagnosticsUnread + 1
      }
      break
    }

    case "error": {
      const payload = event.payload as { code: string; message: string; phase?: string | null; recoverable: boolean }
      next.diagnostics = pushDiagnostic(next.diagnostics, {
        id: generateId(),
        ts: event.ts,
        level: "error",
        source: "agent",
        code: payload.code,
        phase: payload.phase as PhaseId | undefined,
        message: payload.message,
      })
      next.diagnosticsUnread = next.diagnosticsUnread + 1
      next.status = "error"
      break
    }

    case "heartbeat": {
      next.updatedAt = event.ts
      break
    }

    case "agent_complete": {
      const payload = event.payload as { outcome: string; runtime_ms: number }
      // Error stickiness: if already error, don't go to done
      if (next.status === "error" && payload.outcome === "done") {
        next.runtimeMs = payload.runtime_ms
        break
      }
      next.status = payload.outcome === "done" ? "done" : payload.outcome === "error" ? "error" : "stopped"
      next.runtimeMs = payload.runtime_ms
      break
    }

    // content, tool_activity, task_update, repo_selector — no store state changes needed for core session state
    default:
      break
  }

  return next
}

function pushDiagnostic(diagnostics: TelemetryEntry[], entry: TelemetryEntry): TelemetryEntry[] {
  const next = [...diagnostics, entry]
  if (next.length > DIAGNOSTICS_MAX) {
    return next.slice(next.length - DIAGNOSTICS_MAX)
  }
  return next
}

// =============================================================================
// Selectors
// =============================================================================

export function selectPhases(state: SessionState): Record<PhaseId, PhaseEntry> {
  return state.phases
}

export function selectStatus(state: SessionState): { status: AgentStatus; message?: string; runtimeMs?: number } {
  return { status: state.status, message: state.message, runtimeMs: state.runtimeMs }
}

export function selectConnection(state: SessionState): { connection: ConnectionState; reconnectAttempt: number } {
  return { connection: state.connection, reconnectAttempt: state.reconnectAttempt }
}

export function selectDiagnostics(state: SessionState): { entries: TelemetryEntry[]; unread: number } {
  return { entries: state.diagnostics, unread: state.diagnosticsUnread }
}

export function selectThinking(state: SessionState): string {
  return state.thinking
}

export function selectToolActivity(state: SessionState): ToolActivity[] {
  return state.toolActivity
}

// =============================================================================
// AgentSessionStore
// =============================================================================

export interface AgentSessionStore {
  getState(): SessionState
  subscribe(listener: () => void): () => void
  applyEvent(event: AgentEvent): void
  setConnection(connection: ConnectionState, reconnectAttempt: number): void
  resetSession(sessionId: string): void
  markDiagnosticsRead(): void
}

export function createAgentSessionStore(initialSessionId?: string): AgentSessionStore {
  let state: SessionState = createInitialState()
  const listeners = new Set<() => void>()
  let persistTimer: ReturnType<typeof setTimeout> | null = null

  // Attempt to restore from localStorage on creation (SSR-safe)
  if (initialSessionId) {
    const restored = tryLoadFromStorage(initialSessionId)
    if (restored) {
      state = { ...state, ...restored }
    }
  }

  function notify(): void {
    for (const listener of listeners) {
      listener()
    }
  }

  function schedulePersist(): void {
    if (persistTimer !== null) {
      clearTimeout(persistTimer)
    }
    persistTimer = setTimeout(() => {
      persistTimer = null
      persistToStorage(state)
    }, PERSIST_DEBOUNCE_MS)
  }

  function getState(): SessionState {
    return state
  }

  function subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }

  function applyEvent(event: AgentEvent): void {
    state = applyEventToState(state, event)
    notify()
    schedulePersist()
  }

  function resetSession(sessionId: string): void {
    state = {
      ...createInitialState(),
      sessionId,
      startedAt: new Date().toISOString(),
    }
    notify()
    schedulePersist()
  }

  function markDiagnosticsRead(): void {
    if (state.diagnosticsUnread === 0) return
    state = { ...state, diagnosticsUnread: 0 }
    notify()
  }

  function setConnection(connection: ConnectionState, reconnectAttempt: number): void {
    if (state.connection === connection && state.reconnectAttempt === reconnectAttempt) return
    state = { ...state, connection, reconnectAttempt }
    notify()
  }

  return {
    getState,
    subscribe,
    applyEvent,
    setConnection,
    resetSession,
    markDiagnosticsRead,
  }
}

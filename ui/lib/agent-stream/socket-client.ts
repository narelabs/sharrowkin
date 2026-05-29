/**
 * AgentSocketClient — WebSocket client for the Event_Stream protocol.
 *
 * Handles connection, reconnection with exponential backoff, heartbeat watchdog,
 * seq gap detection, and schema validation of incoming events.
 *
 * Requirements: 3.1, 3.2, 3.3, 3.5, 3.7, 8.5
 */

import { parseEvent } from "./schema"
import type { AnyAgentEvent, ConnectionState } from "./types"

// =============================================================================
// Constants
// =============================================================================

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
const HEARTBEAT_TIMEOUT_MS = 45_000
const MAX_RECONNECT_ATTEMPTS = 5
const BACKOFF_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000] // ms

// =============================================================================
// Types
// =============================================================================

export interface ConnectInput {
  task: string
  workspace: string
  sessionId: string
  model?: string
  lastSeq?: number
}

// =============================================================================
// AgentSocketClient
// =============================================================================

export class AgentSocketClient {
  private ws: WebSocket | null = null
  private lastSeq = -1
  private reconnectAttempts = 0
  private heartbeatTimer: ReturnType<typeof setTimeout> | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private eventHandlers = new Set<(e: AnyAgentEvent) => void>()
  private connectionHandlers = new Set<(s: ConnectionState, attempt: number) => void>()
  private currentSessionId: string | null = null
  private currentInput: ConnectInput | null = null
  private closedByUser = false

  // ─── Public API ───────────────────────────────────────────────────

  /**
   * Open a new WebSocket connection and start an agent session.
   */
  connect(input: ConnectInput): void {
    this.closedByUser = false
    this.currentInput = input
    this.currentSessionId = input.sessionId
    this.lastSeq = input.lastSeq ?? -1
    this.reconnectAttempts = 0
    this.openSocket(input)
  }

  /**
   * Resume an existing session from a given seq number.
   */
  resume(sessionId: string, lastSeq: number): void {
    this.closedByUser = false
    this.currentSessionId = sessionId
    this.lastSeq = lastSeq
    this.reconnectAttempts = 0
    this.openSocket({ task: "", workspace: "", sessionId, lastSeq })
  }

  /**
   * Send a JSON message to the backend over the WebSocket.
   */
  send(message: Record<string, unknown>): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message))
    }
  }

  /**
   * Close the connection. No reconnect will be attempted.
   */
  close(reason?: "user" | "navigate"): void {
    this.closedByUser = true
    this.clearTimers()
    if (this.ws) {
      this.ws.close(1000, reason || "user")
      this.ws = null
    }
  }

  /**
   * Subscribe to parsed agent events. Returns an unsubscribe function.
   */
  onEvent(handler: (e: AnyAgentEvent) => void): () => void {
    this.eventHandlers.add(handler)
    return () => {
      this.eventHandlers.delete(handler)
    }
  }

  /**
   * Subscribe to connection state changes. Returns an unsubscribe function.
   */
  onConnectionChange(handler: (s: ConnectionState, attempt: number) => void): () => void {
    this.connectionHandlers.add(handler)
    return () => {
      this.connectionHandlers.delete(handler)
    }
  }

  /**
   * Get the last known seq number (useful for external resume logic).
   */
  getLastSeq(): number {
    return this.lastSeq
  }

  // ─── Private ──────────────────────────────────────────────────────

  private getWsUrl(): string {
    const httpUrl = BACKEND_URL.replace(/\/$/, "")
    const wsUrl = httpUrl.replace(/^http/, "ws")
    return `${wsUrl}/api/agent/ws`
  }

  private openSocket(input: ConnectInput): void {
    this.clearTimers()

    if (this.ws) {
      this.ws.close(1000, "reconnect")
      this.ws = null
    }

    const url = this.getWsUrl()
    const ws = new WebSocket(url)
    this.ws = ws

    ws.onopen = () => {
      this.reconnectAttempts = 0
      this.notifyConnection("online", 0)
      this.resetHeartbeatWatchdog()

      // Send start or resume message
      if (input.lastSeq !== undefined && input.lastSeq >= 0 && !input.task) {
        // Pure resume
        this.send({
          type: "resume",
          session_id: input.sessionId,
          last_seq: input.lastSeq,
        })
      } else if (input.lastSeq !== undefined && input.lastSeq >= 0) {
        // Reconnect with resume
        this.send({
          type: "resume",
          session_id: input.sessionId,
          last_seq: input.lastSeq,
        })
      } else {
        // New session start
        this.send({
          type: "start",
          task: input.task,
          workspace: input.workspace,
          session_id: input.sessionId,
          ...(input.model ? { model: input.model } : {}),
        })
      }
    }

    ws.onmessage = (event) => {
      this.resetHeartbeatWatchdog()

      let raw: unknown
      try {
        raw = JSON.parse(event.data as string)
      } catch {
        console.error("[AgentSocketClient] Failed to parse WebSocket message as JSON")
        return
      }

      const parsed = parseEvent(raw)
      if (!parsed) {
        // Schema violation — already logged by parseEvent
        return
      }

      // Seq gap detection: if event.seq > lastSeq + 1, request resume
      if (parsed.seq > this.lastSeq + 1 && this.lastSeq >= 0) {
        this.send({
          type: "resume",
          session_id: this.currentSessionId,
          last_seq: this.lastSeq,
        })
      }

      // Update lastSeq
      if (parsed.seq > this.lastSeq) {
        this.lastSeq = parsed.seq
      }

      // Notify all event handlers
      for (const handler of this.eventHandlers) {
        handler(parsed)
      }
    }

    ws.onclose = (event) => {
      this.clearHeartbeat()

      if (this.closedByUser) {
        return
      }

      // Unexpected close — attempt reconnect
      this.attemptReconnect()
    }

    ws.onerror = () => {
      // onerror is always followed by onclose, so reconnect logic lives there
    }
  }

  private attemptReconnect(): void {
    if (this.closedByUser) return

    this.reconnectAttempts++

    if (this.reconnectAttempts > MAX_RECONNECT_ATTEMPTS) {
      this.notifyConnection("offline", this.reconnectAttempts)
      return
    }

    this.notifyConnection("reconnecting", this.reconnectAttempts)

    const delayIndex = Math.min(this.reconnectAttempts - 1, BACKOFF_DELAYS.length - 1)
    const delay = BACKOFF_DELAYS[delayIndex]

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      if (this.closedByUser) return

      // Reconnect with resume using last known seq
      this.openSocket({
        task: this.currentInput?.task || "",
        workspace: this.currentInput?.workspace || "",
        sessionId: this.currentSessionId || "",
        lastSeq: this.lastSeq >= 0 ? this.lastSeq : undefined,
      })
    }, delay)
  }

  private resetHeartbeatWatchdog(): void {
    this.clearHeartbeat()
    this.heartbeatTimer = setTimeout(() => {
      this.heartbeatTimer = null
      // Heartbeat timeout — connection is stale
      if (this.ws) {
        this.ws.close(4000, "heartbeat_timeout")
        this.ws = null
      }
      this.notifyConnection("reconnecting", this.reconnectAttempts)
      this.attemptReconnect()
    }, HEARTBEAT_TIMEOUT_MS)
  }

  private clearHeartbeat(): void {
    if (this.heartbeatTimer !== null) {
      clearTimeout(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private clearTimers(): void {
    this.clearHeartbeat()
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private notifyConnection(state: ConnectionState, attempt: number): void {
    for (const handler of this.connectionHandlers) {
      handler(state, attempt)
    }
  }
}

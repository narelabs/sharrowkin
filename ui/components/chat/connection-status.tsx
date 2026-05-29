"use client"

/**
 * ConnectionStatus — subscribes to `selectConnection` from the AgentSessionStore.
 *
 * Shows:
 * - "Connected" (green, auto-hides after 3s)
 * - "Reconnecting (attempt N)" (amber)
 * - "Offline" (red + Reconnect button)
 *
 * NO polling `/api/health` — connection state comes from the store/socket client.
 *
 * Requirements: 3.2, 3.5
 * Validates: Requirements 3.2
 */

import { useSyncExternalStore, useEffect, useRef, useState } from "react"
import { Wifi, WifiOff, Loader2 } from "lucide-react"
import { Surface } from "@/components/visual/surface"
import { selectConnection, type AgentSessionStore } from "@/lib/agent-stream"
import type { AgentSocketClient } from "@/lib/agent-stream"

// =============================================================================
// Component
// =============================================================================

export interface ConnectionStatusProps {
  store?: AgentSessionStore
  socketClient?: AgentSocketClient | null
}

export function ConnectionStatus({ store, socketClient }: ConnectionStatusProps) {
  // If no store provided (legacy call from providers.tsx), render nothing.
  // This avoids the hook-call-on-undefined crash while the migration to
  // store-driven rendering is in progress.
  if (!store) {
    return null
  }

  return <ConnectionStatusInner store={store} socketClient={socketClient} />
}

function ConnectionStatusInner({ store, socketClient }: { store: AgentSessionStore; socketClient?: AgentSocketClient | null }) {
  const { connection, reconnectAttempt } = useSyncExternalStore(
    store.subscribe,
    () => selectConnection(store.getState()),
    () => selectConnection(store.getState())
  )

  // Auto-hide "connected" after 3s
  const [showConnected, setShowConnected] = useState(false)
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const prevConnectionRef = useRef(connection)

  useEffect(() => {
    // Detect transition to "online" from another state
    if (connection === "online" && prevConnectionRef.current !== "online") {
      setShowConnected(true)
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current)
      }
      hideTimerRef.current = setTimeout(() => {
        setShowConnected(false)
        hideTimerRef.current = null
      }, 3000)
    }

    if (connection !== "online") {
      setShowConnected(false)
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current)
        hideTimerRef.current = null
      }
    }

    prevConnectionRef.current = connection

    return () => {
      if (hideTimerRef.current) {
        clearTimeout(hideTimerRef.current)
      }
    }
  }, [connection])

  // Don't render anything when connected and auto-hide has elapsed
  if (connection === "online" && !showConnected) {
    return null
  }

  const handleReconnect = () => {
    if (socketClient) {
      const state = store.getState()
      if (state.sessionId) {
        socketClient.resume(state.sessionId, state.lastSeq)
      }
    }
  }

  return (
    <Surface
      className="connection-status"
      style={{
        position: "fixed",
        bottom: "var(--space-4, 16px)",
        left: "50%",
        transform: "translateX(-50%)",
        zIndex: 9990,
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2, 8px)",
        padding: "var(--space-2, 8px) var(--space-4, 16px)",
        borderRadius: "var(--radius-full, 9999px)",
        fontSize: "var(--text-xs, 12px)",
        fontWeight: 500,
        borderColor: connection === "online"
          ? "var(--color-success)"
          : connection === "reconnecting"
            ? "var(--color-warning)"
            : "var(--color-danger)",
        transition: `all var(--motion-base, 200ms) var(--ease-standard, ease)`,
      }}
      data-connection={connection}
    >
      {/* Icon */}
      {connection === "online" && (
        <Wifi size={14} style={{ color: "var(--color-success)" }} />
      )}
      {connection === "reconnecting" && (
        <Loader2 size={14} style={{ color: "var(--color-warning)" }} />
      )}
      {connection === "offline" && (
        <WifiOff size={14} style={{ color: "var(--color-danger)" }} />
      )}

      {/* Label */}
      <span
        style={{
          color: connection === "online"
            ? "var(--color-success)"
            : connection === "reconnecting"
              ? "var(--color-warning)"
              : "var(--color-danger)",
        }}
      >
        {connection === "online" && "Connected"}
        {connection === "reconnecting" && `Reconnecting (attempt ${reconnectAttempt})`}
        {connection === "offline" && "Offline"}
      </span>

      {/* Reconnect button for offline state */}
      {connection === "offline" && socketClient && (
        <button
          onClick={handleReconnect}
          style={{
            marginLeft: "var(--space-2, 8px)",
            padding: "var(--space-1, 4px) var(--space-3, 12px)",
            borderRadius: "var(--radius-sm, 4px)",
            backgroundColor: "var(--color-danger)",
            color: "var(--color-bg)",
            border: "none",
            fontSize: "var(--text-xs, 12px)",
            fontWeight: 600,
            cursor: "pointer",
            transition: `opacity var(--motion-fast, 120ms) var(--ease-standard, ease)`,
          }}
          onMouseEnter={(e) => { (e.target as HTMLElement).style.opacity = "0.85" }}
          onMouseLeave={(e) => { (e.target as HTMLElement).style.opacity = "1" }}
        >
          Reconnect
        </button>
      )}
    </Surface>
  )
}

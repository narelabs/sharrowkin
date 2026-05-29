"use client"

/**
 * AgentStatusBadge — single-node status indicator with CSS transitions.
 *
 * Subscribes to `selectStatus` and `selectConnection` from the AgentSessionStore.
 * ONE root DOM node, transitions via `data-status` + CSS transition.
 * Error stickiness: error state persists until explicit reset.
 * Watchdog: if no status/heartbeat for 15s during active session → shows "connecting".
 * Shows "Backend offline" when connection is offline.
 *
 * Requirements: 2.3, 2.5, 2.6, 2.7, 4.6, 5.1
 * Validates: Requirements 2.5
 */

import { useSyncExternalStore, useEffect, useRef, useState, useMemo } from "react"
import { Zap, CheckCircle2, AlertCircle, Loader2, Pause, WifiOff } from "lucide-react"
import { selectStatus, selectConnection, type AgentSessionStore } from "@/lib/agent-stream"
import type { AgentStatus } from "@/lib/agent-stream"

// Re-export the type so chat-shell can still import it from here
export type { AgentStatus }

// =============================================================================
// Constants
// =============================================================================

const WATCHDOG_TIMEOUT_MS = 15_000

// =============================================================================
// Status config
// =============================================================================

interface StatusConfig {
  icon: typeof Zap
  label: string
  color: string
  bgColor: string
  borderColor: string
}

function getStatusConfig(status: AgentStatus, isOffline: boolean): StatusConfig {
  if (isOffline) {
    return {
      icon: WifiOff,
      label: "Backend offline",
      color: "var(--color-danger)",
      bgColor: "var(--color-surface-2)",
      borderColor: "var(--color-danger)",
    }
  }

  switch (status) {
    case "idle":
      return {
        icon: Pause,
        label: "Idle",
        color: "var(--color-text-muted)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-border)",
      }
    case "connecting":
      return {
        icon: Loader2,
        label: "Connecting",
        color: "var(--color-accent)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-accent)",
      }
    case "running":
      return {
        icon: Zap,
        label: "Running",
        color: "var(--color-accent)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-accent)",
      }
    case "thinking":
      return {
        icon: Zap,
        label: "Thinking",
        color: "var(--color-accent)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-accent)",
      }
    case "stabilizing":
      return {
        icon: Loader2,
        label: "Stabilizing",
        color: "var(--color-warning)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-warning)",
      }
    case "done":
      return {
        icon: CheckCircle2,
        label: "Done",
        color: "var(--color-success)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-success)",
      }
    case "error":
      return {
        icon: AlertCircle,
        label: "Error",
        color: "var(--color-danger)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-danger)",
      }
    case "stopped":
      return {
        icon: Pause,
        label: "Stopped",
        color: "var(--color-warning)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-warning)",
      }
    default:
      return {
        icon: Pause,
        label: "Unknown",
        color: "var(--color-text-muted)",
        bgColor: "var(--color-surface)",
        borderColor: "var(--color-border)",
      }
  }
}

function formatRuntime(ms: number): string {
  const seconds = (ms / 1000).toFixed(1)
  return `${seconds}s`
}

// =============================================================================
// Component
// =============================================================================

export interface AgentStatusBadgeProps {
  /** New mode: pass the store, component subscribes internally */
  store?: AgentSessionStore
  /** Legacy mode: pass status directly */
  status?: AgentStatus
  /** Legacy mode: pass message directly */
  message?: string
  className?: string
}

export function AgentStatusBadge({ store, status: legacyStatus, message: legacyMessage, className }: AgentStatusBadgeProps) {
  // Store-driven mode
  const storeData = useSyncExternalStore(
    store?.subscribe ?? (() => () => {}),
    () => store ? selectStatus(store.getState()) : null,
    () => store ? selectStatus(store.getState()) : null,
  )

  const connectionData = useSyncExternalStore(
    store?.subscribe ?? (() => () => {}),
    () => store ? selectConnection(store.getState()) : null,
    () => store ? selectConnection(store.getState()) : null,
  )

  // Resolve effective values from store or legacy props
  const status: AgentStatus = storeData?.status ?? legacyStatus ?? "idle"
  const message = storeData?.message ?? legacyMessage
  const runtimeMs = storeData?.runtimeMs
  const connection = connectionData?.connection ?? "online"

  // Watchdog: if no update for 15s during active session → show "connecting"
  const [watchdogTriggered, setWatchdogTriggered] = useState(false)
  const watchdogRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const isActiveSession = status === "running" || status === "thinking" || status === "stabilizing"

  useEffect(() => {
    if (!isActiveSession || !store) {
      setWatchdogTriggered(false)
      if (watchdogRef.current) {
        clearTimeout(watchdogRef.current)
        watchdogRef.current = null
      }
      return
    }

    // Reset watchdog on every store update
    const resetWatchdog = () => {
      if (watchdogRef.current) {
        clearTimeout(watchdogRef.current)
      }
      setWatchdogTriggered(false)
      watchdogRef.current = setTimeout(() => {
        setWatchdogTriggered(true)
      }, WATCHDOG_TIMEOUT_MS)
    }

    resetWatchdog()

    const unsub = store.subscribe(() => {
      resetWatchdog()
    })

    return () => {
      unsub()
      if (watchdogRef.current) {
        clearTimeout(watchdogRef.current)
        watchdogRef.current = null
      }
    }
  }, [isActiveSession, store])

  // Determine effective display status
  const isOffline = connection === "offline"
  const effectiveStatus: AgentStatus = watchdogTriggered ? "connecting" : status
  const config = getStatusConfig(effectiveStatus, isOffline)
  const Icon = config.icon

  // Build display message
  let displayMessage = message
  if (isOffline) {
    displayMessage = "Backend offline"
  } else if (effectiveStatus === "done" && runtimeMs !== undefined) {
    displayMessage = formatRuntime(runtimeMs)
  } else if (watchdogTriggered) {
    displayMessage = "No response..."
  }

  return (
    <div
      className={className}
      data-status={effectiveStatus}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2, 8px)",
        padding: "var(--space-2, 8px) var(--space-3, 12px)",
        borderRadius: "var(--radius-full, 9999px)",
        backgroundColor: config.bgColor,
        border: `1px solid ${config.borderColor}`,
        transition: `all var(--motion-base, 200ms) var(--ease-standard, ease)`,
      }}
    >
      {/* Icon */}
      <Icon
        size={16}
        style={{
          color: config.color,
          flexShrink: 0,
          transition: `color var(--motion-base, 200ms) var(--ease-standard, ease)`,
        }}
      />

      {/* Label + message */}
      <div style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
        <span
          style={{
            fontSize: "var(--text-xs, 12px)",
            fontWeight: 600,
            textTransform: "uppercase",
            letterSpacing: "0.05em",
            color: config.color,
            lineHeight: 1.2,
            transition: `color var(--motion-base, 200ms) var(--ease-standard, ease)`,
          }}
        >
          {config.label}
        </span>
        {displayMessage && (
          <span
            style={{
              fontSize: "var(--text-xs, 12px)",
              color: "var(--color-text-muted)",
              lineHeight: 1.2,
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
            }}
          >
            {displayMessage}
          </span>
        )}
      </div>
    </div>
  )
}

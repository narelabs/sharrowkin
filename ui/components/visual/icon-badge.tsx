"use client"

import { type ReactElement } from "react"
import { cn } from "@/lib/utils"

export type IconBadgeState = "idle" | "active" | "done" | "error"

export interface IconBadgeProps {
  state?: IconBadgeState
  icon: ReactElement
  size?: number
  className?: string
}

const stateStyles: Record<IconBadgeState, { bg: string; color: string; border: string }> = {
  idle: {
    bg: "var(--color-surface-2)",
    color: "var(--color-text-muted)",
    border: "var(--color-border)",
  },
  active: {
    bg: "var(--color-accent)",
    color: "var(--color-bg)",
    border: "var(--color-accent-strong)",
  },
  done: {
    bg: "var(--color-success)",
    color: "var(--color-bg)",
    border: "var(--color-success)",
  },
  error: {
    bg: "var(--color-danger)",
    color: "var(--color-bg)",
    border: "var(--color-danger)",
  },
}

/**
 * IconBadge — circular badge with a slot for a lucide-react icon.
 * State controlled via `data-state` attribute. No gradient classes.
 */
export function IconBadge({ state = "idle", icon, size = 40, className }: IconBadgeProps) {
  const styles = stateStyles[state]

  return (
    <div
      className={cn("icon-badge", className)}
      data-state={state}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: `${size}px`,
        height: `${size}px`,
        borderRadius: "var(--radius-full)",
        backgroundColor: styles.bg,
        color: styles.color,
        border: `2px solid ${styles.border}`,
        transition: `background-color var(--motion-base) var(--ease-standard), color var(--motion-base) var(--ease-standard), border-color var(--motion-base) var(--ease-standard)`,
      }}
    >
      {icon}
    </div>
  )
}

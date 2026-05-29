"use client"

import { type ReactNode } from "react"
import { cn } from "@/lib/utils"

export type BadgeVariant = "neutral" | "success" | "warning" | "danger" | "info"

export interface BadgeProps {
  variant?: BadgeVariant
  children?: ReactNode
  className?: string
}

const variantStyles: Record<BadgeVariant, { bg: string; color: string }> = {
  neutral: { bg: "var(--color-surface-2)", color: "var(--color-text)" },
  success: { bg: "var(--color-success)", color: "var(--color-bg)" },
  warning: { bg: "var(--color-warning)", color: "var(--color-bg)" },
  danger: { bg: "var(--color-danger)", color: "var(--color-bg)" },
  info: { bg: "var(--color-info)", color: "var(--color-bg)" },
}

/**
 * Badge — pill-shaped label with semantic color variants.
 * All colors sourced from CSS custom properties (tokens.css).
 */
export function Badge({ variant = "neutral", children, className }: BadgeProps) {
  const styles = variantStyles[variant]

  return (
    <span
      className={cn("badge", className)}
      data-variant={variant}
      style={{
        display: "inline-flex",
        alignItems: "center",
        borderRadius: "var(--radius-full)",
        padding: "var(--space-1) var(--space-3)",
        fontSize: "var(--text-xs)",
        fontWeight: 500,
        lineHeight: "var(--leading-tight)",
        backgroundColor: styles.bg,
        color: styles.color,
      }}
    >
      {children}
    </span>
  )
}

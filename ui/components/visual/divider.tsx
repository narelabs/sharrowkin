"use client"

import { cn } from "@/lib/utils"

export interface DividerProps {
  orientation?: "horizontal" | "vertical"
  className?: string
}

/**
 * Divider — horizontal or vertical separator line.
 * Uses token-based border color.
 */
export function Divider({ orientation = "horizontal", className }: DividerProps) {
  const isHorizontal = orientation === "horizontal"

  return (
    <div
      role="separator"
      aria-orientation={orientation}
      className={cn("divider", className)}
      style={{
        backgroundColor: "var(--color-border)",
        ...(isHorizontal
          ? { height: "1px", width: "100%" }
          : { width: "1px", height: "100%" }),
      }}
    />
  )
}

"use client"

import { type ReactNode } from "react"
import { cn } from "@/lib/utils"
import { Surface } from "./surface"

export interface CardProps {
  className?: string
  children?: ReactNode
  elevated?: boolean
}

/**
 * Card — extends Surface with padding and optional elevation.
 * Uses token-based spacing and shadow.
 */
export function Card({ className, children, elevated = true }: CardProps) {
  return (
    <Surface
      className={cn("card", className)}
      style={{
        padding: "var(--space-4)",
        boxShadow: elevated ? "var(--shadow-card)" : "none",
      }}
    >
      {children}
    </Surface>
  )
}

"use client"

import { type ElementType, type ComponentPropsWithoutRef, type ReactNode } from "react"
import { cn } from "@/lib/utils"

type SurfaceOwnProps<T extends ElementType = "div"> = {
  as?: T
  className?: string
  children?: ReactNode
}

type SurfaceProps<T extends ElementType = "div"> = SurfaceOwnProps<T> &
  Omit<ComponentPropsWithoutRef<T>, keyof SurfaceOwnProps<T>>

/**
 * Surface — base panel primitive.
 * Uses token-based background, border, and radius.
 * Polymorphic via `as` prop (defaults to "div").
 */
export function Surface<T extends ElementType = "div">({
  as,
  className,
  children,
  ...rest
}: SurfaceProps<T>) {
  const Component = as || "div"

  return (
    <Component
      className={cn("surface", className)}
      style={{
        backgroundColor: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-md)",
      }}
      {...rest}
    >
      {children}
    </Component>
  )
}

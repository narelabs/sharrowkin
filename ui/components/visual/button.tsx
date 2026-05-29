"use client"

import { type ButtonHTMLAttributes, type ReactNode } from "react"
import { cn } from "@/lib/utils"

export type ButtonVariant = "primary" | "secondary" | "ghost" | "destructive"
export type ButtonSize = "sm" | "md"

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children?: ReactNode
  className?: string
}

const variantStyles: Record<ButtonVariant, React.CSSProperties> = {
  primary: {
    backgroundColor: "var(--color-accent)",
    color: "var(--color-bg)",
    border: "1px solid var(--color-accent)",
  },
  secondary: {
    backgroundColor: "var(--color-surface-2)",
    color: "var(--color-text)",
    border: "1px solid var(--color-border)",
  },
  ghost: {
    backgroundColor: "transparent",
    color: "var(--color-text)",
    border: "1px solid transparent",
  },
  destructive: {
    backgroundColor: "var(--color-danger)",
    color: "var(--color-bg)",
    border: "1px solid var(--color-danger)",
  },
}

const sizeStyles: Record<ButtonSize, React.CSSProperties> = {
  sm: {
    padding: "var(--space-1) var(--space-3)",
    fontSize: "var(--text-sm)",
    borderRadius: "var(--radius-sm)",
  },
  md: {
    padding: "var(--space-2) var(--space-4)",
    fontSize: "var(--text-base)",
    borderRadius: "var(--radius-md)",
  },
}

/**
 * Button — interactive button with semantic variants and sizes.
 * All colors sourced from CSS custom properties (tokens.css).
 */
export function Button({
  variant = "primary",
  size = "md",
  children,
  className,
  disabled,
  style,
  ...rest
}: ButtonProps) {
  return (
    <button
      className={cn("button", className)}
      data-variant={variant}
      data-size={size}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        fontWeight: 500,
        lineHeight: "var(--leading-tight)",
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.5 : 1,
        transition: `background-color var(--motion-fast) var(--ease-standard), opacity var(--motion-fast) var(--ease-standard)`,
        ...variantStyles[variant],
        ...sizeStyles[size],
        ...style,
      }}
      {...rest}
    >
      {children}
    </button>
  )
}

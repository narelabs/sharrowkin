"use client"

import {
  createContext,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react"
import { cn } from "@/lib/utils"

// ─── MotionBudgetProvider Context ─────────────────────────────────
// Enforces only one Background instance per route.

interface MotionBudgetContextValue {
  /** Returns true if this is the first (allowed) instance */
  claim: () => boolean
  release: () => void
}

const MotionBudgetContext = createContext<MotionBudgetContextValue | null>(null)

export function MotionBudgetProvider({ children }: { children: ReactNode }) {
  const claimedRef = useRef(false)

  const value: MotionBudgetContextValue = {
    claim: () => {
      if (claimedRef.current) return false
      claimedRef.current = true
      return true
    },
    release: () => {
      claimedRef.current = false
    },
  }

  return (
    <MotionBudgetContext.Provider value={value}>
      {children}
    </MotionBudgetContext.Provider>
  )
}

// ─── Background Component ─────────────────────────────────────────

export type BackgroundIntensity = "off" | "subtle" | "full"

export interface BackgroundProps {
  intensity?: BackgroundIntensity
  className?: string
}

const intensityParticleCount: Record<BackgroundIntensity, number> = {
  off: 0,
  subtle: 4,
  full: 8,
}

/**
 * Background — single-instance cinematic background layer.
 * Controlled by MotionBudgetProvider context.
 * Max 8 particle elements. Second mount = no-op + console.warn in dev.
 */
export function Background({ intensity = "subtle", className }: BackgroundProps) {
  const budget = useContext(MotionBudgetContext)
  const [allowed, setAllowed] = useState(false)

  useEffect(() => {
    if (!budget) {
      if (process.env.NODE_ENV === "development") {
        console.warn(
          "[Background] MotionBudgetProvider not found in tree. Background will not render."
        )
      }
      return
    }

    const ok = budget.claim()
    if (!ok) {
      if (process.env.NODE_ENV === "development") {
        console.warn(
          "[Background] Only one Background instance is allowed per route. This instance is a no-op."
        )
      }
      return
    }

    setAllowed(true)
    return () => {
      budget.release()
      setAllowed(false)
    }
  }, [budget])

  if (!allowed || intensity === "off") return null

  const count = intensityParticleCount[intensity]

  return (
    <div
      className={cn("background", className)}
      aria-hidden="true"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: -1,
        overflow: "hidden",
        pointerEvents: "none",
      }}
    >
      {Array.from({ length: count }, (_, i) => (
        <div
          key={i}
          className="background-particle"
          style={{
            position: "absolute",
            borderRadius: "var(--radius-full)",
            backgroundColor: "var(--color-accent)",
            opacity: 0.06 + (i % 3) * 0.02,
            width: `${60 + i * 20}px`,
            height: `${60 + i * 20}px`,
            top: `${10 + (i * 12) % 80}%`,
            left: `${5 + (i * 15) % 85}%`,
            filter: "blur(40px)",
            animation: `background-float var(--motion-slow) var(--ease-standard) infinite alternate`,
            animationDelay: `${i * 200}ms`,
          }}
        />
      ))}
    </div>
  )
}

"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react"

// ─── Constants ────────────────────────────────────────────────────

const STORAGE_KEY = "sharrowkin.motion.reduced"

// ─── Context ──────────────────────────────────────────────────────

interface MotionGateContextValue {
  motionAllowed: boolean
}

const MotionGateContext = createContext<MotionGateContextValue>({ motionAllowed: true })

/**
 * useMotionAllowed — returns whether motion/animation is currently allowed.
 * Combines three sources:
 * 1. prefers-reduced-motion: reduce (OS-level)
 * 2. Manual toggle from localStorage key `sharrowkin.motion.reduced`
 * 3. Page Visibility API (document.hidden)
 *
 * When any source disables motion, returns false.
 */
export function useMotionAllowed(): boolean {
  return useContext(MotionGateContext).motionAllowed
}

// ─── MotionGate Component ─────────────────────────────────────────

export interface MotionGateProps {
  children: ReactNode
}

/**
 * MotionGate — wrapper that combines three motion-disable sources.
 * When any source disables motion, children receive `data-motion="off"`
 * and decorative animations should not render.
 */
export function MotionGate({ children }: MotionGateProps) {
  // Source 1: prefers-reduced-motion
  const [prefersReduced, setPrefersReduced] = useState(false)

  // Source 2: manual toggle from localStorage
  const [manualReduced, setManualReduced] = useState(false)

  // Source 3: page visibility
  const [pageHidden, setPageHidden] = useState(false)

  // Initialize on mount (client-only)
  useEffect(() => {
    // Source 1: matchMedia
    const mql = window.matchMedia("(prefers-reduced-motion: reduce)")
    setPrefersReduced(mql.matches)

    const handleMediaChange = (e: MediaQueryListEvent) => {
      setPrefersReduced(e.matches)
    }
    mql.addEventListener("change", handleMediaChange)

    // Source 2: localStorage
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === "true") {
      setManualReduced(true)
    }

    // Listen for storage changes from other tabs
    const handleStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) {
        setManualReduced(e.newValue === "true")
      }
    }
    window.addEventListener("storage", handleStorage)

    // Source 3: Page Visibility
    setPageHidden(document.hidden)
    const handleVisibility = () => {
      setPageHidden(document.hidden)
    }
    document.addEventListener("visibilitychange", handleVisibility)

    return () => {
      mql.removeEventListener("change", handleMediaChange)
      window.removeEventListener("storage", handleStorage)
      document.removeEventListener("visibilitychange", handleVisibility)
    }
  }, [])

  // Also listen for same-tab localStorage changes via custom event
  useEffect(() => {
    const handleLocalUpdate = () => {
      const stored = localStorage.getItem(STORAGE_KEY)
      setManualReduced(stored === "true")
    }
    window.addEventListener("sharrowkin:motion-toggle", handleLocalUpdate)
    return () => {
      window.removeEventListener("sharrowkin:motion-toggle", handleLocalUpdate)
    }
  }, [])

  const motionAllowed = !prefersReduced && !manualReduced && !pageHidden

  const value = useMemo<MotionGateContextValue>(
    () => ({ motionAllowed }),
    [motionAllowed]
  )

  return (
    <MotionGateContext.Provider value={value}>
      <div data-motion={motionAllowed ? "on" : "off"}>
        {children}
      </div>
    </MotionGateContext.Provider>
  )
}

// ─── Helper for settings page toggle ──────────────────────────────

/**
 * Toggles the manual motion-reduced preference in localStorage.
 * Dispatches a custom event so same-tab MotionGate picks up the change.
 */
export function toggleMotionReduced(reduced: boolean): void {
  localStorage.setItem(STORAGE_KEY, String(reduced))
  window.dispatchEvent(new Event("sharrowkin:motion-toggle"))
}

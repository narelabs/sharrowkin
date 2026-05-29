"use client"

import { useLayoutEffect, type ReactNode } from "react"
import { useTheme } from "next-themes"

/**
 * TokenProvider — syncs the resolved theme from next-themes with the
 * `data-theme` attribute on `document.documentElement`.
 *
 * Uses useLayoutEffect to set the attribute before paint, avoiding flash.
 * Does NOT remount children on theme change — just a fragment wrapper.
 */
export function TokenProvider({ children }: { children: ReactNode }) {
  const { resolvedTheme } = useTheme()

  useLayoutEffect(() => {
    if (resolvedTheme) {
      document.documentElement.setAttribute("data-theme", resolvedTheme)
    }
  }, [resolvedTheme])

  return <>{children}</>
}

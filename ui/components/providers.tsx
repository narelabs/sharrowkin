"use client"

import React, { useState, useEffect, useCallback } from "react"
import { Toaster } from "sonner"
import { CommandPalette } from "@/components/chat/command-palette"
import { ConnectionStatus } from "@/components/chat/connection-status"
import { ErrorBoundary } from "@/components/error-boundary"
import { ThemeProvider } from "@/components/theme-provider"
import { TokenProvider } from "@/components/visual/token-provider"

export function Providers({ children }: { children: React.ReactNode }) {
  const [commandPaletteOpen, setCommandPaletteOpen] = useState(false)

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault()
        setCommandPaletteOpen((prev) => !prev)
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [])

  const handleClose = useCallback(() => {
    setCommandPaletteOpen(false)
  }, [])

  return (
    <ErrorBoundary>
      <ThemeProvider attribute="class" defaultTheme="dark" enableSystem={false}>
        <TokenProvider>
          {children}
        </TokenProvider>
      </ThemeProvider>
      <ConnectionStatus />
      <Toaster
        position="bottom-right"
        toastOptions={{
          style: {
            background: "white",
            border: "1px solid rgba(214, 211, 209, 0.6)",
            borderRadius: "16px",
            fontSize: "13px",
            fontFamily: "var(--font-sans)",
            boxShadow: "0 1px 8px rgba(0,0,0,0.04)",
          },
        }}
      />
      <CommandPalette isOpen={commandPaletteOpen} onClose={handleClose} />
    </ErrorBoundary>
  )
}

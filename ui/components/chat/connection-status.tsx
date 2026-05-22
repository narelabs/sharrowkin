"use client"

import React, { useState, useEffect } from "react"
import { Wifi, WifiOff, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

type ConnectionState = "connected" | "disconnected" | "reconnecting"

export function ConnectionStatus() {
  const [state, setState] = useState<ConnectionState>("connected")
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    let retryCount = 0
    const maxRetries = 5

    const checkHealth = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/health`, { signal: AbortSignal.timeout(5000) })
        if (res.ok) {
          if (state !== "connected") {
            setState("connected")
            setVisible(true)
            setTimeout(() => setVisible(false), 3000)
          } else {
            setVisible(false)
          }
          retryCount = 0
        } else {
          throw new Error("not ok")
        }
      } catch {
        if (retryCount < maxRetries) {
          setState("reconnecting")
          retryCount++
        } else {
          setState("disconnected")
        }
        setVisible(true)
      }
    }

    checkHealth()
    const timer = setInterval(checkHealth, 10000)
    return () => clearInterval(timer)
  }, [state])

  if (!visible) return null

  return (
    <div
      className={cn(
        "fixed bottom-4 left-1/2 -translate-x-1/2 z-[9990] flex items-center gap-2 px-4 py-2 rounded-full border shadow-lg text-[12px] font-medium transition-all duration-300 animate-in fade-in slide-in-from-bottom-2",
        state === "connected" && "bg-emerald-50 border-emerald-200 text-emerald-700",
        state === "disconnected" && "bg-red-50 border-red-200 text-red-700",
        state === "reconnecting" && "bg-amber-50 border-amber-200 text-amber-700"
      )}
    >
      {state === "connected" && <Wifi size={14} />}
      {state === "disconnected" && <WifiOff size={14} />}
      {state === "reconnecting" && <Loader2 size={14} className="animate-spin" />}
      <span>
        {state === "connected" && "Backend connected"}
        {state === "disconnected" && "Backend offline"}
        {state === "reconnecting" && "Reconnecting..."}
      </span>
    </div>
  )
}

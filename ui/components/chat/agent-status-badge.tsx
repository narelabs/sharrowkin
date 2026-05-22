"use client"

import { useEffect, useState } from "react"
import { Zap, CheckCircle2, AlertCircle, Loader2, Pause } from "lucide-react"
import { cn } from "@/lib/utils"

export type AgentStatus = "idle" | "connecting" | "running" | "thinking" | "stabilizing" | "done" | "error" | "stopped"

export function AgentStatusBadge({
  status,
  message,
  className
}: {
  status: AgentStatus
  message?: string
  className?: string
}) {
  const [pulseCount, setPulseCount] = useState(0)

  useEffect(() => {
    if (status === "running" || status === "thinking") {
      const interval = setInterval(() => {
        setPulseCount(c => c + 1)
      }, 500)
      return () => clearInterval(interval)
    }
  }, [status])

  const getStatusConfig = () => {
    switch (status) {
      case "idle":
        return {
          icon: Pause,
          label: "Idle",
          gradient: "from-slate-500 to-slate-600",
          glow: "shadow-slate-500/50",
          border: "border-slate-500/30",
          text: "text-slate-400"
        }
      case "connecting":
        return {
          icon: Loader2,
          label: "Connecting",
          gradient: "from-blue-500 to-cyan-500",
          glow: "shadow-blue-500/50",
          border: "border-blue-500/30",
          text: "text-blue-400",
          animate: true
        }
      case "running":
      case "thinking":
        return {
          icon: Zap,
          label: status === "thinking" ? "Thinking" : "Running",
          gradient: "from-blue-500 via-purple-500 to-pink-500",
          glow: "shadow-purple-500/50",
          border: "border-purple-500/30",
          text: "text-purple-400",
          animate: true
        }
      case "stabilizing":
        return {
          icon: Loader2,
          label: "Stabilizing",
          gradient: "from-yellow-500 to-orange-500",
          glow: "shadow-yellow-500/50",
          border: "border-yellow-500/30",
          text: "text-yellow-400",
          animate: true
        }
      case "done":
        return {
          icon: CheckCircle2,
          label: "Done",
          gradient: "from-green-500 to-emerald-500",
          glow: "shadow-green-500/50",
          border: "border-green-500/30",
          text: "text-green-400"
        }
      case "error":
        return {
          icon: AlertCircle,
          label: "Error",
          gradient: "from-red-500 to-rose-500",
          glow: "shadow-red-500/50",
          border: "border-red-500/30",
          text: "text-red-400"
        }
      case "stopped":
        return {
          icon: Pause,
          label: "Stopped",
          gradient: "from-orange-500 to-red-500",
          glow: "shadow-orange-500/50",
          border: "border-orange-500/30",
          text: "text-orange-400"
        }
      default:
        return {
          icon: Pause,
          label: "Unknown",
          gradient: "from-slate-500 to-slate-600",
          glow: "",
          border: "border-slate-500/30",
          text: "text-slate-400"
        }
    }
  }

  const config = getStatusConfig()
  const Icon = config.icon

  return (
    <div className={cn("relative inline-flex items-center gap-3", className)}>
      {/* Main badge */}
      <div
        className={cn(
          "relative flex items-center gap-2 px-4 py-2 rounded-full border backdrop-blur-xl transition-all duration-300",
          config.border,
          config.animate && "animate-glow-pulse"
        )}
      >
        {/* Background glow */}
        {config.animate && (
          <div className={cn(
            "absolute inset-0 rounded-full bg-gradient-to-r blur-lg animate-pulse",
            config.gradient,
            config.glow
          )} />
        )}

        {/* Icon container */}
        <div className="relative z-10">
          <div className={cn(
            "flex items-center justify-center w-6 h-6 rounded-full bg-gradient-to-br",
            config.gradient
          )}>
            <Icon className={cn(
              "w-4 h-4 text-white",
              config.animate && "animate-spin"
            )} />
          </div>

          {/* Pulse rings for active states */}
          {config.animate && (
            <>
              {[0, 1].map(i => (
                <div
                  key={i}
                  className={cn(
                    "absolute inset-0 rounded-full border animate-ping",
                    config.border
                  )}
                  style={{
                    animationDelay: `${i * 0.5}s`,
                    animationDuration: "1.5s"
                  }}
                />
              ))}
            </>
          )}
        </div>

        {/* Status text */}
        <div className="relative z-10 flex flex-col">
          <span className={cn(
            "text-sm font-bold uppercase tracking-wider",
            config.text
          )}>
            {config.label}
          </span>
          {message && (
            <span className="text-xs text-slate-500">
              {message}
            </span>
          )}
        </div>

        {/* Animated gradient overlay */}
        {config.animate && (
          <div className="absolute inset-0 rounded-full overflow-hidden">
            <div className={cn(
              "absolute inset-0 bg-gradient-to-r opacity-30 animate-gradient-shift",
              config.gradient
            )} />
          </div>
        )}
      </div>

      {/* Energy particles for active states */}
      {config.animate && (
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          {Array.from({ length: 4 }).map((_, i) => (
            <div
              key={i}
              className={cn(
                "absolute w-1 h-1 rounded-full animate-float",
                config.text.replace("text-", "bg-")
              )}
              style={{
                left: `${20 + Math.random() * 60}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 2}s`,
                animationDuration: `${2 + Math.random() * 2}s`
              }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

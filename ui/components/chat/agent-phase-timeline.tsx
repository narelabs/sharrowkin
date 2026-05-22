"use client"

import { Check, Loader2, AlertCircle, Circle } from "lucide-react"
import { cn } from "@/lib/utils"

export interface AgentPhase {
  id: string
  label: string
  status: "pending" | "running" | "done" | "error"
  description?: string
  startedAt?: string
  completedAt?: string
}

export function AgentPhaseTimeline({
  phases,
  currentPhase
}: {
  phases: AgentPhase[]
  currentPhase?: string
}) {
  const getPhaseIcon = (phase: AgentPhase) => {
    switch (phase.status) {
      case "done":
        return <Check className="w-4 h-4" />
      case "running":
        return <Loader2 className="w-4 h-4 animate-spin" />
      case "error":
        return <AlertCircle className="w-4 h-4" />
      default:
        return <Circle className="w-4 h-4" />
    }
  }

  const getPhaseColor = (phase: AgentPhase) => {
    switch (phase.status) {
      case "done":
        return "from-green-500 to-emerald-500"
      case "running":
        return "from-blue-500 to-purple-500"
      case "error":
        return "from-red-500 to-rose-500"
      default:
        return "from-slate-600 to-slate-700"
    }
  }

  const getPhaseGlow = (phase: AgentPhase) => {
    switch (phase.status) {
      case "done":
        return "shadow-green-500/50"
      case "running":
        return "shadow-blue-500/50"
      case "error":
        return "shadow-red-500/50"
      default:
        return ""
    }
  }

  return (
    <div className="relative">
      {/* Connecting line */}
      <div className="absolute left-6 top-8 bottom-8 w-0.5 bg-gradient-to-b from-slate-700 via-slate-600 to-slate-700" />

      {/* Phases */}
      <div className="space-y-6">
        {phases.map((phase, index) => {
          const isActive = phase.status === "running"
          const isDone = phase.status === "done"
          const isError = phase.status === "error"

          return (
            <div
              key={phase.id}
              className={cn(
                "relative flex items-start gap-4 transition-all duration-300",
                isActive && "scale-105"
              )}
            >
              {/* Phase icon */}
              <div className="relative z-10 flex-shrink-0">
                {/* Glow effect */}
                {isActive && (
                  <div className="absolute inset-0 rounded-full bg-blue-500 blur-xl animate-pulse" />
                )}

                {/* Icon container */}
                <div
                  className={cn(
                    "relative flex items-center justify-center w-12 h-12 rounded-full border-2 transition-all duration-300",
                    isDone && "border-green-500 bg-gradient-to-br from-green-500/20 to-emerald-500/20",
                    isActive && "border-blue-500 bg-gradient-to-br from-blue-500/20 to-purple-500/20 shadow-lg shadow-blue-500/50",
                    isError && "border-red-500 bg-gradient-to-br from-red-500/20 to-rose-500/20",
                    !isDone && !isActive && !isError && "border-slate-700 bg-slate-800/50"
                  )}
                >
                  <div
                    className={cn(
                      "flex items-center justify-center w-8 h-8 rounded-full bg-gradient-to-br text-white transition-all duration-300",
                      getPhaseColor(phase),
                      isActive && "animate-pulse"
                    )}
                  >
                    {getPhaseIcon(phase)}
                  </div>

                  {/* Rotating ring for active phase */}
                  {isActive && (
                    <>
                      <div className="absolute inset-0 rounded-full border-2 border-blue-500/30 animate-spin-slow" />
                      <div className="absolute inset-0 rounded-full border-2 border-t-blue-500 border-r-purple-500 border-b-transparent border-l-transparent animate-spin" />
                    </>
                  )}

                  {/* Pulse rings for active phase */}
                  {isActive && (
                    <>
                      {[0, 1, 2].map(i => (
                        <div
                          key={i}
                          className="absolute inset-0 rounded-full border border-blue-500/30 animate-ping"
                          style={{
                            animationDelay: `${i * 0.3}s`,
                            animationDuration: "1.5s"
                          }}
                        />
                      ))}
                    </>
                  )}
                </div>
              </div>

              {/* Phase content */}
              <div className="flex-1 pt-2">
                <div
                  className={cn(
                    "inline-flex items-center gap-2 px-4 py-2 rounded-lg transition-all duration-300",
                    isActive && "bg-gradient-to-r from-blue-500/10 via-purple-500/10 to-pink-500/10 border border-blue-500/20 backdrop-blur-sm",
                    isDone && "bg-green-500/5 border border-green-500/10",
                    isError && "bg-red-500/5 border border-red-500/10",
                    !isActive && !isDone && !isError && "bg-slate-800/30 border border-slate-700/30"
                  )}
                >
                  <div>
                    <h4
                      className={cn(
                        "font-semibold transition-colors duration-300",
                        isActive && "text-blue-400",
                        isDone && "text-green-400",
                        isError && "text-red-400",
                        !isActive && !isDone && !isError && "text-slate-400"
                      )}
                    >
                      {phase.label}
                    </h4>
                    {phase.description && (
                      <p className="text-xs text-slate-500 mt-0.5">
                        {phase.description}
                      </p>
                    )}
                  </div>
                </div>

                {/* Energy particles for active phase */}
                {isActive && (
                  <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    {Array.from({ length: 6 }).map((_, i) => (
                      <div
                        key={i}
                        className="absolute w-1 h-1 bg-blue-400 rounded-full animate-float"
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
            </div>
          )
        })}
      </div>
    </div>
  )
}

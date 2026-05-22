"use client"

import { useEffect, useState } from "react"
import { Brain, Cpu, Zap, Activity, ChevronDown, ChevronUp } from "lucide-react"
import { cn } from "@/lib/utils"

export function AgentThinkingIndicator({
  phase = "thinking",
  message = "Processing...",
  intensity = "medium",
  thinkingText = "",
  progress = 0,
  expandable = true
}: {
  phase?: string
  message?: string
  intensity?: "low" | "medium" | "high"
  thinkingText?: string
  progress?: number
  expandable?: boolean
}) {
  const [pulseCount, setPulseCount] = useState(0)
  const [isExpanded, setIsExpanded] = useState(false)

  useEffect(() => {
    const interval = setInterval(() => {
      setPulseCount(c => c + 1)
    }, 1000)
    return () => clearInterval(interval)
  }, [])

  const getPhaseIcon = () => {
    switch (phase.toLowerCase()) {
      case "observe":
      case "explore":
        return <Activity className="w-5 h-5" />
      case "recall":
      case "context":
        return <Brain className="w-5 h-5" />
      case "reason":
      case "plan":
        return <Cpu className="w-5 h-5" />
      case "stabilize":
      case "verify":
        return <Zap className="w-5 h-5" />
      default:
        return <Brain className="w-5 h-5" />
    }
  }

  const getIntensityClass = () => {
    switch (intensity) {
      case "high":
        return "animate-pulse-fast"
      case "medium":
        return "animate-pulse"
      case "low":
        return "animate-pulse-slow"
      default:
        return "animate-pulse"
    }
  }

  const hasThinking = thinkingText && thinkingText.length > 0
  const canExpand = expandable && hasThinking

  return (
    <div className="relative w-full">
      <div
        className={cn(
          "relative flex items-center gap-3 px-6 py-4 rounded-2xl bg-gradient-to-br from-stone-500/10 via-stone-400/10 to-stone-600/10 border border-stone-400/20 backdrop-blur-xl",
          canExpand && "cursor-pointer hover:border-stone-400/40 transition-colors"
        )}
        onClick={() => canExpand && setIsExpanded(!isExpanded)}
      >
        {/* Animated background glow */}
        <div className="absolute inset-0 rounded-2xl bg-gradient-to-r from-stone-400/20 via-stone-500/20 to-stone-600/20 blur-xl animate-pulse" />

        {/* Rotating ring */}
        <div className="relative flex-shrink-0">
          <div className="absolute inset-0 rounded-full border-2 border-stone-400/30 animate-spin-slow" />
          <div className="absolute inset-0 rounded-full border-2 border-t-stone-400 border-r-stone-500 border-b-stone-600 border-l-transparent animate-spin" />

          {/* Icon */}
          <div className={`relative z-10 p-2 rounded-full bg-gradient-to-br from-stone-400 to-stone-600 text-white shadow-lg ${getIntensityClass()}`}>
            {getPhaseIcon()}
          </div>
        </div>

        {/* Text content */}
        <div className="relative z-10 flex flex-col flex-1 min-w-0">
          <span className="text-sm font-semibold text-stone-600 dark:text-stone-400 uppercase tracking-wider">
            {phase}
          </span>
          <span className="text-xs text-stone-500 dark:text-stone-400 truncate">
            {message}
          </span>

          {/* Progress bar */}
          {progress > 0 && progress < 100 && (
            <div className="mt-2 w-full h-1 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-gradient-to-r from-stone-400 to-stone-600 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          )}
        </div>

        {/* Expand button */}
        {canExpand && (
          <div className="relative z-10 flex-shrink-0">
            {isExpanded ? (
              <ChevronUp className="w-5 h-5 text-stone-500" />
            ) : (
              <ChevronDown className="w-5 h-5 text-stone-500" />
            )}
          </div>
        )}

        {/* Pulse rings */}
        <div className="absolute inset-0 rounded-2xl pointer-events-none">
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="absolute inset-0 rounded-2xl border border-stone-400/30 animate-ping"
              style={{
                animationDelay: `${i * 0.5}s`,
                animationDuration: "2s"
              }}
            />
          ))}
        </div>

        {/* Energy particles */}
        <div className="absolute inset-0 overflow-hidden rounded-2xl pointer-events-none">
          {Array.from({ length: 8 }).map((_, i) => (
            <div
              key={i}
              className="absolute w-1 h-1 bg-stone-400 rounded-full animate-float"
              style={{
                left: `${Math.random() * 100}%`,
                top: `${Math.random() * 100}%`,
                animationDelay: `${Math.random() * 2}s`,
                animationDuration: `${2 + Math.random() * 2}s`
              }}
            />
          ))}
        </div>
      </div>

      {/* Expanded thinking content */}
      {isExpanded && hasThinking && (
        <div className="mt-2 p-4 rounded-xl bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800">
          <div className="flex items-start gap-2">
            <Brain className="w-4 h-4 text-stone-500 flex-shrink-0 mt-1" />
            <div className="flex-1 min-w-0">
              <p className="text-xs font-semibold text-gray-700 dark:text-gray-300 mb-2">
                Thinking Process:
              </p>
              <p className="text-sm text-gray-600 dark:text-gray-400 whitespace-pre-wrap">
                {thinkingText}
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

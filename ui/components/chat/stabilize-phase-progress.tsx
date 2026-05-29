"use client"

import { CheckCircle2, XCircle, Loader2, Clock } from "lucide-react"
import { cn } from "@/lib/utils"
import { useEffect, useState } from "react"

export interface TestProgress {
  phase: "applying_patches" | "running_tests" | "analyzing_results" | "retrying"
  currentTest?: string
  totalTests?: number
  passedTests?: number
  failedTests?: number
  logs?: string[]
  elapsedTime?: number
}

export function StabilizePhaseProgress({ progress }: { progress: TestProgress }) {
  const [elapsed, setElapsed] = useState(progress.elapsedTime || 0)

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed(prev => prev + 100)
    }, 100)
    return () => clearInterval(interval)
  }, [])

  const formatTime = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const deciseconds = Math.floor((ms % 1000) / 100)
    return `${seconds}.${deciseconds}s`
  }

  const getPhaseLabel = () => {
    switch (progress.phase) {
      case "applying_patches":
        return "Применение патчей..."
      case "running_tests":
        return "Запуск тестов..."
      case "analyzing_results":
        return "Анализ результатов..."
      case "retrying":
        return "Повторная попытка..."
    }
  }

  const progressPercent = progress.totalTests
    ? ((progress.passedTests || 0) / progress.totalTests) * 100
    : 0

  return (
    <div className="space-y-4 p-4 rounded-lg bg-slate-800/50 border border-slate-700/50">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Loader2 className="w-5 h-5 text-blue-400 animate-spin" />
          <div>
            <h4 className="font-semibold text-blue-400">{getPhaseLabel()}</h4>
            {progress.currentTest && (
              <p className="text-xs text-slate-400 mt-0.5">{progress.currentTest}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Clock className="w-4 h-4" />
          <span className="font-mono">{formatTime(elapsed)}</span>
        </div>
      </div>

      {/* Progress bar */}
      {progress.totalTests && (
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>
              {progress.passedTests || 0} / {progress.totalTests} тестов пройдено
            </span>
            <span>{Math.round(progressPercent)}%</span>
          </div>
          <div className="h-2 bg-slate-700/50 rounded-full overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-purple-500 transition-all duration-300 ease-out"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>
      )}

      {/* Test stats */}
      {(progress.passedTests !== undefined || progress.failedTests !== undefined) && (
        <div className="flex items-center gap-4 text-sm">
          {progress.passedTests !== undefined && (
            <div className="flex items-center gap-2 text-green-400">
              <CheckCircle2 className="w-4 h-4" />
              <span>{progress.passedTests} passed</span>
            </div>
          )}
          {progress.failedTests !== undefined && progress.failedTests > 0 && (
            <div className="flex items-center gap-2 text-red-400">
              <XCircle className="w-4 h-4" />
              <span>{progress.failedTests} failed</span>
            </div>
          )}
        </div>
      )}

      {/* Logs */}
      {progress.logs && progress.logs.length > 0 && (
        <div className="space-y-1 max-h-32 overflow-y-auto scrollbar-thin scrollbar-thumb-slate-700 scrollbar-track-slate-800/50">
          {progress.logs.slice(-10).map((log, i) => (
            <div
              key={i}
              className={cn(
                "text-xs font-mono px-2 py-1 rounded",
                log.includes("PASSED") && "text-green-400 bg-green-500/10",
                log.includes("FAILED") && "text-red-400 bg-red-500/10",
                !log.includes("PASSED") && !log.includes("FAILED") && "text-slate-400"
              )}
            >
              {log}
            </div>
          ))}
        </div>
      )}

      {/* Animated dots for loading */}
      <div className="flex items-center gap-1">
        {[0, 1, 2].map(i => (
          <div
            key={i}
            className="w-1.5 h-1.5 bg-blue-400 rounded-full animate-bounce"
            style={{
              animationDelay: `${i * 0.15}s`,
              animationDuration: "1s"
            }}
          />
        ))}
      </div>
    </div>
  )
}

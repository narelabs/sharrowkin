"use client"

import { useEffect, useState } from "react"
import { Zap, Brain, Database, Cpu, GitBranch } from "lucide-react"

interface EnergyLedger {
  forward: number
  memory_search: number
  trace_replay: number
  expert_reasoning: number
  hebbian: number
  total: number
  flops_g?: number
}

export function AgentEnergyVisualization({
  energyLedger,
  mode = "Full NARE-Field"
}: {
  energyLedger: EnergyLedger
  mode?: string
}) {
  const [animatedValues, setAnimatedValues] = useState(energyLedger)

  useEffect(() => {
    // Animate values smoothly
    const duration = 800
    const steps = 30
    const stepDuration = duration / steps

    let currentStep = 0
    const interval = setInterval(() => {
      currentStep++
      const progress = currentStep / steps

      setAnimatedValues({
        forward: animatedValues.forward + (energyLedger.forward - animatedValues.forward) * progress,
        memory_search: animatedValues.memory_search + (energyLedger.memory_search - animatedValues.memory_search) * progress,
        trace_replay: animatedValues.trace_replay + (energyLedger.trace_replay - animatedValues.trace_replay) * progress,
        expert_reasoning: animatedValues.expert_reasoning + (energyLedger.expert_reasoning - animatedValues.expert_reasoning) * progress,
        hebbian: animatedValues.hebbian + (energyLedger.hebbian - animatedValues.hebbian) * progress,
        total: animatedValues.total + (energyLedger.total - animatedValues.total) * progress,
        flops_g: energyLedger.flops_g
      })

      if (currentStep >= steps) {
        clearInterval(interval)
        setAnimatedValues(energyLedger)
      }
    }, stepDuration)

    return () => clearInterval(interval)
  }, [energyLedger])

  const energyComponents = [
    {
      key: "forward",
      label: "Forward Pass",
      value: animatedValues.forward,
      icon: Zap,
      color: "from-yellow-500 to-orange-500",
      glow: "shadow-yellow-500/50"
    },
    {
      key: "memory_search",
      label: "Memory Search",
      value: animatedValues.memory_search,
      icon: Database,
      color: "from-blue-500 to-cyan-500",
      glow: "shadow-blue-500/50"
    },
    {
      key: "trace_replay",
      label: "Trace Replay",
      value: animatedValues.trace_replay,
      icon: GitBranch,
      color: "from-green-500 to-emerald-500",
      glow: "shadow-green-500/50"
    },
    {
      key: "expert_reasoning",
      label: "Expert Reasoning",
      value: animatedValues.expert_reasoning,
      icon: Brain,
      color: "from-purple-500 to-pink-500",
      glow: "shadow-purple-500/50"
    },
    {
      key: "hebbian",
      label: "Hebbian Update",
      value: animatedValues.hebbian,
      icon: Cpu,
      color: "from-red-500 to-rose-500",
      glow: "shadow-red-500/50"
    },
  ]

  const maxValue = Math.max(...energyComponents.map(c => c.value), 1)

  return (
    <div className="relative p-6 rounded-2xl bg-gradient-to-br from-slate-900/90 via-slate-800/90 to-slate-900/90 border border-slate-700/50 backdrop-blur-xl overflow-hidden">
      {/* Animated background grid */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute inset-0" style={{
          backgroundImage: `
            linear-gradient(to right, rgba(59, 130, 246, 0.3) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(59, 130, 246, 0.3) 1px, transparent 1px)
          `,
          backgroundSize: "20px 20px",
          animation: "grid-flow 20s linear infinite"
        }} />
      </div>

      {/* Header */}
      <div className="relative z-10 flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="relative">
            <div className="absolute inset-0 bg-blue-500 rounded-lg blur-lg animate-pulse" />
            <div className="relative p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg">
              <Cpu className="w-5 h-5 text-white" />
            </div>
          </div>
          <div>
            <h3 className="text-lg font-bold text-white">Cognitive Energy</h3>
            <p className="text-xs text-slate-400">{mode}</p>
          </div>
        </div>

        {/* Total energy display */}
        <div className="flex flex-col items-end">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
              {animatedValues.total.toFixed(1)}
            </span>
            <span className="text-sm text-slate-400">units</span>
          </div>
          {energyLedger.flops_g && (
            <span className="text-xs text-slate-500">
              {energyLedger.flops_g.toFixed(2)} GFLOPS
            </span>
          )}
        </div>
      </div>

      {/* Energy bars */}
      <div className="relative z-10 space-y-4">
        {energyComponents.map((component, index) => {
          const Icon = component.icon
          const percentage = (component.value / maxValue) * 100

          return (
            <div key={component.key} className="group">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Icon className="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" />
                  <span className="text-sm font-medium text-slate-300 group-hover:text-white transition-colors">
                    {component.label}
                  </span>
                </div>
                <span className="text-sm font-bold text-white">
                  {component.value.toFixed(2)}
                </span>
              </div>

              {/* Progress bar */}
              <div className="relative h-2 bg-slate-800 rounded-full overflow-hidden">
                {/* Glow effect */}
                <div
                  className={`absolute inset-0 bg-gradient-to-r ${component.color} opacity-20 blur-sm`}
                  style={{ width: `${percentage}%` }}
                />

                {/* Main bar */}
                <div
                  className={`absolute inset-0 bg-gradient-to-r ${component.color} transition-all duration-500 ease-out overflow-hidden`}
                  style={{ width: `${percentage}%` }}
                >
                  {/* Shimmer effect */}
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/50 to-transparent animate-shimmer pointer-events-none" />
                </div>

                {/* Pulse effect on hover */}
                <div
                  className={`absolute inset-0 bg-gradient-to-r ${component.color} opacity-0 group-hover:opacity-50 transition-opacity duration-300`}
                  style={{ width: `${percentage}%` }}
                />
              </div>
            </div>
          )
        })}
      </div>

      {/* Floating particles */}
      <div className="absolute inset-0 pointer-events-none overflow-hidden">
        {Array.from({ length: 12 }).map((_, i) => (
          <div
            key={i}
            className="absolute w-1 h-1 bg-blue-400/50 rounded-full animate-float-up"
            style={{
              left: `${Math.random() * 100}%`,
              bottom: 0,
              animationDelay: `${Math.random() * 3}s`,
              animationDuration: `${3 + Math.random() * 2}s`
            }}
          />
        ))}
      </div>
    </div>
  )
}

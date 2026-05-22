"use client"

import { Brain, Zap, Code, Sparkles } from "lucide-react"
import { useEffect, useState } from "react"

export function AgentHeroSection() {
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div className="relative flex flex-col items-center justify-center min-h-[60vh] px-4 overflow-hidden">
      {/* Animated background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-blue-500/5 via-purple-500/5 to-pink-500/5 animate-gradient-shift" />

      {/* Grid pattern */}
      <div className="absolute inset-0 opacity-10">
        <div className="absolute inset-0" style={{
          backgroundImage: `
            linear-gradient(to right, rgba(59, 130, 246, 0.3) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(59, 130, 246, 0.3) 1px, transparent 1px)
          `,
          backgroundSize: "40px 40px",
          animation: "grid-flow 20s linear infinite"
        }} />
      </div>

      {/* Floating orbs */}
      <div className="absolute inset-0 overflow-hidden pointer-events-none">
        {Array.from({ length: 8 }).map((_, i) => (
          <div
            key={i}
            className="absolute w-64 h-64 rounded-full blur-3xl opacity-20 animate-float"
            style={{
              left: `${Math.random() * 100}%`,
              top: `${Math.random() * 100}%`,
              background: `radial-gradient(circle, ${
                i % 3 === 0 ? "rgba(59, 130, 246, 0.5)" :
                i % 3 === 1 ? "rgba(168, 85, 247, 0.5)" :
                "rgba(236, 72, 153, 0.5)"
              } 0%, transparent 70%)`,
              animationDelay: `${i * 0.5}s`,
              animationDuration: `${8 + i * 2}s`
            }}
          />
        ))}
      </div>

      {/* Main content */}
      <div className="relative z-10 flex flex-col items-center text-center space-y-8">
        {/* Logo/Icon */}
        <div className="relative">
          {/* Glow rings */}
          {[0, 1, 2].map(i => (
            <div
              key={i}
              className="absolute inset-0 rounded-full border-2 border-blue-500/30 animate-ping"
              style={{
                animationDelay: `${i * 0.5}s`,
                animationDuration: "3s",
                transform: `scale(${1 + i * 0.3})`
              }}
            />
          ))}

          {/* Main icon */}
          <div className="relative">
            <div className="absolute inset-0 bg-gradient-to-br from-blue-500 to-purple-600 rounded-3xl blur-2xl opacity-50 animate-pulse" />
            <div className="relative flex items-center justify-center w-24 h-24 bg-gradient-to-br from-blue-500 via-purple-500 to-pink-500 rounded-3xl shadow-2xl shadow-blue-500/50">
              <Brain className="w-12 h-12 text-white animate-pulse" />
            </div>
          </div>

          {/* Orbiting particles */}
          {[0, 1, 2, 3].map(i => (
            <div
              key={i}
              className="absolute w-3 h-3 bg-blue-400 rounded-full animate-float"
              style={{
                left: `${50 + Math.cos(i * Math.PI / 2) * 60}px`,
                top: `${50 + Math.sin(i * Math.PI / 2) * 60}px`,
                animationDelay: `${i * 0.5}s`
              }}
            />
          ))}
        </div>

        {/* Title */}
        <div className="space-y-4">
          <h1 className={`text-6xl font-bold bg-gradient-to-r from-blue-400 via-purple-400 to-pink-400 bg-clip-text text-transparent transition-all duration-1000 ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}>
            Sharrowkin Agent
          </h1>
          <p className={`text-xl text-slate-400 max-w-2xl transition-all duration-1000 delay-200 ${
            mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
          }`}>
            Autonomous AI coding agent with deep code understanding and intelligent reasoning
          </p>
        </div>

        {/* Features */}
        <div className={`grid grid-cols-1 md:grid-cols-3 gap-6 mt-12 transition-all duration-1000 delay-400 ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}>
          {[
            {
              icon: Brain,
              title: "Deep Understanding",
              description: "Semantic code analysis with context linking",
              gradient: "from-blue-500 to-cyan-500"
            },
            {
              icon: Zap,
              title: "Fast Execution",
              description: "5-phase reasoning with NARE-Field optimization",
              gradient: "from-purple-500 to-pink-500"
            },
            {
              icon: Code,
              title: "Smart Debugging",
              description: "Data flow analysis and intelligent error detection",
              gradient: "from-green-500 to-emerald-500"
            }
          ].map((feature, i) => {
            const Icon = feature.icon
            return (
              <div
                key={i}
                className="relative group p-6 rounded-2xl bg-gradient-to-br from-slate-900/50 to-slate-800/50 border border-slate-700/50 backdrop-blur-xl hover:border-slate-600/50 transition-all duration-300"
              >
                {/* Glow on hover */}
                <div className={`absolute inset-0 rounded-2xl bg-gradient-to-br ${feature.gradient} opacity-0 group-hover:opacity-10 blur-xl transition-opacity duration-300`} />

                <div className="relative z-10 flex flex-col items-center text-center space-y-3">
                  <div className={`p-3 rounded-xl bg-gradient-to-br ${feature.gradient}`}>
                    <Icon className="w-6 h-6 text-white" />
                  </div>
                  <h3 className="text-lg font-semibold text-white">
                    {feature.title}
                  </h3>
                  <p className="text-sm text-slate-400">
                    {feature.description}
                  </p>
                </div>

                {/* Hover particles */}
                <div className="absolute inset-0 overflow-hidden rounded-2xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  {Array.from({ length: 3 }).map((_, j) => (
                    <div
                      key={j}
                      className={`absolute w-1 h-1 rounded-full animate-float bg-gradient-to-r ${feature.gradient}`}
                      style={{
                        left: `${20 + Math.random() * 60}%`,
                        top: `${Math.random() * 100}%`,
                        animationDelay: `${j * 0.3}s`
                      }}
                    />
                  ))}
                </div>
              </div>
            )
          })}
        </div>

        {/* CTA */}
        <div className={`flex items-center gap-4 mt-8 transition-all duration-1000 delay-600 ${
          mounted ? "opacity-100 translate-y-0" : "opacity-0 translate-y-4"
        }`}>
          <div className="flex items-center gap-2 px-6 py-3 rounded-full bg-gradient-to-r from-blue-500 via-purple-500 to-pink-500 text-white font-semibold shadow-lg shadow-purple-500/50 animate-pulse">
            <Sparkles className="w-5 h-5" />
            <span>Start chatting below</span>
          </div>
        </div>
      </div>
    </div>
  )
}

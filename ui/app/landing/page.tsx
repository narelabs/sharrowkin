"use client"

import { useState, useEffect } from "react"
import { useRouter } from "next/navigation"
import { ArrowRight, Zap, Brain, Code, GitBranch, Sparkles, CheckCircle2, Github } from "lucide-react"
import { cn } from "@/lib/utils"

export default function LandingPage() {
  const router = useRouter()
  const [mounted, setMounted] = useState(false)

  useEffect(() => {
    setMounted(true)
  }, [])

  return (
    <div className="min-h-screen bg-white">
      {/* Hero Section */}
      <section className="relative overflow-hidden">
        {/* Animated Background Grid */}
        <div className="absolute inset-0 -z-10">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#f0f0f0_1px,transparent_1px),linear-gradient(to_bottom,#f0f0f0_1px,transparent_1px)] bg-[size:4rem_4rem] [mask-image:radial-gradient(ellipse_80%_50%_at_50%_0%,#000_70%,transparent_110%)]" />
        </div>

        {/* Floating Orbs */}
        <div className="absolute top-20 left-10 w-72 h-72 bg-emerald-500/10 rounded-full blur-3xl animate-float" />
        <div className="absolute top-40 right-20 w-96 h-96 bg-emerald-400/10 rounded-full blur-3xl animate-float-slow" />

        <div className="container mx-auto px-6 pt-20 pb-32">
          {/* Header */}
          <nav className="flex items-center justify-between mb-20">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
                <Sparkles className="w-6 h-6 text-white" />
              </div>
              <span className="text-2xl font-bold bg-gradient-to-r from-emerald-600 to-emerald-500 bg-clip-text text-transparent">
                Sharrowkin
              </span>
            </div>
            <div className="flex items-center gap-4">
              <a
                href="https://github.com/narelabs/sharrowkin"
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-2 px-4 py-2 text-sm text-stone-600 hover:text-stone-900 transition-colors"
              >
                <Github size={18} />
                GitHub
              </a>
              <button
                onClick={() => router.push("/chat")}
                className="px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg transition-all shadow-lg shadow-emerald-500/20 hover:shadow-emerald-500/30"
              >
                Try Now
              </button>
            </div>
          </nav>

          {/* Hero Content */}
          <div className="max-w-4xl mx-auto text-center">
            <div className={cn(
              "inline-flex items-center gap-2 px-4 py-2 bg-emerald-50 border border-emerald-200 rounded-full text-sm text-emerald-700 font-medium mb-8",
              mounted && "text-blur-intro"
            )}>
              <Sparkles size={16} className="text-emerald-500" />
              Autonomous AI Developer Agent
            </div>

            <h1 className={cn(
              "text-6xl md:text-7xl font-bold text-stone-900 mb-6 leading-tight",
              mounted && "text-blur-intro-delay"
            )}>
              Code that writes itself.
              <br />
              <span className="bg-gradient-to-r from-emerald-600 via-emerald-500 to-emerald-600 bg-clip-text text-transparent animate-gradient-shift">
                Powered by memory.
              </span>
            </h1>

            <p className={cn(
              "text-xl text-stone-600 mb-12 max-w-2xl mx-auto leading-relaxed",
              mounted && "fade-in"
            )}>
              Sharrowkin is an autonomous developer agent with 5-phase reasoning cycle and 4 memory systems.
              It learns from every task, remembers solutions, and gets smarter over time.
            </p>

            <div className={cn(
              "flex items-center justify-center gap-4",
              mounted && "fade-in"
            )}>
              <button
                onClick={() => router.push("/chat")}
                className="group flex items-center gap-2 px-8 py-4 bg-emerald-600 hover:bg-emerald-700 text-white font-medium rounded-xl transition-all shadow-xl shadow-emerald-500/30 hover:shadow-emerald-500/40 hover:scale-105"
              >
                Start Building
                <ArrowRight size={18} className="group-hover:translate-x-1 transition-transform" />
              </button>
              <button
                onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
                className="px-8 py-4 bg-white hover:bg-stone-50 text-stone-700 font-medium rounded-xl border border-stone-200 transition-all"
              >
                Learn More
              </button>
            </div>

            {/* Stats */}
            <div className="grid grid-cols-3 gap-8 mt-20 max-w-2xl mx-auto">
              <div className="text-center">
                <div className="text-4xl font-bold text-emerald-600 mb-2">5</div>
                <div className="text-sm text-stone-600">Reasoning Phases</div>
              </div>
              <div className="text-center">
                <div className="text-4xl font-bold text-emerald-600 mb-2">4</div>
                <div className="text-sm text-stone-600">Memory Systems</div>
              </div>
              <div className="text-center">
                <div className="text-4xl font-bold text-emerald-600 mb-2">∞</div>
                <div className="text-sm text-stone-600">Learning Capacity</div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-32 bg-stone-50/50">
        <div className="container mx-auto px-6">
          <div className="text-center mb-20">
            <h2 className="text-4xl md:text-5xl font-bold text-stone-900 mb-4">
              Built for autonomous development
            </h2>
            <p className="text-xl text-stone-600 max-w-2xl mx-auto">
              Sharrowkin combines advanced reasoning with persistent memory to deliver truly autonomous coding.
            </p>
          </div>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-8 max-w-6xl mx-auto">
            {/* Feature 1 */}
            <div className="group p-8 bg-white rounded-2xl border border-stone-200 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-500/10 transition-all">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Brain className="w-6 h-6 text-emerald-600" />
              </div>
              <h3 className="text-xl font-bold text-stone-900 mb-3">5-Phase Reasoning</h3>
              <p className="text-stone-600 leading-relaxed">
                Observe → Recall → Reason → Stabilize → Commit. Each phase builds on the last, ensuring thorough analysis and validation.
              </p>
            </div>

            {/* Feature 2 */}
            <div className="group p-8 bg-white rounded-2xl border border-stone-200 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-500/10 transition-all">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Sparkles className="w-6 h-6 text-emerald-600" />
              </div>
              <h3 className="text-xl font-bold text-stone-900 mb-3">Dynamic Memory</h3>
              <p className="text-stone-600 leading-relaxed">
                DSM, RLD, MemoryField, and TraceMemory work together to remember solutions, patterns, and strategies.
              </p>
            </div>

            {/* Feature 3 */}
            <div className="group p-8 bg-white rounded-2xl border border-stone-200 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-500/10 transition-all">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Code className="w-6 h-6 text-emerald-600" />
              </div>
              <h3 className="text-xl font-bold text-stone-900 mb-3">AST Analysis</h3>
              <p className="text-stone-600 leading-relaxed">
                Deep code understanding through semantic graphs, dependency analysis, and complexity metrics.
              </p>
            </div>

            {/* Feature 4 */}
            <div className="group p-8 bg-white rounded-2xl border border-stone-200 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-500/10 transition-all">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <Zap className="w-6 h-6 text-emerald-600" />
              </div>
              <h3 className="text-xl font-bold text-stone-900 mb-3">Self-Healing</h3>
              <p className="text-stone-600 leading-relaxed">
                Automatically detects and fixes errors, learns from failures, and improves with every iteration.
              </p>
            </div>

            {/* Feature 5 */}
            <div className="group p-8 bg-white rounded-2xl border border-stone-200 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-500/10 transition-all">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <GitBranch className="w-6 h-6 text-emerald-600" />
              </div>
              <h3 className="text-xl font-bold text-stone-900 mb-3">GitHub Integration</h3>
              <p className="text-stone-600 leading-relaxed">
                Clone repos, create branches, commit changes, and open PRs - all autonomously.
              </p>
            </div>

            {/* Feature 6 */}
            <div className="group p-8 bg-white rounded-2xl border border-stone-200 hover:border-emerald-200 hover:shadow-xl hover:shadow-emerald-500/10 transition-all">
              <div className="w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center mb-6 group-hover:scale-110 transition-transform">
                <CheckCircle2 className="w-6 h-6 text-emerald-600" />
              </div>
              <h3 className="text-xl font-bold text-stone-900 mb-3">Test-Driven</h3>
              <p className="text-stone-600 leading-relaxed">
                Runs tests after every change, validates solutions, and ensures code quality automatically.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Architecture Section */}
      <section className="py-32">
        <div className="container mx-auto px-6">
          <div className="max-w-4xl mx-auto">
            <div className="text-center mb-16">
              <h2 className="text-4xl md:text-5xl font-bold text-stone-900 mb-4">
                How it works
              </h2>
              <p className="text-xl text-stone-600">
                A sophisticated 5-phase cycle powered by 4 memory systems
              </p>
            </div>

            {/* Phase Flow */}
            <div className="space-y-6">
              {[
                {
                  phase: "1. Observe",
                  description: "Scans workspace, builds AST, analyzes dependencies and complexity",
                  color: "emerald"
                },
                {
                  phase: "2. Recall",
                  description: "Retrieves similar solutions from DSM, RLD patterns, and TraceMemory",
                  color: "emerald"
                },
                {
                  phase: "3. Reason",
                  description: "Generates solution using LLM with full context and memory",
                  color: "emerald"
                },
                {
                  phase: "4. Stabilize",
                  description: "Validates changes, runs tests, fixes errors automatically",
                  color: "emerald"
                },
                {
                  phase: "5. Commit",
                  description: "Saves solution to memory, updates strategies, learns from success",
                  color: "emerald"
                }
              ].map((item, idx) => (
                <div
                  key={idx}
                  className="flex items-start gap-6 p-6 bg-white rounded-xl border border-stone-200 hover:border-emerald-200 hover:shadow-lg transition-all group"
                >
                  <div className="flex-shrink-0 w-12 h-12 bg-emerald-100 rounded-xl flex items-center justify-center text-emerald-600 font-bold group-hover:scale-110 transition-transform">
                    {idx + 1}
                  </div>
                  <div>
                    <h3 className="text-lg font-bold text-stone-900 mb-2">{item.phase}</h3>
                    <p className="text-stone-600">{item.description}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-32 bg-gradient-to-br from-emerald-600 to-emerald-500 relative overflow-hidden">
        {/* Animated Background */}
        <div className="absolute inset-0 opacity-10">
          <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff_1px,transparent_1px),linear-gradient(to_bottom,#ffffff_1px,transparent_1px)] bg-[size:4rem_4rem]" />
        </div>

        <div className="container mx-auto px-6 relative z-10">
          <div className="max-w-3xl mx-auto text-center">
            <h2 className="text-4xl md:text-5xl font-bold text-white mb-6">
              Ready to build with AI?
            </h2>
            <p className="text-xl text-emerald-50 mb-12">
              Start using Sharrowkin today. No credit card required.
            </p>
            <button
              onClick={() => router.push("/chat")}
              className="group inline-flex items-center gap-2 px-10 py-5 bg-white hover:bg-stone-50 text-emerald-600 font-bold text-lg rounded-xl transition-all shadow-2xl hover:scale-105"
            >
              Get Started Free
              <ArrowRight size={20} className="group-hover:translate-x-1 transition-transform" />
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 bg-stone-50 border-t border-stone-200">
        <div className="container mx-auto px-6">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-emerald-500 to-emerald-600 rounded-lg flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-white" />
              </div>
              <span className="text-lg font-bold text-stone-900">Sharrowkin</span>
            </div>
            <div className="text-sm text-stone-600">
              © 2026 Narelabs. Built with ❤️ for developers.
            </div>
            <div className="flex items-center gap-6">
              <a href="https://github.com/narelabs/sharrowkin" target="_blank" rel="noopener noreferrer" className="text-stone-600 hover:text-stone-900 transition-colors">
                GitHub
              </a>
              <a href="/chat" className="text-stone-600 hover:text-stone-900 transition-colors">
                Chat
              </a>
              <a href="/workflow" className="text-stone-600 hover:text-stone-900 transition-colors">
                Workflow
              </a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

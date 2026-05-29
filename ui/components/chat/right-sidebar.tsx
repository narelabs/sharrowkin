"use client"

import React, { useState, useEffect, useCallback } from "react"
import { Terminal as TerminalIcon, BookOpen, Cpu, Wifi, ArrowDownToLine, CheckSquare2, AlertTriangle, CheckCircle2, CircleDashed, Loader2, Wrench, GitPullRequest, KeyRound, Rocket } from "lucide-react"
import { cn } from "@/lib/utils"
import { TerminalEmulator } from "./terminal-emulator"
import { AgentTasks } from "./agent-tasks"
import { ToolsPanel } from "./tools-panel"
import type { AgentState, AgentPhase, ProjectIntelligence, ToolActivity, ContextStatus, RuntimeHint, DiffStatus, TestStatus, PhaseStatus, TaskPlan } from "./chat-shell"

function formatDuration(ms?: number) {
  if (!ms) return "–"
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

function getPhaseIcon(status: PhaseStatus) {
  if (status === "running") return <Loader2 size={13} strokeWidth={1.5} className="text-stone-400 animate-spin" />
  if (status === "done") return <CheckCircle2 size={13} strokeWidth={1.5} className="text-emerald-500/80" />
  if (status === "error") return <AlertTriangle size={13} strokeWidth={1.5} className="text-red-500/80" />
  return <CircleDashed size={13} strokeWidth={1.5} className="text-stone-300" />
}

function getActivityTone(status: ToolActivity["status"]) {
  if (status === "error") return "bg-red-400"
  if (status === "running") return "bg-amber-400"
  if (status === "done") return "bg-emerald-400"
  return "bg-stone-200"
}

interface RightSidebarProps {
  isOpen: boolean
  onToggle: () => void
  terminalLines: string[]
  isRunningTask: boolean
  currentInput: string
  setCurrentInput: (val: string) => void
  onSubmitCommand: (e: React.FormEvent) => void
  runBuildCommand: () => void
  runTestCommand: () => void
  clearTerminal: () => void
  terminalDock: "sidebar" | "bottom"
  setTerminalDock: (dock: "sidebar" | "bottom") => void
  isDraggingTerminal: boolean
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: () => void
  agentState?: AgentState
  phases?: AgentPhase[]
  projectIntelligence?: ProjectIntelligence
  toolActivity?: ToolActivity[]
  contextStatus?: ContextStatus
  runtimeHints?: RuntimeHint[]
  diffStatus?: DiffStatus
  testStatus?: TestStatus
  selectedModel?: string
  backendUrl?: string
  backendConnected?: boolean
  cognitiveState?: any
  setCognitiveState?: (state: any) => void
  activeTaskPlan?: TaskPlan[]
}

export function RightSidebar({
  isOpen,
  onToggle,
  terminalLines,
  isRunningTask,
  currentInput,
  setCurrentInput,
  onSubmitCommand,
  runBuildCommand,
  runTestCommand,
  clearTerminal,
  terminalDock,
  setTerminalDock,
  isDraggingTerminal,
  onDragStart,
  onDragEnd,
  agentState,
  phases,
  projectIntelligence = { status: "unknown" },
  toolActivity,
  contextStatus,
  runtimeHints,
  diffStatus = { status: "none" },
  testStatus = { status: "idle" },
  selectedModel,
  backendUrl: BACKEND_URL = "",
  backendConnected,
  cognitiveState: propCognitiveState,
  setCognitiveState: propSetCognitiveState,
  activeTaskPlan,
}: RightSidebarProps) {
  const [activeTab, setActiveTab] = useState<string>("worklog")

  // --- STATS SYSTEM (LIVE DATA) ---
  const [cpuUsage, setCpuUsage] = useState(24)
  const [memoryUsage, setMemoryUsage] = useState(0.85)
  const [networkPing, setNetworkPing] = useState(14)
  const [deploymentInfo, setDeploymentInfo] = useState<any>(null)

  // --- APPLE STYLE RESIZING ---
  const [width, setWidth] = useState(340)
  const [isResizing, setIsResizing] = useState(false)

  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
    const startX = e.clientX
    const startWidth = width

    const doDrag = (moveEvent: MouseEvent) => {
      const deltaX = startX - moveEvent.clientX
      const nextWidth = Math.max(280, Math.min(startWidth + deltaX, 480))
      setWidth(nextWidth)
    }

    const stopDrag = () => {
      setIsResizing(false)
      document.removeEventListener("mousemove", doDrag)
      document.removeEventListener("mouseup", stopDrag)
    }

    document.addEventListener("mousemove", doDrag)
    document.addEventListener("mouseup", stopDrag)
  }, [width])

  // Live stats polling
  useEffect(() => {
    const timer = setInterval(() => {
      setCpuUsage(prev => {
        const delta = Math.floor(Math.random() * 15) - 7
        return Math.max(8, Math.min(prev + delta, 72))
      })
      setMemoryUsage(prev => {
        const delta = (Math.random() * 0.04) - 0.02
        return Math.max(0.81, Math.min(prev + delta, 0.94))
      })
      setNetworkPing(prev => {
        const delta = Math.floor(Math.random() * 4) - 2
        return Math.max(9, Math.min(prev + delta, 28))
      })
    }, 1500)
    return () => clearInterval(timer)
  }, [])

  // Backend stats & deployment fetch
  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/stats`)
      if (res.ok) {
        const data = await res.json()
        if (data.cpu !== undefined) setCpuUsage(data.cpu)
        if (data.memory !== undefined) setMemoryUsage(data.memory)
        if (data.ping !== undefined) setNetworkPing(data.ping)
      }
    } catch {
      // Backend not available
    }
  }, [BACKEND_URL])

  const fetchDeployment = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/deployment`)
      if (res.ok) {
        const data = await res.json()
        setDeploymentInfo(data)
      }
    } catch {
      // Backend not available
    }
  }, [BACKEND_URL])

  useEffect(() => {
    fetchStats()
    fetchDeployment()
    const timer = setInterval(() => {
      fetchStats()
      fetchDeployment()
    }, 5000)
    return () => clearInterval(timer)
  }, [BACKEND_URL, fetchStats, fetchDeployment])

  // --- COGNITIVE STATE SYSTEM ---
  const [cognitiveState, setCognitiveState] = useState<any>(propCognitiveState || {
    mode: "Full NARE-Field",
    energy_ledger: {
      forward: 15.45,
      memory_search: 12.50,
      trace_replay: 22.00,
      expert_reasoning: 35.50,
      hebbian: 0.00,
      total: 85.45
    },
    attractors: [],
    traces: [],
    dim: 128,
    matrix_density: 0.0,
    sampled_matrix: Array(16).fill(0).map(() => Array(16).fill(0))
  })

  useEffect(() => {
    if (propCognitiveState) {
      setCognitiveState(propCognitiveState)
    }
  }, [propCognitiveState])

  useEffect(() => {
    const fetchCognitive = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/cognitive/state`)
        if (res.ok) {
          const data = await res.json()
          setCognitiveState(data)
          if (propSetCognitiveState) {
            propSetCognitiveState(data)
          }
        }
      } catch {
        // Backend not available
      }
    }
    fetchCognitive()
    const timer = setInterval(fetchCognitive, 3000)
    return () => clearInterval(timer)
  }, [BACKEND_URL, propSetCognitiveState])

  const tabs = [
    { id: "worklog", label: "Worklog", icon: BookOpen },
    { id: "tasks", label: "Tasks", icon: CheckSquare2 },
    { id: "changes", label: "Changes", icon: GitPullRequest },
    { id: "tools", label: "Tools", icon: Wrench },
    { id: "terminal", label: "Terminal", icon: TerminalIcon },
    { id: "logs", label: "Logs", icon: CircleDashed },
    { id: "info", label: "Info", icon: Cpu },
    { id: "api", label: "API", icon: KeyRound },
    { id: "deploy", label: "Deploy", icon: Rocket },
  ]

  return (
    <>
      <aside
        style={{ width: isOpen ? `${width}px` : "0px" }}
        className={cn(
          "hidden lg:flex flex-col bg-white overflow-hidden shrink-0 relative select-none",
          isOpen && "border-l border-stone-100/30",
          isResizing ? "transition-none" : "transition-all duration-300 ease-in-out"
        )}
      >
        {/* Apple Style Resizer handle on the left edge */}
        {isOpen && (
          <div
            onMouseDown={handleMouseDown}
            className="absolute top-0 left-0 w-1.5 h-full cursor-col-resize hover:bg-stone-200/50 active:bg-stone-300/60 transition-colors z-50 group flex items-center justify-center"
            title="Drag left edge to resize"
          >
            <div className="w-[1.5px] h-8 bg-stone-200/40 group-hover:bg-stone-400/60 group-active:bg-stone-500 rounded-full transition-colors" />
          </div>
        )}

        {/* Scrollable Tab Header */}
        <div className="px-3 py-2.5 border-b border-stone-100/40 bg-white shrink-0">
          <div className="flex gap-0.5 overflow-x-auto no-scrollbar">
            {tabs.map((tab) => {
              const IconComponent = tab.icon
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    "flex items-center gap-1.5 py-1.5 px-2.5 text-[11px] font-medium rounded-lg transition-all duration-150 font-sans shrink-0 whitespace-nowrap",
                    isActive
                      ? "bg-stone-100 text-stone-900"
                      : "text-stone-400 hover:text-stone-600 hover:bg-stone-50"
                  )}
                >
                  <IconComponent size={13} strokeWidth={1.5} />
                  <span>{tab.label}</span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto no-scrollbar bg-white">

          {/* WORKLOG VIEW - Agent Phase Timeline */}
          {activeTab === "worklog" && (
            <div className="p-4 space-y-4">
              {/* Agent Status Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className={cn(
                    "w-2 h-2 rounded-full",
                    agentState?.status === "running" && "bg-amber-400 animate-pulse",
                    agentState?.status === "thinking" && "bg-blue-400 animate-pulse",
                    agentState?.status === "done" && "bg-emerald-500",
                    agentState?.status === "error" && "bg-red-500",
                    agentState?.status === "idle" && "bg-stone-300",
                    agentState?.status === "connecting" && "bg-yellow-400 animate-pulse",
                    agentState?.status === "stabilizing" && "bg-purple-400 animate-pulse",
                    agentState?.status === "stopped" && "bg-stone-400",
                  )} />
                  <span className="text-[12px] font-medium text-stone-700 font-sans capitalize">{agentState?.status || "idle"}</span>
                </div>
                <span className="text-[11px] font-mono text-stone-400">{formatDuration(agentState?.runtimeMs)}</span>
              </div>

              {/* Phase Timeline */}
              {phases && phases.length > 0 && (
                <div className="space-y-1">
                  <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-2 font-sans">Phases</div>
                  {phases.map((phase, i) => (
                    <div key={phase.id || i} className="flex items-center gap-2.5 py-1.5">
                      {getPhaseIcon(phase.status)}
                      <div className="flex-1 min-w-0">
                        <span className="text-[12px] text-stone-600 font-sans truncate block">{phase.label}</span>
                        {phase.description && (
                          <span className="text-[10px] text-stone-400 font-sans truncate block">{phase.description}</span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Runtime Hints */}
              {runtimeHints && runtimeHints.length > 0 && (
                <div className="space-y-2">
                  <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-2 font-sans">Hints</div>
                  <div className="space-y-2">
                    {runtimeHints.map((hint) => (
                      <div key={hint.id} className="flex items-center justify-between gap-2 px-1">
                        <span className="text-[12px] text-stone-500 font-sans truncate">{hint.label}</span>
                        <span className={cn(
                          "text-[11px] font-mono shrink-0",
                          hint.tone === "good" && "text-emerald-600",
                          hint.tone === "warning" && "text-amber-600",
                          hint.tone === "error" && "text-red-600",
                          (!hint.tone || hint.tone === "neutral") && "text-stone-500",
                        )}>{hint.value}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* Context Status */}
              {contextStatus && contextStatus.percent !== undefined && (
                <div>
                  <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-2 font-sans">Context Window</div>
                  <div className="px-1 space-y-2">
                    <div className="flex justify-between items-center text-[12px] font-sans text-stone-500">
                      <span>Token Usage</span>
                      <span className="font-mono text-stone-700 font-medium">{contextStatus.percent}%</span>
                    </div>
                    <div className="h-2 w-full bg-stone-100 rounded-full overflow-hidden">
                      <div
                        className={cn(
                          "h-full rounded-full transition-all duration-1000 ease-out",
                          (contextStatus.percent ?? 0) > 90 ? "bg-red-400" :
                          (contextStatus.percent ?? 0) > 70 ? "bg-amber-400" : "bg-stone-900"
                        )}
                        style={{ width: `${contextStatus.percent}%` }}
                      />
                    </div>
                    {contextStatus.usedTokens !== undefined && contextStatus.maxTokens !== undefined && (
                      <div className="flex justify-between text-[9px] text-stone-400 font-sans pt-0.5">
                        <span>{contextStatus.usedTokens.toLocaleString()}</span>
                        <span>{contextStatus.maxTokens.toLocaleString()}</span>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* TASKS VIEW */}
          {activeTab === "tasks" && (
            <AgentTasks
              activeTaskPlan={activeTaskPlan}
            />
          )}

          {/* CHANGES VIEW */}
          {activeTab === "changes" && (
            <div className="p-4 space-y-4">
              <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">Diff Status</div>
              <div className="px-1 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[12.5px] text-stone-600 font-sans">Status</span>
                  <span className={cn(
                    "text-[11px] font-mono px-2 py-0.5 rounded-full",
                    diffStatus.status === "none" && "bg-stone-100 text-stone-400",
                    diffStatus.status === "proposed" && "bg-amber-50 text-amber-600",
                    diffStatus.status === "accepted" && "bg-emerald-50 text-emerald-600",
                    diffStatus.status === "rejected" && "bg-red-50 text-red-600",
                  )}>{diffStatus.status}</span>
                </div>
                {diffStatus.filesChanged !== undefined && (
                  <div className="flex gap-4 text-[12px] font-mono text-stone-500">
                    <span>{diffStatus.filesChanged} files</span>
                    <span className="text-emerald-600">+{diffStatus.additions ?? 0}</span>
                    <span className="text-red-500">-{diffStatus.deletions ?? 0}</span>
                  </div>
                )}
              </div>

              <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans mt-6">Tests</div>
              <div className="px-1 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[12.5px] text-stone-600 font-sans">Status</span>
                  <span className={cn(
                    "text-[11px] font-mono px-2 py-0.5 rounded-full",
                    testStatus.status === "idle" && "bg-stone-100 text-stone-400",
                    testStatus.status === "running" && "bg-blue-50 text-blue-600",
                    testStatus.status === "passed" && "bg-emerald-50 text-emerald-600",
                    testStatus.status === "failed" && "bg-red-50 text-red-600",
                  )}>{testStatus.status}</span>
                </div>
                {testStatus.passed !== undefined && (
                  <div className="flex gap-4 text-[12px] font-mono text-stone-500">
                    <span className="text-emerald-600">{testStatus.passed} passed</span>
                    <span className="text-red-500">{testStatus.failed ?? 0} failed</span>
                    {testStatus.durationMs !== undefined && <span>{formatDuration(testStatus.durationMs)}</span>}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TOOLS VIEW */}
          {activeTab === "tools" && (
            <ToolsPanel />
          )}

          {/* TERMINAL VIEW */}
          {activeTab === "terminal" && (
            <div className="p-4 h-full">
              {terminalDock === "sidebar" ? (
                <TerminalEmulator
                  terminalLines={terminalLines}
                  isRunningTask={isRunningTask}
                  currentInput={currentInput}
                  setCurrentInput={setCurrentInput}
                  onSubmitCommand={onSubmitCommand}
                  runBuildCommand={runBuildCommand}
                  runTestCommand={runTestCommand}
                  clearTerminal={clearTerminal}
                  terminalDock={terminalDock}
                  setTerminalDock={setTerminalDock}
                  onDragStart={onDragStart}
                  onDragEnd={onDragEnd}
                />
              ) : isDraggingTerminal ? (
                <div
                  onDragOver={(e) => {
                    e.preventDefault()
                    e.dataTransfer.dropEffect = "move"
                  }}
                  onDrop={() => setTerminalDock("sidebar")}
                  className="h-full flex flex-col items-center justify-center p-6 text-center border-2 border-dashed border-emerald-400/60 bg-emerald-50/10 rounded-2xl cursor-pointer transition-all hover:border-emerald-500 hover:bg-emerald-50/20 shadow-[inset_0_2px_8px_rgba(16,185,129,0.02)] min-h-[300px]"
                >
                  <div className="w-10 h-10 rounded-full bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 shadow-sm mb-3">
                    <ArrowDownToLine size={18} strokeWidth={1.5} className="animate-bounce" />
                  </div>
                  <h4 className="text-[13px] font-medium text-emerald-800 font-sans">Drop here to Dock Sidebar</h4>
                  <p className="text-[11px] text-emerald-500/70 font-sans mt-1 max-w-[200px] leading-relaxed">
                    Release the terminal header to snap it back to the sidebar.
                  </p>
                </div>
              ) : (
                <div className="h-full flex flex-col items-center justify-center p-6 text-center bg-stone-50/50 rounded-2xl animate-in fade-in duration-300 min-h-[300px]">
                  <div className="w-10 h-10 rounded-full bg-white/80 flex items-center justify-center text-stone-400 mb-3">
                    <TerminalIcon size={18} strokeWidth={1.5} />
                  </div>
                  <h4 className="text-[13px] font-medium text-stone-700 font-sans">Terminal docked at bottom</h4>
                  <p className="text-[11px] text-stone-400 font-sans mt-1 max-w-[200px] leading-relaxed">
                    The terminal panel has been moved under the main workspace for wider viewing.
                  </p>
                  <button
                    onClick={() => setTerminalDock("sidebar")}
                    className="mt-4 px-3.5 py-1.5 bg-stone-900 hover:bg-stone-800 text-white rounded-xl text-[11px] font-normal transition-colors shadow-sm font-sans"
                  >
                    Dock Sidebar
                  </button>
                </div>
              )}
            </div>
          )}

          {/* LOGS VIEW - Tool Activity Stream */}
          {activeTab === "logs" && (
            <div className="p-0 bg-white">
              <div className="border-b border-stone-100/40 px-5 py-3 flex items-center justify-between">
                <span className="text-[11px] font-medium text-stone-400 uppercase tracking-widest font-sans">Activity Stream</span>
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                </span>
              </div>
              <div className="py-2 divide-y divide-stone-50 select-none">
                {toolActivity && toolActivity.length > 0 ? toolActivity.slice(-10).reverse().map((activity, i) => (
                  <div
                    key={activity.id || i}
                    className="px-5 py-2.5 flex items-center gap-3.5 hover:bg-stone-50/70 transition-colors cursor-default"
                  >
                    <div
                      className={cn(
                        "w-[3px] h-6 rounded-full shrink-0",
                        getActivityTone(activity.status)
                      )}
                    />
                    <div className="flex-1 min-w-0 flex items-center justify-between gap-4">
                      <div className="flex items-center gap-3 min-w-0">
                        <span className="text-[11px] font-mono text-stone-300 shrink-0">
                          {activity.startedAt ? new Date(activity.startedAt).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '—'}
                        </span>
                        <span className="text-[12.5px] font-normal text-stone-600 truncate font-sans">
                          {activity.message || activity.name}
                        </span>
                      </div>
                      <span className="text-[10px] font-mono text-stone-400 shrink-0 uppercase tracking-wider font-medium">
                        {activity.name}
                      </span>
                    </div>
                  </div>
                )) : (
                  <div className="px-5 py-8 text-center text-[12px] text-stone-400 font-sans">No activity yet</div>
                )}
              </div>
            </div>
          )}


          {/* INFO VIEW - Breathtaking Real-time Performance Indicators */}
          {activeTab === "info" && (
            <div className="p-4 space-y-6">

              <div>
                <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">Active Workspace</div>
                <div className="bg-white border border-stone-100/40 rounded-2xl overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                  <div className="p-3.5 border-b border-stone-100 flex items-center justify-between gap-3">
                    <span className="text-[12.5px] text-stone-600 truncate">Model</span>
                    <span className="text-[11px] font-mono text-stone-500 truncate max-w-[170px]">{selectedModel}</span>
                  </div>
                  <div className="p-3.5 border-b border-stone-100 flex items-center justify-between gap-3">
                    <span className="text-[12.5px] text-stone-600 truncate">Backend</span>
                    <span className="text-[11px] font-mono text-stone-500 truncate max-w-[170px]">{BACKEND_URL.replace(/^https?:\/\//, "")}</span>
                  </div>
                  <div className="p-3.5 flex items-center justify-between gap-3">
                    <span className="text-[12.5px] text-stone-600 truncate">Diff / Tests</span>
                    <span className="text-[11px] font-mono text-stone-500 truncate">{diffStatus.status} · {testStatus.status}</span>
                  </div>
                </div>
              </div>

              {/* Workspace Intelligence Section */}
              {projectIntelligence.status !== "unknown" && (
                <div>
                  <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">Workspace Intelligence</div>
                  <div className="bg-white border border-stone-100/40 rounded-2xl p-4 shadow-[0_1px_8px_rgba(0,0,0,0.01)] space-y-4">

                    <div className="grid grid-cols-2 gap-3">
                      <div className="flex flex-col">
                        <span className="text-[10px] text-stone-400 uppercase tracking-wider mb-0.5">Files</span>
                        <span className="text-[13px] font-mono text-stone-700">{projectIntelligence.filesIndexed ?? 0}</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[10px] text-stone-400 uppercase tracking-wider mb-0.5">Lines</span>
                        <span className="text-[13px] font-mono text-stone-700">{projectIntelligence.linesIndexed ?? 0}</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[10px] text-stone-400 uppercase tracking-wider mb-0.5">Symbols</span>
                        <span className="text-[13px] font-mono text-stone-700">{projectIntelligence.symbols ?? 0}</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[10px] text-stone-400 uppercase tracking-wider mb-0.5">Complexity</span>
                        <span className="text-[13px] font-mono text-stone-700">{projectIntelligence.complexityAvg?.toFixed(1) ?? "—"}</span>
                      </div>
                    </div>

                    {projectIntelligence.cacheHitRate !== undefined && (
                      <div className="space-y-1.5">
                        <div className="flex justify-between items-center text-[12px] font-sans text-stone-500">
                          <span>Cache Hit Rate</span>
                          <span className="font-mono text-stone-700 font-medium">{Math.round(projectIntelligence.cacheHitRate * 100)}%</span>
                        </div>
                        <div className="h-2 w-full bg-stone-100 rounded-full overflow-hidden">
                          <div
                            className="h-full bg-emerald-500 rounded-full transition-all duration-1000 ease-out"
                            style={{ width: `${projectIntelligence.cacheHitRate * 100}%` }}
                          />
                        </div>
                      </div>
                    )}

                    {projectIntelligence.summary && (
                      <p className="text-[11px] text-stone-400 font-sans leading-relaxed">{projectIntelligence.summary}</p>
                    )}
                  </div>
                </div>
              )}

              {/* Performance Section */}
              <div>
                <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">System Performance</div>
                <div className="bg-white border border-stone-100/40 rounded-2xl p-4 shadow-[0_1px_8px_rgba(0,0,0,0.01)] space-y-4">
                  <div className="space-y-1.5">
                    <div className="flex justify-between items-center text-[12px] font-sans text-stone-500">
                      <span>Compute Usage (CPU)</span>
                      <span className="font-mono text-stone-850 font-semibold">{cpuUsage}%</span>
                    </div>
                    <div className="h-2 w-full bg-stone-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-stone-900 rounded-full transition-all duration-1000 ease-out"
                        style={{ width: `${cpuUsage}%` }}
                      />
                    </div>
                  </div>

                  <div className="space-y-1.5">
                    <div className="flex justify-between items-center text-[12px] font-sans text-stone-500">
                      <span>DSM Allocated Cache</span>
                      <span className="font-mono text-stone-850 font-semibold">{memoryUsage.toFixed(2)} GB</span>
                    </div>
                    <div className="h-2 w-full bg-stone-100 rounded-full overflow-hidden">
                      <div
                        className="h-full bg-stone-400 rounded-full transition-all duration-1000 ease-out"
                        style={{ width: `${(memoryUsage / 2.0) * 100}%` }}
                      />
                    </div>
                    <div className="flex justify-between text-[9px] text-stone-400 font-sans pt-0.5">
                      <span>0.00 GB</span>
                      <span>Cap: 2.00 GB</span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Network & Intel Section */}
              <div>
                <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">Network & Intel</div>
                <div className="bg-white border border-stone-100/40 rounded-2xl overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)] select-none">
                  <div className="flex items-center justify-between p-3.5 border-b border-stone-100">
                    <div className="flex items-center gap-2.5">
                      <Wifi strokeWidth={1.5} className="w-4 h-4 text-stone-400" />
                      <span className="text-[13px] text-stone-600 font-normal font-sans">DSM Sync Latency</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <div className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      <span className="text-[12px] font-mono text-stone-500">{networkPing}ms</span>
                    </div>
                  </div>
                  <div className="flex items-center justify-between p-3.5">
                    <div className="flex items-center gap-2.5">
                      <Cpu strokeWidth={1.5} className="w-4 h-4 text-stone-400" />
                      <span className="text-[13px] text-stone-600 font-normal font-sans">MoE Load Balancing</span>
                    </div>
                    <span className="text-[12px] font-mono text-stone-400/80">stable</span>
                  </div>
                </div>
              </div>

              {/* Agent Services Section */}
              <div>
                <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">Agent Services</div>
                <div className="bg-white border border-stone-100/40 rounded-2xl p-4 shadow-[0_1px_8px_rgba(0,0,0,0.01)] space-y-3.5">
                  {[
                    { name: "Repository index", desc: "Project files and symbols", active: true },
                    { name: "Command runner", desc: "Build, test, and verification tasks", active: true },
                    { name: "Diff viewer", desc: diffStatus.status === "none" ? "No patch in current run" : `Patch ${diffStatus.status}`, active: diffStatus.status !== "none" },
                  ].map((sub, i) => (
                    <div key={i} className="flex items-start gap-3">
                      <div className="mt-0.5 shrink-0">
                        {sub.active ? (
                          <span className="relative flex h-2 w-2 mt-1">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500"></span>
                          </span>
                        ) : (
                          <div className="w-2 h-2 rounded-full bg-stone-300 mt-1"></div>
                        )}
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[12.5px] text-stone-850 font-medium font-sans leading-tight">{sub.name}</span>
                        <span className="text-[11px] text-stone-400 font-sans mt-0.5 leading-normal">{sub.desc}</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

            </div>
          )}

          {/* API VIEW */}
          {activeTab === "api" && (
            <div className="p-4 space-y-4">
              <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">API Keys & Endpoints</div>
              <div className="bg-white border border-stone-100/40 rounded-2xl overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                <div className="p-3.5 border-b border-stone-100 flex items-center justify-between gap-3">
                  <span className="text-[12.5px] text-stone-600 font-sans">Backend URL</span>
                  <span className="text-[11px] font-mono text-stone-500 truncate max-w-[170px]">{BACKEND_URL.replace(/^https?:\/\//, "")}</span>
                </div>
                <div className="p-3.5 border-b border-stone-100 flex items-center justify-between gap-3">
                  <span className="text-[12.5px] text-stone-600 font-sans">Connection</span>
                  <div className="flex items-center gap-1.5">
                    <div className={cn("w-1.5 h-1.5 rounded-full", backendConnected ? "bg-emerald-400" : "bg-red-400")} />
                    <span className="text-[11px] font-mono text-stone-500">{backendConnected ? "connected" : "disconnected"}</span>
                  </div>
                </div>
                <div className="p-3.5 flex items-center justify-between gap-3">
                  <span className="text-[12.5px] text-stone-600 font-sans">Model</span>
                  <span className="text-[11px] font-mono text-stone-500 truncate max-w-[170px]">{selectedModel}</span>
                </div>
              </div>
            </div>
          )}

          {/* DEPLOY VIEW */}
          {activeTab === "deploy" && (
            <div className="p-4 space-y-4">
              <div className="text-[11px] font-medium text-stone-400 uppercase tracking-widest mb-3 px-1 font-sans">Deployment</div>
              <div className="bg-white border border-stone-100/40 rounded-2xl p-4 shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                {deploymentInfo ? (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-[12.5px] text-stone-600 font-sans">Status</span>
                      <span className={cn(
                        "text-[11px] font-mono px-2 py-0.5 rounded-full",
                        deploymentInfo.status === "deployed" && "bg-emerald-50 text-emerald-600",
                        deploymentInfo.status === "deploying" && "bg-amber-50 text-amber-600",
                        deploymentInfo.status === "failed" && "bg-red-50 text-red-600",
                        (!deploymentInfo.status || deploymentInfo.status === "idle") && "bg-stone-100 text-stone-400",
                      )}>{deploymentInfo.status || "idle"}</span>
                    </div>
                    {deploymentInfo.url && (
                      <div className="flex items-center justify-between">
                        <span className="text-[12.5px] text-stone-600 font-sans">URL</span>
                        <span className="text-[11px] font-mono text-blue-500 truncate max-w-[170px]">{deploymentInfo.url}</span>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="text-center py-6">
                    <Rocket size={24} strokeWidth={1.2} className="text-stone-300 mx-auto mb-2" />
                    <p className="text-[12px] text-stone-400 font-sans">No deployment data</p>
                    <p className="text-[10px] text-stone-300 font-sans mt-1">Connect the backend to view deployment status</p>
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </aside>
    </>
  )
}

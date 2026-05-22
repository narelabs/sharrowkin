"use client"

import React, { useState, useEffect, useCallback, useRef } from "react"
import { LeftSidebar } from "./left-sidebar"
import { RightSidebar } from "./right-sidebar"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
import { 
  Zap, 
  Play, 
  Square, 
  Settings, 
  RefreshCw, 
  Plus, 
  Clock, 
  ShieldCheck, 
  X, 
  Check, 
  Sliders,
  Cpu,
  Layers,
  Terminal,
  ArrowRight,
  GitBranch,
  Search,
  Sparkles,
  Activity,
  Code,
  FileText,
  CheckCircle2
} from "lucide-react"
import { cn } from "@/lib/utils"

export function AutomationsShell() {
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)

  // Terminal state for RightSidebar
  const [terminalLines, setTerminalLines] = useState<string[]>([])
  const [isRunningTask, setIsRunningTask] = useState(false)
  const [currentInput, setCurrentInput] = useState("")
  const [terminalDock, setTerminalDock] = useState<"sidebar" | "bottom">("sidebar")
  const [isDraggingTerminal, setIsDraggingTerminal] = useState(false)

  // Real-time Agent WebSocket state
  const [agentLogs, setAgentLogs] = useState<string[]>([
    "System initialized. Awaiting task launch...",
  ])
  const [currentPhase, setCurrentPhase] = useState<string>("idle") // idle, observe, recall, reason, stabilize, commit, failed
  const [generatedDiff, setGeneratedDiff] = useState<string>("")
  const [taskPrompt, setTaskPrompt] = useState("Run full test suite via pytest and stabilize any failing tests")
  const [targetWorkspace, setTargetWorkspace] = useState("")
  const [workspacePath, setWorkspacePath] = useState("")
  
  const socketRef = useRef<WebSocket | null>(null)
  const logsEndRef = useRef<HTMLDivElement | null>(null)

  // Auto scroll logs
  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [agentLogs])

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const response = await fetch(`${BACKEND_URL}/api/settings`)
        if (!response.ok) return
        const data = await response.json()
        if (data.workspace_path) {
          setWorkspacePath(data.workspace_path)
          setTargetWorkspace((current) => current || data.workspace_path)
        }
      } catch {}
    }
    loadSettings()
  }, [])

  const runBuildCommand = useCallback(() => {
    if (isRunningTask) return
    setIsRunningTask(true)
    setTerminalLines(prev => [...prev, "", "$ npm run build"])
    fetch(`${BACKEND_URL}/api/terminal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "npm run build" }),
    })
      .then((res) => res.json())
      .then((data) => setTerminalLines((prev) => [...prev, ...(Array.isArray(data.output) ? data.output : [JSON.stringify(data)])]))
      .catch((err) => setTerminalLines((prev) => [...prev, `error: ${err.message}`]))
      .finally(() => setIsRunningTask(false))
  }, [isRunningTask])

  const runTestCommand = useCallback(() => {
    if (isRunningTask) return
    setIsRunningTask(true)
    setTerminalLines(prev => [...prev, "", "$ npm test"])
    fetch(`${BACKEND_URL}/api/terminal`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: "npm test" }),
    })
      .then((res) => res.json())
      .then((data) => setTerminalLines((prev) => [...prev, ...(Array.isArray(data.output) ? data.output : [JSON.stringify(data)])]))
      .catch((err) => setTerminalLines((prev) => [...prev, `error: ${err.message}`]))
      .finally(() => setIsRunningTask(false))
  }, [isRunningTask])

  const clearTerminal = useCallback(() => {
    setTerminalLines([])
  }, [])

  const handleCommandSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentInput) return
    const cmd = currentInput.trim()
    setTerminalLines(prev => [...prev, `$ ${currentInput}`])
    setCurrentInput("")
    setIsRunningTask(true)

    try {
      const response = await fetch(`${BACKEND_URL}/api/terminal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      })

      if (!response.ok) {
        throw new Error("Failed to communicate with NARE-Field backend.")
      }

      const data = await response.json()
      if (data.output && Array.isArray(data.output)) {
        setTerminalLines((prev) => [...prev, ...data.output])
      }
    } catch (err: any) {
      setTerminalLines((prev) => [
        ...prev,
        `bash: command failed: ${cmd}`,
        `error: ${err.message}`
      ])
    } finally {
      setIsRunningTask(false)
    }
  }, [currentInput])

  // WebSocket Agent runner
  const handleLaunchAgent = useCallback((customPrompt?: string) => {
    if (isRunningTask) return
    const activePrompt = customPrompt || taskPrompt
    setIsRunningTask(true)
    setAgentLogs([])
    setGeneratedDiff("")
    setCurrentPhase("observe")
    setTerminalLines(prev => [...prev, ``, `[AGENT] Starting autonomous workspace task: "${activePrompt}"`])

    const WS_URL = BACKEND_URL.replace(/^http/, "ws")
    const ws = new WebSocket(`${WS_URL}/api/agent/ws`)
    socketRef.current = ws

    ws.onopen = () => {
      const githubToken = localStorage.getItem("github_token") || ""
      ws.send(JSON.stringify({
        task: activePrompt,
          workspace_path: targetWorkspace,
          plan_mode: "autonomous",
          github_token: githubToken,
      }))
      setAgentLogs(prev => [...prev, "[WS] Connected to sharrowkin agent broker.", "[WS] Dispatched task payload..."])
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)

        if (data.type === "phase_change") {
          setCurrentPhase(data.phase)
          setAgentLogs(prev => [...prev, ``, `➔ Phase Transition: ${data.phase.toUpperCase()}`])
        } else if (data.type === "log") {
          setAgentLogs(prev => [...prev, `[${data.level?.toUpperCase() || "INFO"}] ${data.message}`])
        } else if (data.type === "diff" || data.type === "patch_proposed") {
          if (data.diff) {
            setGeneratedDiff(data.diff)
          }
          setAgentLogs(prev => [...prev, `✔ Proposed code patch generated successfully.`])
        } else if (data.type === "content") {
          setAgentLogs(prev => [...prev, data.content])
        } else if (data.type === "test_result") {
          setAgentLogs(prev => [
            ...prev,
            `[TESTS] Run complete. Exit Code: ${data.exit_code}`,
            `[PYTEST] Output:\n${data.output}`
          ])
        } else if (data.type === "status" && data.status === "done") {
          setIsRunningTask(false)
          setCurrentPhase("commit")
          setAgentLogs(prev => [...prev, ``, `✔ Autonomous run complete.`])
          triggerToast("Agent run completed.")
        } else if (data.type === "status" && (data.status === "error" || data.status === "needs_key")) {
          setIsRunningTask(false)
          setCurrentPhase("failed")
          setAgentLogs(prev => [...prev, ``, `✖ AGENT FAILURE: ${data.status}`])
          triggerToast("Agent run needs attention.")
        } else if (data.type === "error") {
          setIsRunningTask(false)
          setCurrentPhase("failed")
          setAgentLogs(prev => [...prev, ``, `✖ AGENT FAILURE: ${data.message}`])
          triggerToast("Agent run failed.")
        }
      } catch (err) {
        console.error("Failed to parse socket message", err)
      }
    }

    ws.onerror = (err) => {
      setAgentLogs(prev => [...prev, "✖ WebSocket error. Check if backend port 8000 is active."])
      setIsRunningTask(false)
      setCurrentPhase("failed")
    }

    ws.onclose = () => {
      setAgentLogs(prev => [...prev, "[WS] WebSocket channel disconnected."])
      setIsRunningTask(false)
    }
  }, [isRunningTask, taskPrompt, targetWorkspace])

  const handleStopAgent = useCallback(() => {
    if (socketRef.current) {
      socketRef.current.close()
    }
    setIsRunningTask(false)
    setCurrentPhase("idle")
    setAgentLogs(prev => [...prev, "[WS] Forcefully aborted agent routine."])
  }, [])

  // Terminal dock drag state
  const handleDragStart = useCallback(() => setIsDraggingTerminal(true), [])
  const handleDragEnd = useCallback(() => setIsDraggingTerminal(false), [])

  useEffect(() => {
    const handleGlobalDragEnd = () => setIsDraggingTerminal(false)
    window.addEventListener("dragend", handleGlobalDragEnd)
    window.addEventListener("drop", handleGlobalDragEnd)
    return () => {
      window.removeEventListener("dragend", handleGlobalDragEnd)
      window.removeEventListener("drop", handleGlobalDragEnd)
    }
  }, [])

  const [successToast, setSuccessToast] = useState("")

  const triggerToast = (msg: string) => {
    setSuccessToast(msg)
    setTimeout(() => setSuccessToast(""), 3500)
  }

  // Phase layout items
  const phases = [
    { key: "observe", label: "Explore", desc: "Repository analysis" },
    { key: "recall", label: "Context", desc: "Load relevant files" },
    { key: "reason", label: "Plan", desc: "Decide the changes" },
    { key: "stabilize", label: "Verify", desc: "Run checks" },
    { key: "commit", label: "Finalize", desc: "Prepare summary" }
  ]

  // Recommended workspace actions
  const recommendedActions = [
    {
      title: "Run tests and fix failures",
      prompt: "Run the full test suite and fix any failing tests",
      desc: "Runs checks, identifies failures, and applies focused fixes."
    },
    {
      title: "Summarize recent work",
      prompt: "Generate a concise report for recent workspace changes",
      desc: "Aggregates changes into a professional engineering update."
    },
    {
      title: "Analyze repository structure",
      prompt: "Analyze the full workspace and map the application architecture",
      desc: "Scans code, routes, components, dependencies, and key files."
    },
    {
      title: "Review implementation quality",
      prompt: "Review the current implementation and list the highest impact improvements",
      desc: "Finds code quality, UX, reliability, and verification gaps."
    }
  ]

  const repoLabel = workspacePath ? workspacePath.split(/[\\/]/).filter(Boolean).pop() || workspacePath : "No workspace selected"

  return (
    <div className="h-dvh bg-background flex overflow-hidden">
      <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />

      {/* Main Area */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-[#f7f7f9] overflow-hidden">
        
        {/* Top Header - White & Clean */}
        <div className="h-14 border-b border-stone-200/60 flex items-center justify-between px-8 bg-white/80 backdrop-blur-md z-10 shrink-0">
          <div className="flex items-center gap-2.5 text-stone-850">
            <Zap className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
            <span className="font-medium text-[13px] tracking-wide text-stone-700">sharrowkin AI Core</span>
          </div>
          <div className="flex items-center gap-4 text-[11px] text-stone-400 font-mono">
            <div className="flex items-center gap-1.5">
              <span className={cn(
                "w-2 h-2 rounded-full",
                isRunningTask ? "bg-emerald-500 animate-pulse" : "bg-stone-300"
              )} />
              <span>Status: {isRunningTask ? "ACTIVE RUN" : "AWAITING INSTRUCTION"}</span>
            </div>
          </div>
        </div>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-8 relative">
          <div className="max-w-4xl mx-auto space-y-6 animate-in fade-in duration-300">
            
            {/* 1. AGENT HERO CARD: Meet sharrowkin, connected to your project! */}
            <div className="border border-stone-200/60 bg-white rounded-3xl p-8 shadow-[0_1px_15px_rgba(0,0,0,0.015)] relative overflow-hidden">
              <div className="absolute top-0 right-0 w-64 h-64 bg-stone-50 rounded-full blur-3xl -z-10 translate-x-12 -translate-y-12" />
              
              <div className="flex flex-col md:flex-row gap-6 items-start md:items-center">
                {/* Visual Neural Node Animation / Avatar */}
                <div className="w-14 h-14 rounded-full bg-stone-900 flex items-center justify-center shrink-0 shadow-md relative">
                  <Cpu className="w-6 h-6 text-white stroke-[1.25]" />
                  <span className="absolute bottom-0 right-0 w-3.5 h-3.5 bg-emerald-500 border-2 border-white rounded-full animate-pulse" />
                </div>

                <div className="space-y-1 flex-1">
                  <div className="flex items-center gap-2.5 flex-wrap">
                    <h2 className="text-lg font-normal text-stone-800 tracking-tight">sharrowkin Developer Agent</h2>
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-stone-100 text-stone-600 border border-stone-200/30">
                      v0.1.0 Active
                    </span>
                  </div>
                  <p className="text-[13px] text-stone-400 font-light max-w-xl leading-relaxed">
                    I am connected to <span className="font-mono text-[12px] bg-stone-50 px-1.5 py-0.5 rounded text-stone-700">{repoLabel}</span>. 
                    I can read the repository, plan changes, edit code, run tests, and report the result clearly.
                  </p>
                </div>
              </div>

              {/* Connected Project Stats Pill Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6 pt-6 border-t border-stone-100">
                <div className="space-y-0.5">
                  <span className="text-[10px] text-stone-400 uppercase tracking-widest block">Active Repo</span>
                  <span className="text-[12.5px] font-mono text-stone-800 font-normal truncate block">{repoLabel}</span>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] text-stone-400 uppercase tracking-widest block">Intelligence</span>
                  <span className="text-[12.5px] text-stone-800 font-normal">Repository-aware</span>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] text-stone-400 uppercase tracking-widest block">Local Memory</span>
                  <span className="text-[12.5px] font-mono text-stone-800 font-normal">Context ready</span>
                </div>
                <div className="space-y-0.5">
                  <span className="text-[10px] text-stone-400 uppercase tracking-widest block">Healing Loop</span>
                  <span className="text-[12.5px] text-stone-800 font-normal">Test verification</span>
                </div>
              </div>
            </div>

            {/* 2. RECOMMENDED PROJECT ACTIONS: Clicking one runs the agent immediately! */}
            <div className="space-y-3">
              <span className="text-[11px] font-medium text-stone-400 uppercase tracking-widest px-1 block">
                What do you want me to do in your project?
              </span>
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {recommendedActions.map((action, idx) => (
                  <button
                    key={idx}
                    onClick={() => {
                      setTaskPrompt(action.prompt)
                      handleLaunchAgent(action.prompt)
                    }}
                    disabled={isRunningTask}
                    className="flex flex-col text-left p-4.5 bg-white border border-stone-200/60 rounded-2xl hover:border-stone-800 hover:shadow-sm transition-all duration-200 group relative disabled:opacity-60 disabled:cursor-not-allowed"
                  >
                    <div className="flex items-center justify-between w-full mb-1">
                      <span className="text-[13.5px] font-medium text-stone-850 group-hover:text-stone-950 transition-colors">
                        {action.title}
                      </span>
                      <ArrowRight className="w-3.5 h-3.5 text-stone-300 group-hover:text-stone-700 transition-colors transform group-hover:translate-x-1" />
                    </div>
                    <span className="text-[11.5px] text-stone-400 font-light leading-relaxed">
                      {action.desc}
                    </span>
                  </button>
                ))}
              </div>
            </div>

            {/* 3. CUSTOM SPECIFICATION PROMPT BAR */}
            <div className="border border-stone-200/60 bg-white rounded-2xl p-6 shadow-[0_1px_8px_rgba(0,0,0,0.01)] space-y-4">
              <div className="flex items-center justify-between border-b border-stone-100 pb-3">
                <span className="text-[11px] font-medium text-stone-400 uppercase tracking-widest">Or enter a custom instruction</span>
                <span className="text-[11px] font-mono text-stone-400 truncate">workspace: {targetWorkspace || workspacePath || "not configured"}</span>
              </div>

              <div className="space-y-4">
                <div className="space-y-1.5">
                  <textarea
                    rows={2}
                    value={taskPrompt}
                    onChange={(e) => setTaskPrompt(e.target.value)}
                    placeholder="Describe a custom task for the agent (e.g. 'Write a new python function for computing metrics' or 'Find unused variables')..."
                    disabled={isRunningTask}
                    className="w-full p-4 border border-stone-250/70 rounded-2xl text-[13px] font-sans text-stone-800 placeholder:text-stone-300 focus:outline-none focus:border-stone-400 focus:ring-0 transition-colors bg-stone-50/20 font-light resize-none"
                  />
                </div>

                <div className="flex flex-col sm:flex-row gap-3 items-center justify-between">
                  <div className="flex items-center gap-1.5 text-[11px] text-stone-400 font-mono">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    <span>Auto-compiling, AST-parsing, Pytest execution</span>
                  </div>
                  
                  {isRunningTask ? (
                    <button
                      onClick={handleStopAgent}
                      className="w-full sm:w-auto h-10 flex items-center justify-center gap-1.5 px-6 bg-stone-900 hover:bg-stone-850 text-white rounded-xl text-[12.5px] transition-colors shadow-sm font-sans"
                    >
                      <Square className="w-3.5 h-3.5 fill-white" />
                      <span>Abort Agent Execution</span>
                    </button>
                  ) : (
                    <button
                      onClick={() => handleLaunchAgent()}
                      disabled={!taskPrompt.trim()}
                      className="w-full sm:w-auto h-10 flex items-center justify-center gap-1.5 px-6 bg-stone-900 hover:bg-stone-850 text-white rounded-xl text-[12.5px] transition-colors shadow-sm font-sans disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Play className="w-3.5 h-3.5 fill-white" />
                      <span>Launch Autonomous Run</span>
                    </button>
                  )}
                </div>
              </div>
            </div>

            {/* 4. ACTIVE COGNITIVE CYCLE RUN STATUS (ONLY VISIBLE/EXPANDED ON RUN) */}
            {(isRunningTask || currentPhase !== "idle") && (
              <div className="border border-stone-200/60 bg-white rounded-2xl p-6 shadow-[0_1px_8px_rgba(0,0,0,0.01)] animate-in slide-in-from-top duration-300">
                <span className="text-[11px] font-medium text-stone-400 uppercase tracking-widest block mb-4">
                  Active Execution Cycle
                </span>
                
                <div className="grid grid-cols-1 sm:grid-cols-5 gap-3">
                  {phases.map((p, idx) => {
                    const isActive = currentPhase === p.key
                    const isPast = ["observe", "recall", "reason", "stabilize", "commit"].indexOf(currentPhase) > idx
                    return (
                      <div 
                        key={p.key}
                        className={cn(
                          "p-3 rounded-xl border transition-all text-center flex flex-col gap-1 items-center justify-center relative",
                          isActive 
                            ? "border-stone-800 bg-stone-50/50 shadow-sm" 
                            : isPast 
                              ? "border-stone-200/60 bg-white text-stone-400" 
                              : "border-stone-150 bg-stone-50/30 text-stone-300"
                        )}
                      >
                        <div className="flex items-center gap-1.5">
                          <span className={cn(
                            "w-2 h-2 rounded-full",
                            isActive ? "bg-stone-800 animate-ping" : isPast ? "bg-stone-400" : "bg-stone-200"
                          )} />
                          <span className="text-[12.5px] font-medium tracking-tight">{p.label}</span>
                        </div>
                        <span className="text-[10px] font-light leading-tight">{p.desc}</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {/* 5. PROCESS LOGS & DIFF PANEL (ONLY VISIBLE/EXPANDED ON RUN) */}
            {(isRunningTask || currentPhase !== "idle") && (
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 animate-in slide-in-from-bottom duration-300">
                
                {/* Agent Logs Feed (Left) */}
                <div className="lg:col-span-7 border border-stone-200/60 bg-white rounded-2xl flex flex-col shadow-[0_1px_8px_rgba(0,0,0,0.01)] overflow-hidden h-[380px]">
                  <div className="px-5 py-3 border-b border-stone-100 flex items-center justify-between shrink-0 bg-stone-50/30">
                    <span className="text-[11px] font-medium text-stone-400 uppercase tracking-widest">Live Process Stream</span>
                    <span className="text-[10px] font-mono text-stone-400">ws://stream</span>
                  </div>
                  <div className="flex-1 overflow-y-auto p-5 font-mono text-[11px] leading-relaxed text-stone-600 space-y-2 bg-[#fbfcff] no-scrollbar">
                    {agentLogs.map((log, idx) => (
                      <div 
                        key={idx} 
                        className={cn(
                          "whitespace-pre-wrap border-l-2 pl-3 py-0.5",
                          log.startsWith("✖") ? "border-red-300 text-red-600 bg-red-50/30" :
                          log.startsWith("✔") ? "border-emerald-300 text-emerald-600 bg-emerald-50/30" :
                          log.startsWith("➔") ? "border-stone-800 text-stone-800 font-medium" :
                          "border-stone-100"
                        )}
                      >
                        {log}
                      </div>
                    ))}
                    <div ref={logsEndRef} />
                  </div>
                </div>

                {/* Streamed Code Patch / Diff (Right) */}
                <div className="lg:col-span-5 border border-stone-200/60 bg-white rounded-2xl flex flex-col shadow-[0_1px_8px_rgba(0,0,0,0.01)] overflow-hidden h-[380px]">
                  <div className="px-5 py-3 border-b border-stone-100 flex items-center justify-between shrink-0 bg-stone-50/30">
                    <span className="text-[11px] font-medium text-stone-400 uppercase tracking-widest">Streamed Code Patch</span>
                    <span className="text-[10px] font-mono text-stone-400">git diff</span>
                  </div>
                  <div className="flex-1 overflow-y-auto p-5 font-mono text-[11px] leading-relaxed text-stone-600 bg-[#fafafc] no-scrollbar">
                    {generatedDiff ? (
                      <div className="space-y-0.5 whitespace-pre">
                        {generatedDiff.split("\n").map((line, idx) => (
                          <div 
                            key={idx}
                            className={cn(
                              "px-1 py-0.5 rounded",
                              line.startsWith("+") ? "bg-emerald-50 text-emerald-600" :
                              line.startsWith("-") ? "bg-rose-50 text-rose-600" :
                              line.startsWith("@@") ? "text-indigo-400 font-light" :
                              "text-stone-500"
                            )}
                          >
                            {line}
                          </div>
                        ))}
                      </div>
                    ) : (
                      <div className="h-full flex flex-col items-center justify-center text-center text-stone-300 font-sans gap-2 p-6">
                        <Layers className="w-8 h-8 stroke-[1]" />
                        <span className="text-[12px] font-light">No patch generated yet. Start the agent loop to stream modifications.</span>
                      </div>
                    )}
                  </div>
                </div>

              </div>
            )}

          </div>
        </div>
      </div>

      {/* Floating Success Toast */}
      {successToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-stone-900 border border-stone-850 text-white text-[12.5px] font-sans px-4.5 py-3.5 rounded-2xl shadow-xl flex items-center gap-2.5 animate-in slide-in-from-bottom duration-300">
          <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{successToast}</span>
        </div>
      )}

      {/* Right Sidebar with fully functional terminal lines sync */}
      <RightSidebar 
        isOpen={rightSidebarOpen} 
        onToggle={() => setRightSidebarOpen(!rightSidebarOpen)} 
        terminalLines={terminalLines}
        isRunningTask={isRunningTask}
        currentInput={currentInput}
        setCurrentInput={setCurrentInput}
        onSubmitCommand={handleCommandSubmit}
        runBuildCommand={runBuildCommand}
        runTestCommand={runTestCommand}
        clearTerminal={clearTerminal}
        terminalDock={terminalDock}
        setTerminalDock={setTerminalDock}
        isDraggingTerminal={isDraggingTerminal}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
      />
    </div>
  )
}

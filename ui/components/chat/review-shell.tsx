"use client"

import React, { useState, useEffect, useCallback } from "react"
import { LeftSidebar } from "./left-sidebar"
import { RightSidebar } from "./right-sidebar"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
import { 
  CheckSquare2, 
  Github, 
  GitPullRequest, 
  Clock, 
  ChevronRight, 
  CheckCircle2, 
  ArrowLeft, 
  XCircle,
  FileCode,
  ShieldCheck,
  X
} from "lucide-react"
import { Button } from "@/components/ui/button"
import { cn } from "@/lib/utils"

export function ReviewShell() {
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)
  
  // Terminal emulator state for RightSidebar
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "sharrowkin-core ~ bash",
    "$ dsm status",
    "→ Repository context connected: stable",
    "→ 12,408 Memory chunks active",
    "",
    "$ dsm logs",
    "[SUCCESS] Code Review module loaded.",
  ])
  const [isRunningTask, setIsRunningTask] = useState(false)
  const [currentInput, setCurrentInput] = useState("")
  const [terminalDock, setTerminalDock] = useState<"sidebar" | "bottom">("sidebar")
  const [isDraggingTerminal, setIsDraggingTerminal] = useState(false)

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

  // PR Core Data
  const [pullRequests, setPullRequests] = useState<any[]>([])
  const [branches, setBranches] = useState<any[]>([])
  const [currentBranch, setCurrentBranch] = useState<string>("main")

  // GitHub integration states
  const [isGitHubConnected, setIsGitHubConnected] = useState(false)
  const [isGitHubModalOpen, setIsGitHubModalOpen] = useState(false)
  const [githubUsername, setGithubUsername] = useState("")
  const [githubToken, setGithubToken] = useState("")
  const [repoUrl, setRepoUrl] = useState("")
  const [connectError, setConnectError] = useState("")
  const [isConnecting, setIsConnecting] = useState(false)

  const fetchBranches = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/git/branches`)
      if (res.ok) {
        const data = await res.json()
        setBranches(data.branches || [])
        setCurrentBranch(data.current || "main")
      }
    } catch (err) {
      console.error("Failed to load git branches:", err)
    }
  }, [])

  const fetchChanges = useCallback(async () => {
    try {
      const res = await fetch(`${BACKEND_URL}/api/git/changes`)
      if (res.ok) {
        const data = await res.json()
        setPullRequests(data)
      }
    } catch (err) {
      console.error("Failed to load real git changes:", err)
      setPullRequests([])
    }
  }, [])

  useEffect(() => {
    fetchBranches()
    fetchChanges()
  }, [fetchBranches, fetchChanges])

  const [selectedPR, setSelectedPR] = useState<any | null>(null)
  const [reviewMessage, setReviewMessage] = useState("")
  const [successToast, setSuccessToast] = useState("")

  const triggerToast = (msg: string) => {
    setSuccessToast(msg)
    setTimeout(() => setSuccessToast(""), 3500)
  }

  const handleApprove = async (prId: string) => {
    const response = await fetch(`${BACKEND_URL}/api/patch/accept`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_path: selectedPR?.repo || "workspace", note: reviewMessage }),
    })
    if (!response.ok) return triggerToast(`Could not accept ${prId}.`)
    setPullRequests(prev => prev.map(pr => pr.id === prId ? { ...pr, status: "accepted" } : pr))
    setSelectedPR(null)
    triggerToast(`Patch ${prId} accepted.`)
    setTerminalLines(prev => [
      ...prev,
      `[INFO] Patch ${prId} accepted via backend.`
    ])
  }

  const handleReject = async (prId: string) => {
    const response = await fetch(`${BACKEND_URL}/api/patch/reject`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ workspace_path: selectedPR?.repo || "workspace", note: reviewMessage || "Need adjustments" }),
    })
    if (!response.ok) return triggerToast(`Could not request changes for ${prId}.`)
    setPullRequests(prev => prev.map(pr => pr.id === prId ? { ...pr, status: "rejected" } : pr))
    setSelectedPR(null)
    triggerToast(`⚠️ Pull request ${prId} changes requested.`)
    setTerminalLines(prev => [
      ...prev,
      `[WARN] Pull Request ${prId} changes requested: "${reviewMessage || "Need adjustments"}"`
    ])
    setReviewMessage("")
  }

  return (
    <div className="h-dvh bg-background flex overflow-hidden">
      <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />

      {/* Main Area */}
      <div className="flex-1 flex flex-col relative min-w-0 bg-[#f7f7f9] overflow-hidden">
        
        {/* Top Header - White & Clean */}
        <div className="h-14 border-b border-stone-200/60 flex items-center justify-between px-8 bg-white/80 backdrop-blur-md z-10 shrink-0">
          <div className="flex items-center gap-2.5 text-stone-850">
            <CheckSquare2 className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
            <span className="font-medium text-[13px] tracking-wide text-stone-700">Code Reviews</span>
            {currentBranch && (
              <>
                <span className="text-stone-300">•</span>
                <span className="text-[12px] font-mono text-stone-500">{currentBranch}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={async () => {
                if (isGitHubConnected) {
                  setIsGitHubConnected(false)
                  setGithubUsername("")
                  setGithubToken("")
                  setRepoUrl("")
                  setConnectError("")
                  try {
                    await fetch(`${BACKEND_URL}/api/git/connect`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({ username: "", token: "", repo_url: "" })
                    })
                  } catch (e) {}
                  triggerToast("Disconnected GitHub account.")
                  fetchChanges()
                } else {
                  setConnectError("")
                  setIsGitHubModalOpen(true)
                }
              }}
              className={cn(
                "flex items-center gap-2 px-3 py-1.5 border transition-all text-[12px] rounded-lg shadow-[0_1px_3px_rgba(0,0,0,0.01)]",
                isGitHubConnected
                  ? "bg-emerald-50/50 border-emerald-200/60 text-emerald-700 hover:bg-emerald-50"
                  : "bg-white border-stone-200/50 hover:bg-stone-50 text-stone-600"
              )}
            >
              <Github className={cn("w-3.5 h-3.5", isGitHubConnected ? "text-emerald-600" : "text-stone-400")} strokeWidth={1.5} />
              <span>
                {isGitHubConnected ? `Connected as ${githubUsername}` : "Connect GitHub"}
              </span>
            </button>
          </div>
        </div>

        {/* Content Box */}
        <div className="flex-1 overflow-hidden flex relative">
          
          {/* Main List Column */}
          <div className={cn(
            "flex-1 overflow-y-auto p-8 transition-all duration-300", 
            selectedPR ? "max-w-[45%]" : "max-w-4xl mx-auto w-full"
          )}>
            
            {/* Header Description */}
            <div className="flex flex-col gap-1 mb-6">
              <h1 className="text-xl font-light text-stone-800 tracking-tight">Pull Requests</h1>
              <p className="text-[13px] text-stone-400 font-light">Review real workspace diffs, accept patches, or request changes.</p>
            </div>

            {/* Premium, Minimalist GitHub Integrations list */}
            <div className="border border-stone-200/60 bg-white rounded-2xl overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
              <div className="px-6 py-4 border-b border-stone-100 flex items-center justify-between">
                <span className="text-[12.5px] font-semibold text-stone-500 tracking-tight">Active Pull Requests</span>
                <span className="text-[11px] font-mono text-stone-400">{pullRequests.length} total</span>
              </div>
              
              <div className="divide-y divide-stone-100">
                {pullRequests.length === 0 && (
                  <div className="px-6 py-10 text-center">
                    <GitPullRequest className="mx-auto mb-3 h-6 w-6 text-stone-300" strokeWidth={1.5} />
                    <div className="text-[13px] text-stone-700">No workspace changes to review</div>
                    <div className="mt-1 text-[12px] text-stone-400">Run an autonomous task or edit files; real diffs will appear here.</div>
                  </div>
                )}
                {pullRequests.map((pr) => (
                  <div 
                    key={pr.id} 
                    onClick={() => {
                      if (pr.status !== "accepted") {
                        setSelectedPR(pr)
                      }
                    }}
                    className={cn(
                      "group/item flex items-center justify-between px-6 py-4 transition-colors cursor-pointer",
                      selectedPR?.id === pr.id ? "bg-stone-50" : "hover:bg-stone-50/50"
                    )}
                  >
                    
                    {/* Left: Info */}
                    <div className="flex items-center gap-4 min-w-0">
                      <div className={cn(
                        "w-8 h-8 rounded-full flex items-center justify-center border shrink-0",
                        pr.status === "accepted" && "bg-emerald-50 border-emerald-100 text-emerald-600",
                        pr.status === "rejected" && "bg-rose-50 border-rose-100 text-rose-600",
                        pr.status === "pending" && "bg-stone-50 border-stone-150 text-stone-600"
                      )}>
                        <GitPullRequest className="w-3.5 h-3.5" strokeWidth={1.5} />
                      </div>
                      
                      <div className="flex flex-col gap-0.5 min-w-0">
                        <span className="text-[13.5px] text-stone-800 font-normal truncate group-hover/item:text-stone-900 transition-colors">
                          {pr.title}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-stone-400 font-mono">{pr.id}</span>
                          <span className="text-[11px] text-stone-200">•</span>
                          <span className="text-[11px] text-stone-400/80">{pr.repo}</span>
                        </div>
                      </div>
                    </div>

                    {/* Right: Actions / Status */}
                    <div className="flex items-center gap-6 shrink-0 ml-4">
                      <div className="flex items-center gap-1.5 text-stone-400">
                        <Clock className="w-3 h-3" strokeWidth={1.5} />
                        <span className="text-[11px] font-normal">{pr.time}</span>
                      </div>
                      
                      <div className="w-[85px] flex justify-end">
                        {pr.status === 'accepted' ? (
                          <span className="text-[10px] text-emerald-600 bg-emerald-50 border border-emerald-100/50 px-2 py-0.5 rounded-md font-mono font-medium">
                            Accepted
                          </span>
                        ) : pr.status === 'rejected' ? (
                          <span className="text-[10px] text-rose-600 bg-rose-50 border border-rose-100/50 px-2 py-0.5 rounded-md font-mono font-medium">
                            Changes
                          </span>
                        ) : (
                          <span className="flex items-center gap-1 px-2.5 py-1 bg-stone-900 text-white rounded-xl text-[11px] shadow-sm font-sans">
                            <span>Review</span>
                            <ChevronRight className="w-3 h-3" />
                          </span>
                        )}
                      </div>
                    </div>

                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Premium Review Panel (Split Column) */}
          {selectedPR && (
            <div className="w-[55%] border-l border-stone-200/60 bg-white flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
              {/* Header */}
              <div className="p-6 border-b border-stone-200/55 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2">
                  <button 
                    onClick={() => setSelectedPR(null)}
                    className="p-1 hover:bg-stone-100 rounded-lg text-stone-500 transition-colors mr-1"
                  >
                    <ArrowLeft size={16} />
                  </button>
                  <div className="flex flex-col">
                    <h2 className="text-[14.5px] font-medium text-stone-800">{selectedPR.id} Review</h2>
                    <span className="text-[11px] text-stone-400 font-mono mt-0.5">{selectedPR.repo}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 bg-amber-50 text-amber-700 border border-amber-100/60 px-2 py-0.5 rounded-md text-[10px] font-mono">
                  Awaiting Approval
                </div>
              </div>

              {/* Body Content */}
              <div className="flex-1 overflow-y-auto p-6 space-y-6">
                
                {/* Description info */}
                <div className="bg-stone-50/50 border border-stone-250/30 rounded-2xl p-4 space-y-2">
                  <div className="text-[12px] font-semibold text-stone-500 tracking-tight">PR Description</div>
                  <p className="text-[13px] text-stone-600 font-light leading-relaxed">{selectedPR.description}</p>
                </div>

                {/* Live Diff Code Block inside Review panel */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between px-1">
                    <span className="text-[12px] font-semibold text-stone-500 tracking-tight">Files Changed</span>
                    <span className="text-[11px] text-stone-400 font-mono">1 file</span>
                  </div>

                  {selectedPR.filesChanged.map((file: { name: string; original: string; modified: string }, idx: number) => (
                    <div key={idx} className="border border-stone-200/60 rounded-2xl overflow-hidden shadow-[0_1px_4px_rgba(0,0,0,0.01)] bg-stone-50">
                      <div className="px-4 py-2 bg-stone-100/40 border-b border-stone-200/50 flex items-center gap-2">
                        <FileCode size={13} className="text-stone-400" />
                        <span className="text-[11px] text-stone-500 font-mono truncate">{file.name}</span>
                      </div>
                      
                      {/* Diff viewer content */}
                      <div className="p-4 font-mono text-[11px] leading-relaxed overflow-x-auto space-y-1 bg-white select-text">
                        <div className="text-stone-300 select-none pb-1">// Diff view</div>
                        <div className="bg-rose-50/65 text-rose-700 px-2.5 py-1.5 rounded-lg border border-rose-100/40 flex items-start gap-2">
                          <span className="text-rose-450 select-none font-bold shrink-0">-</span>
                          <span className="break-all">{file.original}</span>
                        </div>
                        <div className="bg-emerald-50/65 text-emerald-700 px-2.5 py-1.5 rounded-lg border border-emerald-100/40 flex items-start gap-2">
                          <span className="text-emerald-450 select-none font-bold shrink-0">+</span>
                          <span className="break-all">{file.modified}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>

                {/* Review Form Input */}
                <div className="space-y-2 pt-2">
                  <span className="text-[12px] font-semibold text-stone-500 tracking-tight px-1">Feedback Comments (Optional)</span>
                  <textarea
                    value={reviewMessage}
                    onChange={(e) => setReviewMessage(e.target.value)}
                    placeholder="Provide specific feedback or requested amendments here..."
                    className="w-full min-h-[90px] p-3.5 border border-stone-200/70 rounded-2xl text-[12.5px] font-sans text-stone-700 placeholder:text-stone-300 focus:outline-none focus:border-stone-400 focus:ring-0 transition-colors bg-stone-50/30"
                  />
                </div>

              </div>

              {/* Footer Actions */}
              <div className="p-6 border-t border-stone-200/55 bg-stone-50/20 shrink-0 flex items-center justify-between gap-3">
                <button 
                  onClick={() => handleReject(selectedPR.id)}
                  className="flex items-center gap-1.5 px-4 py-2.5 border border-stone-200 hover:bg-stone-50 text-stone-600 rounded-xl text-[12px] font-medium font-sans transition-colors shrink-0"
                >
                  <XCircle size={14} className="text-stone-400" />
                  <span>Request Changes</span>
                </button>

                <button 
                  onClick={() => handleApprove(selectedPR.id)}
                  className="flex-1 flex items-center justify-center gap-1.5 px-4 py-2.5 bg-stone-900 hover:bg-stone-850 text-white rounded-xl text-[12px] font-medium font-sans transition-colors shadow-sm"
                >
                  <CheckCircle2 size={14} />
                  <span>Accept Patch</span>
                </button>
              </div>

            </div>
          )}

        </div>
      </div>

      {/* Floating Success Toast notification */}
      {successToast && (
        <div className="fixed bottom-6 right-6 z-50 bg-stone-900 border border-stone-800 text-white text-[12px] font-sans px-4 py-3 rounded-2xl shadow-xl flex items-center gap-2.5 animate-in slide-in-from-bottom duration-300">
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

      {/* Connect GitHub Modal */}
      {isGitHubModalOpen && (
        <div className="fixed inset-0 bg-stone-950/20 backdrop-blur-sm z-[9999] flex items-center justify-center p-4">
          <div className="bg-white border border-stone-200 shadow-2xl rounded-3xl w-full max-w-sm overflow-hidden animate-in fade-in zoom-in duration-200">
            <div className="px-6 py-4 border-b border-stone-100 flex items-center justify-between">
              <span className="text-[14px] font-semibold text-stone-800 tracking-tight">Connect GitHub Account</span>
              <button
                onClick={() => setIsGitHubModalOpen(false)}
                className="w-6 h-6 rounded-full hover:bg-stone-100 flex items-center justify-center text-stone-400 hover:text-stone-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="p-6 space-y-4">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider block">Username</label>
                <input
                  type="text"
                  value={githubUsername}
                  onChange={(e) => setGithubUsername(e.target.value)}
                  placeholder="e.g. starface77"
                  className="w-full px-3 py-2 border border-stone-200 rounded-xl text-[13px] focus:outline-none focus:border-stone-400 bg-stone-50/50"
                />
              </div>
              
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider block">Personal Access Token (optional)</label>
                <input
                  type="password"
                  value={githubToken}
                  onChange={(e) => setGithubToken(e.target.value)}
                  placeholder="ghp_****************"
                  className="w-full px-3 py-2 border border-stone-200 rounded-xl text-[13px] focus:outline-none focus:border-stone-400 bg-stone-50/50"
                />
              </div>

              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-stone-400 uppercase tracking-wider block">Clone Repository (optional)</label>
                <input
                  type="text"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  placeholder="e.g. starface77/NareCLI or https://..."
                  className="w-full px-3 py-2 border border-stone-200 rounded-xl text-[13px] focus:outline-none focus:border-stone-400 bg-stone-50/50"
                />
              </div>

              {connectError && (
                <div className="text-[11.5px] text-rose-600 bg-rose-50 border border-rose-100 p-3 rounded-xl font-light leading-relaxed">
                  {connectError}
                </div>
              )}
            </div>
            
            <div className="px-6 py-4 bg-stone-50 border-t border-stone-100 flex items-center justify-end gap-2">
              <button
                onClick={() => setIsGitHubModalOpen(false)}
                className="px-4 py-2 border border-stone-200 text-stone-600 rounded-xl text-[12px] hover:bg-stone-100 font-medium transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!githubUsername.trim() || isConnecting}
                onClick={async () => {
                  setIsConnecting(true)
                  setConnectError("")
                  try {
                    const response = await fetch(`${BACKEND_URL}/api/git/connect`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        username: githubUsername,
                        token: githubToken,
                        repo_url: repoUrl
                      })
                    })
                    const data = await response.json()
                    if (data.status === "success") {
                      setIsGitHubConnected(true)
                      setIsGitHubModalOpen(false)
                      triggerToast(data.message || "Repository connected successfully!")
                      setTerminalLines(prev => [
                        ...prev,
                        `[SUCCESS] GitHub connected as ${githubUsername}`,
                        data.repo ? `[INFO] Cloned repo to projects/${data.repo.name}` : `[INFO] Connected workspace.`
                      ])
                      fetchChanges()
                    } else {
                      setConnectError(data.message || "Failed to connect repository")
                    }
                  } catch (err: any) {
                    setConnectError(err.message || "Network error occurred")
                  } finally {
                    setIsConnecting(false)
                  }
                }}
                className="px-4 py-2 bg-stone-900 text-white rounded-xl text-[12px] hover:bg-stone-850 font-medium shadow-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isConnecting ? "Connecting..." : "Connect"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

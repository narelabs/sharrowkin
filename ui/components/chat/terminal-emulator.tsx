"use client"

import type React from "react"
import { useRef, useEffect, useCallback } from "react"
import { PlayCircle, Trash2, Maximize2, Minimize2, GripHorizontal } from "lucide-react"
import { cn } from "@/lib/utils"

interface TerminalEmulatorProps {
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
  onDragStart?: (e: React.DragEvent) => void
  onDragEnd?: () => void
}

export function TerminalEmulator({
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
  onDragStart,
  onDragEnd,
}: TerminalEmulatorProps) {
  const terminalEndRef = useRef<HTMLDivElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom
  useEffect(() => {
    terminalEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [terminalLines])

  // Listen to Recent Commands clicks from LeftSidebar
  useEffect(() => {
    const handleCommandClickEvent = (e: Event) => {
      const cmd = (e as CustomEvent).detail
      if (cmd) {
        setCurrentInput(cmd)
      }
    }
    window.addEventListener("sharrowkin-terminal-cmd", handleCommandClickEvent)
    return () => window.removeEventListener("sharrowkin-terminal-cmd", handleCommandClickEvent)
  }, [setCurrentInput])

  // Intercept command submissions to update localStorage "Recent Commands" dynamically!
  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    if (currentInput.trim()) {
      const typed = currentInput.trim()
      const stored = localStorage.getItem("sharrowkin-recent-commands")
      let commands = stored ? JSON.parse(stored) : []
      
      // Keep only unique, place new one at start, limit to 4
      commands = [typed, ...commands.filter((c: string) => c !== typed)].slice(0, 4)
      localStorage.setItem("sharrowkin-recent-commands", JSON.stringify(commands))
      
      // Dispatch update notification event so LeftSidebar refreshes instantly
      window.dispatchEvent(new Event("sharrowkin-commands-updated"))
    }
    onSubmitCommand(e)
  }, [currentInput, onSubmitCommand])

  // Focus input when clicking terminal container
  const handleContainerClick = () => {
    const inputEl = containerRef.current?.querySelector("input")
    if (inputEl) {
      inputEl.focus()
    }
  }

  return (
    <div 
      className="h-full flex flex-col bg-transparent select-none"
      onClick={handleContainerClick}
    >
      {/* Apple-Like Ultra-Minimalist Terminal Panel */}
      <div className="flex-1 bg-white border border-stone-200/60 rounded-2xl flex flex-col overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.015)] min-h-0 relative">
        
        {/* Clean Terminal Header */}
        <div 
          draggable={true}
          onDragStart={onDragStart}
          onDragEnd={onDragEnd}
          className="flex items-center justify-between px-4 py-2 border-b border-stone-200/60 bg-stone-50/80 shrink-0 select-none cursor-grab active:cursor-grabbing hover:bg-stone-100/50 transition-all z-10"
          title="Drag header to move or dock terminal"
        >
          <div className="flex items-center gap-2.5">
            <GripHorizontal size={12} className="text-stone-300 hover:text-stone-500 transition-colors cursor-grab" />
            <span className="text-[11px] text-stone-500 font-medium tracking-tight">Terminal</span>
            <span className="text-[10px] text-stone-400 font-mono">~/sharrowkin</span>
          </div>
          
          <div className="flex items-center gap-2">
            <button
              onClick={(e) => {
                e.stopPropagation()
                setTerminalDock(terminalDock === "sidebar" ? "bottom" : "sidebar")
              }}
              className="flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-medium text-stone-400 hover:text-stone-700 hover:bg-stone-200/50 transition-all"
              title={terminalDock === "sidebar" ? "Dock to Bottom" : "Dock to Right Sidebar"}
            >
              {terminalDock === "sidebar" ? (
                <Minimize2 size={10} className="text-stone-400" />
              ) : (
                <Maximize2 size={10} className="text-stone-400" />
              )}
            </button>
          </div>
        </div>
        
        {/* Terminal Body */}
        <div 
          ref={containerRef}
          className="p-4 flex-1 overflow-y-auto font-mono text-[11.5px] leading-relaxed text-stone-600 space-y-1 select-text no-scrollbar cursor-text bg-transparent z-10"
        >
          {terminalLines.map((line, idx) => {
            const isCommand = line.startsWith("$")
            const isHeader = line.includes("~ bash")
            const isSuccess = line.startsWith("✔") || line.startsWith(" PASS") || line.startsWith("  ✓") || line.includes("successfully") || line.includes("[SUCCESS]")
            const isWarning = line.includes("[WARN]") || line.includes("info  -") || line.includes("warning") || line.startsWith("▶")
            const isSystem = line.startsWith("→")
            const isAgent = line.startsWith("[AGENT]") || line.startsWith("➔") || line.startsWith("💭")
            const isError = line.startsWith("✖") || line.includes("error:")

            return (
              <div
                key={idx}
                className={cn(
                  "font-mono leading-relaxed",
                  isCommand && "text-stone-800 font-medium flex items-center gap-1.5 mt-1",
                  isHeader && "text-stone-400 font-normal border-b border-stone-100/80 pb-1 mb-2",
                  isSuccess && "text-emerald-600 font-medium",
                  isWarning && "text-amber-600/80 font-normal",
                  isSystem && "text-stone-700 font-medium border-b border-stone-100/80 pb-1 mb-2 mt-3",
                  isAgent && "text-blue-600/80 font-normal",
                  isError && "text-red-500 font-medium"
                )}
              >
                {isCommand ? (
                  <>
                    <span className="text-stone-400 select-none font-normal">$</span>
                    <span>{line.substring(2)}</span>
                  </>
                ) : (
                  line
                )}
              </div>
            )
          })}
          
          {/* Command Line Input */}
          <form 
            onSubmit={handleSubmit} 
            className="flex items-center gap-1.5 pt-1 shrink-0 z-10"
            onClick={(e) => e.stopPropagation()}
          >
            <span className="text-stone-400 select-none font-normal">$</span>
            <div className="flex-1 flex items-center relative">
              <input
                type="text"
                value={currentInput}
                onChange={(e) => setCurrentInput(e.target.value)}
                disabled={isRunningTask}
                className="flex-1 bg-transparent border-none outline-none focus:outline-none focus:ring-0 p-0 text-[11.5px] font-mono text-stone-800 placeholder:text-stone-300"
                placeholder={isRunningTask ? "running..." : "type command..."}
                autoFocus
              />
              {!currentInput && !isRunningTask && (
                <span className="absolute left-0 w-1.5 h-3.5 bg-stone-400 animate-[pulse_0.9s_infinite] select-none pointer-events-none ml-[0.5px]" />
              )}
            </div>
          </form>
          <div ref={terminalEndRef} />
        </div>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-2 shrink-0 mt-2.5 font-sans">
        <button
          disabled={isRunningTask}
          onClick={(e) => { e.stopPropagation(); runBuildCommand(); }}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-stone-500 hover:text-stone-800 hover:bg-stone-100 transition-all rounded-lg text-[11px] font-medium disabled:opacity-40 font-sans active:scale-[0.97]"
        >
          <PlayCircle size={12} strokeWidth={1.5} />
          <span>Build</span>
        </button>
        <button
          disabled={isRunningTask}
          onClick={(e) => { e.stopPropagation(); runTestCommand(); }}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-stone-500 hover:text-stone-800 hover:bg-stone-100 transition-all rounded-lg text-[11px] font-medium disabled:opacity-40 font-sans active:scale-[0.97]"
        >
          <PlayCircle size={12} strokeWidth={1.5} />
          <span>Tests</span>
        </button>
        <button
          onClick={(e) => { e.stopPropagation(); clearTerminal(); }}
          className="flex-1 flex items-center justify-center gap-1.5 py-1.5 text-stone-500 hover:text-stone-800 hover:bg-stone-100 transition-all rounded-lg text-[11px] font-medium font-sans active:scale-[0.97]"
        >
          <Trash2 size={12} strokeWidth={1.5} />
          <span>Clear</span>
        </button>
      </div>
    </div>
  )
}

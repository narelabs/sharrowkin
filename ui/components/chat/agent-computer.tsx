"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { FileCode, TerminalSquare, GitCompare, Cpu, X, FileText, Loader2, Pencil, FilePlus2, Eye } from "lucide-react"
import { cn } from "@/lib/utils"

export type AgentComputerView = "editor" | "terminal" | "diff"

export interface AgentFile {
  path: string
  content: string
  isWriting: boolean
  action: "wrote" | "edited" | "read"
  linesChanged?: number
}

interface AgentComputerProps {
  isOpen: boolean
  onClose: () => void
  view: AgentComputerView
  setView: (v: AgentComputerView) => void
  files: Map<string, AgentFile>
  activeFile: string | null
  onSelectFile: (path: string) => void
  terminalLines: string[]
  diffContent: string
  fileDiffs: Map<string, string>
  isAgentActive: boolean
  currentAction?: string
}

function fileLanguage(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase()
  switch (ext) {
    case "ts": case "tsx": return "typescript"
    case "js": case "jsx": return "javascript"
    case "py": return "python"
    case "md": return "markdown"
    case "json": return "json"
    case "css": return "css"
    case "html": return "html"
    case "sh": return "bash"
    default: return ext || "text"
  }
}

function baseName(path: string): string {
  return path.split("/").pop() || path
}

function actionIcon(action: AgentFile["action"]) {
  if (action === "wrote") return FilePlus2
  if (action === "edited") return Pencil
  return Eye
}

export function AgentComputer({
  isOpen,
  onClose,
  view,
  setView,
  files,
  activeFile,
  onSelectFile,
  terminalLines,
  diffContent,
  fileDiffs,
  isAgentActive,
  currentAction,
}: AgentComputerProps) {
  const editorBodyRef = useRef<HTMLDivElement>(null)
  const terminalEndRef = useRef<HTMLDivElement>(null)

  // Resizable width — drag the left edge
  const [width, setWidth] = useState(460)
  const [isResizing, setIsResizing] = useState(false)

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizing(true)
    const startX = e.clientX
    const startWidth = width
    const doDrag = (moveEvent: MouseEvent) => {
      const deltaX = startX - moveEvent.clientX
      setWidth(Math.max(340, Math.min(startWidth + deltaX, 760)))
    }
    const stopDrag = () => {
      setIsResizing(false)
      document.removeEventListener("mousemove", doDrag)
      document.removeEventListener("mouseup", stopDrag)
    }
    document.addEventListener("mousemove", doDrag)
    document.addEventListener("mouseup", stopDrag)
  }, [width])

  const editor = activeFile ? files.get(activeFile) ?? null : null

  useEffect(() => {
    if (view === "editor" && editor?.isWriting && editorBodyRef.current) {
      editorBodyRef.current.scrollTop = editorBodyRef.current.scrollHeight
    }
  }, [editor?.content, editor?.isWriting, view])

  useEffect(() => {
    if (view === "terminal") {
      terminalEndRef.current?.scrollIntoView({ behavior: "smooth" })
    }
  }, [terminalLines, view])

  if (!isOpen) return null

  const tabs: { id: AgentComputerView; label: string; icon: typeof FileCode }[] = [
    { id: "editor", label: "Editor", icon: FileCode },
    { id: "terminal", label: "Terminal", icon: TerminalSquare },
    { id: "diff", label: "Diff", icon: GitCompare },
  ]

  const fileList = Array.from(files.values())
  const editorLines = editor?.content.split("\n") ?? []

  // Diff for the active file if available, otherwise the full patch
  const activeDiff = (activeFile && fileDiffs.get(activeFile)) || diffContent
  const diffLines = (activeDiff || "").split("\n")
  const additions = diffLines.filter(l => l.startsWith("+") && !l.startsWith("+++")).length
  const deletions = diffLines.filter(l => l.startsWith("-") && !l.startsWith("---")).length

  return (
    <aside
      style={{ width: `${width}px` }}
      className={cn(
        "hidden lg:flex shrink-0 flex-col bg-white border-l border-stone-100/40 overflow-hidden relative",
        isResizing ? "select-none" : "",
      )}
    >
      {/* Resize handle on the left edge */}
      <div
        onMouseDown={handleResizeStart}
        className="absolute left-0 top-0 z-50 flex h-full w-1.5 cursor-col-resize items-center justify-center transition-colors hover:bg-stone-200/40 active:bg-stone-300/50 group"
        title="Drag to resize"
      >
        <div className="h-8 w-[1.5px] rounded-full bg-stone-200/50 transition-colors group-hover:bg-stone-400/60 group-active:bg-stone-500" />
      </div>

      {/* Header */}
      <div className="flex h-14 shrink-0 items-center justify-between border-b border-stone-100/40 px-5 bg-white">
        <div className="flex min-w-0 items-center gap-2.5">
          <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-stone-100 text-stone-500">
            <Cpu size={14} strokeWidth={1.6} />
          </div>
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="text-[13px] font-medium text-stone-700">Agent's Computer</span>
            <span className="truncate text-[11px] text-stone-400">
              {isAgentActive ? (currentAction || "Working...") : "Idle"}
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {isAgentActive && (
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500" />
            </span>
          )}
          <button onClick={onClose} className="rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600" aria-label="Close agent computer">
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex shrink-0 items-center border-b border-stone-100/40 bg-white px-3 py-2.5">
        <div className="flex gap-0.5 bg-stone-100 p-0.5 rounded-lg">
          {tabs.map(({ id, label, icon: Icon }) => {
            const active = view === id
            return (
              <button
                key={id}
                onClick={() => setView(id)}
                className={cn(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[11.5px] font-medium transition-all",
                  active ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600",
                )}
              >
                <Icon size={13} strokeWidth={1.6} />
                <span>{label}</span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Body: file list + content */}
      <div className="flex flex-1 overflow-hidden bg-stone-50/40">
        {/* File list — shown for editor & diff views */}
        {view !== "terminal" && fileList.length > 0 && (
          <div className="flex w-[160px] shrink-0 flex-col border-r border-stone-100/50 bg-white/60 overflow-y-auto no-scrollbar">
            <div className="px-3 py-2 text-[10px] font-medium uppercase tracking-widest text-stone-400">
              Files · {fileList.length}
            </div>
            <div className="px-1.5 pb-2 space-y-0.5">
              {fileList.map((f) => {
                const Icon = actionIcon(f.action)
                const isActive = activeFile === f.path
                return (
                  <button
                    key={f.path}
                    onClick={() => onSelectFile(f.path)}
                    title={f.path}
                    className={cn(
                      "group flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left transition-colors",
                      isActive ? "bg-stone-100" : "hover:bg-stone-50",
                    )}
                  >
                    <Icon size={12} strokeWidth={1.6} className={cn(
                      "shrink-0",
                      f.action === "wrote" ? "text-emerald-500" : f.action === "edited" ? "text-amber-500" : "text-stone-400",
                    )} />
                    <span className={cn("truncate text-[11.5px]", isActive ? "text-stone-800 font-medium" : "text-stone-500")}>
                      {baseName(f.path)}
                    </span>
                    {f.isWriting && <Loader2 size={10} className="ml-auto shrink-0 animate-spin text-emerald-500" />}
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Content area */}
        <div className="flex-1 overflow-hidden p-3">
          <AnimatePresence mode="wait">
            {/* EDITOR */}
            {view === "editor" && (
              <motion.div key="editor" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.16 }} className="h-full">
                {editor ? (
                  <div className="flex h-full flex-col rounded-2xl border border-stone-100/40 bg-white overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                    <div className="flex shrink-0 items-center gap-2 border-b border-stone-100/60 bg-stone-50/50 px-4 py-2.5">
                      <FileCode size={13} className="text-stone-400 shrink-0" strokeWidth={1.6} />
                      <span className="truncate font-mono text-[11.5px] text-stone-600">{editor.path}</span>
                      <span className="ml-auto shrink-0 rounded-md bg-stone-100 px-1.5 py-0.5 text-[9.5px] uppercase tracking-wider text-stone-400">
                        {fileLanguage(editor.path)}
                      </span>
                      {editor.isWriting && <Loader2 size={12} className="shrink-0 animate-spin text-emerald-500" />}
                    </div>
                    <div ref={editorBodyRef} className="flex-1 overflow-auto no-scrollbar">
                      <pre className="min-h-full font-mono text-[11.5px] leading-[1.7] py-2">
                        {editorLines.map((line, i) => (
                          <div key={i} className="flex hover:bg-stone-50/70">
                            <span className="sticky left-0 inline-block w-10 shrink-0 select-none px-2 text-right text-[10px] text-stone-300">{i + 1}</span>
                            <code className="whitespace-pre px-3 text-stone-700">{line || " "}</code>
                          </div>
                        ))}
                        {editor.isWriting && (
                          <div className="flex">
                            <span className="inline-block w-10 shrink-0" />
                            <span className="ml-3 inline-block h-3.5 w-[6px] animate-[pulse_0.9s_infinite] rounded-sm bg-stone-400" />
                          </div>
                        )}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <EmptyState icon={FileText} title="No file open" subtitle="Files the agent reads or edits will show up here." />
                )}
              </motion.div>
            )}

            {/* TERMINAL */}
            {view === "terminal" && (
              <motion.div key="terminal" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.16 }} className="h-full">
                <div className="flex h-full flex-col rounded-2xl border border-stone-100/40 bg-white overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                  <div className="flex shrink-0 items-center gap-1.5 border-b border-stone-100/60 bg-stone-50/50 px-4 py-2.5">
                    <span className="h-2.5 w-2.5 rounded-full bg-red-300" />
                    <span className="h-2.5 w-2.5 rounded-full bg-amber-300" />
                    <span className="h-2.5 w-2.5 rounded-full bg-emerald-300" />
                    <span className="ml-2 font-mono text-[10.5px] text-stone-400">~/sharrowkin</span>
                  </div>
                  <div className="flex-1 overflow-auto no-scrollbar p-4 font-mono text-[11.5px] leading-relaxed space-y-1">
                    {terminalLines.length === 0 ? (
                      <span className="text-stone-300">Waiting for commands...</span>
                    ) : (
                      terminalLines.map((line, i) => {
                        const isCommand = line.startsWith("$") || line.startsWith("[TERMINAL]")
                        const isSuccess = line.startsWith("✔") || line.includes("[SUCCESS]") || line.includes("passed")
                        const isError = line.startsWith("✖") || line.includes("error:") || line.includes("[ERROR]")
                        const isAgent = line.startsWith("💭") || line.startsWith("[AGENT]") || line.startsWith("➔")
                        return (
                          <div key={i} className={cn(
                            "whitespace-pre-wrap break-words",
                            isCommand ? "text-stone-800 font-medium" :
                            isSuccess ? "text-emerald-600 font-medium" :
                            isError ? "text-red-500 font-medium" :
                            isAgent ? "text-blue-600/80" : "text-stone-500",
                          )}>
                            {isCommand && line.startsWith("$") ? (<><span className="text-stone-300 select-none">$ </span>{line.substring(2)}</>) : line}
                          </div>
                        )
                      })
                    )}
                    <div ref={terminalEndRef} />
                  </div>
                </div>
              </motion.div>
            )}

            {/* DIFF */}
            {view === "diff" && (
              <motion.div key="diff" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.16 }} className="h-full">
                {activeDiff ? (
                  <div className="flex h-full flex-col rounded-2xl border border-stone-100/40 bg-white overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                    <div className="flex shrink-0 items-center gap-2 border-b border-stone-100/60 bg-stone-50/50 px-4 py-2.5">
                      <GitCompare size={13} className="text-stone-400 shrink-0" strokeWidth={1.6} />
                      <span className="truncate font-mono text-[11.5px] text-stone-600">{activeFile ? baseName(activeFile) : "all changes"}</span>
                      <div className="ml-auto flex shrink-0 items-center gap-1.5">
                        <span className="rounded-md bg-emerald-50 px-1.5 py-0.5 text-[10px] font-mono text-emerald-600">+{additions}</span>
                        <span className="rounded-md bg-rose-50 px-1.5 py-0.5 text-[10px] font-mono text-rose-600">-{deletions}</span>
                      </div>
                    </div>
                    <div className="flex-1 overflow-auto no-scrollbar p-3">
                      <pre className="font-mono text-[11.5px] leading-[1.65]">
                        {diffLines.map((line, i) => {
                          const type =
                            line.startsWith("+++") || line.startsWith("---") ? "header" :
                            line.startsWith("@@") ? "hunk" :
                            line.startsWith("+") ? "add" :
                            line.startsWith("-") ? "del" : "ctx"
                          return (
                            <div key={i} className={cn(
                              "whitespace-pre px-2 py-0.5",
                              type === "add" ? "bg-emerald-50/70 text-emerald-700" :
                              type === "del" ? "bg-rose-50/50 text-rose-600" :
                              type === "hunk" ? "text-indigo-400 font-light bg-indigo-50/30 mt-2 mb-1 rounded" :
                              type === "header" ? "text-stone-500 font-semibold" : "text-stone-500",
                            )}>
                              {line || " "}
                            </div>
                          )
                        })}
                      </pre>
                    </div>
                  </div>
                ) : (
                  <EmptyState icon={GitCompare} title="No changes yet" subtitle="Diffs appear here once the agent edits files." />
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </aside>
  )
}

function EmptyState({ icon: Icon, title, subtitle }: { icon: typeof FileText; title: string; subtitle: string }) {
  return (
    <div className="flex h-full flex-col items-center justify-center rounded-2xl border border-stone-100/40 bg-white px-8 text-center shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-stone-50 text-stone-300">
        <Icon size={22} strokeWidth={1.2} />
      </div>
      <p className="text-[13px] font-medium text-stone-600">{title}</p>
      <p className="mt-1 text-[11.5px] text-stone-400 leading-relaxed max-w-[220px]">{subtitle}</p>
    </div>
  )
}

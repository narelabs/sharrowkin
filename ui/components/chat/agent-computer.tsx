"use client"

import { useEffect, useRef, useState, useCallback } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { FileCode, TerminalSquare, GitCompare, Cpu, X, FileText, Loader2, Pencil, FilePlus2, Eye, Globe, RotateCw, ExternalLink, MessageSquarePlus, Send, Copy } from "lucide-react"
import { cn } from "@/lib/utils"

export type AgentComputerView = "editor" | "terminal" | "diff" | "browser"

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
  previewUrl?: string | null
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
  previewUrl,
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

  // Browser/preview state: editable address bar synced to the detected URL,
  // plus a key bumped on reload to force the iframe to remount.
  const [urlInput, setUrlInput] = useState("")
  const [loadedUrl, setLoadedUrl] = useState("")
  const [reloadKey, setReloadKey] = useState(0)

  // Render the site at a real desktop width and scale it down to fit the
  // panel, so responsive layouts show their desktop form instead of collapsing
  // into a cramped mobile view.
  const PREVIEW_DESIGN_WIDTH = 1280
  const viewportRef = useRef<HTMLDivElement>(null)
  const [viewportWidth, setViewportWidth] = useState(0)
  const [viewportHeight, setViewportHeight] = useState(0)

  // Annotation mode: drag a box over the preview and send a note to the agent.
  const [annotateMode, setAnnotateMode] = useState(false)
  const [selRect, setSelRect] = useState<{ x: number; y: number; w: number; h: number } | null>(null)
  const [dragStart, setDragStart] = useState<{ x: number; y: number } | null>(null)
  const [note, setNote] = useState("")

  // Clone ("Copy") mode: enter a URL and ask the agent to recreate the whole
  // site or just a specific part/style you like.
  const [cloneOpen, setCloneOpen] = useState(false)
  const [cloneUrl, setCloneUrl] = useState("")
  const [cloneScope, setCloneScope] = useState<"whole" | "part">("whole")
  const [cloneWhat, setCloneWhat] = useState("")

  useEffect(() => {
    // When the agent surfaces a new dev-server URL, adopt it as the address.
    if (previewUrl && previewUrl !== loadedUrl) {
      setUrlInput(previewUrl)
      setLoadedUrl(previewUrl)
    }
  }, [previewUrl]) // eslint-disable-line react-hooks/exhaustive-deps

  // Track the viewport width so we can compute the desktop->panel scale factor.
  useEffect(() => {
    const el = viewportRef.current
    if (!el || typeof ResizeObserver === "undefined") return
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        setViewportWidth(e.contentRect.width)
        setViewportHeight(e.contentRect.height)
      }
    })
    ro.observe(el)
    setViewportWidth(el.clientWidth)
    setViewportHeight(el.clientHeight)
    return () => ro.disconnect()
  }, [view, loadedUrl])

  const normalizeUrl = useCallback((raw: string): string => {
    const v = raw.trim()
    if (!v) return ""
    return /^https?:\/\//i.test(v) ? v : `http://${v}`
  }, [])

  const navigate = useCallback(() => {
    const next = normalizeUrl(urlInput)
    if (!next) return
    setLoadedUrl(next)
    setReloadKey((k) => k + 1)
  }, [urlInput, normalizeUrl])

  // Send the annotation (selection box + note) to the composer as a structured
  // hint. The user reviews and presses send — same pattern as welcome prompts.
  const sendAnnotation = useCallback(() => {
    if (!note.trim()) return
    const scale = viewportWidth > 0 ? viewportWidth / PREVIEW_DESIGN_WIDTH : 1
    let region = ""
    if (selRect) {
      // Convert the on-screen box back to the site's own (desktop) coordinates.
      const rx = Math.round(selRect.x / scale)
      const ry = Math.round(selRect.y / scale)
      const rw = Math.round(selRect.w / scale)
      const rh = Math.round(selRect.h / scale)
      region = ` (region ~${rw}×${rh}px at x:${rx}, y:${ry} on a ${PREVIEW_DESIGN_WIDTH}px-wide layout)`
    }
    const msg = `Looking at the preview of ${loadedUrl || "the site"}${region}: ${note.trim()}`
    window.dispatchEvent(new CustomEvent("sharrowkin-insert-prompt", { detail: msg }))
    setNote("")
    setSelRect(null)
    setAnnotateMode(false)
  }, [note, selRect, viewportWidth, loadedUrl])

  // Build a "clone this site" instruction for the agent and drop it in the
  // composer. The agent can fetch the URL (run_command/curl) and recreate it.
  const sendClone = useCallback(() => {
    const target = normalizeUrl(cloneUrl)
    if (!target) return
    const what = cloneWhat.trim()
    let msg: string
    if (cloneScope === "whole") {
      msg =
        `Clone the website at ${target} into this workspace. ` +
        `Fetch the page (e.g. curl) and inspect its HTML, layout, and styling, then recreate it as faithfully as you can — ` +
        `structure, sections, colors, typography, and responsive behavior. Build it with the workspace's existing stack/conventions, ` +
        `and start a dev server so I can preview the result.` +
        (what ? ` Notes: ${what}` : "")
    } else {
      msg =
        `Look at ${target} and reproduce ${what || "the part I like"} in this workspace. ` +
        `Fetch the page, study how that piece is built (markup + CSS), and recreate just that — matching its look and feel — ` +
        `using the workspace's existing stack/conventions. Don't copy the whole site, only ${what || "that part"}.`
    }
    window.dispatchEvent(new CustomEvent("sharrowkin-submit-prompt", { detail: msg }))
    setCloneOpen(false)
    setCloneWhat("")
  }, [cloneUrl, cloneScope, cloneWhat, normalizeUrl])

  if (!isOpen) return null

  const previewScale = viewportWidth > 0 ? viewportWidth / PREVIEW_DESIGN_WIDTH : 1

  const tabs: { id: AgentComputerView; label: string; icon: typeof FileCode }[] = [
    { id: "editor", label: "Editor", icon: FileCode },
    { id: "terminal", label: "Terminal", icon: TerminalSquare },
    { id: "diff", label: "Diff", icon: GitCompare },
    { id: "browser", label: "Preview", icon: Globe },
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
        {/* File list — shown for editor & diff views (not terminal/browser) */}
        {view !== "terminal" && view !== "browser" && fileList.length > 0 && (
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

            {/* BROWSER / PREVIEW */}
            {view === "browser" && (
              <motion.div key="browser" initial={{ opacity: 0, y: 4 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0, y: -4 }} transition={{ duration: 0.16 }} className="h-full">
                <div className="flex h-full flex-col rounded-2xl border border-stone-100/40 bg-white overflow-hidden shadow-[0_1px_8px_rgba(0,0,0,0.01)]">
                  {/* Address bar */}
                  <div className="flex shrink-0 items-center gap-1.5 border-b border-stone-100/60 bg-stone-50/50 px-3 py-2">
                    <button
                      onClick={() => setReloadKey((k) => k + 1)}
                      disabled={!loadedUrl}
                      title="Reload"
                      className="shrink-0 rounded-md p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      <RotateCw size={13} strokeWidth={1.6} />
                    </button>
                    <div className="flex flex-1 items-center gap-1.5 rounded-lg bg-white px-2.5 py-1.5 ring-1 ring-stone-200/70">
                      <Globe size={12} strokeWidth={1.6} className="shrink-0 text-stone-300" />
                      <input
                        value={urlInput}
                        onChange={(e) => setUrlInput(e.target.value)}
                        onKeyDown={(e) => { if (e.key === "Enter") navigate() }}
                        placeholder="localhost:3000"
                        spellCheck={false}
                        className="min-w-0 flex-1 bg-transparent font-mono text-[11.5px] text-stone-600 outline-none placeholder:text-stone-300"
                      />
                    </div>
                    <button
                      onClick={() => {
                        setCloneOpen((v) => !v)
                        if (!cloneOpen) setCloneUrl(urlInput || loadedUrl || "")
                      }}
                      title="Copy this site — let the agent clone it (whole or just a part)"
                      className={cn(
                        "shrink-0 rounded-md p-1.5 transition-colors",
                        cloneOpen ? "bg-stone-800 text-white hover:bg-stone-700" : "text-stone-400 hover:bg-stone-100 hover:text-stone-600",
                      )}
                    >
                      <Copy size={13} strokeWidth={1.6} />
                    </button>
                    <button
                      onClick={() => { setAnnotateMode((v) => !v); setSelRect(null) }}
                      disabled={!loadedUrl}
                      title={annotateMode ? "Cancel annotation" : "Select a region and tell the agent what to fix"}
                      className={cn(
                        "shrink-0 rounded-md p-1.5 transition-colors disabled:opacity-40 disabled:hover:bg-transparent",
                        annotateMode ? "bg-stone-800 text-white hover:bg-stone-700" : "text-stone-400 hover:bg-stone-100 hover:text-stone-600",
                      )}
                    >
                      <MessageSquarePlus size={13} strokeWidth={1.6} />
                    </button>
                    <button
                      onClick={() => loadedUrl && window.open(loadedUrl, "_blank", "noopener,noreferrer")}
                      disabled={!loadedUrl}
                      title="Open in new tab"
                      className="shrink-0 rounded-md p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600 disabled:opacity-40 disabled:hover:bg-transparent"
                    >
                      <ExternalLink size={13} strokeWidth={1.6} />
                    </button>
                  </div>
                  {/* Viewport */}
                  <div ref={viewportRef} className="relative flex-1 overflow-hidden bg-stone-100/50">
                    {loadedUrl ? (
                      <>
                        {/* Render at desktop width, scale down to the panel so
                            responsive layouts show their desktop form. */}
                        <iframe
                          key={reloadKey}
                          src={loadedUrl}
                          title="Preview"
                          className="border-0 bg-white origin-top-left"
                          style={{
                            width: `${PREVIEW_DESIGN_WIDTH}px`,
                            height: previewScale > 0 ? `${viewportHeight / previewScale}px` : "100%",
                            transform: `scale(${previewScale})`,
                          }}
                          sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-modals"
                        />
                        {/* Annotation overlay: drag a box, then write a note. */}
                        {annotateMode && (
                          <div
                            className="absolute inset-0 z-10 cursor-crosshair bg-stone-900/5"
                            onMouseDown={(e) => {
                              const r = e.currentTarget.getBoundingClientRect()
                              const x = e.clientX - r.left, y = e.clientY - r.top
                              setDragStart({ x, y })
                              setSelRect({ x, y, w: 0, h: 0 })
                            }}
                            onMouseMove={(e) => {
                              if (!dragStart) return
                              const r = e.currentTarget.getBoundingClientRect()
                              const cx = e.clientX - r.left, cy = e.clientY - r.top
                              setSelRect({
                                x: Math.min(dragStart.x, cx),
                                y: Math.min(dragStart.y, cy),
                                w: Math.abs(cx - dragStart.x),
                                h: Math.abs(cy - dragStart.y),
                              })
                            }}
                            onMouseUp={() => setDragStart(null)}
                          >
                            {selRect && (selRect.w > 4 || selRect.h > 4) && (
                              <div
                                className="absolute rounded-sm border-2 border-stone-800 bg-stone-800/10 pointer-events-none"
                                style={{ left: selRect.x, top: selRect.y, width: selRect.w, height: selRect.h }}
                              />
                            )}
                          </div>
                        )}
                        {/* Note composer for the current selection. */}
                        {annotateMode && (
                          <div className="absolute bottom-3 left-3 right-3 z-20 flex items-end gap-2 rounded-xl border border-stone-200/70 bg-white/95 p-2 shadow-lg backdrop-blur-xl">
                            <textarea
                              value={note}
                              onChange={(e) => setNote(e.target.value)}
                              onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) sendAnnotation() }}
                              placeholder={selRect && selRect.w > 4 ? "What should the agent change here?" : "Drag to select a region, then describe what to fix..."}
                              rows={2}
                              className="min-w-0 flex-1 resize-none bg-transparent px-1.5 py-1 text-[12px] text-stone-700 outline-none placeholder:text-stone-400"
                            />
                            <button
                              onClick={sendAnnotation}
                              disabled={!note.trim()}
                              title="Send to agent (Ctrl/Cmd+Enter)"
                              className="shrink-0 flex items-center gap-1.5 rounded-lg bg-stone-800 px-2.5 py-2 text-[11.5px] font-medium text-white transition-colors hover:bg-stone-700 disabled:opacity-40"
                            >
                              <Send size={12} strokeWidth={1.8} />
                              Send
                            </button>
                          </div>
                        )}
                      </>
                    ) : (
                      <EmptyState
                        icon={Globe}
                        title="No preview yet"
                        subtitle="When the agent starts a dev server, its URL appears here. Or type an address above to load it."
                      />
                    )}

                    {/* Clone ("Copy") overlay — floats over the viewport so it
                        never pushes the toolbar/iframe layout around. */}
                    {cloneOpen && (
                      <div className="absolute inset-0 z-30 flex items-center justify-center bg-stone-900/20 backdrop-blur-[2px] p-4">
                        <div className="w-full max-w-[340px] rounded-2xl border border-stone-100/40 bg-white p-5 shadow-[0_8px_30px_rgba(0,0,0,0.08)]">
                          <div className="mb-1 flex items-center gap-2">
                            <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-stone-100 text-stone-500">
                              <Copy size={13} strokeWidth={1.7} />
                            </div>
                            <div className="flex flex-col leading-tight">
                              <span className="text-[13px] font-medium text-stone-700">Copy a site</span>
                              <span className="text-[11px] text-stone-400">The agent recreates it for you</span>
                            </div>
                            <button
                              onClick={() => setCloneOpen(false)}
                              className="ml-auto rounded-lg p-1.5 text-stone-400 transition-colors hover:bg-stone-100 hover:text-stone-600"
                            >
                              <X size={14} strokeWidth={1.6} />
                            </button>
                          </div>

                          <label className="mt-4 block text-[10px] font-medium uppercase tracking-widest text-stone-400">Site URL</label>
                          <div className="mt-1.5 flex items-center gap-2 rounded-xl bg-stone-50/70 px-3 py-2.5 ring-1 ring-stone-200/60 focus-within:ring-stone-300">
                            <Globe size={13} strokeWidth={1.6} className="shrink-0 text-stone-300" />
                            <input
                              value={cloneUrl}
                              onChange={(e) => setCloneUrl(e.target.value)}
                              placeholder="https://site-you-like.com"
                              spellCheck={false}
                              autoFocus
                              className="min-w-0 flex-1 bg-transparent font-mono text-[12px] text-stone-700 outline-none placeholder:text-stone-300"
                            />
                          </div>

                          <label className="mt-4 block text-[10px] font-medium uppercase tracking-widest text-stone-400">What to copy</label>
                          <div className="mt-1.5 grid grid-cols-2 gap-2">
                            <button
                              onClick={() => setCloneScope("whole")}
                              className={cn(
                                "rounded-xl px-3 py-2.5 text-left transition-colors ring-1",
                                cloneScope === "whole" ? "bg-stone-100 ring-stone-300" : "bg-white ring-stone-200/60 hover:ring-stone-300",
                              )}
                            >
                              <span className={cn("block text-[12px] font-medium", cloneScope === "whole" ? "text-stone-800" : "text-stone-600")}>Whole site</span>
                              <span className="mt-0.5 block text-[10.5px] leading-snug text-stone-400">Full layout &amp; pages</span>
                            </button>
                            <button
                              onClick={() => setCloneScope("part")}
                              className={cn(
                                "rounded-xl px-3 py-2.5 text-left transition-colors ring-1",
                                cloneScope === "part" ? "bg-stone-100 ring-stone-300" : "bg-white ring-stone-200/60 hover:ring-stone-300",
                              )}
                            >
                              <span className={cn("block text-[12px] font-medium", cloneScope === "part" ? "text-stone-800" : "text-stone-600")}>Just a part</span>
                              <span className="mt-0.5 block text-[10.5px] leading-snug text-stone-400">A section or style</span>
                            </button>
                          </div>

                          <label className="mt-4 block text-[10px] font-medium uppercase tracking-widest text-stone-400">
                            {cloneScope === "whole" ? "Notes (optional)" : "What do you like?"}
                          </label>
                          <textarea
                            value={cloneWhat}
                            onChange={(e) => setCloneWhat(e.target.value)}
                            onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) sendClone() }}
                            placeholder={cloneScope === "whole" ? "Anything to emphasize?" : "e.g. the hero section, the pricing cards, the color scheme"}
                            rows={2}
                            className="mt-1.5 w-full resize-none rounded-xl bg-stone-50/70 px-3 py-2.5 text-[12px] text-stone-700 outline-none ring-1 ring-stone-200/60 placeholder:text-stone-400 focus:ring-stone-300"
                          />

                          <button
                            onClick={sendClone}
                            disabled={!cloneUrl.trim() || (cloneScope === "part" && !cloneWhat.trim())}
                            className="mt-4 flex w-full items-center justify-center gap-1.5 rounded-xl bg-stone-800 px-3 py-2.5 text-[12.5px] font-medium text-white transition-colors hover:bg-stone-700 disabled:opacity-40 disabled:hover:bg-stone-800"
                          >
                            <Send size={13} strokeWidth={1.8} />
                            Send to agent
                          </button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
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

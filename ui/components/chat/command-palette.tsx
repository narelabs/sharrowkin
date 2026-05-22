"use client"

import React, { useState, useEffect, useRef, useCallback } from "react"
import { useRouter } from "next/navigation"
import {
  MessageSquare,
  BookOpen,
  CheckSquare2,
  Settings,
  Palette,
  FolderTree,
  Zap,
  Search,
  FlaskConical,
  FolderSearch,
  Trash2,
  Plus,
  Terminal,
  GitBranch,
} from "lucide-react"
import { cn } from "@/lib/utils"

interface CommandItem {
  id: string
  label: string
  description?: string
  icon: React.ElementType
  category: "navigate" | "action" | "search"
  action: () => void
  shortcut?: string
}

interface CommandPaletteProps {
  isOpen: boolean
  onClose: () => void
}

export function CommandPalette({ isOpen, onClose }: CommandPaletteProps) {
  const [query, setQuery] = useState("")
  const inputRef = useRef<HTMLInputElement>(null)
  const router = useRouter()
  const [selectedIndex, setSelectedIndex] = useState(0)

  const commands: CommandItem[] = [
    // Navigation
    { id: "nav-chat", label: "Chat", description: "Open AI chat", icon: MessageSquare, category: "navigate", action: () => router.push("/chat"), shortcut: "Alt+1" },
    { id: "nav-wiki", label: "Wiki", description: "Project knowledge base", icon: BookOpen, category: "navigate", action: () => router.push("/wiki"), shortcut: "Alt+2" },
    { id: "nav-review", label: "Review", description: "Code review & PRs", icon: CheckSquare2, category: "navigate", action: () => router.push("/review"), shortcut: "Alt+3" },
    { id: "nav-automations", label: "Automations", description: "Autonomous agent tasks", icon: Zap, category: "navigate", action: () => router.push("/automations"), shortcut: "Alt+4" },
    { id: "nav-workflow", label: "Workflow", description: "Project explorer", icon: FolderTree, category: "navigate", action: () => router.push("/workflow"), shortcut: "Alt+5" },
    { id: "nav-personas", label: "Personas", description: "Agent personality themes", icon: Palette, category: "navigate", action: () => router.push("/personas") },
    { id: "nav-settings", label: "Settings", description: "Configuration", icon: Settings, category: "navigate", action: () => router.push("/settings") },

    // Actions
    { id: "act-new-chat", label: "New Chat", description: "Start a new conversation", icon: Plus, category: "action", action: () => { router.push(`/chat?session=session-${Date.now()}`); } },
    { id: "act-scan", label: "Scan Workspace", description: "Index all project files", icon: FolderSearch, category: "action", action: () => { window.dispatchEvent(new CustomEvent("sharrowkin-terminal-cmd", { detail: "agent tool scan_workspace" })); } },
    { id: "act-test", label: "Run Tests", description: "Execute test suite", icon: FlaskConical, category: "action", action: () => { window.dispatchEvent(new CustomEvent("sharrowkin-terminal-cmd", { detail: "npm test" })); } },
    { id: "act-diff", label: "Git Diff", description: "Show uncommitted changes", icon: GitBranch, category: "action", action: () => { window.dispatchEvent(new CustomEvent("sharrowkin-terminal-cmd", { detail: "git diff" })); } },
    { id: "act-clear", label: "Clear Terminal", description: "Reset terminal output", icon: Trash2, category: "action", action: () => { window.dispatchEvent(new CustomEvent("sharrowkin-terminal-cmd", { detail: "clear" })); } },
  ]

  const filtered = query
    ? commands.filter(
        (cmd) =>
          cmd.label.toLowerCase().includes(query.toLowerCase()) ||
          (cmd.description && cmd.description.toLowerCase().includes(query.toLowerCase()))
      )
    : commands

  useEffect(() => {
    if (isOpen) {
      setQuery("")
      setSelectedIndex(0)
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [isOpen])

  useEffect(() => {
    setSelectedIndex(0)
  }, [query])

  const handleSelect = useCallback((cmd: CommandItem) => {
    cmd.action()
    onClose()
  }, [onClose])

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault()
        setSelectedIndex((prev) => Math.min(prev + 1, filtered.length - 1))
      } else if (e.key === "ArrowUp") {
        e.preventDefault()
        setSelectedIndex((prev) => Math.max(prev - 1, 0))
      } else if (e.key === "Enter") {
        e.preventDefault()
        if (filtered[selectedIndex]) {
          handleSelect(filtered[selectedIndex])
        }
      } else if (e.key === "Escape") {
        onClose()
      }
    },
    [filtered, selectedIndex, handleSelect, onClose]
  )

  // Global Ctrl+K listener
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault()
        if (isOpen) {
          onClose()
        }
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [isOpen, onClose])

  if (!isOpen) return null

  const grouped = {
    navigate: filtered.filter((c) => c.category === "navigate"),
    action: filtered.filter((c) => c.category === "action"),
  }

  let flatIndex = 0

  return (
    <div className="fixed inset-0 z-[9999] flex items-start justify-center pt-[20vh]" onClick={onClose}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/20 backdrop-blur-sm" />

      {/* Palette */}
      <div
        className="relative w-full max-w-[520px] bg-white rounded-2xl border border-stone-200 shadow-2xl overflow-hidden animate-in fade-in slide-in-from-top-2 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input */}
        <div className="flex items-center gap-3 px-5 py-4 border-b border-stone-100">
          <Search size={18} strokeWidth={1.5} className="text-stone-400 shrink-0" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a command or search..."
            className="flex-1 text-[14px] text-stone-800 placeholder:text-stone-400 bg-transparent outline-none"
          />
          <kbd className="hidden sm:flex items-center gap-0.5 px-1.5 py-0.5 rounded-md bg-stone-100 border border-stone-200 text-[10px] font-mono text-stone-500">
            ESC
          </kbd>
        </div>

        {/* Results */}
        <div className="max-h-[360px] overflow-y-auto p-2">
          {filtered.length === 0 && (
            <div className="px-4 py-8 text-center text-[13px] text-stone-400">
              No commands found
            </div>
          )}

          {grouped.navigate.length > 0 && (
            <div className="mb-1">
              <div className="px-3 py-1.5 text-[10px] font-medium text-stone-400 uppercase tracking-widest">Navigate</div>
              {grouped.navigate.map((cmd) => {
                const Icon = cmd.icon
                const idx = flatIndex++
                return (
                  <button
                    key={cmd.id}
                    onClick={() => handleSelect(cmd)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors text-left",
                      idx === selectedIndex ? "bg-stone-100" : "hover:bg-stone-50"
                    )}
                  >
                    <Icon size={16} strokeWidth={1.5} className="text-stone-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium text-stone-800">{cmd.label}</div>
                      {cmd.description && <div className="text-[11px] text-stone-400 truncate">{cmd.description}</div>}
                    </div>
                    {cmd.shortcut && (
                      <kbd className="px-1.5 py-0.5 rounded bg-stone-100 border border-stone-200 text-[10px] font-mono text-stone-500">
                        {cmd.shortcut}
                      </kbd>
                    )}
                  </button>
                )
              })}
            </div>
          )}

          {grouped.action.length > 0 && (
            <div className="mb-1">
              <div className="px-3 py-1.5 text-[10px] font-medium text-stone-400 uppercase tracking-widest">Actions</div>
              {grouped.action.map((cmd) => {
                const Icon = cmd.icon
                const idx = flatIndex++
                return (
                  <button
                    key={cmd.id}
                    onClick={() => handleSelect(cmd)}
                    className={cn(
                      "w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-colors text-left",
                      idx === selectedIndex ? "bg-stone-100" : "hover:bg-stone-50"
                    )}
                  >
                    <Icon size={16} strokeWidth={1.5} className="text-stone-500 shrink-0" />
                    <div className="flex-1 min-w-0">
                      <div className="text-[13px] font-medium text-stone-800">{cmd.label}</div>
                      {cmd.description && <div className="text-[11px] text-stone-400 truncate">{cmd.description}</div>}
                    </div>
                    {cmd.shortcut && (
                      <kbd className="px-1.5 py-0.5 rounded bg-stone-100 border border-stone-200 text-[10px] font-mono text-stone-500">
                        {cmd.shortcut}
                      </kbd>
                    )}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-4 py-2.5 border-t border-stone-100 flex items-center justify-between text-[10px] text-stone-400">
          <span>↑↓ navigate · ↵ select · esc close</span>
          <span className="font-mono">Ctrl+K</span>
        </div>
      </div>
    </div>
  )
}

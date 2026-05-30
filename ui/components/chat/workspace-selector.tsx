"use client"

import { useState } from "react"
import { Folder, FolderOpen, Loader2, Check, ChevronDown, Clock, AlertCircle } from "lucide-react"
import { cn } from "@/lib/utils"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover"
import {
  pickWorkspaceFolder,
  validateWorkspace,
  getRecentWorkspaces,
  isTauri,
  folderName,
} from "@/lib/workspace"

interface WorkspaceSelectorProps {
  workspace: string | null
  onSelect: (path: string) => void
  disabled?: boolean
}

// Inline folder selector that lives inside the composer (chat-style).
// Clicking the chip opens the native OS folder picker (Windows Explorer)
// directly on desktop. A small chevron opens a popover with recents and a
// manual-path fallback (also the path used when running in a browser).
export function WorkspaceSelector({ workspace, onSelect, disabled }: WorkspaceSelectorProps) {
  const [open, setOpen] = useState(false)
  const [manualPath, setManualPath] = useState("")
  const [checking, setChecking] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const recents = typeof window !== "undefined" ? getRecentWorkspaces() : []
  const desktop = isTauri()

  const confirm = async (path: string) => {
    const trimmed = path.trim()
    if (!trimmed) return
    setChecking(true)
    setError(null)
    const ok = await validateWorkspace(trimmed)
    setChecking(false)
    if (!ok) {
      setError("Folder isn't reachable. Check the path and that the backend is running.")
      return
    }
    onSelect(trimmed)
    setManualPath("")
    setOpen(false)
  }

  const handleBrowse = async () => {
    setError(null)
    const picked = await pickWorkspaceFolder()
    if (picked) await confirm(picked)
  }

  // Primary chip click: open the native picker on desktop, otherwise fall
  // back to the popover (browser/dev has no OS dialog).
  const handleChipClick = () => {
    if (disabled || checking) return
    if (desktop) {
      handleBrowse()
    } else {
      setOpen(true)
    }
  }

  return (
    <div
      className={cn(
        "flex h-8 shrink-0 items-center rounded-full transition-colors",
        workspace ? "bg-stone-100/70" : "bg-amber-50",
      )}
    >
      {/* Main chip — opens Windows Explorer directly on desktop */}
      <button
        type="button"
        onClick={handleChipClick}
        disabled={disabled}
        title={desktop ? "Open folder picker" : undefined}
        className={cn(
          "flex h-8 min-w-0 max-w-[200px] items-center gap-1.5 rounded-l-full pl-3 pr-1 text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50",
          workspace
            ? "text-stone-600 hover:bg-stone-200/60 hover:text-stone-900"
            : "text-amber-700 hover:bg-amber-100",
        )}
      >
        {checking ? (
          <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-stone-500" />
        ) : workspace ? (
          <Folder className="h-3.5 w-3.5 shrink-0 text-stone-500" strokeWidth={1.5} />
        ) : (
          <FolderOpen className="h-3.5 w-3.5 shrink-0 text-amber-600" strokeWidth={1.5} />
        )}
        <span className="min-w-0 truncate">{workspace ? folderName(workspace) : "Folder"}</span>
      </button>

      {/* Chevron — opens the popover with recents + manual path */}
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            disabled={disabled}
            aria-label="Folder options"
            className={cn(
              "flex h-8 shrink-0 items-center rounded-r-full pl-0.5 pr-2 transition-colors disabled:cursor-not-allowed disabled:opacity-50",
              workspace ? "text-stone-500 hover:bg-stone-200/60" : "text-amber-600 hover:bg-amber-100",
            )}
          >
            <ChevronDown className="h-3 w-3 opacity-70" />
          </button>
        </PopoverTrigger>
        <PopoverContent
          align="start"
          side="top"
          sideOffset={10}
          className="w-[320px] rounded-2xl border-stone-200/70 bg-white/95 p-1.5 shadow-xl backdrop-blur-xl"
        >
          {workspace && (
            <div className="mb-1 flex items-start gap-2 rounded-xl bg-stone-50 px-3 py-2.5">
              <Folder className="mt-0.5 h-4 w-4 shrink-0 text-stone-400" strokeWidth={1.5} />
              <div className="min-w-0">
                <div className="text-[12.5px] font-medium text-stone-800">Current folder</div>
                <div className="truncate font-mono text-[11px] text-stone-400">{workspace}</div>
              </div>
            </div>
          )}

          {/* Browse (native dialog) — desktop only */}
          {desktop && (
            <button
              onClick={handleBrowse}
              disabled={checking}
              className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2.5 text-left transition-colors hover:bg-stone-50 disabled:opacity-60"
            >
              <FolderOpen className="h-4 w-4 shrink-0 text-stone-500" strokeWidth={1.8} />
              <span className="flex-1 text-[13px] font-medium text-stone-800">Browse folders…</span>
              {checking && <Loader2 className="h-3.5 w-3.5 animate-spin text-stone-400" />}
            </button>
          )}

          {/* Manual path */}
          <div className="mt-1 flex items-center gap-1.5 rounded-xl bg-stone-50 px-2 py-1">
            <input
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") confirm(manualPath)
              }}
              placeholder="Paste an absolute path"
              className="min-w-0 flex-1 bg-transparent px-1.5 py-1.5 font-mono text-[12px] text-stone-800 outline-none placeholder:font-sans placeholder:text-stone-400"
            />
            <button
              onClick={() => confirm(manualPath)}
              disabled={!manualPath.trim() || checking}
              className="flex h-7 shrink-0 items-center rounded-lg bg-stone-900 px-3 text-[12px] font-medium text-white transition-colors hover:bg-stone-800 disabled:opacity-40"
            >
              {checking ? <Loader2 className="h-3 w-3 animate-spin" /> : "Open"}
            </button>
          </div>

          {error && (
            <div className="mt-1.5 flex items-start gap-1.5 rounded-lg bg-red-50 px-2.5 py-2 text-[11.5px] text-red-600">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          {/* Recent folders */}
          {recents.length > 0 && (
            <div className="mt-1.5 border-t border-stone-100 pt-1.5">
              <div className="flex items-center gap-1.5 px-3 py-1 text-[11px] font-medium text-stone-400">
                <Clock className="h-3 w-3" />
                Recent
              </div>
              {recents.map((path) => (
                <button
                  key={path}
                  onClick={() => confirm(path)}
                  disabled={checking}
                  className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-left transition-colors hover:bg-stone-50 disabled:opacity-60"
                >
                  <Folder className="h-3.5 w-3.5 shrink-0 text-stone-400" strokeWidth={1.8} />
                  <div className="min-w-0 flex-1">
                    <div className="truncate text-[12.5px] text-stone-700">{folderName(path)}</div>
                  </div>
                  {workspace === path && <Check className="h-3.5 w-3.5 shrink-0 text-stone-500" />}
                </button>
              ))}
            </div>
          )}
        </PopoverContent>
      </Popover>
    </div>
  )
}

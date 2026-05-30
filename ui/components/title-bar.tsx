"use client"

import { useEffect, useState } from "react"
import { Minus, Square, Copy as Restore, X, PanelLeft, PenSquare, Search } from "lucide-react"
import { isTauri } from "@/lib/workspace"
import { cn } from "@/lib/utils"

// Actions surfaced in the title bar. These do NOT duplicate the left-sidebar
// navigation — they're window-level quick actions wired through custom events
// that the chat shell / sidebar listen for.
const ACTIONS = [
  { icon: PanelLeft, label: "Sidebar", event: "sharrowkin-toggle-sidebar" },
  { icon: PenSquare, label: "New chat", event: "sharrowkin-new-chat" },
  { icon: Search, label: "Search", event: "sharrowkin-open-search" },
]

// Custom desktop title bar. The Tauri window is frameless (decorations:false),
// so we draw our own bar: branding + quick actions on the left and the three
// custom window controls on the right. Renders nothing in the browser.
export function TitleBar() {
  const [mounted, setMounted] = useState(false)
  const [desktop, setDesktop] = useState(false)
  const [maximized, setMaximized] = useState(false)

  useEffect(() => {
    setMounted(true)
    const d = isTauri()
    setDesktop(d)
    if (!d) return
    let unlisten: (() => void) | undefined
    ;(async () => {
      try {
        const { getCurrentWindow } = await import("@tauri-apps/api/window")
        const w = getCurrentWindow()
        setMaximized(await w.isMaximized())
        unlisten = await w.onResized(async () => setMaximized(await w.isMaximized()))
      } catch {
        /* not in a Tauri window */
      }
    })()
    return () => unlisten?.()
  }, [])

  if (!mounted || !desktop) return null

  const win = async () => (await import("@tauri-apps/api/window")).getCurrentWindow()
  const onMinimize = async () => (await win()).minimize()
  const onToggleMax = async () => {
    const w = await win()
    await w.toggleMaximize()
    setMaximized(await w.isMaximized())
  }
  const onClose = async () => (await win()).close()

  return (
    <div
      data-tauri-drag-region
      className="flex h-11 shrink-0 select-none items-center justify-between bg-[#f7f7f7] pl-3 pr-2"
    >
      {/* Brand + quick actions */}
      <div className="flex items-center gap-1.5">
        <div data-tauri-drag-region className="flex items-center gap-2 pr-1.5">
          <img src="/logo.png" alt="" className="h-[18px] w-[18px] rounded-[5px] object-contain" draggable={false} />
          <span className="text-[13px] font-medium tracking-tight text-stone-800">Sharrowkin</span>
        </div>
        <div className="flex items-center gap-0.5">
          {ACTIONS.map(({ icon: Icon, label, event }) => (
            <ActionButton key={label} label={label} onClick={() => window.dispatchEvent(new CustomEvent(event))}>
              <Icon size={15} strokeWidth={1.7} />
            </ActionButton>
          ))}
        </div>
      </div>

      {/* Window controls — custom, not native chrome */}
      <div className="flex items-center gap-1">
        <WindowButton onClick={onMinimize} label="Minimize">
          <Minus size={15} strokeWidth={1.8} />
        </WindowButton>
        <WindowButton onClick={onToggleMax} label={maximized ? "Restore" : "Maximize"}>
          {maximized ? <Restore size={12} strokeWidth={1.8} /> : <Square size={11} strokeWidth={1.8} />}
        </WindowButton>
        <WindowButton onClick={onClose} label="Close" danger>
          <X size={16} strokeWidth={1.8} />
        </WindowButton>
      </div>
    </div>
  )
}

// Icon-only by default; the label slides open on hover.
function ActionButton({
  children,
  onClick,
  label,
}: {
  children: React.ReactNode
  onClick: () => void
  label: string
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className="group flex h-8 items-center rounded-lg px-[7px] text-stone-500 transition-colors hover:bg-stone-200/55 hover:text-stone-900"
    >
      {children}
      <span className="max-w-0 overflow-hidden whitespace-nowrap text-[12.5px] font-medium transition-[max-width,margin] duration-200 ease-out group-hover:ml-1.5 group-hover:max-w-[90px]">
        {label}
      </span>
    </button>
  )
}

function WindowButton({
  children,
  onClick,
  label,
  danger = false,
}: {
  children: React.ReactNode
  onClick: () => void
  label: string
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={cn(
        "flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 transition-colors",
        danger ? "hover:bg-red-500 hover:text-white" : "hover:bg-stone-200/60 hover:text-stone-900",
      )}
    >
      {children}
    </button>
  )
}

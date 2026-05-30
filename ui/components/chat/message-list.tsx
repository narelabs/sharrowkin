"use client"

import { useEffect, useRef, useState } from "react"
import { MessageBubble } from "./message-bubble"
import type { Message } from "./chat-shell"
import { TypingIndicator } from "./typing-indicator"
import { AlertCircle, Bot, RefreshCw, ArrowDown, ListTodo, FileCode, FlaskConical, GitBranch } from "lucide-react"
import { Button } from "@/components/ui/button"

interface MessageListProps {
  messages: Message[]
  isStreaming: boolean
  error: string | null
  onRetry: () => void
  isLoaded: boolean // Added isLoaded prop to know when localStorage is loaded
  onOpenDiff?: (filename: string) => void
}

export function MessageList({ messages, isStreaming, error, onRetry, isLoaded, onOpenDiff }: MessageListProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const rafRef = useRef<number | null>(null)
  const autoScrollRef = useRef(true)

  const setAuto = (v: boolean) => {
    autoScrollRef.current = v
    setAutoScroll(v)
  }

  // A single continuous RAF loop owns auto-scrolling. While we're following, it
  // eases toward the bottom every frame so new messages, streamed text, and
  // growing tool lists glide instead of jumping. It NEVER fights the user:
  // user intent (wheel/touch up) flips following off below, and the loop only
  // moves downward toward the bottom, never upward.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const tick = () => {
      if (autoScrollRef.current) {
        const target = container.scrollHeight - container.clientHeight
        const current = container.scrollTop
        const diff = target - current
        if (diff > 0.5) {
          const step = Math.max(diff * 0.22, Math.min(diff, 1.5))
          container.scrollTop = current + step
        }
      }
      rafRef.current = requestAnimationFrame(tick)
    }

    rafRef.current = requestAnimationFrame(tick)
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current)
      rafRef.current = null
    }
  }, [])

  // User intent: scrolling up (wheel up / touch drag down) immediately stops
  // following so the view stays put. This is the authoritative signal — it
  // can't be confused with our own programmatic scrolling.
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const onWheel = (e: WheelEvent) => {
      if (e.deltaY < 0) setAuto(false)
    }
    let touchY = 0
    const onTouchStart = (e: TouchEvent) => { touchY = e.touches[0]?.clientY ?? 0 }
    const onTouchMove = (e: TouchEvent) => {
      const y = e.touches[0]?.clientY ?? 0
      if (y > touchY + 2) setAuto(false) // dragging down = scrolling content up
      touchY = y
    }

    container.addEventListener("wheel", onWheel, { passive: true })
    container.addEventListener("touchstart", onTouchStart, { passive: true })
    container.addEventListener("touchmove", onTouchMove, { passive: true })
    return () => {
      container.removeEventListener("wheel", onWheel)
      container.removeEventListener("touchstart", onTouchStart)
      container.removeEventListener("touchmove", onTouchMove)
    }
  }, [])

  // A brand-new message re-engages following so we track the latest turn.
  useEffect(() => {
    setAuto(true)
  }, [messages.length])

  // Re-engage following once the user scrolls back near the bottom.
  const handleScroll = () => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 80
    if (isAtBottom && !autoScrollRef.current) setAuto(true)
  }

  const lastMessage = messages[messages.length - 1]
  const showTypingIndicator =
    isStreaming &&
    (messages.length === 0 ||
      lastMessage?.role === "user" ||
      (lastMessage?.role === "assistant" && lastMessage?.content === "" && (!lastMessage.toolSteps || lastMessage.toolSteps.length === 0)))

  if (!isLoaded) {
    return (
      <div className="absolute inset-0 flex items-center justify-center">
        <div className="h-6 w-6 rounded-full border border-stone-100 border-t-stone-400 animate-spin" />
      </div>
    )
  }

  return (
    <>
    <div
      ref={containerRef}
      onScroll={handleScroll}
      className="absolute inset-0 overflow-y-auto pt-8 pb-32 space-y-4 border-none px-6"
      role="log"
      aria-label="Chat messages"
      aria-live="polite"
    >
      {/* Empty state */}
      {messages.length === 0 && !error && !isStreaming && (
        <div className="flex flex-col items-center justify-center h-full text-center text-stone-400 relative px-4">
          <div className="relative mb-5 flex h-12 w-12 items-center justify-center rounded-2xl bg-white/80 transition-all duration-300 hover:-translate-y-[2px]">
            <Bot size={22} strokeWidth={1.5} className="text-stone-600 relative z-10" />
          </div>

          <p className="text-[18px] font-semibold text-stone-800 tracking-tight">
            Professional coding agent
          </p>
          <p className="text-[14px] mt-2 text-stone-400 font-normal leading-relaxed max-w-[360px]">
            Describe a repository task. The agent will plan, edit, run checks, and report progress in the thread.
          </p>

          {/* Capability pills — match the composer's quick-action chip token */}
          <div className="mt-6 flex flex-wrap items-center justify-center gap-1.5 max-w-[400px]">
            {[
              { icon: ListTodo, label: "Plans" },
              { icon: FileCode, label: "Edits code" },
              { icon: FlaskConical, label: "Runs checks" },
              { icon: GitBranch, label: "Commits" },
            ].map(({ icon: Icon, label }) => (
              <span
                key={label}
                className="inline-flex items-center gap-1.5 rounded-full bg-stone-100/60 px-3.5 py-1.5 text-[12.5px] font-normal text-stone-500"
              >
                <Icon size={13} strokeWidth={1.5} className="text-stone-400" />
                {label}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Messages */}
      {messages
        .filter((message) => {
          if (isStreaming && message.role === "assistant" && message === lastMessage && message.content === "" && (!message.toolSteps || message.toolSteps.length === 0)) {
            return false
          }
          return true
        })
        .map((message) => (
          <MessageBubble
            key={message.id}
            message={message}
            isStreaming={isStreaming && message.role === "assistant" && message === lastMessage}
            onOpenDiff={onOpenDiff}
          />
        ))}

      {showTypingIndicator && <TypingIndicator />}

      {/* Error state */}
      {error && (
        <div
          className="flex items-center gap-3 p-4 bg-red-50 border border-red-200 rounded-xl"
          role="alert"
          style={{
            boxShadow:
              "rgba(14, 63, 126, 0.04) 0px 0px 0px 1px, rgba(42, 51, 69, 0.04) 0px 1px 1px -0.5px, rgba(42, 51, 70, 0.04) 0px 3px 3px -1.5px, rgba(42, 51, 70, 0.04) 0px 6px 6px -3px, rgba(14, 63, 126, 0.04) 0px 12px 12px -6px, rgba(14, 63, 126, 0.04) 0px 24px 24px -12px",
          }}
        >
          <AlertCircle className="w-5 h-5 text-red-500 shrink-0" aria-hidden="true" />
          <div className="flex-1">
            <p className="text-sm font-medium text-red-800">Something went wrong</p>
            <p className="text-xs text-red-600 mt-0.5">{error}</p>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRetry}
            className="text-red-600 hover:text-red-700 hover:bg-red-100 transition-colors"
            aria-label="Retry sending message"
          >
            <RefreshCw className="w-4 h-4 mr-1" aria-hidden="true" />
            Retry
          </Button>
        </div>
      )}

      {/* Scroll anchor */}
      <div ref={bottomRef} aria-hidden="true" className="h-20" />
    </div>

    {/* Jump to latest — appears only when the user has scrolled up */}
    {!autoScroll && messages.length > 0 && (
      <button
        onClick={() => setAuto(true)}
        className="absolute bottom-36 left-1/2 -translate-x-1/2 z-10 flex items-center gap-1.5 rounded-full bg-white/90 backdrop-blur border border-stone-200 shadow-[0_4px_20px_rgba(0,0,0,0.08)] px-3.5 py-2 text-[13px] font-medium text-stone-600 hover:text-stone-900 hover:shadow-[0_6px_24px_rgba(0,0,0,0.12)] hover:-translate-y-[1px] transition-all duration-200 animate-in fade-in slide-in-from-bottom-2"
        aria-label="Jump to latest message"
      >
        <ArrowDown size={14} strokeWidth={2} />
        {isStreaming ? "Follow along" : "Jump to latest"}
      </button>
    )}
    </>
  )
}

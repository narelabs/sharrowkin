"use client"

import { useEffect, useRef, useState } from "react"
import { MessageBubble } from "./message-bubble"
import type { Message } from "./chat-shell"
import { TypingIndicator } from "./typing-indicator"
import { AlertCircle, Bot, RefreshCw } from "lucide-react"
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
  const lastScrollRef = useRef<number>(0)

  useEffect(() => {
    if (!containerRef.current) return
    // Immediate scroll to bottom when messages change
    const container = containerRef.current
    container.scrollTop = container.scrollHeight
    setAutoScroll(true)
  }, [messages.length])

  useEffect(() => {
    if (!isStreaming || !autoScroll || !containerRef.current) {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
      return
    }

    const container = containerRef.current
    lastScrollRef.current = container.scrollTop

    const smoothScroll = () => {
      if (!container) return

      const { scrollHeight, clientHeight } = container
      const targetScroll = scrollHeight - clientHeight
      const currentScroll = lastScrollRef.current
      const diff = targetScroll - currentScroll

      if (diff > 0.5) {
        const newScroll = currentScroll + diff * 0.03
        lastScrollRef.current = newScroll
        container.scrollTop = newScroll
      }

      rafRef.current = requestAnimationFrame(smoothScroll)
    }

    // Start immediately
    rafRef.current = requestAnimationFrame(smoothScroll)

    return () => {
      if (rafRef.current) {
        cancelAnimationFrame(rafRef.current)
        rafRef.current = null
      }
    }
  }, [isStreaming, autoScroll])

  // Detect if user scrolls up to disable auto-scroll
  const handleScroll = () => {
    if (!containerRef.current || isStreaming) return

    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 150
    setAutoScroll(isAtBottom)
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
        <div className="h-6 w-6 rounded-full border border-stone-200 border-t-stone-500 animate-spin" />
      </div>
    )
  }

  return (
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
        <div className="flex flex-col items-center justify-center h-full text-center text-stone-400 relative">
          {/* Subtle floating particles */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-20">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="absolute w-2 h-2 rounded-full animate-float-slow"
                style={{
                  left: `${20 + Math.random() * 60}%`,
                  top: `${20 + Math.random() * 60}%`,
                  background: `linear-gradient(to bottom, #F7B2FB 50%, #786EF1 80%, #5588FB 100%)`,
                  animationDelay: `${i * 0.5}s`,
                  animationDuration: `${4 + i * 0.5}s`
                }}
              />
            ))}
          </div>

          <div className="relative mb-5 flex h-12 w-12 items-center justify-center rounded-2xl border border-stone-200 bg-white shadow-[0_2px_12px_rgba(0,0,0,0.04)] transition-all duration-300 hover:-translate-y-[2px] hover:shadow-[0_4px_20px_rgba(0,0,0,0.08)]">
            <Bot size={22} strokeWidth={1.5} className="text-stone-600 relative z-10" />
          </div>

          <p className="text-[18px] font-semibold text-stone-800 tracking-tight">
            Professional coding agent
          </p>
          <p className="text-[14px] mt-2 text-stone-400 font-normal leading-relaxed max-w-[360px]">
            Describe a repository task. The agent will plan, edit, run checks, and report progress in the thread.
          </p>
        </div>
      )}

      {/* Messages */}
      {messages
        .filter((message) => {
          // Hide empty assistant messages during streaming only if they don't have toolSteps.
          // If they have toolSteps, show them immediately so the timeline is visible!
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
  )
}

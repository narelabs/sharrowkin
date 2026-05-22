"use client"

import { useState, useRef, useEffect } from "react"
import { FileCode, Loader2, Sparkles, Send, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { MarkdownRenderer } from "@/components/chat/markdown-renderer"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

interface CodeViewerProps {
  filename: string | null
  content: string | null
  isLoading: boolean
}

export function CodeViewer({ filename, content, isLoading }: CodeViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  
  // Selection and Floating Button State
  const [selectedText, setSelectedText] = useState("")
  const [buttonPos, setButtonPos] = useState<{ x: number; y: number } | null>(null)
  
  // Inline Chat State
  const [isChatOpen, setIsChatOpen] = useState(false)
  const [prompt, setPrompt] = useState("")
  const [aiResponse, setAiResponse] = useState("")
  const [isThinking, setIsThinking] = useState(false)

  // Handle text selection
  const handleMouseUp = () => {
    if (isChatOpen) return // Don't trigger if chat is already open

    const selection = window.getSelection()
    if (!selection || selection.isCollapsed) {
      if (!isChatOpen) {
        setButtonPos(null)
        setSelectedText("")
      }
      return
    }

    const text = selection.toString().trim()
    if (text.length > 0) {
      const range = selection.getRangeAt(0)
      const rect = range.getBoundingClientRect()
      
      if (containerRef.current) {
        const containerRect = containerRef.current.getBoundingClientRect()
        let x = rect.left - containerRect.left
        let y = rect.bottom - containerRect.top + 8
        
        // Prevent overflow on the right side
        if (x + 360 > containerRect.width) {
          x = containerRect.width - 380
        }
        // Ensure it doesn't go off the left side
        if (x < 10) x = 10
        
        setButtonPos({ x, y })
        setSelectedText(text)
      }
    } else {
      setButtonPos(null)
      setSelectedText("")
    }
  }

  // Hide button if clicked outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (buttonPos && !isChatOpen && containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setButtonPos(null)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    return () => document.removeEventListener("mousedown", handleClickOutside)
  }, [buttonPos, isChatOpen])

  const openChat = () => {
    setIsChatOpen(true)
    setButtonPos(null) // hide the button, show the chat
  }

  const closeChat = () => {
    setIsChatOpen(false)
    setPrompt("")
    setAiResponse("")
    setSelectedText("")
  }

  const handleSendPrompt = async () => {
    if (!prompt.trim() || !filename || !selectedText) return

    setIsThinking(true)
    setAiResponse("")

    try {
      const res = await fetch(`${BACKEND_URL}/api/inline-ai`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename,
          selected_text: selectedText,
          prompt: prompt.trim()
        })
      })

      if (res.ok) {
        const data = await res.json()
        setAiResponse(data.response)
      } else {
        setAiResponse("Failed to connect to AI.")
      }
    } catch (err) {
      setAiResponse(`Error: ${err}`)
    } finally {
      setIsThinking(false)
    }
  }

  if (isLoading) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center text-stone-400 bg-white">
        <Loader2 className="w-6 h-6 animate-spin mb-3 text-stone-300" />
        <span className="text-[13px]">Loading file content...</span>
      </div>
    )
  }

  if (!filename || content === null) {
    return (
      <div className="h-full w-full flex flex-col items-center justify-center text-stone-400 bg-white">
        <FileCode size={32} strokeWidth={1} className="mb-3 opacity-50" />
        <span className="text-[13px]">Select a file from the explorer to view its contents.</span>
      </div>
    )
  }

  const lines = content.split('\n')

  return (
    <div className="h-full flex flex-col bg-white relative" ref={containerRef}>
      {/* Header */}
      <div className="h-14 border-b border-stone-200/60 flex items-center px-6 shrink-0 bg-stone-50/50">
        <div className="flex items-center gap-2.5">
          <FileCode className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
          <span className="font-medium text-[13px] text-stone-700">{filename.split(/[\\/]/).pop()}</span>
          <span className="text-[11px] text-stone-400 font-mono ml-2">{lines.length} lines</span>
        </div>
      </div>

      {/* Code Area */}
      <div 
        className="flex-1 overflow-auto bg-white p-4 relative"
        onMouseUp={handleMouseUp}
      >
        <div className="font-mono text-[12.5px] leading-relaxed flex pb-20">
          <div className="flex flex-col text-stone-300 select-none pr-4 text-right border-r border-stone-100 min-w-[2.5rem]">
            {lines.map((_, i) => (
              <span key={i + 1}>{i + 1}</span>
            ))}
          </div>
          <div className="flex flex-col pl-4 text-stone-600 whitespace-pre overflow-x-auto">
            {lines.map((line, i) => (
              <span key={i + 1} className="min-h-[1.5rem]">{line || " "}</span>
            ))}
          </div>
        </div>

        {/* Floating Sparkle Button */}
        {buttonPos && !isChatOpen && (
          <button
            onClick={openChat}
            style={{ top: buttonPos.y, left: buttonPos.x }}
            className="absolute z-10 flex items-center gap-1.5 px-3 py-1.5 bg-white hover:bg-stone-50 border border-stone-200/80 rounded-full shadow-[0_4px_12px_rgba(0,0,0,0.08)] text-stone-700 transition-all cursor-pointer group animate-in zoom-in-95 fade-in duration-150"
          >
            <Sparkles size={13} className="text-stone-400 group-hover:text-stone-600 transition-colors" />
            <span className="text-[12px] font-medium font-sans">Ask AI</span>
          </button>
        )}

        {/* Inline AI Chat Modal */}
        {isChatOpen && buttonPos && (
          <div 
            style={{ top: buttonPos.y, left: buttonPos.x, minWidth: "360px", maxWidth: "420px" }}
            className="absolute z-20 bg-white/95 backdrop-blur-xl border border-stone-200/80 rounded-2xl shadow-[0_12px_40px_rgb(0,0,0,0.12)] flex flex-col font-sans overflow-hidden animate-in fade-in zoom-in-95 duration-200 origin-top-left"
          >
            {/* Clean Input First Design */}
            <div className="p-1.5">
              <form 
                onSubmit={(e) => { e.preventDefault(); handleSendPrompt() }}
                className="flex items-center gap-2 relative bg-[#f4f4f5] rounded-xl px-2 py-1 transition-all focus-within:ring-2 focus-within:ring-stone-200/60 focus-within:bg-white"
              >
                <Sparkles size={14} className="text-stone-400 ml-1 shrink-0" />
                <input 
                  type="text" 
                  value={prompt}
                  onChange={(e) => setPrompt(e.target.value)}
                  placeholder="Ask about this code..."
                  className="flex-1 bg-transparent border-none text-[13px] focus:outline-none placeholder:text-stone-400 text-stone-800 font-medium py-1.5"
                  autoFocus
                />
                
                {prompt.trim() && !isThinking ? (
                  <button 
                    type="submit"
                    className="p-1.5 bg-stone-900 text-white rounded-lg hover:bg-stone-800 transition-colors flex items-center justify-center shrink-0 shadow-sm animate-in zoom-in-75 fade-in duration-150"
                  >
                    <Send size={12} className="ml-[1px]" />
                  </button>
                ) : (
                  <button onClick={closeChat} type="button" className="p-1.5 hover:bg-stone-200/80 rounded-lg text-stone-400 hover:text-stone-600 transition-colors shrink-0">
                    <X size={14} strokeWidth={1.5} />
                  </button>
                )}
              </form>
            </div>
            
            {(aiResponse || isThinking) && (
              <div className="px-3 pb-3 border-t border-stone-100/80 pt-3 max-h-[350px] overflow-y-auto no-scrollbar bg-white/50">
                {aiResponse ? (
                  <div className="text-[13px] text-stone-700 leading-relaxed prose prose-sm prose-p:my-1 prose-pre:bg-stone-50 prose-pre:text-stone-800 prose-pre:p-3 prose-pre:border prose-pre:border-stone-100 prose-pre:rounded-xl">
                    <MarkdownRenderer content={aiResponse} />
                  </div>
                ) : (
                  <div className="flex items-center gap-2 text-[13px] text-stone-500 py-2 animate-pulse">
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-stone-400" />
                    <span>Thinking...</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

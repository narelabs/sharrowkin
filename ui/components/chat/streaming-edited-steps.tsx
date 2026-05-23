"use client"

import { useState, useEffect } from "react"
import { motion, AnimatePresence } from "framer-motion"
import { FileCode, CheckCircle2, Loader2 } from "lucide-react"
import { cn } from "@/lib/utils"

interface FileEdit {
  filename: string
  additions: number
  deletions: number
  status: "pending" | "editing" | "done"
  message?: string // Промежуточное сообщение агента
}

interface StreamingEditedStepsProps {
  edits: FileEdit[]
  className?: string
  onFileClick?: (filename: string) => void
  onOpenWorkspace?: () => void
  isStreaming?: boolean // Add flag to control animation
}

function shortenPath(path: string): string {
  const parts = path.split("/")
  if (parts.length <= 3) return path
  return `.../${parts.slice(-2).join("/")}`
}

export function StreamingEditedSteps({ edits, className, onFileClick, onOpenWorkspace, isStreaming = false }: StreamingEditedStepsProps) {
  const [visibleEdits, setVisibleEdits] = useState<FileEdit[]>([])

  // Simulate streaming: show edits one by one
  useEffect(() => {
    if (edits.length === 0) {
      setVisibleEdits([])
      return
    }

    // If not streaming, show all edits immediately
    if (!isStreaming) {
      setVisibleEdits(edits)
      return
    }

    // Show edits progressively only when streaming
    let currentIndex = 0
    const interval = setInterval(() => {
      if (currentIndex < edits.length) {
        setVisibleEdits((prev) => [...prev, edits[currentIndex]])
        currentIndex++
      } else {
        clearInterval(interval)
      }
    }, 800) // Show one edit every 800ms

    return () => clearInterval(interval)
  }, [edits, isStreaming])

  if (visibleEdits.length === 0) return null

  return (
    <div className={cn("space-y-2", className)}>
      <AnimatePresence mode="popLayout">
        {visibleEdits.map((edit, index) => (
          <motion.div
            key={`${edit.filename}-${index}`}
            initial={{ opacity: 0, y: 10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.3, ease: "easeOut" }}
          >
            {/* File edit card */}
            <button
              onClick={() => {
                onFileClick?.(edit.filename)
                onOpenWorkspace?.()
              }}
              className={cn(
                "w-full flex items-center gap-2.5 py-[5px] group transition-all duration-150 hover:bg-stone-50/50 rounded-lg px-2 -mx-2"
              )}
            >
              {/* Status icon */}
              <div className="flex h-4 w-4 shrink-0 items-center justify-center">
                {edit.status === "editing" && (
                  <Loader2 strokeWidth={1.5} className="h-3.5 w-3.5 animate-spin text-stone-400" />
                )}
                {edit.status === "done" && (
                  <CheckCircle2 strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-300" />
                )}
                {edit.status === "pending" && (
                  <FileCode strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-300" />
                )}
              </div>

              {/* File info */}
              <div className="min-w-0 flex-1 flex items-center gap-1.5 text-[13px] leading-5">
                <span className={cn(
                  "shrink-0 transition-colors",
                  edit.status === "editing" ? "text-stone-700 font-medium" : "text-stone-500"
                )}>
                  Edited
                </span>
                <code className={cn(
                  "inline-flex items-center gap-1 px-1.5 py-0 rounded text-[11.5px] font-mono leading-5 truncate max-w-[280px]",
                  "bg-stone-100/70 text-stone-600"
                )}>
                  <FileCode size={11} className="text-stone-400 shrink-0" />
                  {shortenPath(edit.filename)}
                </code>

                {/* Diff stats */}
                {(edit.additions > 0 || edit.deletions > 0) && (
                  <span className="text-[11px] text-stone-400">
                    {edit.additions > 0 && `+${edit.additions}`}
                    {edit.deletions > 0 && ` −${edit.deletions}`}
                  </span>
                )}
              </div>

              {/* Duration */}
              <span className={cn(
                "shrink-0 text-[11px] tabular-nums text-stone-400 transition-opacity",
                edit.status === "editing" ? "opacity-100" : "opacity-0 group-hover:opacity-100"
              )}>
                {edit.status === "editing" ? "now" : "1s"}
              </span>
            </button>

            {/* Agent message after file edit */}
            {edit.message && edit.status === "done" && (
              <motion.div
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.3 }}
                className="ml-6 text-[12px] text-stone-500 leading-5"
              >
                {edit.message}
              </motion.div>
            )}
          </motion.div>
        ))}
      </AnimatePresence>
    </div>
  )
}

// Hook to convert tool steps to streaming edits
export function useStreamingEdits(toolSteps?: Array<{ name: string; status: string; description?: string }>) {
  const [edits, setEdits] = useState<FileEdit[]>([])

  useEffect(() => {
    if (!toolSteps) {
      setEdits([])
      return
    }

    const fileEdits: FileEdit[] = []
    const seenKeys = new Set<string>() // Track seen file+status combinations to avoid duplicates

    for (const step of toolSteps) {
      // Match "Edited filename.py +30" or "filename.py +30 -5"
      const editMatch = step.name.match(/^(?:Edited\s+)?(.+?)\s+\+(\d+)(?:\s+[-−](\d+))?/)

      if (editMatch) {
        const [, filename, additions, deletions] = editMatch
        const cleanFilename = filename.trim()
        const status = step.status === "done" ? "done" : step.status === "running" ? "editing" : "pending"

        // Create unique key: filename + status
        const uniqueKey = `${cleanFilename}:${status}`

        // Skip if we've already seen this exact file+status combination
        if (seenKeys.has(uniqueKey)) {
          continue
        }
        seenKeys.add(uniqueKey)

        fileEdits.push({
          filename: cleanFilename,
          additions: parseInt(additions, 10),
          deletions: deletions ? parseInt(deletions, 10) : 0,
          status: status,
          message: step.description
        })
      }
    }

    setEdits(fileEdits)
  }, [toolSteps])

  return edits
}

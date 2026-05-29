"use client"

import { useState, useMemo } from "react"
import { cn } from "@/lib/utils"
import { ScrollArea } from "@/components/ui/scroll-area"
import { File, Copy, Check } from "lucide-react"

interface FileDiffViewerProps {
  filename: string
  oldContent?: string
  newContent: string
  className?: string
}

interface DiffLine {
  type: "added" | "removed" | "unchanged"
  content: string
  oldLineNumber?: number
  newLineNumber?: number
}

function computeDiff(oldContent: string, newContent: string): DiffLine[] {
  const oldLines = oldContent.split("\n")
  const newLines = newContent.split("\n")

  const diff: DiffLine[] = []
  let oldIndex = 0
  let newIndex = 0

  // Simple line-by-line diff (можно улучшить с помощью библиотеки diff)
  while (oldIndex < oldLines.length || newIndex < newLines.length) {
    const oldLine = oldLines[oldIndex]
    const newLine = newLines[newIndex]

    if (oldLine === newLine) {
      diff.push({
        type: "unchanged",
        content: oldLine || "",
        oldLineNumber: oldIndex + 1,
        newLineNumber: newIndex + 1
      })
      oldIndex++
      newIndex++
    } else {
      // Check if line was removed
      if (oldIndex < oldLines.length && !newLines.includes(oldLine)) {
        diff.push({
          type: "removed",
          content: oldLine,
          oldLineNumber: oldIndex + 1
        })
        oldIndex++
      }
      // Check if line was added
      else if (newIndex < newLines.length) {
        diff.push({
          type: "added",
          content: newLine,
          newLineNumber: newIndex + 1
        })
        newIndex++
      }
    }
  }

  return diff
}

export function FileDiffViewer({ filename, oldContent = "", newContent, className }: FileDiffViewerProps) {
  const [copied, setCopied] = useState(false)

  const diffLines = useMemo(() => {
    if (!oldContent) {
      // New file - all lines are added
      return newContent.split("\n").map((line, index): DiffLine => ({
        type: "added" as const,
        content: line,
        newLineNumber: index + 1
      }))
    }

    return computeDiff(oldContent, newContent)
  }, [oldContent, newContent])

  const handleCopy = async () => {
    await navigator.clipboard.writeText(newContent)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  return (
    <div className={cn("flex flex-col h-full bg-white border border-stone-200 rounded-lg", className)}>
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-stone-200 bg-stone-50">
        <div className="flex items-center gap-2">
          <File className="w-4 h-4 text-stone-500" />
          <span className="text-[13px] font-medium text-stone-700">{filename}</span>
        </div>

        <button
          onClick={handleCopy}
          className="flex items-center gap-1.5 px-2 py-1 text-[11px] text-stone-600 hover:text-stone-900 hover:bg-stone-100 rounded transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-emerald-500" />
              <span>Copied</span>
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              <span>Copy</span>
            </>
          )}
        </button>
      </div>

      {/* Diff content */}
      <ScrollArea className="flex-1">
        <div className="font-mono text-[12px]">
          {diffLines.map((line, index) => (
            <div
              key={index}
              className={cn(
                "flex items-start",
                line.type === "added" && "bg-emerald-50 border-l-2 border-emerald-500",
                line.type === "removed" && "bg-red-50 border-l-2 border-red-500",
                line.type === "unchanged" && "bg-white"
              )}
            >
              {/* Line numbers */}
              <div className="flex shrink-0 select-none">
                <span
                  className={cn(
                    "inline-block w-12 px-2 py-0.5 text-right text-stone-400",
                    line.type === "removed" && "bg-red-100 text-red-600"
                  )}
                >
                  {line.oldLineNumber || ""}
                </span>
                <span
                  className={cn(
                    "inline-block w-12 px-2 py-0.5 text-right text-stone-400",
                    line.type === "added" && "bg-emerald-100 text-emerald-600"
                  )}
                >
                  {line.newLineNumber || ""}
                </span>
              </div>

              {/* Diff marker */}
              <span
                className={cn(
                  "inline-block w-6 px-1 py-0.5 text-center shrink-0",
                  line.type === "added" && "text-emerald-600 font-bold",
                  line.type === "removed" && "text-red-600 font-bold",
                  line.type === "unchanged" && "text-stone-300"
                )}
              >
                {line.type === "added" ? "+" : line.type === "removed" ? "−" : " "}
              </span>

              {/* Line content */}
              <pre
                className={cn(
                  "flex-1 px-2 py-0.5 whitespace-pre-wrap break-all",
                  line.type === "added" && "text-emerald-900",
                  line.type === "removed" && "text-red-900",
                  line.type === "unchanged" && "text-stone-700"
                )}
              >
                {line.content}
              </pre>
            </div>
          ))}
        </div>
      </ScrollArea>
    </div>
  )
}

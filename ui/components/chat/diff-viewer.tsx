"use client"

import { useState } from "react"
import { X, Columns, Rows, FileCode } from "lucide-react"
import { cn } from "@/lib/utils"

interface DiffViewerProps {
  filename: string
  diffContent?: string
  onClose: () => void
  onAccept?: () => void
}

export function DiffViewer({ filename, diffContent, onClose }: DiffViewerProps) {
  const [viewMode, setViewMode] = useState<"split" | "unified">("unified")

  // Parse real unified diff into lines with metadata
  const parsedLines = (diffContent || "").split("\n").map((line) => {
    if (line.startsWith("+++") || line.startsWith("---")) {
      return { text: line, type: "header" as const }
    }
    if (line.startsWith("@@")) {
      return { text: line, type: "hunk" as const }
    }
    if (line.startsWith("+")) {
      return { text: line, type: "add" as const }
    }
    if (line.startsWith("-")) {
      return { text: line, type: "del" as const }
    }
    return { text: line, type: "ctx" as const }
  })

  const additions = parsedLines.filter(l => l.type === "add").length
  const deletions = parsedLines.filter(l => l.type === "del").length

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Diff Header */}
      <div className="h-14 border-b border-stone-100/40 flex items-center justify-between px-6 bg-white shrink-0">
        <div className="flex items-center gap-2.5">
          <FileCode className="w-4 h-4 text-stone-400" strokeWidth={1.5} />
          <span className="font-medium text-[13px] text-stone-700">{filename}</span>
          <span className="text-[10px] text-emerald-600 font-mono bg-emerald-50 px-1.5 py-0.5 rounded-md">+{additions}</span>
          <span className="text-[10px] text-rose-600 font-mono bg-rose-50 px-1.5 py-0.5 rounded-md">-{deletions}</span>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex bg-stone-100 p-0.5 rounded-lg shrink-0">
            <button
              onClick={() => setViewMode("unified")}
              className={cn(
                "p-1 rounded-md transition-all",
                viewMode === "unified" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"
              )}
              title="Unified View"
            >
              <Rows size={14} strokeWidth={1.5} />
            </button>
            <button
              onClick={() => setViewMode("split")}
              className={cn(
                "p-1 rounded-md transition-all",
                viewMode === "split" ? "bg-white text-stone-800 shadow-sm" : "text-stone-400 hover:text-stone-600"
              )}
              title="Split View"
            >
              <Columns size={14} strokeWidth={1.5} />
            </button>
          </div>

          <div className="w-[1px] h-5 bg-stone-200"></div>

          <button onClick={onClose} className="p-1 text-stone-400 hover:text-stone-600 transition-colors">
            <X size={16} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* Code diff container */}
      <div className="flex-1 overflow-y-auto p-6 bg-stone-50/40 no-scrollbar">
        {!diffContent ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-stone-300 p-8">
            <FileCode size={32} strokeWidth={1} className="mb-3" />
            <span className="text-[13px]">No diff content available yet.</span>
          </div>
        ) : (
          <div className="border border-stone-100/30 bg-white rounded-2xl overflow-hidden">
            <div className="p-4 overflow-x-auto text-[12.5px] font-mono leading-relaxed select-text">
              <div className="space-y-0">
                {parsedLines.map((line, idx) => (
                  <div
                    key={idx}
                    className={cn(
                      "px-2 py-0.5 whitespace-pre",
                      line.type === "add" ? "bg-emerald-50/70 text-emerald-700" :
                      line.type === "del" ? "bg-rose-50/50 text-rose-600" :
                      line.type === "hunk" ? "text-indigo-400 font-light bg-indigo-50/30 mt-2 mb-1 rounded" :
                      line.type === "header" ? "text-stone-500 font-semibold" :
                      "text-stone-500"
                    )}
                  >
                    {line.text || " "}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

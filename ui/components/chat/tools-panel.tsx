"use client"

import React, { useState, useEffect, useCallback } from "react"
import {
  Wrench,
  FolderSearch,
  FileCode,
  ListTree,
  GitBranch,
  FlaskConical,
  Terminal,
  Globe,
  Link,
  Network,
  Brain,
  Database,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
} from "lucide-react"
import { cn } from "@/lib/utils"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

interface ToolParam {
  name: string
  type: string
  required: boolean
}

interface AgentTool {
  name: string
  description: string
  category: string
  parameters: ToolParam[]
}

type ToolRunStatus = "idle" | "running" | "done" | "error"

interface ToolRun {
  name: string
  status: ToolRunStatus
  result?: string
  startedAt?: number
}

const CATEGORY_ICONS: Record<string, React.ElementType> = {
  workspace: FolderSearch,
  code: FileCode,
  testing: FlaskConical,
  web: Globe,
  memory: Brain,
}

const TOOL_ICONS: Record<string, React.ElementType> = {
  scan_workspace: FolderSearch,
  read_file: FileCode,
  list_files: ListTree,
  apply_changes: FileCode,
  git_diff: GitBranch,
  run_pytest: FlaskConical,
  run_terminal_command: Terminal,
  search_web: Globe,
  fetch_url: Link,
  dependency_analysis: Network,
  semantic_graph: Network,
  memory_query: Database,
}

function getStatusIcon(status: ToolRunStatus) {
  if (status === "running") return <Loader2 size={12} className="animate-spin text-stone-400" />
  if (status === "done") return <CheckCircle2 size={12} className="text-emerald-500" />
  if (status === "error") return <XCircle size={12} className="text-red-500" />
  return null
}

export function ToolsPanel() {
  const [tools, setTools] = useState<AgentTool[]>([])
  const [toolRuns, setToolRuns] = useState<Record<string, ToolRun>>({})
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null)

  useEffect(() => {
    const fetchTools = async () => {
      try {
        const res = await fetch(`${BACKEND_URL}/api/tools`)
        if (res.ok) {
          const data = await res.json()
          setTools(data.tools || [])
        }
      } catch {
        // Backend offline — use built-in list
        setTools([])
      }
    }
    fetchTools()
  }, [])

  const categories = Array.from(new Set(tools.map((t) => t.category)))

  const handleQuickRun = useCallback(async (toolName: string) => {
    setToolRuns((prev) => ({
      ...prev,
      [toolName]: { name: toolName, status: "running", startedAt: Date.now() },
    }))

    try {
      const res = await fetch(`${BACKEND_URL}/api/terminal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: `agent tool ${toolName}` }),
      })
      const data = await res.json()
      setToolRuns((prev) => ({
        ...prev,
        [toolName]: {
          name: toolName,
          status: "done",
          result: Array.isArray(data.output) ? data.output.join("\n") : "Done",
          startedAt: prev[toolName]?.startedAt,
        },
      }))
    } catch (err: any) {
      setToolRuns((prev) => ({
        ...prev,
        [toolName]: {
          name: toolName,
          status: "error",
          result: err.message,
          startedAt: prev[toolName]?.startedAt,
        },
      }))
    }
  }, [])

  const quickRunTools = ["scan_workspace", "run_pytest", "git_diff"]

  return (
    <div className="p-4 space-y-4">
      {/* Quick Actions */}
      <div className="space-y-2">
        <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">Quick Actions</span>
        <div className="grid grid-cols-3 gap-2">
          {quickRunTools.map((name) => {
            const tool = tools.find((t) => t.name === name)
            const run = toolRuns[name]
            const Icon = TOOL_ICONS[name] || Wrench

            return (
              <button
                key={name}
                onClick={() => handleQuickRun(name)}
                disabled={run?.status === "running"}
                className={cn(
                  "flex flex-col items-center gap-1.5 p-2.5 rounded-xl border transition-all text-center",
                  run?.status === "running"
                    ? "border-stone-300 bg-stone-50 cursor-wait"
                    : "border-stone-200/60 bg-white hover:bg-stone-50 hover:border-stone-300"
                )}
              >
                <div className="relative">
                  <Icon size={16} strokeWidth={1.5} className="text-stone-500" />
                  {run && (
                    <div className="absolute -top-1 -right-1.5">
                      {getStatusIcon(run.status)}
                    </div>
                  )}
                </div>
                <span className="text-[10px] font-medium text-stone-600 leading-tight">
                  {tool?.name.replace(/_/g, " ") || name}
                </span>
              </button>
            )
          })}
        </div>
      </div>

      {/* Tools by Category */}
      <div className="space-y-1">
        <span className="text-[11px] font-medium text-stone-500 uppercase tracking-wider">All Tools</span>
        {categories.map((cat) => {
          const CatIcon = CATEGORY_ICONS[cat] || Wrench
          const catTools = tools.filter((t) => t.category === cat)
          const isExpanded = expandedCategory === cat

          return (
            <div key={cat} className="rounded-xl border border-stone-200/60 bg-white overflow-hidden">
              <button
                onClick={() => setExpandedCategory(isExpanded ? null : cat)}
                className="w-full flex items-center gap-2 px-3 py-2.5 hover:bg-stone-50/80 transition-colors"
              >
                <CatIcon size={14} strokeWidth={1.5} className="text-stone-400" />
                <span className="text-[12px] font-medium text-stone-700 capitalize flex-1 text-left">{cat}</span>
                <span className="text-[10px] text-stone-400 font-mono">{catTools.length}</span>
              </button>

              {isExpanded && (
                <div className="border-t border-stone-100 divide-y divide-stone-50">
                  {catTools.map((tool) => {
                    const ToolIcon = TOOL_ICONS[tool.name] || Wrench
                    const run = toolRuns[tool.name]

                    return (
                      <div key={tool.name} className="flex items-center gap-2.5 px-3 py-2 group">
                        <ToolIcon size={13} strokeWidth={1.5} className="text-stone-400 shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="text-[11.5px] font-medium text-stone-700 truncate">
                            {tool.name.replace(/_/g, " ")}
                          </div>
                          <div className="text-[10px] text-stone-400 truncate">{tool.description}</div>
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          {run && getStatusIcon(run.status)}
                          {tool.parameters.length === 0 && (
                            <button
                              onClick={() => handleQuickRun(tool.name)}
                              className="opacity-0 group-hover:opacity-100 p-1 rounded-md hover:bg-stone-100 transition-all"
                              title={`Run ${tool.name}`}
                            >
                              <Play size={11} className="text-stone-500" />
                            </button>
                          )}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Empty State */}
      {tools.length === 0 && (
        <div className="flex flex-col items-center justify-center py-8 text-stone-400 gap-2">
          <Wrench size={20} strokeWidth={1.5} />
          <span className="text-[11px]">Connecting to agent...</span>
        </div>
      )}
    </div>
  )
}

"use client"

import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import type { Message, ToolStep, TaskPlan } from "./chat-shell"
import { Loader2, CheckCircle2, ChevronRight, ChevronDown, CircleDashed, FileCode, XCircle, ListTodo, Clock, Bug, AlertCircle, Lightbulb, Bot, Search, Wrench, FlaskConical, Brain } from "lucide-react"
import { MarkdownRenderer } from "./markdown-renderer"
import { RepoSelectorCard } from "./repo-selector-card"
import { StreamingEditedSteps, useStreamingEdits } from "./streaming-edited-steps"
import Image from "next/image"

interface MessageBubbleProps {
  message: Message
  isStreaming?: boolean
  onOpenDiff?: (filename: string) => void
}

function formatElapsed(ms: number): string {
  const safeMs = Math.max(0, ms)
  const seconds = Math.max(1, Math.round(safeMs / 1000))
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const remainingSeconds = seconds % 60
  if (minutes < 60) return remainingSeconds ? `${minutes}m ${remainingSeconds}s` : `${minutes}m`
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`
}

function getStepDuration(index: number, isRunning: boolean): string {
  if (isRunning) return "now"
  return `${Math.max(1, index + 1)}s`
}

function getStepIcon(status: string) {
  if (status === "running") return <Loader2 strokeWidth={1.5} className="h-3.5 w-3.5 animate-spin text-stone-400" />
  if (status === "done") return <CheckCircle2 strokeWidth={1.5} className="h-3.5 w-3.5 text-emerald-500/80" />
  if (status === "error") return <XCircle strokeWidth={1.5} className="h-3.5 w-3.5 text-red-500/80" />
  return <CircleDashed strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-300" />
}

function getTaskIcon(status: string) {
  if (status === "in_progress") return <Loader2 strokeWidth={1.5} className="w-3 h-3 text-blue-500 animate-spin" />
  if (status === "done") return <CheckCircle2 strokeWidth={1.5} className="w-3 h-3 text-emerald-500" />
  if (status === "error") return <XCircle strokeWidth={1.5} className="w-3 h-3 text-red-500" />
  return <CircleDashed strokeWidth={1.5} className="w-3 h-3 text-stone-300" />
}

type AgentActivityKind = "thinking" | "searching" | "tool" | "testing" | "working" | "file"

function stripRawFunctionCalls(content: string) {
  const withoutCompleteBlocks = content.replace(/<function_calls>[\s\S]*?<\/function_calls>/g, "")
  const openBlockIndex = withoutCompleteBlocks.indexOf("<function_calls>")
  const visible = openBlockIndex >= 0 ? withoutCompleteBlocks.slice(0, openBlockIndex) : withoutCompleteBlocks
  return visible.replace(/\n{3,}/g, "\n\n").trimStart()
}

function extractRepoSelector(content: string): { content: string; repoSelector: any | null } {
  const match = content.match(/__REPO_SELECTOR__(.+?)__/)
  if (match) {
    try {
      const repoSelector = JSON.parse(match[1])
      const cleanContent = content.replace(/__REPO_SELECTOR__.+?__/, "").trim()
      return { content: cleanContent, repoSelector }
    } catch (e) {
      return { content, repoSelector: null }
    }
  }
  return { content, repoSelector: null }
}

function getActivityKind(step: ToolStep): AgentActivityKind {
  const text = `${step.name} ${step.description || ""}`.toLowerCase()
  if (/^edited\s/.test(text) || /\+\d+\s*$/.test(step.name)) return "file"
  if (/\.(tsx?|jsx?|css|scss|py|html|md|json|ya?ml|mjs|cjs)\b/.test(text) || /\+\d+\s*[−-]\d+/.test(text)) return "file"
  if (/^thought\b|think|reason|plan|context|^memory\s/.test(text)) return "thinking"
  if (/^read\s|search|explor|inspect|^scan\s|index|find|grep|rg|list/.test(text)) return "searching"
  if (/test|verify|build|lint|pytest|npm|check|^run tests/.test(text)) return "testing"
  if (/tool|command|^terminal|patch|diff|edit|prepared/.test(text)) return "tool"
  return "working"
}

function getKindLabel(kind: AgentActivityKind) {
  if (kind === "file") return "Edited"
  if (kind === "thinking") return "Thinking"
  if (kind === "searching") return "Searching"
  if (kind === "testing") return "Testing"
  if (kind === "tool") return "Using tool"
  return "Working"
}

function getKindIcon(kind: AgentActivityKind) {
  if (kind === "file") return FileCode
  if (kind === "thinking") return Brain
  if (kind === "searching") return Search
  if (kind === "testing") return FlaskConical
  if (kind === "tool") return Wrench
  return Bot
}

function shortenPath(raw: string): string {
  const parts = raw.replace(/\\/g, "/").split("/").filter(Boolean)
  if (parts.length <= 2) return parts.join("/")
  return parts.slice(-2).join("/")
}

function extractTarget(step: ToolStep): string | null {
  const desc = step.description || ""
  const name = step.name || ""
  const full = `${name} ${desc}`
  const fileMatch = full.match(/([a-zA-Z]:\\[^\s'"]+)|((?:[\w@.-]+\/)+[\w@.-]+\.\w+)/);
  if (fileMatch) return shortenPath(fileMatch[0])
  const projMatch = desc.match(/^\s*([\w.-]+)\s*$/)
  if (projMatch && !desc.includes(" ")) return projMatch[1]
  return null
}


function formatStepDisplay(step: ToolStep): { verb: string; target: string | null; detail: string | null; isCode: boolean } {
  const name = step.name || ""
  const desc = step.description || ""
  const nameLower = name.toLowerCase()
  const target = extractTarget(step)

  if (step.id?.startsWith("tool-call-")) {
    const parts = name.split(/\s+/)
    const verb = parts[0] || name
    const rest = parts.slice(1).join(" ")
    return { verb, target: rest ? shortenPath(rest) : target, detail: null, isCode: true }
  }

  if (/^(scan|read|search|explore|analyze|memory|thought|terminal|git|run|edited|write)/i.test(nameLower)) {
    const parts = name.split(/\s+/)
    const verb = parts[0]
    const rest = parts.slice(1).join(" ")
    if (rest && rest.length > 0) {
      return { verb, target: shortenPath(rest), detail: desc && desc !== rest ? desc : null, isCode: /[./\\]/.test(rest) }
    }
    return { verb, target, detail: desc || null, isCode: false }
  }

  if (/explored|scanning|exploring/i.test(nameLower)) {
    return { verb: name, target, detail: null, isCode: false }
  }

  if (target) {
    return { verb: name.replace(target, "").replace(/\s+/g, " ").trim() || name, target, detail: null, isCode: true }
  }

  return { verb: name, target: null, detail: desc || null, isCode: false }
}

function AgentTimelineRow({ step, index, onOpenDiff }: { step: ToolStep; index: number, onOpenDiff?: (filename: string) => void }) {
  const isRunning = step.status === "running"
  const kind = getActivityKind(step)
  const KindIcon = getKindIcon(kind)
  const isFilePatch = step.id.startsWith("patch-") || step.name.toLowerCase().includes("patch") || step.name === "Prepared code changes"
  const display = formatStepDisplay(step)

  return (
    <div
      className={cn(
        "relative flex items-center gap-2.5 py-[5px] group transition-all duration-150",
        isFilePatch && onOpenDiff && "cursor-pointer hover:bg-stone-50/50 rounded-lg px-2 -mx-2"
      )}
      onClick={() => { if (isFilePatch && onOpenDiff) onOpenDiff("agent-patch.diff") }}
    >
      <div className="flex h-4 w-4 shrink-0 items-center justify-center">
        {isRunning ? (
          <KindIcon strokeWidth={1.8} className="h-3.5 w-3.5 animate-pulse text-stone-500" />
        ) : step.status === "error" ? (
          <XCircle strokeWidth={1.5} className="h-3.5 w-3.5 text-red-500/80" />
        ) : (
          <KindIcon strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-300" />
        )}
      </div>
      <div className="min-w-0 flex-1 flex items-center gap-1.5 text-[13px] leading-5">
        <span className={cn(
          "shrink-0 transition-colors",
          step.status === "error" ? "text-red-600 font-medium" : isRunning ? "text-stone-700 font-medium" : "text-stone-500"
        )}>
          {display.verb}
        </span>
        {display.target && (
          <code className={cn(
            "inline-flex items-center gap-1 px-1.5 py-0 rounded text-[11.5px] font-mono leading-5 truncate max-w-[280px]",
            "bg-stone-100/70 text-stone-600"
          )}>
            {display.isCode && <FileCode size={11} className="text-stone-400 shrink-0" />}
            {display.target}
          </code>
        )}
        {display.detail && !display.target && (
          <span className="text-stone-400 truncate">{display.detail}</span>
        )}
      </div>
      <span className={cn(
        "shrink-0 text-[11px] tabular-nums text-stone-400 transition-opacity",
        isRunning ? "opacity-100" : "opacity-0 group-hover:opacity-100"
      )}>{getStepDuration(index, isRunning)}</span>
    </div>
  )
}

function AgentTimelineFileGroup({ group, index }: { group: ToolStep[]; index: number }) {
  const [expanded, setExpanded] = useState(false)
  const isRunning = group.some(s => s.status === "running")
  const hasError = group.some(s => s.status === "error")
  const kind = getActivityKind(group[0])
  const KindIcon = getKindIcon(kind)
  
  return (
    <div className="py-[2px]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-2.5 py-[5px] group transition-all duration-150 text-left"
      >
        <div className="flex h-4 w-4 shrink-0 items-center justify-center">
          {isRunning ? <Loader2 strokeWidth={1.5} className="h-3.5 w-3.5 animate-spin text-stone-400" /> : hasError ? <XCircle strokeWidth={1.5} className="h-3.5 w-3.5 text-red-500/80" /> : <KindIcon strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-300" />}
        </div>
        <div className="min-w-0 flex-1 flex items-center gap-1.5 text-[13px] leading-5">
          {expanded ? <ChevronDown size={12} className="text-stone-400 shrink-0" /> : <ChevronRight size={12} className="text-stone-400 shrink-0" />}
          <span className="text-stone-500">Worked on {group.length} files</span>
        </div>
        <span className="shrink-0 text-[11px] tabular-nums text-stone-400 opacity-0 group-hover:opacity-100 transition-opacity">{getStepDuration(index, isRunning)}</span>
      </button>
      {expanded && (
        <div className="ml-6 pl-4 border-l border-stone-100/60 space-y-0">
          {group.map((step) => (
            <AgentTimelineRow key={step.id} step={step} index={index} />
          ))}
        </div>
      )}
    </div>
  )
}

function TaskPlanItem({ task, depth = 0 }: { task: TaskPlan; depth?: number }) {
  const [expanded, setExpanded] = useState(true)
  const hasSubtasks = task.subtasks && task.subtasks.length > 0

  return (
    <div className={cn("flex flex-col", depth > 0 && "ml-4 mt-1")}>
      <div className="flex items-center gap-2 py-1">
        {hasSubtasks && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="shrink-0 hover:bg-stone-100 rounded p-0.5 transition-colors"
          >
            {expanded ? (
              <ChevronDown strokeWidth={1.5} className="w-3 h-3 text-stone-400" />
            ) : (
              <ChevronRight strokeWidth={1.5} className="w-3 h-3 text-stone-400" />
            )}
          </button>
        )}
        {!hasSubtasks && <div className="w-4" />}

        {getTaskIcon(task.status)}

        <span className={cn(
          "text-[12px] font-medium transition-colors",
          task.status === "in_progress" ? "text-stone-800" :
          task.status === "done" ? "text-stone-500 line-through" :
          task.status === "error" ? "text-red-600" :
          "text-stone-600"
        )}>
          {task.title}
        </span>

        {task.estimatedTime && task.status === "pending" && (
          <span className="flex items-center gap-1 text-[10px] text-stone-400 ml-auto">
            <Clock strokeWidth={1.5} className="w-2.5 h-2.5" />
            {task.estimatedTime}
          </span>
        )}
      </div>

      {hasSubtasks && expanded && (
        <div className="flex flex-col">
          {task.subtasks!.map((subtask) => (
            <TaskPlanItem key={subtask.id} task={subtask} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

function ThoughtSection({ lines, isStreaming }: { lines: string[]; isStreaming: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const preview = lines[0]?.slice(0, 120) || "Reasoning..."
  
  return (
    <div className="py-[2px]">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1.5 text-[13px] leading-5 transition-colors hover:text-stone-600 group py-[3px]"
      >
        <Brain size={14} strokeWidth={1.5} className={cn("text-stone-400 shrink-0", isStreaming && "animate-pulse")} />
        {expanded ? <ChevronDown size={12} className="text-stone-400 shrink-0" /> : <ChevronRight size={12} className="text-stone-400 shrink-0" />}
        <span className={cn("transition-colors", isStreaming ? "text-stone-700 font-medium" : "text-stone-400")}>
          Thought{isStreaming ? "..." : ""}
        </span>
      </button>
      {expanded && (
        <div className="ml-3 pl-4 border-l border-stone-100/60 py-2 text-[13px] text-stone-500 leading-6 max-h-[300px] overflow-y-auto no-scrollbar">
          {lines.map((line, i) => (
            <div key={i} className="animate-in fade-in duration-200" style={{ animationDelay: `${i * 30}ms` }}>
              {line}
            </div>
          ))}
        </div>
      )}
      {!expanded && (
        <div className="ml-8 text-[12px] text-stone-400 truncate max-w-[500px] leading-5">
          {preview}
        </div>
      )}
    </div>
  )
}

export function MessageBubble({ message, isStreaming = false, onOpenDiff }: MessageBubbleProps) {
  const isUser = message.role === "user"
  const [expandedSteps, setExpandedSteps] = useState(true)
  const [now, setNow] = useState(() => Date.now())

  // Use streaming edits hook
  const streamingEdits = useStreamingEdits(message.toolSteps)

  useEffect(() => {
    if (isUser || !isStreaming) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [isUser, isStreaming])

  if (!isUser) {
    const steps = message.toolSteps || []
    const hasSteps = steps.length > 0
    const isWorking = hasSteps && steps.some((step) => step.status === "running")
    const elapsed = formatElapsed((isStreaming ? now : message.createdAt.getTime() + Math.max(1000, steps.length * 1000)) - message.createdAt.getTime())
    const completedTodos = message.taskPlan?.filter((task) => task.status === "done").length || 0
    const thoughtLines = message.thinkingText?.split("\n").map((line) => line.trim()).filter(Boolean) || []
    const strippedContent = stripRawFunctionCalls(message.content)
    const { content: visibleContent, repoSelector } = extractRepoSelector(strippedContent)
    const kinds = new Set(steps.map(getActivityKind))
    const activitySummary = ["thinking", "searching", "tool", "testing", "file", "working"]
      .filter((kind) => kinds.has(kind as AgentActivityKind))
      .map((kind) => getKindLabel(kind as AgentActivityKind).toLowerCase())

    // Group sequential file operations to make UI cleaner
    const groupedSteps: { type: 'single' | 'group', step?: ToolStep, group?: ToolStep[], id: string, index: number }[] = []
    let currentFileGroup: ToolStep[] = []
    let currentGroupIndex = -1

    steps.forEach((step, idx) => {
      const kind = getActivityKind(step)
      const isSimpleFileStep = (kind === "file" || kind === "searching") && 
        !step.id.startsWith("patch-") && 
        !step.name.includes("Patching") && 
        !step.name.includes("Prepared code changes") && 
        !step.name.includes("Analyzed error") &&
        !step.name.includes("Explored") &&
        (step.name.includes("Updated") || step.name.includes("Created") || step.name.includes("Read"))

      if (isSimpleFileStep) {
        if (currentFileGroup.length === 0) {
          currentGroupIndex = idx
        }
        currentFileGroup.push(step)
      } else {
        if (currentFileGroup.length > 0) {
          if (currentFileGroup.length === 1) {
            groupedSteps.push({ type: 'single', step: currentFileGroup[0], id: currentFileGroup[0].id, index: currentGroupIndex })
          } else {
            groupedSteps.push({ type: 'group', group: currentFileGroup, id: `group-${currentFileGroup[0].id}`, index: currentGroupIndex })
          }
          currentFileGroup = []
        }
        groupedSteps.push({ type: 'single', step: step, id: step.id, index: idx })
      }
    })
    
    if (currentFileGroup.length > 0) {
      if (currentFileGroup.length === 1) {
        groupedSteps.push({ type: 'single', step: currentFileGroup[0], id: currentFileGroup[0].id, index: currentGroupIndex })
      } else {
        groupedSteps.push({ type: 'group', group: currentFileGroup, id: `group-${currentFileGroup[0].id}`, index: currentGroupIndex })
      }
    }

    return (
      <div className="w-full max-w-3xl mx-auto py-8 animate-in fade-in duration-300">
        <div className="flex flex-col gap-4">
          <div className="space-y-1">
            {/* Thought section — Devin style */}
            {thoughtLines.length > 0 && (
              <ThoughtSection lines={thoughtLines} isStreaming={isStreaming} />
            )}

            {/* Worked for Xs — collapsible */}
            {(groupedSteps.length > 0 || (message.taskPlan && message.taskPlan.length > 0)) && (
              <div>
                <button
                  onClick={() => setExpandedSteps(!expandedSteps)}
                  className="flex items-center gap-1.5 text-[13px] leading-5 transition-colors hover:text-stone-600 group py-[3px]"
                >
                  {expandedSteps ? <ChevronDown size={13} strokeWidth={1.5} className="text-stone-400" /> : <ChevronRight size={13} strokeWidth={1.5} className="text-stone-400" />}
                  <span className={cn(
                    "transition-colors",
                    (isStreaming || isWorking) ? "text-stone-700 font-medium" : "text-stone-400"
                  )}>
                    {isStreaming || isWorking ? "Working" : "Worked"} for {elapsed}
                  </span>
                  {steps.length > 0 && <span className="text-stone-400 text-[12px]">· {steps.length} {steps.length === 1 ? "action" : "actions"}</span>}
                  {activitySummary.length > 0 && <span className="text-stone-400 text-[12px]">· {activitySummary.slice(0, 3).join(", ")}</span>}
                </button>

                {expandedSteps && (
                  <div className="ml-3 pl-4 border-l border-stone-100/60 space-y-0 pb-1">
                    {/* Streaming edited steps - show files one by one */}
                    {streamingEdits.length > 0 && (
                      <div className="py-2">
                        <StreamingEditedSteps
                          edits={streamingEdits}
                          onFileClick={onOpenDiff}
                          onOpenWorkspace={() => {
                            // Signal to parent to open workspace panel
                            const event = new CustomEvent("open-workspace-panel")
                            window.dispatchEvent(event)
                          }}
                          isStreaming={isStreaming}
                        />
                      </div>
                    )}

                    {message.taskPlan && message.taskPlan.length > 0 && (
                      <div className="py-1.5">
                        <div className="flex items-center gap-2.5 text-[13px] leading-5 text-stone-500 py-[5px]">
                          <div className="flex h-4 w-4 shrink-0 items-center justify-center">
                            <ListTodo size={14} strokeWidth={1.5} className="text-stone-300" />
                          </div>
                          <span>Created {message.taskPlan.length} tasks</span>
                          <span className="text-stone-400 text-[11px]">{completedTodos}/{message.taskPlan.length}</span>
                        </div>
                        <div className="ml-6 mt-0.5 space-y-0.5">
                          {message.taskPlan.map((task) => (
                            <TaskPlanItem key={task.id} task={task} />
                          ))}
                        </div>
                      </div>
                    )}

                    {groupedSteps.map((item) => {
                      if (item.type === 'group' && item.group) {
                        return <AgentTimelineFileGroup key={item.id} group={item.group} index={item.index} />
                      } else if (item.type === 'single' && item.step) {
                        return <AgentTimelineRow key={item.id} step={item.step} index={item.index} onOpenDiff={onOpenDiff} />
                      }
                      return null
                    })}
                  </div>
                )}
              </div>
            )}
          </div>

          {visibleContent && (
            <div className="text-[14px] text-stone-900 font-normal leading-7 tracking-[-0.01em] max-w-full overflow-x-auto animate-in fade-in duration-300">
              <MarkdownRenderer content={visibleContent} isStreaming={isStreaming} />
            </div>
          )}

          {/* Repository Selector Card */}
          {repoSelector && (
            <div className="mt-4 animate-in fade-in duration-300">
              <RepoSelectorCard
                prompt={repoSelector.prompt}
                repos={repoSelector.repos}
                onSelect={(repo) => {
                  // Send selected repo back to agent
                  const event = new CustomEvent("repo-selected", { detail: repo })
                  window.dispatchEvent(event)
                }}
              />
            </div>
          )}

          {/* Debug Analysis */}
          {message.debugAnalysis && (
            <div className="w-full max-w-[600px]">
              <div className="bg-gradient-to-br from-red-50/40 to-orange-50/20 rounded-xl p-3">
                <div className="flex items-center gap-2 mb-2">
                  <Bug strokeWidth={1.5} className="w-4 h-4 text-red-600" />
                  <span className="text-[13px] font-semibold text-red-900">Error Analysis</span>
                  <span className="text-[10px] text-red-600 bg-red-100/60 px-1.5 py-0.5 rounded-md ml-auto">
                    {message.debugAnalysis.errorType}
                  </span>
                </div>

                <div className="flex flex-col gap-2">
                  {/* Error location */}
                  {message.debugAnalysis.filePath && (
                    <div className="flex items-center gap-2 text-[11px] text-stone-600">
                      <FileCode strokeWidth={1.5} className="w-3 h-3" />
                      <span className="font-mono">
                        {message.debugAnalysis.filePath}:{message.debugAnalysis.lineNumber}
                      </span>
                    </div>
                  )}

                  {/* Root cause */}
                  <div className="flex items-start gap-2">
                    <AlertCircle strokeWidth={1.5} className="w-3.5 h-3.5 text-red-500 mt-0.5 shrink-0" />
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[11px] font-medium text-red-700">Root Cause:</span>
                      <span className="text-[12px] text-stone-700 leading-relaxed">
                        {message.debugAnalysis.rootCause}
                      </span>
                    </div>
                  </div>

                  {/* Suggested fix */}
                  <div className="flex items-start gap-2">
                    <Lightbulb strokeWidth={1.5} className="w-3.5 h-3.5 text-amber-500 mt-0.5 shrink-0" />
                    <div className="flex flex-col gap-0.5">
                      <span className="text-[11px] font-medium text-amber-700">Suggested Fix:</span>
                      <span className="text-[12px] text-stone-700 leading-relaxed font-mono bg-stone-50 px-2 py-1 rounded">
                        {message.debugAnalysis.suggestedFix}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Diff Card */}
          {visibleContent && visibleContent.includes("```diff") && onOpenDiff && (
            <div className="flex items-center justify-between p-4 bg-stone-50/60 rounded-2xl max-w-[500px] animate-in fade-in slide-in-from-bottom-2 duration-500 transition-all hover:bg-stone-50">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-white/80 flex items-center justify-center">
                  <FileCode size={16} strokeWidth={1.5} className="text-stone-400" />
                </div>
                <div className="flex flex-col">
                  <span className="text-[13px] text-stone-800 font-medium">Proposed Changes</span>
                  <span className="text-[11px] text-stone-400 font-normal mt-0.5">Review agent patch</span>
                </div>
              </div>
              <button
                onClick={() => onOpenDiff("agent-patch.diff")}
                className="px-3.5 py-1.5 text-white rounded-xl text-[12.5px] font-normal transition-all duration-200 shadow-[0_2px_12px_rgba(0,0,0,0.15)] hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(0,0,0,0.2)] shrink-0 ml-4"
                style={{ backgroundImage: 'linear-gradient(180deg, #2c2c2c 0%, #111111 100%)' }}
              >
                View Diff
              </button>
            </div>
          )}

          {/* Streaming dots */}
          {isStreaming && !message.content && !hasSteps && thoughtLines.length === 0 && (
            <div className="flex items-center gap-2 text-[13px] text-stone-400">
              <Bot size={15} strokeWidth={1.5} />
              <span>Starting agent run</span>
              <div className="flex items-center gap-1">
                <div className="w-1.5 h-1.5 rounded-full bg-stone-300 animate-pulse" />
                <div className="w-1.5 h-1.5 rounded-full bg-stone-300 animate-pulse delay-75" />
                <div className="w-1.5 h-1.5 rounded-full bg-stone-300 animate-pulse delay-150" />
              </div>
            </div>
          )}
        </div>
      </div>
    )
  }

  // User Message
  return (
    <div className="flex w-full justify-end max-w-3xl mx-auto py-4 user-message-enter">
      <div className="flex flex-col items-end gap-1.5 max-w-[85%] md:max-w-[75%]">
        <div className="rounded-[20px] rounded-br-[6px] bg-stone-50/80 text-stone-800 font-normal px-4 py-3 transition-all duration-200">
          <div className="flex flex-col gap-2">
            {message.imageData && (
              <div className="w-32 h-32 rounded-xl overflow-hidden image-bounce">
                <Image
                  src={message.imageData || "/placeholder.svg"}
                  alt="Uploaded image"
                  width={128}
                  height={128}
                  className="w-full h-full object-cover hover:scale-105 transition-transform duration-500"
                />
              </div>
            )}
            <p className="text-[14px] leading-relaxed whitespace-pre-wrap break-words">{message.content}</p>
          </div>
        </div>
      </div>
    </div>
  )
}

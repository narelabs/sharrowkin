"use client"

import { useState, useEffect } from "react"
import { cn } from "@/lib/utils"
import type { Message, ToolStep, TaskPlan } from "./chat-shell"
import { Loader2, CheckCircle2, ChevronRight, ChevronDown, CircleDashed, FileCode, XCircle, ListTodo, Clock, Bug, AlertCircle, Lightbulb, Bot, Search, Wrench, FlaskConical, Brain } from "lucide-react"
import { MarkdownRenderer } from "./markdown-renderer"
import { RepoSelectorCard } from "./repo-selector-card"
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
  // Tool call patterns — Devin-style: "Edited path/file.py +N", "Read path/file.py"
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

function getKindColor(kind: AgentActivityKind): { bg: string; border: string; text: string; icon: string } {
  // All steps use neutral gray colors, shimmer effect will be added separately for running steps
  return {
    bg: "bg-stone-50",
    border: "border-stone-200/60",
    text: "text-stone-700",
    icon: "text-stone-500"
  }
}

// Extract file paths into beautiful badges
function renderDescriptionWithFiles(text: string, onOpenDiff?: (filename: string) => void) {
  const regex = /([a-zA-Z]:\\[^\s\]'"]+)|((?:[\w.-]+\/)+[\w.-]+)|'([\w.-]+\.\w+)'|"([\w.-]+\.\w+)"/g;
  const parts = [];
  let lastIndex = 0;
  let match;
  
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push(<span key={`text-${lastIndex}`}>{text.substring(lastIndex, match.index)}</span>);
    }
    const path = match[1] || match[2] || match[3] || match[4];
    const filename = path.split(/[\\/]/).pop() || path;
    const isClickable = !!onOpenDiff;
    
    parts.push(
      <span 
        key={`file-${match.index}`} 
        onClick={(e) => {
          if (onOpenDiff) {
            e.stopPropagation();
            onOpenDiff("agent-patch.diff"); // Or pass the actual filename if the diff viewer supports it
          }
        }}
        className={cn(
          "inline-flex items-center gap-1 px-1.5 py-0 mx-1 bg-stone-100 text-stone-700 border border-stone-200/60 rounded-md text-[11px] font-mono shadow-[0_1px_2px_rgba(0,0,0,0.02)] translate-y-[-1px]",
          isClickable && "cursor-pointer hover:bg-stone-200/80 hover:border-stone-300 transition-colors"
        )}
      >
        <FileCode size={11} className="text-stone-400" />
        {filename}
      </span>
    );
    lastIndex = regex.lastIndex;
  }
  
  if (lastIndex < text.length) {
    parts.push(<span key={`text-${lastIndex}`}>{text.substring(lastIndex)}</span>);
  }
  
  return parts.length > 0 ? parts : text;
}

function AgentTimelineRow({ step, index, onOpenDiff }: { step: ToolStep; index: number, onOpenDiff?: (filename: string) => void }) {
  const isRunning = step.status === "running"
  const kind = getActivityKind(step)
  const KindIcon = getKindIcon(kind)
  const colors = getKindColor(kind)

  const isFilePatch = step.id.startsWith("patch-") || step.name.toLowerCase().includes("patch") || step.name === "Prepared code changes"
  const isFileKind = kind === "file"
  const filename = step.description?.split(" ").find(part => /\.(tsx?|jsx?|css|scss|py|html|md|json|ya?ml|mjs|cjs)\b/.test(part))

  // Filter out redundant descriptions
  const shouldShowDescription = step.description && !["Finished.", "Done", "Working"].includes(step.description.trim())

  // Try to detect terminal commands to style them like a console
  const isTerminalCommand = shouldShowDescription && (step.description!.includes("$ ") || step.description!.includes("npm ") || step.description!.includes("git ") || step.description!.includes("python "))

  return (
    <div
      className={cn(
        "relative flex items-start gap-3 py-1.5 group transition-all duration-200",
        isFilePatch && onOpenDiff && "cursor-pointer hover:bg-stone-50/50 rounded-lg px-2 -mx-2"
      )}
      onClick={() => { if (isFilePatch && onOpenDiff) onOpenDiff("agent-patch.diff") }}
    >
      <div className="relative -ml-[7px] mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center bg-white">
        {isRunning ? (
          <KindIcon strokeWidth={1.8} className={cn("h-3.5 w-3.5 animate-pulse transition-colors", colors.icon)} />
        ) : step.status === "error" ? (
          getStepIcon(step.status)
        ) : (
          <KindIcon strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-400" />
        )}
      </div>
      <div className="min-w-0 flex-1 text-[13px] font-normal leading-5 text-stone-500">
        {step.id?.startsWith("tool-call-") ? (
          <>
            <span className={cn("font-medium transition-colors", step.status === "error" ? "text-red-600" : isRunning ? colors.text : "text-stone-700")}>
              {step.name}
            </span>
          </>
        ) : (
          <>
            <span className={cn(
              "relative inline-block transition-colors",
              isRunning ? "text-stone-700 font-medium" : "text-stone-400"
            )}>
              {isRunning && (
                <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/90 to-transparent opacity-90 animate-shimmer pointer-events-none" />
              )}
              <span className="relative z-10">{getKindLabel(kind)}</span>
            </span>
            <span className={cn("ml-2 font-medium transition-colors", step.status === "error" ? "text-red-600" : isRunning ? colors.text : "text-stone-700")}>
              {(isFilePatch || isFileKind) && !step.name.includes(" ") ? (
                 <span className="inline-flex items-center gap-1.5 px-1.5 py-0.5 bg-stone-100 text-stone-700 border border-stone-200/60 rounded-md text-[11.5px] font-mono shadow-[0_1px_2px_rgba(0,0,0,0.02)] translate-y-[-1px] transition-colors">
                   <FileCode size={12} className="text-stone-400" />
                   {step.name}
                 </span>
              ) : step.name}
            </span>
          </>
        )}
        
        {shouldShowDescription && (
          <div className="mt-1">
            {isTerminalCommand ? (
              <div className="text-[11.5px] font-mono text-stone-600 whitespace-pre-wrap break-all leading-relaxed bg-stone-50/80 border border-stone-200/50 rounded-md px-2.5 py-2">
                {step.description?.split('\n').map((line, i) => (
                  <div key={i} className="flex">
                    {line.startsWith("$") ? (
                      <>
                        <span className="text-emerald-600/80 font-semibold mr-2 shrink-0">$</span>
                        <span className="text-indigo-600/80">{line.substring(1).trim()}</span>
                      </>
                    ) : (
                      <span>{line}</span>
                    )}
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-[13px] font-normal leading-relaxed text-stone-500">
                {renderDescriptionWithFiles(step.description!, isFilePatch ? onOpenDiff : undefined)}
              </div>
            )}
          </div>
        )}
      </div>
      <span className="shrink-0 text-[12px] tabular-nums text-stone-400 opacity-0 group-hover:opacity-100 transition-opacity">{getStepDuration(index, isRunning)}</span>
    </div>
  )
}

function AgentTimelineFileGroup({ group, index }: { group: ToolStep[]; index: number }) {
  const isRunning = group.some(s => s.status === "running")
  const hasError = group.some(s => s.status === "error")
  const kind = getActivityKind(group[0])
  const KindIcon = getKindIcon(kind)
  
  return (
    <div className="relative flex items-start gap-3 py-2 group/timeline">
      <div className="relative -ml-[7px] mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center bg-white">
        {isRunning ? getStepIcon("running") : hasError ? getStepIcon("error") : <KindIcon strokeWidth={1.5} className="h-3.5 w-3.5 text-stone-400" />}
      </div>
      <div className="min-w-0 flex-1 text-[13px] font-normal leading-5 text-stone-500">
        <span className="text-stone-400">{getKindLabel(kind)}</span>
        <span className={cn("ml-2 font-medium text-stone-700")}>
          Worked on {group.length} files
        </span>
        
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {group.map((step) => {
            const rawPath = step.description?.split('\n')[0]?.trim() || step.name;
            const pathParts = rawPath.split(/[\\/]/);
            const filename = pathParts.pop();
            const directory = pathParts.length > 0 ? pathParts.join('/') + '/' : '';

            return (
              <span key={step.id} className="inline-flex items-center gap-1.5 px-2 py-1 bg-stone-50 text-stone-700 border border-stone-200/80 rounded-md text-[11.5px] font-mono shadow-sm hover:bg-stone-100 hover:border-stone-300 transition-all cursor-default">
                <FileCode size={12} className={step.status === "error" ? "text-red-400" : "text-stone-400"} />
                <span className={step.status === "error" ? "text-red-600" : ""}>
                  {directory && <span className="text-stone-400 font-normal">{directory}</span>}
                  {filename}
                </span>
              </span>
            )
          })}
        </div>
      </div>
      <span className="shrink-0 text-[12px] tabular-nums text-stone-400 opacity-0 group-hover/timeline:opacity-100 transition-opacity">{getStepDuration(index, isRunning)}</span>
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

export function MessageBubble({ message, isStreaming = false, onOpenDiff }: MessageBubbleProps) {
  const isUser = message.role === "user"
  const [expandedSteps, setExpandedSteps] = useState(true)
  const [now, setNow] = useState(() => Date.now())

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
      <div className="w-full max-w-3xl mx-auto py-6 animate-in fade-in duration-300">
        <div className="flex flex-col gap-4">
          <div className="space-y-2">
            <button
              onClick={() => setExpandedSteps(!expandedSteps)}
              className="flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[13px] font-normal leading-5 transition-colors hover:text-stone-600 group"
            >
              {expandedSteps ? <ChevronDown size={13} strokeWidth={1.5} className="text-stone-400" /> : <ChevronRight size={13} strokeWidth={1.5} className="text-stone-400" />}
              <span className={cn(
                "relative inline-block transition-all duration-300",
                (isStreaming || isWorking) ? "text-stone-700 font-medium" : "text-stone-400"
              )}>
                {(isStreaming || isWorking) && (
                  <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white to-transparent opacity-90 animate-shimmer pointer-events-none" />
                )}
                <span className="relative z-10">{isStreaming || isWorking ? "Working" : "Worked"} for {elapsed}</span>
              </span>
              {steps.length > 0 && <span className="text-stone-400">· {steps.length} {steps.length === 1 ? "action" : "actions"}</span>}
              {activitySummary.length > 0 && <span className="text-stone-400">· {activitySummary.slice(0, 4).join(", ")}</span>}
            </button>

            {expandedSteps && (
              <div className="ml-[6px] pl-5 border-l border-transparent">
                {message.taskPlan && message.taskPlan.length > 0 && (
                  <div className="py-1.5">
                    <div className="relative flex items-center gap-3 text-[13px] font-normal leading-5 text-stone-500">
                      <ListTodo size={14} strokeWidth={1.5} className="-ml-[22px] bg-white text-stone-400" />
                      <span>Created {message.taskPlan.length} Tasks</span>
                      <span className="text-stone-400">{completedTodos}/{message.taskPlan.length}</span>
                    </div>
                    <div className="mt-1.5 space-y-0.5">
                      {message.taskPlan.map((task) => (
                        <TaskPlanItem key={task.id} task={task} />
                      ))}
                    </div>
                  </div>
                )}

                {thoughtLines.length > 0 && (
                  <div className="py-2 px-3 bg-gradient-to-br from-purple-50/50 to-blue-50/30 border border-purple-100/60 rounded-lg">
                    <div className="relative flex items-center gap-2 text-[13px] font-medium leading-5 text-purple-700 mb-2">
                      <Brain size={16} strokeWidth={2} className={cn("text-purple-500", isStreaming && "animate-pulse")} />
                      <span>Agent Thinking{isStreaming ? "..." : ""}</span>
                      {isStreaming && (
                        <div className="ml-auto flex gap-1">
                          <div className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
                          <div className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
                          <div className="w-1.5 h-1.5 bg-purple-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
                        </div>
                      )}
                    </div>
                    <div className="text-[13px] font-normal leading-6 text-stone-600 space-y-1 max-h-[300px] overflow-y-auto">
                      {thoughtLines.map((line, index) => (
                        <div key={`${line}-${index}`} className="animate-in fade-in slide-in-from-left-2 duration-300" style={{ animationDelay: `${index * 50}ms` }}>
                          <span className="text-purple-400 mr-2">▸</span>{line}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {groupedSteps.length > 0 && groupedSteps.map((item) => {
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
              <div className="bg-gradient-to-br from-red-50/50 to-orange-50/30 border border-red-100/60 rounded-xl p-3 shadow-sm">
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
            <div className="flex items-center justify-between p-4 bg-stone-50 border border-stone-200/60 rounded-2xl max-w-[500px] shadow-[0_2px_12px_rgba(0,0,0,0.04)] animate-in fade-in slide-in-from-bottom-2 duration-500 transition-all hover:-translate-y-[1px] hover:shadow-[0_4px_20px_rgba(0,0,0,0.06)]">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-white border border-stone-200/60 flex items-center justify-center shadow-[0_1px_3px_rgba(0,0,0,0.01)]">
                  <FileCode size={16} strokeWidth={1.5} className="text-stone-500" />
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
        <div className="rounded-[20px] rounded-br-[6px] bg-[#f4f4f5] text-stone-800 font-normal px-4 py-3 transition-all duration-200 hover:shadow-[0_2px_12px_rgba(0,0,0,0.04)] hover:-translate-y-[1px]">
          <div className="flex flex-col gap-2">
            {message.imageData && (
              <div className="w-32 h-32 rounded-xl overflow-hidden border border-stone-100 shadow-sm image-bounce">
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

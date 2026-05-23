"use client"

import { useState, useEffect, useCallback, useMemo, useRef } from "react"
import { useSearchParams } from "next/navigation"
import { ArrowDownToLine, MessageSquareDashed, PanelRight } from "lucide-react"
import { MessageList } from "./message-list"
import { Composer, type AIModel } from "./composer"
import { Button } from "@/components/ui/button"
import { LeftSidebar } from "./left-sidebar"
import { RightSidebar } from "./right-sidebar"
import { WorkspacePanel } from "./workspace-panel"
import { FileDiffViewer } from "./file-diff-viewer"

import { DiffViewer } from "./diff-viewer"
import { TerminalEmulator } from "./terminal-emulator"
import { cn } from "@/lib/utils"

// Backend URL — configurable via env var, defaults to localhost
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
const WS_URL = BACKEND_URL.replace(/^http/, "ws")

// Data model for messages
export interface ToolStep {
  id: string
  name: string
  status: "running" | "done" | "error"
  description?: string
}

export interface TaskPlan {
  id: string
  title: string
  status: "pending" | "in_progress" | "done" | "error"
  subtasks?: TaskPlan[]
  estimatedTime?: string
}

export interface DebugAnalysis {
  errorType: string
  errorMessage: string
  filePath: string
  lineNumber: number
  rootCause: string
  suggestedFix: string
}

export interface Message {
  id: string
  role: "user" | "assistant"
  content: string
  createdAt: Date
  imageData?: string
  toolSteps?: ToolStep[]
  taskPlan?: TaskPlan[]  // Hierarchical task plan
  debugAnalysis?: DebugAnalysis  // Error analysis from debugger
  thinkingText?: string
}

export type AgentStatus = "idle" | "connecting" | "running" | "thinking" | "stabilizing" | "done" | "error" | "stopped"
export type PhaseStatus = "pending" | "running" | "done" | "error"

export interface AgentState {
  status: AgentStatus
  phase?: string
  message?: string
  startedAt?: string
  updatedAt?: string
  runtimeMs?: number
}

export interface AgentPhase {
  id: string
  label: string
  status: PhaseStatus
  description?: string
  startedAt?: string
  completedAt?: string
}

export interface ProjectIntelligence {
  status: "unknown" | "warming" | "ready" | "stale" | "error"
  workspacePath?: string
  filesIndexed?: number
  linesIndexed?: number
  symbols?: number
  complexityAvg?: number
  circularDependencies?: number
  mostComplexFunctions?: Array<{ id: string; complexity: number; line: number }>
  cacheHitRate?: number
  lastIndexedAt?: string
  summary?: string
}

export interface ToolActivity {
  id: string
  name: string
  status: "queued" | "running" | "done" | "error"
  message?: string
  target?: string
  startedAt?: string
  durationMs?: number
}

export interface ContextStatus {
  usedTokens?: number
  maxTokens?: number
  percent?: number
  status?: "healthy" | "compact" | "near_limit" | "overflow" | "unknown"
  cache?: "cold" | "warming" | "ready" | "stale"
}

export interface DiffStatus {
  filename?: string
  status: "none" | "proposed" | "accepted" | "rejected"
  filesChanged?: number
  additions?: number
  deletions?: number
}

export interface TestStatus {
  status: "idle" | "running" | "passed" | "failed"
  command?: string
  message?: string
  passed?: number
  failed?: number
  durationMs?: number
}

export interface RuntimeHint {
  id: string
  label: string
  value: string
  tone?: "neutral" | "good" | "warning" | "error"
}

const DEFAULT_PHASES: AgentPhase[] = [
  { id: "observe", label: "Explore", status: "pending", description: "Understand the workspace" },
  { id: "reason", label: "Plan", status: "pending", description: "Generate patch" },
  { id: "validate", label: "Verify", status: "pending", description: "Run tests and verify" },
]

function normalizePhaseName(phase?: string) {
  return (phase || "").toString().toLowerCase().replace(/\s+/g, "_")
}

function formatDuration(ms?: number) {
  if (!ms || ms < 0) return "—"
  if (ms < 1000) return `${Math.round(ms)}ms`
  const seconds = Math.round(ms / 1000)
  if (seconds < 60) return `${seconds}s`
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`
}

function parseNumber(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined
}

// localStorage key for persisting messages
const MODEL_STORAGE_KEY = "chat-selected-model"

// Generates a unique ID for messages
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 9)}`
}

export function ChatShell() {
  const searchParams = useSearchParams()
  const activeSessionId = searchParams?.get("session") || "session-1"
  const STORAGE_KEY = `sharrowkin-session-messages-${activeSessionId}`

  const [messages, setMessages] = useState<Message[]>([])
  const [isStreaming, setIsStreaming] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const socketRef = useRef<WebSocket | null>(null)
  const startedAtRef = useRef<number | null>(null)
  const [selectedModel, setSelectedModel] = useState<AIModel>("google/gemini-2.5-flash")
  const [isLoaded, setIsLoaded] = useState(false)
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true)
  const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false)
  const [selectedFile, setSelectedFile] = useState<string>()
  const [workspaceFiles, setWorkspaceFiles] = useState<Array<{
    name: string
    path: string
    type: "file" | "directory"
    children?: any[]
    modified?: boolean
    additions?: number
    deletions?: number
  }>>([])
  const [activeDiffFile, setActiveDiffFile] = useState<string | null>(null)
  const [lastDiffContent, setLastDiffContent] = useState("")
  const [fileDiffs, setFileDiffs] = useState<Map<string, string>>(new Map()) // Store diff per file
  const [agentState, setAgentState] = useState<AgentState>({ status: "idle", message: "Workspace ready" })
  const [agentPhases, setAgentPhases] = useState<AgentPhase[]>(DEFAULT_PHASES)
  const [projectIntelligence, setProjectIntelligence] = useState<ProjectIntelligence>({ status: "unknown" })
  const [toolActivity, setToolActivity] = useState<ToolActivity[]>([])
  const [contextStatus, setContextStatus] = useState<ContextStatus>({ status: "unknown", cache: "cold" })
  const [runtimeHints, setRuntimeHints] = useState<RuntimeHint[]>([])
  const [diffStatus, setDiffStatus] = useState<DiffStatus>({ status: "none" })
  const [testStatus, setTestStatus] = useState<TestStatus>({ status: "idle" })
  const [planMode, setPlanMode] = useState<"autonomous" | "interactive" | "analyze">("autonomous")
  const [cognitiveState, setCognitiveState] = useState<any>({
    mode: "Full NARE-Field",
    energy_ledger: {
      forward: 15.45,
      memory_search: 12.50,
      trace_replay: 22.00,
      expert_reasoning: 35.50,
      hebbian: 0.00,
      total: 85.45
    },
    attractors: [],
    traces: [],
    dim: 128,
    matrix_density: 0.0,
    sampled_matrix: Array(16).fill(0).map(() => Array(16).fill(0))
  })

  const backendConnected = agentState.status !== "error" || !error

  const workspacePath = useMemo(() => projectIntelligence.workspacePath || "active workspace", [projectIntelligence.workspacePath])

  // --- LIFTED TERMINAL EMULATOR STATE ---
  const [terminalLines, setTerminalLines] = useState<string[]>([
    "sharrowkin-core ~ bash",
    "$ agent start --mode=autonomous",
    "[INFO] Initializing workspace...",
    "[INFO] Loading repository context...",
    "[INFO] Connecting to language model...",
    "→ System ready. Awaiting input.",
  ])
  const [isRunningTask, setIsRunningTask] = useState(false)
  const [activeTaskPlan, setActiveTaskPlan] = useState<TaskPlan[]>([])
  const [currentInput, setCurrentInput] = useState("")
  const [terminalDock, setTerminalDock] = useState<"sidebar" | "bottom">("sidebar")
  const [isDraggingTerminal, setIsDraggingTerminal] = useState(false)
  const [terminalHeight, setTerminalHeight] = useState(250)
  const [isResizingTerminal, setIsResizingTerminal] = useState(false)

  // Run a real command via the backend terminal API
  const runRealCommand = useCallback(async (cmd: string) => {
    if (isRunningTask) return
    setIsRunningTask(true)
    setTerminalLines((prev) => [...prev, "", `$ ${cmd}`])
    try {
      const response = await fetch(`${BACKEND_URL}/api/terminal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      })
      const data = await response.json()
      if (data.output && Array.isArray(data.output)) {
        setTerminalLines((prev) => [...prev, ...data.output])
      }
    } catch (err: any) {
      setTerminalLines((prev) => [...prev, `error: ${err.message}`])
    } finally {
      setIsRunningTask(false)
    }
  }, [isRunningTask])

  const runBuildCommand = useCallback(() => {
    runRealCommand("npm run build")
  }, [runRealCommand])

  const runTestCommand = useCallback(() => {
    runRealCommand("npm test")
  }, [runRealCommand])

  const clearTerminal = useCallback(() => {
    setTerminalLines(["sharrowkin-core ~ bash", "$ cleared console", "→ System ready. Awaiting input."])
  }, [])

  const handleCommandSubmit = useCallback(async (e: React.FormEvent) => {
    e.preventDefault()
    if (!currentInput.trim() || isRunningTask) return

    const cmd = currentInput.trim()
    setTerminalLines((prev) => [...prev, `$ ${cmd}`])
    setCurrentInput("")

    const normalizedCmd = cmd.toLowerCase()

    if (normalizedCmd === "clear") {
      clearTerminal()
      return
    }

    setIsRunningTask(true)

    try {
      const response = await fetch(`${BACKEND_URL}/api/terminal`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: cmd }),
      })

      if (!response.ok) {
        throw new Error("Failed to communicate with NARE-Field backend.")
      }

      const data = await response.json()
      if (data.output && Array.isArray(data.output)) {
        setTerminalLines((prev) => [...prev, ...data.output])
      }
    } catch (err: any) {
      setTerminalLines((prev) => [
        ...prev,
        `bash: command failed: ${cmd}`,
        `error: ${err.message}`
      ])
    } finally {
      setIsRunningTask(false)
    }
  }, [currentInput, isRunningTask, clearTerminal, runBuildCommand, runTestCommand])

  const handleDragStart = useCallback((e: React.DragEvent) => {
    setIsDraggingTerminal(true)
    if (e.dataTransfer) {
      e.dataTransfer.setData("text/plain", "terminal")
      e.dataTransfer.effectAllowed = "move"
    }
  }, [])

  const handleDragEnd = useCallback(() => {
    setIsDraggingTerminal(false)
  }, [])

  // Safe global drag end reset
  useEffect(() => {
    const handleGlobalDragEnd = () => {
      setIsDraggingTerminal(false)
    }
    window.addEventListener("dragend", handleGlobalDragEnd)
    window.addEventListener("drop", handleGlobalDragEnd)
    return () => {
      window.removeEventListener("dragend", handleGlobalDragEnd)
      window.removeEventListener("drop", handleGlobalDragEnd)
    }
  }, [])

  const handleTerminalResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    setIsResizingTerminal(true)
    const startY = e.clientY
    const startHeight = terminalHeight

    const doDrag = (moveEvent: MouseEvent) => {
      const deltaY = startY - moveEvent.clientY // drag up increases height
      const nextHeight = Math.max(160, Math.min(startHeight + deltaY, 480))
      setTerminalHeight(nextHeight)
    }

    const stopDrag = () => {
      setIsResizingTerminal(false)
      document.removeEventListener("mousemove", doDrag)
      document.removeEventListener("mouseup", stopDrag)
    }

    document.addEventListener("mousemove", doDrag)
    document.addEventListener("mouseup", stopDrag)
  }, [terminalHeight])

  // Listen for workspace panel open event
  useEffect(() => {
    const handleOpenWorkspace = () => {
      setWorkspacePanelOpen(true)
    }
    window.addEventListener("open-workspace-panel", handleOpenWorkspace)
    return () => window.removeEventListener("open-workspace-panel", handleOpenWorkspace)
  }, [])

  // Load messages from localStorage on mount and when active session changes
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        const parsed = JSON.parse(stored)
        const messagesWithDates = parsed.map((msg: Message) => ({
          ...msg,
          createdAt: new Date(msg.createdAt),
        }))
        setMessages(messagesWithDates)
      } else {
        // Clean welcome for new sessions
        let defaultMessages: Message[] = []
        setMessages(defaultMessages)
      }
      const savedModel = localStorage.getItem(MODEL_STORAGE_KEY) as AIModel | null
      if (savedModel) {
        setSelectedModel(savedModel)
      }
    } catch (e) {
      console.error("Failed to load from localStorage:", e)
    } finally {
      setIsLoaded(true)
    }
  }, [activeSessionId, STORAGE_KEY])

  // Persist messages to localStorage whenever they change
  useEffect(() => {
    if (!isLoaded) return
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages))
    } catch (e) {
      console.error("Failed to save messages to localStorage:", e)
    }
  }, [messages, STORAGE_KEY, isLoaded])

  // Handle repository selection from RepoSelectorCard
  useEffect(() => {
    const handleRepoSelected = (event: CustomEvent) => {
      const repo = event.detail
      if (repo && repo.full_name) {
        // Send message to agent with selected repository
        const message = `Я выбрал репозиторий: ${repo.full_name}`
        handleSendMessage(message)
      }
    }

    window.addEventListener("repo-selected", handleRepoSelected as EventListener)
    return () => {
      window.removeEventListener("repo-selected", handleRepoSelected as EventListener)
    }
  }, [])

  const handleModelChange = useCallback((model: AIModel) => {
    setSelectedModel(model)
    localStorage.setItem(MODEL_STORAGE_KEY, model)
  }, [])

  const resetAgentWorkspace = useCallback(() => {
    socketRef.current?.close()
    socketRef.current = null
    startedAtRef.current = null
    setIsStreaming(false)
    setError(null)
    setAgentState({ status: "idle", message: "Workspace ready" })
    setAgentPhases(DEFAULT_PHASES)
    setToolActivity([])
    setContextStatus({ status: "unknown", cache: projectIntelligence.status === "ready" ? "ready" : "cold" })
    setRuntimeHints([])
    setDiffStatus({ status: "none" })
    setTestStatus({ status: "idle" })
  }, [projectIntelligence.status])

  const setPhaseStatus = useCallback((phase: string, status: PhaseStatus, description?: string) => {
    const normalized = normalizePhaseName(phase)
    const phaseIndex = DEFAULT_PHASES.findIndex((item) => item.id === normalized)
    const now = new Date().toISOString()

    setAgentPhases((prev) => {
      const source = prev.length ? prev : DEFAULT_PHASES
      return source.map((item, index) => {
        if (phaseIndex >= 0) {
          if (index < phaseIndex) return { ...item, status: item.status === "error" ? "error" : "done", completedAt: item.completedAt || now }
          if (index === phaseIndex) return { ...item, status, description: description || item.description, startedAt: item.startedAt || now, completedAt: status === "done" ? now : item.completedAt }
          return status === "error" && index === phaseIndex ? { ...item, status: "error" } : item
        }
        if (item.id === normalized) return { ...item, status, description: description || item.description, startedAt: item.startedAt || now }
        return item
      })
    })
  }, [])

  const appendToolActivity = useCallback((activity: Omit<ToolActivity, "id" | "startedAt"> & { id?: string; startedAt?: string }) => {
    const entry: ToolActivity = {
      ...activity,
      id: activity.id || generateId(),
      startedAt: activity.startedAt || new Date().toISOString(),
    }
    setToolActivity((prev) => [entry, ...prev.filter((item) => item.id !== entry.id)].slice(0, 40))
  }, [])

  // Send a message to the AI
  const sendMessage = useCallback(
    async (content: string, imageData?: string) => {
      if ((!content.trim() && !imageData) || isStreaming) return

      setError(null)

      const userMessage: Message = {
        id: generateId(),
        role: "user",
        content: content.trim() || "Describe this image",
        createdAt: new Date(),
        imageData,
      }

      const assistantMessage: Message = {
        id: generateId(),
        role: "assistant",
        content: "",
        createdAt: new Date(),
        toolSteps: [
          { id: "step-1", name: "Preparing workspace", status: "running", description: "Opening the repository context." }
        ]
      }

      const newMessages = [...messages, userMessage, assistantMessage]
      setMessages(newMessages)
      setIsStreaming(true)
      startedAtRef.current = Date.now()
      setAgentState({ status: "connecting", phase: "connect", message: "Connecting to autonomous backend", startedAt: new Date().toISOString() })
      setAgentPhases(DEFAULT_PHASES)
      setToolActivity([])
      setRuntimeHints([{ id: "model", label: "model", value: selectedModel, tone: "neutral" }])
      setDiffStatus({ status: "none" })
      setTestStatus({ status: "idle" })
      appendToolActivity({ name: "Connection", status: "running", message: "Opening the agent session" })

      // --- REAL STREAMING VIA WEBSOCKET TO BACKEND AGENT ---
      let currentSteps: ToolStep[] = [
        { id: "step-1", name: "Preparing workspace", status: "running", description: "Opening the repository context." }
      ];

      const updateSteps = (newSteps: ToolStep[]) => {
        currentSteps = newSteps;
        setMessages(prev => prev.map(msg => {
          if (msg.id === assistantMessage.id) {
            return { ...msg, toolSteps: newSteps };
          }
          return msg;
        }));
      };

      const appendStep = (step: Omit<ToolStep, "id"> & { id?: string }) => {
        const entry: ToolStep = { id: step.id || generateId(), name: step.name, status: step.status, description: step.description }
        const existingIndex = currentSteps.findIndex((item) => item.id === entry.id)
        const nextSteps = existingIndex >= 0
          ? currentSteps.map((item, index) => index === existingIndex ? entry : item)
          : [...currentSteps, entry].slice(-24)
        updateSteps(nextSteps)
      }

      const parsedFunctionCallKeys = new Set<string>()

      const setAssistantContent = (content: string) => {
        setMessages(prev => prev.map(msg => {
          if (msg.id === assistantMessage.id) {
            return { ...msg, content };
          }
          return msg;
        }));
      };

      const extractFunctionCalls = (raw: string) => {
        const completeBlockRegex = /<function_calls>[\s\S]*?<\/function_calls>/g
        const invokeRegex = /<invoke\s+name=["']([^"']+)["'][^>]*>([\s\S]*?)<\/invoke>/g
        const parameterRegex = /<parameter\s+name=["']([^"']+)["'][^>]*>([\s\S]*?)<\/parameter>/g

        for (const blockMatch of raw.matchAll(completeBlockRegex)) {
          const block = blockMatch[0]
          for (const invokeMatch of block.matchAll(invokeRegex)) {
            const toolName = invokeMatch[1]
            const body = invokeMatch[2]
            const params: string[] = []

            for (const paramMatch of body.matchAll(parameterRegex)) {
              const name = paramMatch[1]
              const value = paramMatch[2].replace(/\s+/g, " ").trim()
              if (value) params.push(`${name}: ${value}`)
            }

            const key = `${toolName}:${params.join("|")}`
            if (!parsedFunctionCallKeys.has(key)) {
              parsedFunctionCallKeys.add(key)
              appendStep({
                id: `function-call-${key}`,
                name: toolName,
                status: "done",
                description: params.join(" · ") || "Tool call",
              })
            }
          }
        }

        const withoutCompleteBlocks = raw.replace(completeBlockRegex, "")
        const openBlockIndex = withoutCompleteBlocks.indexOf("<function_calls>")
        const visible = openBlockIndex >= 0 ? withoutCompleteBlocks.slice(0, openBlockIndex) : withoutCompleteBlocks
        return visible.replace(/\n{3,}/g, "\n\n").trimStart()
      }

      // Fetch via WebSocket to our autonomous agent backend!
      try {
        socketRef.current?.close()
        const ws = new WebSocket(`${WS_URL}/api/agent/ws`)
        socketRef.current = ws
        
        ws.onopen = async () => {
          const githubToken = localStorage.getItem("github_token") || ""

          // Try to get workspace from multiple sources
          let workspace = localStorage.getItem("sharrowkin-workspace-path") ||
                         projectIntelligence.workspacePath || ""

          // If still empty, fetch from backend settings
          if (!workspace) {
            try {
              const response = await fetch(`${BACKEND_URL}/api/settings`)
              if (response.ok) {
                const data = await response.json()
                workspace = data.workspace_path || ""
                // Save to localStorage for next time
                if (workspace) {
                  localStorage.setItem("sharrowkin-workspace-path", workspace)
                }
              }
            } catch (err) {
              console.error("Failed to fetch workspace from backend:", err)
            }
          }

          // Final fallback - use current directory or prompt user
          if (!workspace) {
            workspace = process.cwd() || "/tmp/workspace"
          }

          ws.send(JSON.stringify({
            task: content.trim(),
            workspace: workspace,
            model: selectedModel,
            plan_mode: planMode,
            github_token: githubToken,
            session_id: activeSessionId,
          }))
          
          updateSteps([
            { id: "observe", name: "Exploring repository", status: "running", description: "Reading project files and structure" }
          ])
          setAgentState({ status: "running", phase: "observe", message: "Observing workspace", startedAt: new Date(startedAtRef.current || Date.now()).toISOString(), updatedAt: new Date().toISOString() })
          setPhaseStatus("observe", "running", "Scanning active project files")
          appendToolActivity({ name: "Autonomous run", status: "running", message: content.trim(), target: workspacePath })
          setProjectIntelligence((prev) => ({ ...prev, status: prev.status === "ready" ? "ready" : "warming" }))
          setTerminalLines(prev => [...prev, "", `[AGENT] Task started: "${content.trim()}"`])
        }
        
        let fullResponse = ""
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            
            if (data.type === "phase_change") {
              // Update tool steps based on phase
              const phaseNames: Record<string, string> = {
                observe: "Exploring repository",
                reason: "Planning changes",
                validate: "Running verification",
              }
              
              const currentPhaseKey = data.phase
              const allKeys = ["observe", "reason", "validate"]

              updateSteps(currentSteps.map((step) => (
                (allKeys.includes(step.id) || step.id.startsWith("phase-")) && step.status === "running"
                  ? { ...step, status: "done", description: step.description || "Done" }
                  : step
              )))
              appendStep({ id: currentPhaseKey, name: phaseNames[currentPhaseKey] || currentPhaseKey, status: "running", description: data.message || "Working" })
              setAgentState((prev) => ({ ...prev, status: currentPhaseKey === "validate" ? "stabilizing" : "running", phase: currentPhaseKey, message: phaseNames[currentPhaseKey] || "Working", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
              setPhaseStatus(currentPhaseKey, "running", data.message || "Working")
              appendToolActivity({ name: phaseNames[currentPhaseKey] || currentPhaseKey, status: "running", message: data.message || "Phase transition" })
              setTerminalLines(prev => [...prev, `➔ Transitioned to phase: ${data.phase.toUpperCase()}`])
              
            } else if (data.type === "thinking") {
              // Show agent's thinking/reasoning in the chat
              const thinkingText = data.content || ""
              setMessages(prev => prev.map(msg => {
                if (msg.id === assistantMessage.id) {
                  return { ...msg, thinkingText: msg.thinkingText ? msg.thinkingText + "\n" + thinkingText : thinkingText }
                }
                return msg
              }))
              setAgentState((prev) => ({ ...prev, status: "thinking", message: thinkingText.slice(0, 120) || "Reasoning", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
              appendToolActivity({ name: "Reasoning", status: "running", message: thinkingText.slice(0, 180) })
              appendStep({ id: "thinking-live", name: "Thinking", status: "running", description: thinkingText.slice(0, 180) })
              setTerminalLines(prev => [...prev, `💭 ${thinkingText}`])

            } else if (data.type === "task_plan") {
              // Hierarchical task plan from planner
              const plan = data.plan || []
              setActiveTaskPlan(plan)
              setMessages(prev => prev.map(msg => {
                if (msg.id === assistantMessage.id) {
                  return { ...msg, taskPlan: plan }
                }
                return msg
              }))
              appendToolActivity({ name: "Execution plan", status: "done", message: `${plan.length} top-level tasks` })
              appendStep({ id: "todos-created", name: `Created ${plan.length} tasks`, status: "done", description: "Execution plan ready" })
              setTerminalLines(prev => [...prev, `📋 Execution plan generated: ${plan.length} top-level tasks`])

            } else if (data.type === "task_update") {
              // Update task status in plan
              const taskId = data.task_id
              const newStatus = data.status

              const updateTaskStatus = (tasks: TaskPlan[]): TaskPlan[] => {
                return tasks.map(task => {
                  if (task.id === taskId) {
                    return { ...task, status: newStatus }
                  }
                  if (task.subtasks) {
                    return { ...task, subtasks: updateTaskStatus(task.subtasks) }
                  }
                  return task
                })
              }

              setActiveTaskPlan(prev => updateTaskStatus(prev))
              setMessages(prev => prev.map(msg => {
                if (msg.id === assistantMessage.id && msg.taskPlan) {
                  return { ...msg, taskPlan: updateTaskStatus(msg.taskPlan) }
                }
                return msg
              }))

            } else if (data.type === "log") {
              const logName = data.tag && data.tag !== "info" && data.tag !== "log" ? data.tag : (data.message?.split(":")[0]?.slice(0, 60) || "Agent")
              appendToolActivity({ name: logName, status: data.level === "error" ? "error" : "done", message: data.message })
              appendStep({ name: logName, status: data.level === "error" ? "error" : "done", description: data.message })
              setTerminalLines(prev => [...prev, `[${data.level?.toUpperCase() || 'INFO'}] ${data.message}`])

            } else if (data.type === "debug_analysis") {
              // Intelligent error analysis from debugger
              const debugInfo = {
                errorType: data.error_type || "Unknown",
                errorMessage: data.error_message || "",
                filePath: data.file_path || "",
                lineNumber: data.line_number || 0,
                rootCause: data.root_cause || "",
                suggestedFix: data.suggested_fix || ""
              }

              // Add debug analysis to message
              setMessages(prev => prev.map(msg => {
                if (msg.id === assistantMessage.id) {
                  return { ...msg, debugAnalysis: debugInfo }
                }
                return msg
              }))

              setAgentState((prev) => ({ ...prev, status: "error", message: debugInfo.errorMessage || debugInfo.errorType, updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
              appendToolActivity({ name: "Recoverable error", status: "error", message: debugInfo.rootCause || debugInfo.errorMessage, target: debugInfo.filePath })
              appendStep({ name: "Analyzed error", status: "error", description: debugInfo.rootCause || debugInfo.errorMessage })
              setTerminalLines(prev => [
                ...prev,
                `🐛 Error Analysis: ${debugInfo.errorType}`,
                `   Root cause: ${debugInfo.rootCause}`,
                `   Suggested fix: ${debugInfo.suggestedFix}`
              ])

            } else if (data.type === "diff" || data.type === "patch_proposed") {
              const diffText = data.diff || ""
              const additions = diffText.split("\n").filter((line: string) => line.startsWith("+") && !line.startsWith("+++")).length
              const deletions = diffText.split("\n").filter((line: string) => line.startsWith("-") && !line.startsWith("---")).length
              const filesChanged = Array.isArray(data.files) ? data.files.length : undefined
              const fileStats = new Map<string, { additions: number; deletions: number }>()
              let currentFile = ""
              for (const line of diffText.split("\n")) {
                if (line.startsWith("diff --git ")) {
                  currentFile = line.split(" b/")[1] || line.split(" a/")[1] || ""
                  if (currentFile) fileStats.set(currentFile, { additions: 0, deletions: 0 })
                } else if (currentFile && line.startsWith("+") && !line.startsWith("+++")) {
                  fileStats.get(currentFile)!.additions += 1
                } else if (currentFile && line.startsWith("-") && !line.startsWith("---")) {
                  fileStats.get(currentFile)!.deletions += 1
                }
              }
              setLastDiffContent(diffText)

              // Parse and store diff for each file
              const newFileDiffs = new Map<string, string>()
              const lines = diffText.split("\n")
              let currentFileName = ""
              let currentFileDiff: string[] = []

              for (const line of lines) {
                if (line.startsWith("diff --git")) {
                  // Save previous file's diff
                  if (currentFileName && currentFileDiff.length > 0) {
                    newFileDiffs.set(currentFileName, currentFileDiff.join("\n"))
                  }
                  // Start new file
                  const match = line.match(/diff --git a\/(.+?) b\/(.+)/)
                  currentFileName = match ? match[2] : ""
                  currentFileDiff = [line]
                } else if (currentFileName) {
                  currentFileDiff.push(line)
                }
              }
              // Save last file
              if (currentFileName && currentFileDiff.length > 0) {
                newFileDiffs.set(currentFileName, currentFileDiff.join("\n"))
              }
              setFileDiffs(newFileDiffs)

              if (planMode === "autonomous") {
                setDiffStatus({ filename: "agent-patch.diff", status: "accepted", filesChanged, additions, deletions })
              } else {
                setDiffStatus({ filename: "agent-patch.diff", status: "proposed", filesChanged, additions, deletions })
              }
              appendToolActivity({ name: planMode === "autonomous" ? "Patch applied" : "Patch proposed", status: "done", message: `${filesChanged ?? 0} file(s), +${additions}/-${deletions}` })
              appendStep({ name: planMode === "autonomous" ? "Applied code changes" : "Prepared code changes", status: "done", description: `${filesChanged ?? 0} file(s), +${additions}/-${deletions}` })
              for (const [file, stats] of fileStats) {
                appendStep({ id: `patch-${file}`, name: file, status: "done", description: `+${stats.additions} −${stats.deletions}` })
              }
              setTerminalLines(prev => [...prev, `✔ Patch generated: ${(data.files || []).length} file(s) changed`])
              if (diffText) {
                setTerminalLines(prev => [...prev, ...diffText.split("\n").slice(0, 30)])
              }
              // Store diff content and trigger diff viewer if not autonomous
              if (planMode !== "autonomous") {
                setActiveDiffFile("agent-patch.diff")
              }
              
            } else if (data.type === "test_result") {
              const passed = data.success === true
              setTestStatus({ status: passed ? "passed" : "failed", command: data.command, message: data.message, passed: parseNumber(data.passed), failed: parseNumber(data.failed), durationMs: parseNumber(data.duration_ms ?? data.durationMs) })
              appendToolActivity({ name: "Test verification", status: passed ? "done" : "error", message: data.message || `Success: ${data.success}` })
              appendStep({ name: "Ran verification", status: passed ? "done" : "error", description: data.command || data.message || `Success: ${data.success}` })
              setTerminalLines(prev => [
                ...prev, 
                `[TEST] Run complete. Success: ${data.success}`,
              ])
              
            } else if (data.type === "agent_state") {
              setAgentState((prev) => ({
                ...prev,
                status: data.status || prev.status,
                phase: data.phase || prev.phase,
                message: data.message || data.detail || prev.message,
                updatedAt: data.updated_at || new Date().toISOString(),
                runtimeMs: parseNumber(data.runtime_ms ?? data.runtimeMs) ?? (startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs),
              }))
              if (data.phase) setPhaseStatus(data.phase, data.status === "error" ? "error" : data.status === "done" ? "done" : "running", data.message)

            } else if (data.type === "project_intelligence") {
              setProjectIntelligence((prev) => ({
                ...prev,
                status: data.status || prev.status || "unknown",
                workspacePath: data.workspace_path || data.workspacePath || prev.workspacePath,
                filesIndexed: parseNumber(data.files_indexed ?? data.filesIndexed) ?? prev.filesIndexed,
                linesIndexed: parseNumber(data.lines_indexed ?? data.linesIndexed) ?? prev.linesIndexed,
                symbols: parseNumber(data.symbols) ?? prev.symbols,
                complexityAvg: parseNumber(data.complexity_avg) ?? prev.complexityAvg,
                circularDependencies: parseNumber(data.circular_dependencies) ?? prev.circularDependencies,
                mostComplexFunctions: data.most_complex_functions || prev.mostComplexFunctions,
                cacheHitRate: parseNumber(data.cache_hit_rate ?? data.cacheHitRate) ?? prev.cacheHitRate,
                lastIndexedAt: data.last_indexed_at || data.lastIndexedAt || prev.lastIndexedAt,
                summary: data.summary || prev.summary,
              }))
              appendToolActivity({ name: "Project intelligence", status: data.status === "error" ? "error" : "done", message: data.summary || data.status })
              const wsPath = data.workspace_path || data.workspacePath || ""
              const projectName = wsPath ? wsPath.split(/[\\/]/).filter(Boolean).pop() || wsPath : "project"
              const filesCount = typeof data.files_indexed === "number" ? data.files_indexed : 0
              const linesCount = typeof data.lines_indexed === "number" ? data.lines_indexed : 0
              appendStep({
                name: `Explored ${filesCount} files, ${linesCount.toLocaleString()} lines`,
                status: data.status === "error" ? "error" : "done",
                description: projectName,
              })

            } else if (data.type === "tool_activity") {
              appendToolActivity({
                id: data.id,
                name: data.name || data.tool || "Tool activity",
                status: data.status || "running",
                message: data.message || data.detail,
                target: data.target || data.path,
                durationMs: parseNumber(data.duration_ms ?? data.durationMs),
              })
              appendStep({ id: data.id, name: data.name || data.tool || "Tool activity", status: data.status || "running", description: data.message || data.detail || data.target || data.path })

            } else if (data.type === "tool_call") {
              // Devin-style tool invocation display
              const toolLabels: Record<string, string> = {
                scan_workspace: "Scan workspace",
                read_file: "Read",
                write_file: "Edited",
                analyze_dependencies: "Analyze dependencies",
                memory_recall: "Memory recall",
                memory_store: "Memory store",
                llm_generate: "Thought",
                terminal: "Terminal",
                run_tests: "Run tests",
                search_code: "Search",
                git_diff: "Git diff",
              }
              const label = toolLabels[data.tool] || data.tool
              const target = data.target || ""
              const detail = data.detail || ""
              const linesChanged = data.lines_changed || 0
              const stepName = linesChanged > 0
                ? `${label} ${target} +${linesChanged}`
                : target
                  ? `${label} ${target}`
                  : label
              const stepDetail = detail || (data.status === "running" ? "Working..." : "Done")
              const stepId = `tool-call-${data.tool}-${target}`

              appendStep({
                id: stepId,
                name: stepName,
                status: data.status === "error" ? "error" : data.status === "running" ? "running" : "done",
                description: stepDetail,
              })
              appendToolActivity({
                id: stepId,
                name: label,
                status: data.status === "error" ? "error" : data.status === "running" ? "running" : "done",
                message: `${target} ${detail}`.trim(),
                target: target,
              })
              setTerminalLines(prev => [...prev, `[${label.toUpperCase()}] ${target} ${detail}`])

            } else if (data.type === "context_status") {
              setContextStatus({
                usedTokens: parseNumber(data.used_tokens ?? data.usedTokens),
                maxTokens: parseNumber(data.max_tokens ?? data.maxTokens),
                percent: parseNumber(data.percent ?? data.percentage),
                status: data.status || "unknown",
                cache: data.cache,
              })

            } else if (data.type === "cognitive_update") {
              setCognitiveState((prev: any) => ({
                ...prev,
                mode: data.mode || prev.mode,
                energy_ledger: data.energy_ledger || prev.energy_ledger,
                attractors: data.attractors || prev.attractors,
                sampled_matrix: data.sampled_matrix || prev.sampled_matrix || Array(16).fill(0).map(() => Array(16).fill(0))
              }))

            } else if (data.type === "runtime_hint" || data.type === "performance_hint") {
              const hint: RuntimeHint = { id: data.id || generateId(), label: data.label || data.name || "hint", value: String(data.value || data.message || ""), tone: data.tone || "neutral" }
              setRuntimeHints((prev) => [hint, ...prev.filter((item) => item.id !== hint.id)].slice(0, 6))

            } else if (data.type === "repo_selector") {
              // Repository selector card from agent
              const repoSelectorData = {
                prompt: data.prompt || "Выберите репозиторий:",
                repos: data.repos || []
              }

              // Store repo selector in message metadata
              setMessages(prev => prev.map(msg => {
                if (msg.id === assistantMessage.id) {
                  return {
                    ...msg,
                    content: msg.content + `\n\n__REPO_SELECTOR__${JSON.stringify(repoSelectorData)}__`
                  }
                }
                return msg
              }))

              appendToolActivity({ name: "Repository selection", status: "running", message: "Waiting for user to select repository" })
              appendStep({ id: "repo-selector", name: "Select repository", status: "running", description: repoSelectorData.prompt })

            } else if (data.type === "session_created") {
              // Backend created/updated session with auto-generated title
              const sessionTitle = data.title || "New Session"
              const sessionId = data.session_id || activeSessionId

              // Update session title in localStorage
              const storedSessions = localStorage.getItem("sharrowkin-sessions-list")
              if (storedSessions) {
                try {
                  const sessions = JSON.parse(storedSessions)
                  const existingIndex = sessions.findIndex((s: any) => s.id === sessionId)
                  if (existingIndex >= 0) {
                    sessions[existingIndex].label = sessionTitle
                  } else {
                    sessions.unshift({ id: sessionId, label: sessionTitle })
                  }
                  localStorage.setItem("sharrowkin-sessions-list", JSON.stringify(sessions))
                } catch (err) {
                  console.error("Failed to update session title:", err)
                }
              }

              setTerminalLines(prev => [...prev, `📝 Session: "${sessionTitle}"`])

            } else if (data.type === "content") {
              // Direct content from agent (e.g. conversational reply)
              fullResponse += data.content || ""
              setAssistantContent(extractFunctionCalls(fullResponse))
              
            } else if (data.type === "status") {
              if (data.status === "done") {
                updateSteps(currentSteps.map(s => ({ ...s, status: "done", description: "Finished." })))
                setAgentPhases((prev) => prev.map((phase) => ({ ...phase, status: phase.status === "error" ? "error" : "done", completedAt: phase.completedAt || new Date().toISOString() })))
                setAgentState((prev) => ({ ...prev, status: "done", message: "Autonomous run complete", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
                appendToolActivity({ name: "Autonomous run", status: "done", message: "Complete" })
                appendStep({ id: "run-complete", name: "Autonomous run complete", status: "done", description: "Ready for review" })
                setIsStreaming(false)
                setTerminalLines(prev => [...prev, `✔ Autonomous run complete.`])
                ws.close()
              } else if (data.status === "error" || data.status === "needs_key") {
                updateSteps(currentSteps.map(s => s.status === "running" ? { ...s, status: "error", description: data.status === "needs_key" ? "API key required" : "Error" } : s))
                setAgentState((prev) => ({ ...prev, status: "error", message: data.status === "needs_key" ? "API key required" : "Agent run needs attention", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
                setPhaseStatus(agentState.phase || "reason", "error", data.status)
                appendToolActivity({ name: "Agent status", status: "error", message: data.status })
                setIsStreaming(false)
                setTerminalLines(prev => [...prev, `✖ Status: ${data.status}`])
                ws.close()
              }
              
            } else if (data.type === "error") {
              updateSteps(currentSteps.map(s => s.status === "running" ? { ...s, status: "error", description: data.message } : s))
              setError(data.message)
              setAgentState((prev) => ({ ...prev, status: "error", message: data.message || "Agent error", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
              setPhaseStatus(agentState.phase || "reason", "error", data.message)
              appendToolActivity({ name: "Agent error", status: "error", message: data.message })
              setIsStreaming(false)
              setTerminalLines(prev => [...prev, `✖ Error: ${data.message}`])
              ws.close()
            }
          } catch (e) {
            console.error(e)
          }
        }
        
        ws.onerror = () => {
          setError("WebSocket error. Could not connect to backend.")
          setAgentState((prev) => ({ ...prev, status: "error", message: "Backend websocket unavailable", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
          appendToolActivity({ name: "WebSocket", status: "error", message: "Could not connect to backend" })
          setIsStreaming(false)
        }
        
        ws.onclose = () => {
          if (socketRef.current === ws) socketRef.current = null
          setIsStreaming(false)
        }
        
      } catch (err: any) {
        console.error(err)
        setError(err.message)
        setAgentState((prev) => ({ ...prev, status: "error", message: err.message || "Connection error", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
        updateSteps([
          { id: "step-1", name: "Connection Error", status: "error", description: "Could not connect to Python backend. Is it running?" }
        ])
        appendToolActivity({ name: "Connection error", status: "error", message: "Could not connect to Python backend" })
        setIsStreaming(false)
      }
    },
    [messages, isStreaming, selectedModel, appendToolActivity, setPhaseStatus, workspacePath, agentState.phase, planMode],
  )

  const retry = useCallback(() => {
    if (messages.length === 0) return
    const lastUserMessage = [...messages].reverse().find((m) => m.role === "user")
    if (lastUserMessage) {
      const index = messages.findIndex((m) => m.id === lastUserMessage.id)
      setMessages(messages.slice(0, index))
      setError(null)
      setTimeout(() => sendMessage(lastUserMessage.content, lastUserMessage.imageData), 100)
    }
  }, [messages, sendMessage])

  const stopStreaming = useCallback(() => {
    socketRef.current?.close()
    socketRef.current = null
    setAgentState((prev) => ({ ...prev, status: "stopped", message: "Run stopped by user", updatedAt: new Date().toISOString(), runtimeMs: startedAtRef.current ? Date.now() - startedAtRef.current : prev.runtimeMs }))
    appendToolActivity({ name: "Run stopped", status: "done", message: "Stopped by user" })
    setIsStreaming(false)
  }, [appendToolActivity])

  // Extract diff for specific file from full diff
  const getFileDiff = useCallback((filename: string, fullDiff: string): string => {
    if (!fullDiff) return ""

    const lines = fullDiff.split("\n")
    const fileDiffLines: string[] = []
    let inTargetFile = false

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i]

      // Check if this is the start of our target file
      if (line.startsWith("diff --git") && line.includes(filename)) {
        inTargetFile = true
        fileDiffLines.push(line)
        continue
      }

      // Check if we've moved to a different file
      if (line.startsWith("diff --git") && !line.includes(filename)) {
        if (inTargetFile) break // We've collected all lines for our file
        inTargetFile = false
        continue
      }

      // Collect lines while we're in the target file
      if (inTargetFile) {
        fileDiffLines.push(line)
      }
    }

    return fileDiffLines.join("\n")
  }, [])

  const clearChat = useCallback(() => {
    setMessages([])
    setError(null)
    resetAgentWorkspace()
    localStorage.removeItem(STORAGE_KEY)
  }, [STORAGE_KEY, resetAgentWorkspace])

  return (
    <div className="h-dvh bg-white flex overflow-hidden text-stone-900">
      {/* Left Sidebar */}
      <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />

      {/* Workspace Panel - opens when user clicks on edited file */}
      {workspacePanelOpen && workspaceFiles.length > 0 && (
        <WorkspacePanel
          files={workspaceFiles}
          onFileClick={(path) => {
            setSelectedFile(path)
            setActiveDiffFile(path)
          }}
          selectedFile={selectedFile}
          className="w-64 shrink-0"
        />
      )}

      {/* Main Workspace split */}
      <div className="flex-1 flex overflow-hidden relative">
        
        {/* Main Chat Area - Center */}
        <div className={cn("flex-1 flex flex-col relative min-w-0 transition-all duration-300 bg-white", activeDiffFile ? "max-w-[50%]" : "max-w-full")}>
          <div className="flex h-12 shrink-0 items-center justify-between px-5 text-[13px]">
            <div className="flex min-w-0 items-center gap-3">
              <span className="truncate font-normal text-stone-900">{workspacePath}</span>
              <span className="hidden rounded-full bg-stone-50 px-2 py-1 text-[12px] text-stone-500 sm:inline-flex">agent workspace</span>
            </div>
            <div className="flex items-center gap-1.5 text-stone-500">
              <Button
                onClick={clearChat}
                variant="ghost"
                size="icon"
                className="h-8 w-8 rounded-lg text-stone-500 hover:bg-stone-100 hover:text-stone-900"
                aria-label="Reset chat"
              >
                <MessageSquareDashed className="w-4 h-4" />
              </Button>
              <button onClick={() => setRightSidebarOpen(!rightSidebarOpen)} className="rounded-lg p-2 transition-colors hover:bg-stone-100" aria-label="Toggle right panel">
                <PanelRight size={16} strokeWidth={1.6} />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-hidden">
            <MessageList 
              messages={messages} 
              isStreaming={isStreaming} 
              error={error} 
              onRetry={retry} 
              isLoaded={isLoaded} 
              onOpenDiff={setActiveDiffFile}
            />
          </div>

          {/* Bottom Terminal Drag Drop Zone */}
          {isDraggingTerminal && terminalDock === "sidebar" && (
            <div 
              onDragOver={(e) => {
                e.preventDefault()
                e.dataTransfer.dropEffect = "move"
              }}
              onDrop={() => {
                setTerminalDock("bottom")
                setIsDraggingTerminal(false)
              }}
              className="mx-6 my-3 h-[180px] border border-dashed border-emerald-300/40 bg-emerald-50/5 rounded-2xl flex flex-col items-center justify-center gap-2.5 cursor-pointer transition-all hover:border-emerald-400/60 hover:bg-emerald-50/10 animate-pulse shrink-0"
            >
              <div className="w-10 h-10 rounded-full bg-emerald-50/60 flex items-center justify-center text-emerald-500 mb-1">
                <ArrowDownToLine size={18} strokeWidth={1.5} className="animate-bounce" />
              </div>
              <h4 className="text-[13px] font-medium text-emerald-800 font-sans">Drop here to Dock Terminal</h4>
              <p className="text-[11px] text-emerald-500/70 font-sans max-w-[240px] text-center leading-relaxed">
                Release your drag here to snap the terminal panel horizontally below the chat.
              </p>
            </div>
          )}

          {/* Bottom terminal dock */}
          {terminalDock === "bottom" && (
            <div 
              style={{ height: `${terminalHeight}px` }}
              className={cn(
                "border-t border-stone-100/40 bg-white px-6 pb-4 pt-5 shrink-0 relative flex flex-col min-h-0",
                isResizingTerminal ? "transition-none" : "transition-all duration-300 ease-in-out"
              )}
            >
              {/* Apple style horizontal resize bar on top edge */}
              <div 
                onMouseDown={handleTerminalResizeStart}
                className="absolute top-0 left-0 w-full h-1.5 cursor-row-resize hover:bg-stone-200/50 active:bg-stone-350/60 transition-colors z-50 flex items-center justify-center group"
                title="Drag top edge to resize terminal height"
              >
                <div className="h-[1.5px] w-12 bg-stone-200/40 group-hover:bg-stone-400/60 group-active:bg-stone-500 rounded-full transition-colors" />
              </div>

              <div className="flex-1 min-h-0 pt-1">
                <TerminalEmulator
                  terminalLines={terminalLines}
                  isRunningTask={isRunningTask}
                  currentInput={currentInput}
                  setCurrentInput={setCurrentInput}
                  onSubmitCommand={handleCommandSubmit}
                  runBuildCommand={runBuildCommand}
                  runTestCommand={runTestCommand}
                  clearTerminal={clearTerminal}
                  terminalDock={terminalDock}
                  setTerminalDock={setTerminalDock}
                  onDragStart={handleDragStart}
                  onDragEnd={handleDragEnd}
                />
              </div>
            </div>
          )}

          <div className="flex-shrink-0">
            <Composer
               onSend={sendMessage}
               onStop={stopStreaming}
               isStreaming={isStreaming}
               disabled={!!error}
               selectedModel={selectedModel}
               onModelChange={handleModelChange}
               planMode={planMode}
               onPlanModeChange={setPlanMode}
               bottomOffset={terminalDock === "bottom" ? (terminalHeight + 24) : (isDraggingTerminal && terminalDock === "sidebar") ? 204 : 24}
             />
          </div>
        </div>

        {/* Diff Viewer panel */}
        {activeDiffFile && (
          <div className="w-1/2 border-l border-stone-100/30 bg-white flex flex-col overflow-hidden animate-in slide-in-from-right duration-300">
            <DiffViewer
              filename={activeDiffFile}
              diffContent={fileDiffs.get(activeDiffFile) || getFileDiff(activeDiffFile, lastDiffContent)}
              onClose={() => setActiveDiffFile(null)}
              onAccept={() => {
                setDiffStatus((prev) => ({ ...prev, status: "accepted" }))
                setActiveDiffFile(null)
              }}
            />
          </div>
        )}
      </div>

      {/* Right Sidebar with Terminal/Logs/Info */}
      <RightSidebar 
        isOpen={rightSidebarOpen} 
        onToggle={() => setRightSidebarOpen(!rightSidebarOpen)} 
        terminalLines={terminalLines}
        isRunningTask={isRunningTask}
        currentInput={currentInput}
        setCurrentInput={setCurrentInput}
        onSubmitCommand={handleCommandSubmit}
        runBuildCommand={runBuildCommand}
        runTestCommand={runTestCommand}
        clearTerminal={clearTerminal}
        terminalDock={terminalDock}
        setTerminalDock={setTerminalDock}
        isDraggingTerminal={isDraggingTerminal}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        agentState={agentState}
        phases={agentPhases}
        projectIntelligence={projectIntelligence}
        toolActivity={toolActivity}
        contextStatus={contextStatus}
        runtimeHints={runtimeHints}
        diffStatus={diffStatus}
        testStatus={testStatus}
        selectedModel={selectedModel}
        backendUrl={BACKEND_URL}
        backendConnected={backendConnected}
        cognitiveState={cognitiveState}
        setCognitiveState={setCognitiveState}
        activeTaskPlan={activeTaskPlan}
      />
    </div>
  )
}

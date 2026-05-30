"use client"

import { useState, useEffect, Suspense } from "react"
import { useRouter } from "next/navigation"
import { Loader2, Clock, CheckCircle2, XCircle, Trash2, MessageSquare } from "lucide-react"
import { LeftSidebar } from "@/components/chat/left-sidebar"
import { toast } from "sonner"
import { cn } from "@/lib/utils"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

interface Session {
  id: string
  title: string
  created_at: string
  updated_at: string
  task: string
  status: "running" | "completed" | "failed"
  workspace_path: string
  model: string
  message_count: number
}

export default function DashboardPage() {
  const router = useRouter()
  const [sessions, setSessions] = useState<Session[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [leftSidebarOpen, setLeftSidebarOpen] = useState(true)

  useEffect(() => {
    // Import sessions from localStorage first, then fetch from backend
    const importAndFetch = async () => {
      // Get sessions from localStorage
      const storedSessions = localStorage.getItem("sharrowkin-sessions-list")
      if (storedSessions) {
        try {
          const localSessions = JSON.parse(storedSessions)
          if (localSessions.length > 0) {
            // Import to backend
            await fetch(`${BACKEND_URL}/api/sessions/import`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify(localSessions),
            })
          }
        } catch (err) {
          console.error("Failed to import sessions:", err)
        }
      }

      // Fetch all sessions from backend
      await fetchSessions()
    }

    importAndFetch()
  }, [])

  const fetchSessions = async () => {
    setIsLoading(true)
    try {
      const res = await fetch(`${BACKEND_URL}/api/sessions/`)
      if (res.ok) {
        const data = await res.json()
        setSessions(data.sessions || [])
      } else {
        toast.error("Failed to load sessions")
      }
    } catch (err) {
      console.error("Failed to fetch sessions:", err)
      toast.error("Failed to load sessions")
    } finally {
      setIsLoading(false)
    }
  }

  const handleDeleteSession = async (sessionId: string) => {
    if (!confirm("Delete this session?")) return

    try {
      const res = await fetch(`${BACKEND_URL}/api/sessions/${sessionId}`, {
        method: "DELETE",
      })
      if (res.ok) {
        setSessions(prev => prev.filter(s => s.id !== sessionId))
        toast.success("Session deleted")
      } else {
        toast.error("Failed to delete session")
      }
    } catch (err) {
      console.error("Failed to delete session:", err)
      toast.error("Failed to delete session")
    }
  }

  const handleOpenSession = (sessionId: string) => {
    router.push(`/chat?session=${sessionId}`)
  }

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMs / 3600000)
    const diffDays = Math.floor(diffMs / 86400000)

    if (diffMins < 1) return "Just now"
    if (diffMins < 60) return `${diffMins}m ago`
    if (diffHours < 24) return `${diffHours}h ago`
    if (diffDays < 7) return `${diffDays}d ago`
    return date.toLocaleDateString()
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "running":
        return <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
      case "completed":
        return <CheckCircle2 className="w-4 h-4 text-emerald-500" />
      case "failed":
        return <XCircle className="w-4 h-4 text-red-500" />
      default:
        return <Clock className="w-4 h-4 text-stone-400" />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case "running":
        return "bg-blue-50 text-blue-700 border-blue-200"
      case "completed":
        return "bg-emerald-50 text-emerald-700 border-emerald-200"
      case "failed":
        return "bg-red-50 text-red-700 border-red-200"
      default:
        return "bg-stone-50 text-stone-700 border-stone-200"
    }
  }

  return (
    <div className="h-full bg-background flex overflow-hidden">
      <Suspense>
        <LeftSidebar isOpen={leftSidebarOpen} onToggle={() => setLeftSidebarOpen(!leftSidebarOpen)} />
      </Suspense>

      <div className="flex-1 flex flex-col overflow-hidden bg-white font-sans relative z-10">
        {/* Header */}
        <header className="h-[52px] bg-white flex items-center justify-between px-5 shrink-0 border-b border-stone-100/50">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 text-stone-700 font-medium text-[13.5px]">
              <MessageSquare size={16} className="text-emerald-500" />
              <span>Sessions Dashboard</span>
            </div>
          </div>
        </header>

        {/* Main Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {isLoading ? (
            <div className="flex items-center justify-center h-64">
              <Loader2 className="w-6 h-6 animate-spin text-stone-400" />
            </div>
          ) : sessions.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-64 text-center">
              <MessageSquare className="w-12 h-12 text-stone-300 mb-3" />
              <p className="text-[14px] text-stone-500">No sessions yet</p>
              <p className="text-[12px] text-stone-400 mt-1">Start a conversation in Chat to create your first session</p>
            </div>
          ) : (
            <div className="max-w-4xl mx-auto space-y-3">
              {sessions.map((session) => (
                <div
                  key={session.id}
                  className="bg-white border border-stone-200/60 rounded-lg p-4 hover:border-stone-300 hover:shadow-sm transition-all cursor-pointer"
                  onClick={() => handleOpenSession(session.id)}
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        {getStatusIcon(session.status)}
                        <h3 className="text-[14px] font-medium text-stone-800 truncate">
                          {session.title}
                        </h3>
                        <span
                          className={cn(
                            "px-2 py-0.5 text-[10px] font-medium rounded-full border",
                            getStatusColor(session.status)
                          )}
                        >
                          {session.status}
                        </span>
                      </div>
                      <p className="text-[12px] text-stone-500 line-clamp-2 mb-2">
                        {session.task}
                      </p>
                      <div className="flex items-center gap-4 text-[11px] text-stone-400">
                        <span className="flex items-center gap-1">
                          <Clock size={11} />
                          {formatDate(session.updated_at)}
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageSquare size={11} />
                          {session.message_count} messages
                        </span>
                        <span className="text-stone-300">•</span>
                        <span>{session.model}</span>
                      </div>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation()
                        handleDeleteSession(session.id)
                      }}
                      className="p-2 text-stone-400 hover:text-red-500 hover:bg-red-50 rounded-md transition-colors"
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import { BookOpen, Bot, ChevronDown, GitPullRequest, LayoutPanelLeft, Menu, Plus, Search, Settings, Workflow, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { getAgentName } from "@/lib/persona-api"

interface LeftSidebarProps {
  isOpen: boolean
  onToggle: () => void
}

interface GitHubUser {
  login: string
  name: string
  avatar_url: string
}

const NAV_ITEMS = [
  { icon: Bot, label: "Chat", href: "/chat" },
  { icon: LayoutPanelLeft, label: "Dashboard", href: "/dashboard" },
  { icon: BookOpen, label: "Wiki", href: "/wiki" },
  { icon: GitPullRequest, label: "Review", href: "/review" },
  { icon: Workflow, label: "Workflow", href: "/workflow" },
]

export function LeftSidebar({ isOpen, onToggle }: LeftSidebarProps) {
  const pathname = usePathname()
  const router = useRouter()
  const searchParams = useSearchParams()
  const activeSessionId = searchParams?.get("session") || "session-1"
  const [agentName, setAgentName] = useState("Sharrowkin")
  const [sessions, setSessions] = useState<Array<{ id: string; label: string }>>([])
  const [recentOpen, setRecentOpen] = useState(true)
  const [sessionSearchOpen, setSessionSearchOpen] = useState(false)
  const [sessionSearch, setSessionSearch] = useState("")
  const [githubUser, setGithubUser] = useState<GitHubUser | null>(null)

  useEffect(() => {
    const fetchAgentName = async () => {
      try {
        const response = await getAgentName()
        setAgentName(response.agent_name)
      } catch {}
    }

    fetchAgentName()
    window.addEventListener("persona-changed", fetchAgentName)
    return () => window.removeEventListener("persona-changed", fetchAgentName)
  }, [])

  useEffect(() => {
    const userStr = localStorage.getItem("github_user")
    if (userStr) {
      try {
        setGithubUser(JSON.parse(userStr))
      } catch (err) {
        console.error("Failed to parse GitHub user:", err)
      }
    }
  }, [])

  useEffect(() => {
    const storedSessions = localStorage.getItem("sharrowkin-sessions-list")
    if (storedSessions) {
      setSessions(JSON.parse(storedSessions))
      return
    }

    const defaultSessions = [{ id: "session-1", label: "New agent session" }]
    localStorage.setItem("sharrowkin-sessions-list", JSON.stringify(defaultSessions))
    setSessions(defaultSessions)
  }, [])

  const handleNewChat = useCallback(() => {
    const newId = `session-${Date.now()}`
    const nextSession = { id: newId, label: `New agent session ${sessions.length + 1}` }
    const nextSessions = [nextSession, ...sessions]
    localStorage.setItem("sharrowkin-sessions-list", JSON.stringify(nextSessions))
    setSessions(nextSessions)
    router.push(`/chat?session=${newId}`)
  }, [router, sessions])

  return (
    <>
      <button
        onClick={onToggle}
        className="fixed left-3 top-3 z-50 rounded-lg p-2 text-stone-500 transition-colors hover:bg-stone-100 lg:hidden"
        aria-label="Toggle sidebar"
      >
        {isOpen ? <X strokeWidth={1.7} size={18} /> : <Menu strokeWidth={1.7} size={18} />}
      </button>

      <aside
        className={cn(
          "fixed lg:relative z-40 h-full shrink-0 overflow-hidden bg-[#f7f7f7] text-stone-700 transition-all duration-300 ease-out",
          isOpen ? "w-[296px]" : "w-0",
        )}
      >
        <div className="flex h-full flex-col">
          <div className="flex h-12 items-center justify-between px-3">
            {githubUser ? (
              <div className="flex min-w-0 items-center gap-2 px-1.5 py-1 text-left">
                <img src={githubUser.avatar_url} alt={githubUser.login} className="h-5 w-5 shrink-0 rounded-full" />
                <span className="truncate text-[13px] font-medium text-stone-900">@{githubUser.login}</span>
              </div>
            ) : (
              <div className="flex min-w-0 items-center gap-2 px-1.5 py-1 text-left">
                <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded bg-stone-200 text-[11px] font-medium text-stone-600">D</span>
                <span className="truncate text-[13px] font-medium text-stone-900">Local workspace</span>
              </div>
            )}
            <button onClick={onToggle} className="rounded-md p-1.5 text-stone-500 transition-colors hover:bg-stone-200/50" aria-label="Collapse sidebar">
              <LayoutPanelLeft size={16} strokeWidth={1.5} />
            </button>
          </div>

          <nav className="px-2.5 py-2">
            <div className="space-y-0.5">
              {NAV_ITEMS.map(({ icon: Icon, label, href }) => {
                const active = href === "/chat"
                  ? pathname?.startsWith("/chat")
                  : pathname?.startsWith(href)
                return (
                  <Link
                    key={label}
                    href={href === "/chat" ? `/chat?session=${activeSessionId}` : href}
                    className={cn(
                      "group flex h-8 items-center gap-2.5 rounded-md px-2 text-[13px] font-normal transition-colors",
                      active
                        ? "bg-stone-200/60 text-stone-950"
                        : "text-stone-500 hover:bg-stone-200/45 hover:text-stone-950",
                    )}
                  >
                    <Icon size={15} strokeWidth={1.65} className={active ? "text-stone-900" : "text-stone-500"} />
                    <span className="flex-1">{label}</span>
                  </Link>
                )
              })}
            </div>
          </nav>

          <div className="mt-3 flex-1 overflow-y-auto px-2.5 no-scrollbar">
            <div className="mb-2 flex items-center justify-between px-2">
              <button onClick={() => setRecentOpen((value) => !value)} className="flex items-center gap-1 text-[12px] font-normal text-stone-500 transition-colors hover:text-stone-800">
                <ChevronDown size={13} strokeWidth={1.7} className={cn("text-stone-400 transition-transform duration-200", recentOpen ? "" : "-rotate-90")} />
                Recent
              </button>
              <div className="flex items-center gap-1 text-stone-400">
                <button onClick={() => setSessionSearchOpen((value) => !value)} className="rounded p-1 transition-colors hover:bg-stone-200/50 hover:text-stone-700" aria-label="Search sessions">
                  <Search size={14} strokeWidth={1.6} />
                </button>
                <button onClick={handleNewChat} className="rounded p-1 transition-colors hover:bg-stone-200/50 hover:text-stone-700" aria-label="New session">
                  <Plus size={15} strokeWidth={1.6} />
                </button>
              </div>
            </div>

            {sessionSearchOpen && (
              <input
                value={sessionSearch}
                onChange={(event) => setSessionSearch(event.target.value)}
                autoFocus
                placeholder="Search sessions"
                className="mb-2 w-full rounded-md bg-white px-2.5 py-1.5 text-[12.5px] text-stone-800 outline-none ring-1 ring-stone-200 placeholder:text-stone-400"
              />
            )}

            {recentOpen && (
              <div className="space-y-0.5">
                {sessions.filter((session) => session.label.toLowerCase().includes(sessionSearch.toLowerCase())).map((session) => {
                  const active = activeSessionId === session.id
                  return (
                    <button
                      key={session.id}
                      onClick={() => router.push(`/chat?session=${session.id}`)}
                      className={cn(
                        "w-full rounded-md px-2.5 py-2 text-left transition-colors",
                        active ? "bg-stone-200/70" : "hover:bg-stone-200/45",
                      )}
                    >
                      <div className="truncate text-[13px] font-normal text-stone-800">{session.label}</div>
                      <div className="mt-0.5 flex items-center gap-1.5 text-[12px] text-stone-500">
                        <span>{active ? "Active session" : "Local session"}</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            )}

            {/* Workflow Status Section */}
            <div className="mt-6 px-2">
              <div className="text-[12px] font-normal text-stone-500 mb-2">Workflow</div>
              <div className="space-y-2">
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-stone-600">Status</span>
                  <span className="text-emerald-600 font-medium">Ready</span>
                </div>
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-stone-600">Files indexed</span>
                  <span className="text-stone-700 font-mono">—</span>
                </div>
                <div className="flex items-center justify-between text-[12px]">
                  <span className="text-stone-600">Last sync</span>
                  <span className="text-stone-500 font-mono text-[11px]">—</span>
                </div>
              </div>
            </div>
          </div>

          <div className="flex items-center justify-between px-3 py-3">
            <Link href="/settings" className="flex h-8 items-center gap-2 rounded-md px-2 text-[13px] text-stone-700 transition-colors hover:bg-stone-200/50">
              <Settings size={15} strokeWidth={1.65} />
              Settings
            </Link>
            <span className="rounded-full px-2 py-1 text-[11px] text-stone-400">{agentName}</span>
          </div>

          {!githubUser && (
            <div className="px-3 pb-3">
              <Link
                href="/settings?tab=github"
                className="flex items-center justify-center gap-2 rounded-lg bg-blue-600 px-3 py-2 text-[13px] font-medium text-white transition-colors hover:bg-blue-700"
              >
                Connect GitHub
              </Link>
            </div>
          )}
        </div>
      </aside>

      {isOpen && <div className="fixed inset-0 z-30 bg-stone-900/5 backdrop-blur-[1px] lg:hidden" onClick={onToggle} />}
    </>
  )
}

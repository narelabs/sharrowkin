"use client"

import { useState, useEffect } from "react"
import { Github, LogOut, GitBranch, GitPullRequest, FileText, CheckCircle2, Loader2 } from "lucide-react"

interface GitHubUser {
  login: string
  name: string
  avatar_url: string
  email: string
}

interface GitHubRepo {
  id: number
  name: string
  full_name: string
  private: boolean
  default_branch: string
}

export function GitHubSettings() {
  const [isConnected, setIsConnected] = useState(false)
  const [user, setUser] = useState<GitHubUser | null>(null)
  const [repos, setRepos] = useState<GitHubRepo[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>("")
  const [defaultBranch, setDefaultBranch] = useState("main")
  const [autoCommit, setAutoCommit] = useState(true)
  const [commitTemplate, setCommitTemplate] = useState("feat: {description}\n\nCo-Authored-By: Sharrowkin Agent <agent@sharrowkin.ai>")
  const [prTemplate, setPrTemplate] = useState("## Summary\n{summary}\n\n## Changes\n{changes}\n\n## Test Plan\n{test_plan}")
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const token = localStorage.getItem("github_token")
    const savedUser = localStorage.getItem("github_user")

    if (token && savedUser) {
      setIsConnected(true)
      setUser(JSON.parse(savedUser))
      loadRepos(token)
    }

    const savedRepo = localStorage.getItem("github_selected_repo")
    const savedBranch = localStorage.getItem("github_default_branch")
    const savedAutoCommit = localStorage.getItem("github_auto_commit")
    const savedCommitTemplate = localStorage.getItem("github_commit_template")
    const savedPrTemplate = localStorage.getItem("github_pr_template")

    if (savedRepo) setSelectedRepo(savedRepo)
    if (savedBranch) setDefaultBranch(savedBranch)
    if (savedAutoCommit) setAutoCommit(savedAutoCommit === "true")
    if (savedCommitTemplate) setCommitTemplate(savedCommitTemplate)
    if (savedPrTemplate) setPrTemplate(savedPrTemplate)
  }, [])

  const loadRepos = async (token: string) => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
      const response = await fetch(`${backendUrl}/api/github/repos`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (response.ok) {
        const data = await response.json()
        setRepos(data.repos || [])
      }
    } catch (err) {
      console.error("Failed to load repos:", err)
    }
  }

  const handleConnect = async () => {
    setLoading(true)
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
      const response = await fetch(`${backendUrl}/api/github/oauth/authorize`)

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const data = await response.json()

      if (data.status === "error") {
        alert(data.message)
        setLoading(false)
        return
      }

      localStorage.setItem("github_oauth_state", data.state)
      window.location.href = data.url  // Fixed: was data.authorization_url
    } catch (err) {
      console.error("Failed to start OAuth:", err)
      alert("Failed to connect to GitHub. Make sure backend is running and GitHub OAuth is configured.")
      setLoading(false)
    }
  }

  const handleDisconnect = () => {
    localStorage.removeItem("github_token")
    localStorage.removeItem("github_user")
    localStorage.removeItem("github_selected_repo")
    setIsConnected(false)
    setUser(null)
    setRepos([])
    setSelectedRepo("")
  }

  const handleSaveSettings = () => {
    localStorage.setItem("github_selected_repo", selectedRepo)
    localStorage.setItem("github_default_branch", defaultBranch)
    localStorage.setItem("github_auto_commit", autoCommit.toString())
    localStorage.setItem("github_commit_template", commitTemplate)
    localStorage.setItem("github_pr_template", prTemplate)
  }

  useEffect(() => {
    if (isConnected) {
      handleSaveSettings()
    }
  }, [selectedRepo, defaultBranch, autoCommit, commitTemplate, prTemplate])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-stone-800">GitHub Integration</h3>
          <p className="text-sm text-stone-600 mt-1">Connect your GitHub account for repository operations</p>
        </div>
        {isConnected && user && (
          <div className="flex items-center gap-3">
            <img src={user.avatar_url} alt={user.login} className="w-10 h-10 rounded-full" />
            <div className="text-right">
              <p className="text-sm font-medium text-stone-800">{user.name || user.login}</p>
              <p className="text-xs text-stone-500">@{user.login}</p>
            </div>
          </div>
        )}
      </div>

      {!isConnected ? (
        <button
          onClick={handleConnect}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded-lg hover:bg-stone-800 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Connecting...
            </>
          ) : (
            <>
              <Github className="w-4 h-4" />
              Connect GitHub
            </>
          )}
        </button>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-2 px-4 py-2 bg-green-50 border border-green-200 rounded-lg">
            <CheckCircle2 className="w-4 h-4 text-green-600" />
            <span className="text-sm text-green-700">Connected to GitHub</span>
            <button
              onClick={handleDisconnect}
              className="ml-auto flex items-center gap-1 text-xs text-red-600 hover:text-red-700"
            >
              <LogOut className="w-3 h-3" />
              Disconnect
            </button>
          </div>

          <div className="space-y-3">
            <label className="block">
              <span className="text-sm font-medium text-stone-700 flex items-center gap-2">
                <GitBranch className="w-4 h-4" />
                Default Repository
              </span>
              <select
                value={selectedRepo}
                onChange={(e) => setSelectedRepo(e.target.value)}
                className="mt-1 w-full px-3 py-2 bg-white border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a repository</option>
                {repos.map((repo) => (
                  <option key={repo.id} value={repo.full_name}>
                    {repo.full_name} {repo.private ? "(Private)" : "(Public)"}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm font-medium text-stone-700">Default Branch</span>
              <input
                type="text"
                value={defaultBranch}
                onChange={(e) => setDefaultBranch(e.target.value)}
                placeholder="main"
                className="mt-1 w-full px-3 py-2 bg-white border border-stone-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </label>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={autoCommit}
                onChange={(e) => setAutoCommit(e.target.checked)}
                className="w-4 h-4 text-blue-600 border-stone-300 rounded focus:ring-blue-500"
              />
              <span className="text-sm text-stone-700">Auto-commit changes after successful execution</span>
            </label>

            <label className="block">
              <span className="text-sm font-medium text-stone-700 flex items-center gap-2">
                <FileText className="w-4 h-4" />
                Commit Message Template
              </span>
              <textarea
                value={commitTemplate}
                onChange={(e) => setCommitTemplate(e.target.value)}
                rows={3}
                className="mt-1 w-full px-3 py-2 bg-white border border-stone-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="feat: {description}"
              />
              <p className="mt-1 text-xs text-stone-500">
                Available variables: {"{description}"}, {"{files}"}, {"{timestamp}"}
              </p>
            </label>

            <label className="block">
              <span className="text-sm font-medium text-stone-700 flex items-center gap-2">
                <GitPullRequest className="w-4 h-4" />
                Pull Request Template
              </span>
              <textarea
                value={prTemplate}
                onChange={(e) => setPrTemplate(e.target.value)}
                rows={6}
                className="mt-1 w-full px-3 py-2 bg-white border border-stone-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder="## Summary&#10;{summary}"
              />
              <p className="mt-1 text-xs text-stone-500">
                Available variables: {"{summary}"}, {"{changes}"}, {"{test_plan}"}
              </p>
            </label>
          </div>
        </div>
      )}
    </div>
  )
}

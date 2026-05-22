"use client"

import { useEffect, useState } from "react"
import { AlertCircle, Github, Loader2, FolderGit2 } from "lucide-react"
import { useRouter } from "next/navigation"

interface GitHubStatus {
  connected: boolean
  user?: string
  repository?: {
    url: string
    branch: string
    clean: boolean
  } | null
  message: string
}

export function GitHubGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [status, setStatus] = useState<GitHubStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [initializingRepo, setInitializingRepo] = useState(false)

  useEffect(() => {
    checkGitHubStatus()
  }, [])

  const checkGitHubStatus = async () => {
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

      // Get token from localStorage and send to backend
      const token = localStorage.getItem("github_token")

      // If we have a token, send it to backend to update SETTINGS
      if (token) {
        try {
          await fetch(`${backendUrl}/api/settings`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ github_token: token }),
          })
        } catch (err) {
          console.error("Failed to sync token to backend:", err)
        }
      }

      const response = await fetch(`${backendUrl}/api/github/status`)

      if (!response.ok) {
        console.error(`GitHub status check failed: HTTP ${response.status}`)
        setStatus({
          connected: false,
          repository: null,
          message: "Cannot connect to backend. Make sure backend is running on http://127.0.0.1:8000"
        })
        setLoading(false)
        return
      }

      const data = await response.json()
      setStatus(data)
    } catch (err) {
      console.error("Failed to check GitHub status:", err)
      setStatus({
        connected: false,
        repository: null,
        message: "Cannot connect to backend. Make sure backend is running."
      })
    } finally {
      setLoading(false)
    }
  }

  const handleInitRepo = async () => {
    const workspacePath = localStorage.getItem("sharrowkin-workspace-path")
    if (!workspacePath) {
      alert("Please set workspace path in Settings first")
      router.push("/settings")
      return
    }

    const repoUrl = prompt("Enter GitHub repository URL (e.g., https://github.com/user/repo.git):")
    if (!repoUrl) return

    setInitializingRepo(true)
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
      const response = await fetch(`${backendUrl}/api/github/init-repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          workspace_path: workspacePath,
          repo_url: repoUrl,
        }),
      })

      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || "Failed to initialize repository")
      }

      await checkGitHubStatus()
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to initialize repository")
    } finally {
      setInitializingRepo(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-stone-50 to-stone-100">
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="w-8 h-8 text-stone-400 animate-spin" />
          <p className="text-sm text-stone-600">Checking GitHub connection...</p>
        </div>
      </div>
    )
  }

  if (!status?.connected) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-stone-50 to-stone-100">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-red-50 rounded-full flex items-center justify-center">
              <AlertCircle className="w-8 h-8 text-red-500" />
            </div>
            <h2 className="text-xl font-semibold text-stone-800">GitHub Connection Required</h2>
            <p className="text-sm text-stone-600 text-center">
              Sharrowkin Agent requires GitHub connection to work. Please connect your GitHub account in Settings.
            </p>
            <p className="text-xs text-stone-500 text-center mt-2">{status?.message}</p>
            <button
              onClick={() => router.push("/settings?tab=github")}
              className="flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded-lg hover:bg-stone-800 transition-colors"
            >
              <Github className="w-4 h-4" />
              Go to Settings
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (!status?.repository) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-stone-50 to-stone-100">
        <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
          <div className="flex flex-col items-center gap-4">
            <div className="w-16 h-16 bg-yellow-50 rounded-full flex items-center justify-center">
              <FolderGit2 className="w-8 h-8 text-yellow-500" />
            </div>
            <h2 className="text-xl font-semibold text-stone-800">Repository Not Configured</h2>
            <p className="text-sm text-stone-600 text-center">
              Your workspace is not connected to a git repository. Initialize a repository to start working.
            </p>
            <p className="text-xs text-stone-500 text-center mt-2">{status?.message}</p>
            <div className="flex gap-3 mt-2">
              <button
                onClick={handleInitRepo}
                disabled={initializingRepo}
                className="flex items-center gap-2 px-4 py-2 bg-stone-900 text-white rounded-lg hover:bg-stone-800 transition-colors disabled:opacity-50"
              >
                {initializingRepo ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Initializing...
                  </>
                ) : (
                  <>
                    <FolderGit2 className="w-4 h-4" />
                    Initialize Repository
                  </>
                )}
              </button>
              <button
                onClick={() => router.push("/settings")}
                className="px-4 py-2 bg-stone-100 text-stone-700 rounded-lg hover:bg-stone-200 transition-colors"
              >
                Settings
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return <>{children}</>
}

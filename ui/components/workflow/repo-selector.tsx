"use client"

import { useState, useEffect } from "react"
import { Github, Loader2, FolderGit2, ChevronDown } from "lucide-react"

interface GitHubRepo {
  id: number
  name: string
  full_name: string
  private: boolean
  description: string
  html_url: string
  default_branch: string
  language: string
  stargazers_count: number
  updated_at: string
}

interface RepoSelectorProps {
  onSelectRepo: (repo: GitHubRepo) => void
  selectedRepo: GitHubRepo | null
}

export function RepoSelector({ onSelectRepo, selectedRepo }: RepoSelectorProps) {
  const [repos, setRepos] = useState<GitHubRepo[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isOpen, setIsOpen] = useState(false)
  const [githubConnected, setGithubConnected] = useState(false)

  useEffect(() => {
    loadRepos()
  }, [])

  const loadRepos = async () => {
    setIsLoading(true)
    try {
      const token = localStorage.getItem("github_token")
      if (!token) {
        setGithubConnected(false)
        setIsLoading(false)
        return
      }

      setGithubConnected(true)
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
    } finally {
      setIsLoading(false)
    }
  }

  if (!githubConnected) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-4 flex items-start gap-3">
        <Github className="w-5 h-5 text-amber-600 mt-0.5" />
        <div>
          <h3 className="text-sm font-medium text-amber-900">GitHub Not Connected</h3>
          <p className="text-xs text-amber-700 mt-1">
            Connect your GitHub account in Settings to browse repositories.
          </p>
          <a
            href="/settings?tab=github"
            className="inline-block mt-2 text-xs font-medium text-amber-700 hover:text-amber-900 underline"
          >
            Go to Settings →
          </a>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="bg-white border border-stone-200 rounded-lg p-4 flex items-center justify-center gap-2">
        <Loader2 className="w-4 h-4 animate-spin text-stone-400" />
        <span className="text-sm text-stone-500">Loading repositories...</span>
      </div>
    )
  }

  return (
    <div className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full bg-white border border-stone-200 rounded-lg p-3 flex items-center justify-between hover:border-stone-300 transition-colors"
      >
        <div className="flex items-center gap-3">
          <FolderGit2 className="w-5 h-5 text-emerald-600" />
          <div className="text-left">
            {selectedRepo ? (
              <>
                <div className="text-sm font-medium text-stone-900">{selectedRepo.full_name}</div>
                <div className="text-xs text-stone-500 mt-0.5">
                  {selectedRepo.language && <span className="mr-2">{selectedRepo.language}</span>}
                  {selectedRepo.private ? "Private" : "Public"}
                </div>
              </>
            ) : (
              <div className="text-sm text-stone-500">Select a repository</div>
            )}
          </div>
        </div>
        <ChevronDown className={`w-4 h-4 text-stone-400 transition-transform ${isOpen ? "rotate-180" : ""}`} />
      </button>

      {isOpen && (
        <>
          <div className="fixed inset-0 z-10" onClick={() => setIsOpen(false)} />
          <div className="absolute top-full left-0 right-0 mt-2 bg-white border border-stone-200 rounded-lg shadow-lg max-h-[400px] overflow-y-auto z-20">
            {repos.length === 0 ? (
              <div className="p-4 text-center text-sm text-stone-500">No repositories found</div>
            ) : (
              <div className="divide-y divide-stone-100">
                {repos.map((repo) => (
                  <button
                    key={repo.id}
                    onClick={() => {
                      onSelectRepo(repo)
                      setIsOpen(false)
                    }}
                    className="w-full text-left p-3 hover:bg-stone-50 transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="text-sm font-medium text-stone-900 truncate">{repo.full_name}</div>
                        {repo.description && (
                          <div className="text-xs text-stone-500 mt-1 line-clamp-2">{repo.description}</div>
                        )}
                        <div className="flex items-center gap-3 mt-2 text-xs text-stone-400">
                          {repo.language && <span>{repo.language}</span>}
                          <span>{repo.private ? "Private" : "Public"}</span>
                          {repo.stargazers_count > 0 && <span>⭐ {repo.stargazers_count}</span>}
                        </div>
                      </div>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}

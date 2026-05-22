"use client"

import { useState } from "react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import { ScrollArea } from "@/components/ui/scroll-area"
import { Lock, Globe, Code2, Star } from "lucide-react"

interface Repo {
  id: string
  name: string
  full_name: string
  description: string
  language: string
  private: boolean
  url: string
  stars?: number
}

interface RepoSelectorCardProps {
  prompt: string
  repos: Repo[]
  onSelect: (repo: Repo) => void
}

export function RepoSelectorCard({ prompt, repos, onSelect }: RepoSelectorCardProps) {
  const [selectedRepo, setSelectedRepo] = useState<string | null>(null)

  const handleSelect = (repo: Repo) => {
    setSelectedRepo(repo.id)
    onSelect(repo)
  }

  return (
    <Card className="w-full max-w-2xl mx-auto my-4 border-blue-200 bg-blue-50/50">
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Code2 className="h-5 w-5 text-blue-600" />
          {prompt}
        </CardTitle>
        <CardDescription>
          Выберите репозиторий для работы
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ScrollArea className="h-[400px] pr-4">
          <div className="space-y-2">
            {repos.map((repo) => (
              <button
                key={repo.id}
                onClick={() => handleSelect(repo)}
                className={`w-full text-left p-4 rounded-lg border-2 transition-all hover:border-blue-400 hover:bg-blue-50 ${
                  selectedRepo === repo.id
                    ? "border-blue-500 bg-blue-100"
                    : "border-gray-200 bg-white"
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="font-semibold text-sm truncate">
                        {repo.full_name}
                      </h3>
                      {repo.private ? (
                        <Lock className="h-3 w-3 text-gray-500 flex-shrink-0" />
                      ) : (
                        <Globe className="h-3 w-3 text-gray-500 flex-shrink-0" />
                      )}
                    </div>
                    {repo.description && (
                      <p className="text-xs text-gray-600 line-clamp-2 mb-2">
                        {repo.description}
                      </p>
                    )}
                    <div className="flex items-center gap-2 flex-wrap">
                      {repo.language && (
                        <Badge variant="secondary" className="text-xs">
                          {repo.language}
                        </Badge>
                      )}
                      {repo.private ? (
                        <Badge variant="outline" className="text-xs">
                          Private
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-xs">
                          Public
                        </Badge>
                      )}
                      {repo.stars !== undefined && repo.stars > 0 && (
                        <div className="flex items-center gap-1 text-xs text-gray-500">
                          <Star className="h-3 w-3" />
                          {repo.stars}
                        </div>
                      )}
                    </div>
                  </div>
                  {selectedRepo === repo.id && (
                    <div className="flex-shrink-0">
                      <div className="h-6 w-6 rounded-full bg-blue-500 flex items-center justify-center">
                        <svg
                          className="h-4 w-4 text-white"
                          fill="none"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth="2"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                        >
                          <path d="M5 13l4 4L19 7" />
                        </svg>
                      </div>
                    </div>
                  )}
                </div>
              </button>
            ))}
          </div>
        </ScrollArea>
      </CardContent>
    </Card>
  )
}

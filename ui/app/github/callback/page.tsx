import { Suspense } from "react"
import { GitHubOAuthCallback } from "@/components/github/oauth-callback"

export default function GitHubCallbackPage() {
  return (
    <Suspense fallback={<div className="flex items-center justify-center min-h-screen">Loading...</div>}>
      <GitHubOAuthCallback />
    </Suspense>
  )
}

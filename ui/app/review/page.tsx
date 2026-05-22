import { ReviewShell } from "@/components/chat/review-shell"
import { GitHubGuard } from "@/components/chat/github-guard"
import type { Metadata } from "next"
import { Suspense } from "react"

export const metadata: Metadata = {
  title: "Review - sharrowkin",
  description: "Code Review and Pull Requests",
}

export default function ReviewPage() {
  return (
    <Suspense>
      <GitHubGuard>
        <ReviewShell />
      </GitHubGuard>
    </Suspense>
  )
}

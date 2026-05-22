import { WikiShell } from "@/components/chat/wiki-shell"
import { GitHubGuard } from "@/components/chat/github-guard"
import type { Metadata } from "next"
import { Suspense } from "react"

export const metadata: Metadata = {
  title: "Wiki - sharrowkin",
  description: "Project Knowledge Base",
}

export default function WikiPage() {
  return (
    <Suspense>
      <GitHubGuard>
        <WikiShell />
      </GitHubGuard>
    </Suspense>
  )
}

import { ChatShell } from "@/components/chat/chat-shell"
// import { GitHubGuard } from "@/components/chat/github-guard"
import type { Metadata } from "next"
import { Suspense } from "react"

export const metadata: Metadata = {
  title: "Chat - AI Assistant",
  description: "Chat with our AI assistant powered by Sharrowkin",
}

export default function ChatPage() {
  return (
    // Temporarily disabled GitHubGuard for development
    // <GitHubGuard>
      <Suspense>
        <ChatShell />
      </Suspense>
    // </GitHubGuard>
  )
}

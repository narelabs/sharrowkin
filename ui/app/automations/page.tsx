import { AutomationsShell } from "@/components/chat/automations-shell"
import type { Metadata } from "next"
import { Suspense } from "react"

export const metadata: Metadata = {
  title: "Automations - sharrowkin",
  description: "Manage autonomous agents and workflows",
}

export default function AutomationsPage() {
  return (
    <Suspense>
      <AutomationsShell />
    </Suspense>
  )
}

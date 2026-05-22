import { AutomationsShell } from "@/components/chat/automations-shell"
import type { Metadata } from "next"
import { Suspense } from "react"

export const metadata: Metadata = {
  title: "Autonomous - sharrowkin",
  description: "Launch and monitor autonomous agent runs",
}

export default function AutonomousPage() {
  return (
    <Suspense>
      <AutomationsShell />
    </Suspense>
  )
}

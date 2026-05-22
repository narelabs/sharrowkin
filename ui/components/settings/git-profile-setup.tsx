"use client"

import { useEffect, useState } from "react"
import { CheckCircle2, Github, Loader2, Terminal } from "lucide-react"

export function GitProfileSetup() {
  const [status, setStatus] = useState<"idle" | "loading" | "success" | "error">("idle")
  const [message, setMessage] = useState("")
  const [config, setConfig] = useState<{ "user.name": string; "user.email": string } | null>(null)

  const handleSetup = async () => {
    setStatus("loading")
    try {
      const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
      const response = await fetch(`${backendUrl}/api/github/setup-agent-profile`, {
        method: "POST",
      })

      if (!response.ok) {
        throw new Error("Failed to setup git profile")
      }

      const data = await response.json()
      setMessage(data.message)
      setConfig(data.config)
      setStatus("success")
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Unknown error")
      setStatus("error")
    }
  }

  return (
    <div className="rounded-2xl bg-stone-50/80 p-5">
      <div className="mb-5 flex items-center gap-2">
        <Terminal size={16} strokeWidth={1.6} className="text-stone-500" />
        <div>
          <div className="text-[14px] font-normal text-stone-900">Git Profile for Agent</div>
          <div className="text-[12px] text-stone-500">Configure git identity for commits made by Sharrowkin Agent</div>
        </div>
      </div>

      {status === "idle" && (
        <button
          onClick={handleSetup}
          className="rounded-lg bg-stone-900 px-4 py-2 text-[13px] text-white transition-colors hover:bg-stone-800"
        >
          Setup Git Profile
        </button>
      )}

      {status === "loading" && (
        <div className="flex items-center gap-2 text-[13px] text-stone-600">
          <Loader2 className="w-4 h-4 animate-spin" />
          Setting up git profile...
        </div>
      )}

      {status === "success" && config && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-[13px] text-green-700">
            <CheckCircle2 className="w-4 h-4" />
            {message}
          </div>
          <div className="rounded-lg bg-white p-3 space-y-2">
            <div className="text-[12px]">
              <span className="text-stone-500">user.name:</span>
              <span className="ml-2 font-mono text-stone-800">{config["user.name"]}</span>
            </div>
            <div className="text-[12px]">
              <span className="text-stone-500">user.email:</span>
              <span className="ml-2 font-mono text-stone-800">{config["user.email"]}</span>
            </div>
          </div>
          <button
            onClick={() => setStatus("idle")}
            className="text-[12px] text-blue-600 hover:underline"
          >
            Reconfigure
          </button>
        </div>
      )}

      {status === "error" && (
        <div className="space-y-2">
          <div className="text-[13px] text-red-700">{message}</div>
          <button
            onClick={() => setStatus("idle")}
            className="text-[12px] text-blue-600 hover:underline"
          >
            Try again
          </button>
        </div>
      )}
    </div>
  )
}

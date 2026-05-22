"use client"

import { useEffect, useState } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Loader2, CheckCircle2, XCircle } from "lucide-react"

export function GitHubOAuthCallback() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading")
  const [message, setMessage] = useState("Connecting to GitHub...")

  useEffect(() => {
    const handleCallback = async () => {
      const code = searchParams.get("code")
      const state = searchParams.get("state")
      const error = searchParams.get("error")

      if (error) {
        setStatus("error")
        setMessage(`GitHub OAuth error: ${error}`)
        setTimeout(() => router.push("/settings"), 3000)
        return
      }

      if (!code || !state) {
        setStatus("error")
        setMessage("Missing authorization code or state")
        setTimeout(() => router.push("/settings"), 3000)
        return
      }

      try {
        const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
        const response = await fetch(`${backendUrl}/api/github/oauth/callback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, state }),
        })

        if (!response.ok) {
          const errorData = await response.json()
          throw new Error(errorData.detail || "Failed to exchange code for token")
        }

        const data = await response.json()

        localStorage.setItem("github_token", data.access_token)
        localStorage.setItem("github_user", JSON.stringify(data.user))

        setStatus("success")
        setMessage(`Successfully connected as ${data.user.login}`)
        setTimeout(() => router.push("/settings"), 2000)
      } catch (err) {
        setStatus("error")
        setMessage(err instanceof Error ? err.message : "Unknown error occurred")
        setTimeout(() => router.push("/settings"), 3000)
      }
    }

    handleCallback()
  }, [searchParams, router])

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-stone-50 to-stone-100">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <div className="flex flex-col items-center gap-4">
          {status === "loading" && (
            <>
              <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
              <h2 className="text-xl font-semibold text-stone-800">Connecting to GitHub</h2>
              <p className="text-sm text-stone-600 text-center">{message}</p>
            </>
          )}

          {status === "success" && (
            <>
              <CheckCircle2 className="w-12 h-12 text-green-500" />
              <h2 className="text-xl font-semibold text-stone-800">Success!</h2>
              <p className="text-sm text-stone-600 text-center">{message}</p>
              <p className="text-xs text-stone-500">Redirecting to settings...</p>
            </>
          )}

          {status === "error" && (
            <>
              <XCircle className="w-12 h-12 text-red-500" />
              <h2 className="text-xl font-semibold text-stone-800">Connection Failed</h2>
              <p className="text-sm text-stone-600 text-center">{message}</p>
              <p className="text-xs text-stone-500">Redirecting to settings...</p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

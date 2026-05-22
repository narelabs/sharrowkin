"use client"

import { useEffect, Suspense } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { CheckCircle2, Loader2 } from "lucide-react"

function GitHubSuccessContent() {
  const router = useRouter()
  const searchParams = useSearchParams()

  useEffect(() => {
    const token = searchParams.get("token")
    const userStr = searchParams.get("user")

    if (token && userStr) {
      try {
        const user = JSON.parse(userStr)
        localStorage.setItem("github_token", token)
        localStorage.setItem("github_user", JSON.stringify(user))

        setTimeout(() => {
          router.push("/settings?tab=github")
        }, 2000)
      } catch (err) {
        console.error("Failed to parse user data:", err)
        router.push("/settings?error=invalid_data")
      }
    } else {
      router.push("/settings?error=missing_data")
    }
  }, [searchParams, router])

  return (
    <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-stone-50 to-stone-100">
      <div className="bg-white rounded-lg shadow-lg p-8 max-w-md w-full">
        <div className="flex flex-col items-center gap-4">
          <CheckCircle2 className="w-12 h-12 text-green-500" />
          <h2 className="text-xl font-semibold text-stone-800">GitHub Connected!</h2>
          <p className="text-sm text-stone-600 text-center">
            Successfully connected to GitHub. Redirecting to settings...
          </p>
          <Loader2 className="w-6 h-6 text-stone-400 animate-spin" />
        </div>
      </div>
    </div>
  )
}

export default function GitHubSuccessPage() {
  return (
    <Suspense fallback={
      <div className="flex items-center justify-center min-h-screen bg-gradient-to-br from-stone-50 to-stone-100">
        <Loader2 className="w-8 h-8 text-stone-400 animate-spin" />
      </div>
    }>
      <GitHubSuccessContent />
    </Suspense>
  )
}

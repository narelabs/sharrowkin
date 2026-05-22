import { NextRequest, NextResponse } from "next/server"

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams
  const code = searchParams.get("code")
  const state = searchParams.get("state")

  if (!code || !state) {
    return NextResponse.redirect(new URL("/settings?error=missing_params", request.url))
  }

  try {
    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"
    const response = await fetch(`${backendUrl}/api/github/oauth/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, state }),
    })

    if (!response.ok) {
      throw new Error("Failed to exchange code for token")
    }

    const data = await response.json()

    if (data.status === "error") {
      return NextResponse.redirect(new URL(`/settings?error=${encodeURIComponent(data.message)}`, request.url))
    }

    // Redirect to a page that will handle storing the token in localStorage
    const redirectUrl = new URL("/github/success", request.url)
    redirectUrl.searchParams.set("token", data.access_token)
    redirectUrl.searchParams.set("user", JSON.stringify(data.user))

    return NextResponse.redirect(redirectUrl)
  } catch (error) {
    console.error("OAuth callback error:", error)
    return NextResponse.redirect(new URL("/settings?error=oauth_failed", request.url))
  }
}

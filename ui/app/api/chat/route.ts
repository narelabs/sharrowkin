/**
 * POST /api/chat
 *
 * Proxies chat requests to the Sharrowkin Python backend.
 * Falls back to the backend's /api/chat endpoint which uses the
 * configured LLM (Gemini / Omniroute / etc.).
 */
export async function POST(req: Request) {
  try {
    const body = await req.json()
    const { messages, model } = body

    if (!messages || !Array.isArray(messages)) {
      return new Response(
        JSON.stringify({ error: "Invalid request: messages array required" }),
        { status: 400, headers: { "Content-Type": "application/json" } },
      )
    }

    const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

    const response = await fetch(`${backendUrl}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ messages, model: model || "" }),
    })

    if (!response.ok) {
      const errorText = await response.text()
      return new Response(
        JSON.stringify({ error: `Backend error: ${errorText}` }),
        { status: response.status, headers: { "Content-Type": "application/json" } },
      )
    }

    const data = await response.json()
    const responseText = data.response || data.content || "No response from backend."

    return new Response(responseText, {
      status: 200,
      headers: { "Content-Type": "text/plain; charset=utf-8" },
    })
  } catch (error) {
    console.error("Chat API proxy error:", error)
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "An unexpected error occurred",
      }),
      { status: 500, headers: { "Content-Type": "application/json" } },
    )
  }
}

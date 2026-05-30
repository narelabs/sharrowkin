"use client"

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || "http://127.0.0.1:8000"

// Per-session workspace key. Each chat session remembers its own folder.
export function sessionWorkspaceKey(sessionId: string): string {
  return `sharrowkin-session-workspace-${sessionId}`
}

export function getSessionWorkspace(sessionId: string): string | null {
  if (typeof window === "undefined") return null
  return localStorage.getItem(sessionWorkspaceKey(sessionId))
}

export function setSessionWorkspace(sessionId: string, path: string): void {
  if (typeof window === "undefined") return
  localStorage.setItem(sessionWorkspaceKey(sessionId), path)
  // Keep the legacy/global key in sync so other screens (settings, workflow)
  // and the backend default stay aligned with the active session.
  localStorage.setItem("sharrowkin-workspace-path", path)
  localStorage.setItem("workspace_path", path)
  addRecentWorkspace(path)
}

// Running inside the Tauri desktop shell?
export function isTauri(): boolean {
  if (typeof window === "undefined") return false
  return (
    "__TAURI_INTERNALS__" in window ||
    "__TAURI__" in window ||
    // Tauri v2 exposes this boolean on newer runtimes.
    (window as any).isTauri === true
  )
}

// Open the native OS folder picker (desktop only). Returns the chosen
// absolute path, or null if the user cancelled or we're not in Tauri.
export async function pickWorkspaceFolder(): Promise<string | null> {
  if (!isTauri()) return null
  try {
    const { open } = await import("@tauri-apps/plugin-dialog")
    const selected = await open({
      directory: true,
      multiple: false,
      title: "Choose the folder the agent will work in",
    })
    if (typeof selected === "string") return selected
    return null
  } catch (err) {
    console.error("Native folder dialog failed:", err)
    return null
  }
}

// Recent workspaces (most-recent-first, capped).
const RECENTS_KEY = "sharrowkin-recent-workspaces"
const MAX_RECENTS = 6

export function getRecentWorkspaces(): string[] {
  if (typeof window === "undefined") return []
  try {
    const raw = localStorage.getItem(RECENTS_KEY)
    return raw ? (JSON.parse(raw) as string[]) : []
  } catch {
    return []
  }
}

export function addRecentWorkspace(path: string): void {
  if (typeof window === "undefined" || !path) return
  const existing = getRecentWorkspaces().filter((p) => p !== path)
  const next = [path, ...existing].slice(0, MAX_RECENTS)
  localStorage.setItem(RECENTS_KEY, JSON.stringify(next))
}

// Validate that a path exists and is a directory the backend can reach.
// Uses the existing /api/workspace/tree endpoint (404s on a missing path).
export async function validateWorkspace(path: string): Promise<boolean> {
  if (!path.trim()) return false
  try {
    const res = await fetch(
      `${BACKEND_URL}/api/workspace/tree?path=${encodeURIComponent(path)}`
    )
    return res.ok
  } catch {
    return false
  }
}

export function folderName(path: string): string {
  if (!path) return ""
  return path.split(/[\\/]/).filter(Boolean).pop() || path
}

// Persona API client

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL || 'http://127.0.0.1:8000'

export interface Persona {
  id: string
  name: string
  description: string
  colors: {
    primary: string
    secondary: string
    accent: string
  }
  tags: string[]
  audio_enabled: boolean
}

export interface PersonasResponse {
  personas: Persona[]
  active_persona: string | null
}

export async function listPersonas(): Promise<PersonasResponse> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/personas`)
    if (!response.ok) throw new Error('Response not OK')
    return await response.json()
  } catch (error) {
    console.warn('listPersonas failed:', error)
    return { personas: [], active_persona: null }
  }
}

export async function getActivePersona(): Promise<{ id: string | null; name: string; description: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/personas/active`)
    if (!response.ok) throw new Error('Response not OK')
    return await response.json()
  } catch (error) {
    console.warn('getActivePersona failed:', error)
    return { id: null, name: 'Default', description: 'Standard Sharrowkin agent' }
  }
}

export async function activatePersona(personaId: string): Promise<{ status: string; message: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/personas/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ persona_id: personaId }),
    })
    if (!response.ok) throw new Error('Response not OK')
    return await response.json()
  } catch (error) {
    console.warn('activatePersona failed:', error)
    return { status: 'error', message: 'Backend offline' }
  }
}

export async function deactivatePersona(): Promise<{ status: string; message: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/personas/deactivate`, {
      method: 'POST',
    })
    if (!response.ok) throw new Error('Response not OK')
    return await response.json()
  } catch (error) {
    console.warn('deactivatePersona failed:', error)
    return { status: 'error', message: 'Backend offline' }
  }
}

export async function getAgentName(): Promise<{ agent_name: string }> {
  try {
    const response = await fetch(`${BACKEND_URL}/api/personas/agent-name`)
    if (!response.ok) throw new Error('Response not OK')
    return await response.json()
  } catch (error) {
    console.warn('getAgentName failed:', error)
    return { agent_name: 'Sharrowkin' }
  }
}

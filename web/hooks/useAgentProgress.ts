'use client'

import { useEffect, useState, useCallback } from 'react'

interface TimelineEvent {
  phase: string
  status: 'pending' | 'active' | 'done' | 'error'
  message?: string
  timestamp: number
  duration?: number
}

interface AgentMessage {
  type: 'phase' | 'log' | 'content' | 'status' | 'result'
  phase?: string
  state?: 'active' | 'done'
  level?: string
  message?: string
  content?: string
  status?: string
}

const PHASES = ['Observe', 'Recall', 'Reason', 'Stabilize', 'Commit']

export function useAgentProgress(wsUrl: string) {
  const [events, setEvents] = useState<TimelineEvent[]>([])
  const [currentPhase, setCurrentPhase] = useState<string>()
  const [isConnected, setIsConnected] = useState(false)
  const [error, setError] = useState<string>()

  const initializeTimeline = useCallback(() => {
    const now = Date.now()
    setEvents(
      PHASES.map((phase) => ({
        phase,
        status: 'pending' as const,
        timestamp: now,
      }))
    )
  }, [])

  useEffect(() => {
    initializeTimeline()

    const ws = new WebSocket(wsUrl)
    const phaseStartTimes = new Map<string, number>()

    ws.onopen = () => {
      setIsConnected(true)
      setError(undefined)
    }

    ws.onmessage = (event) => {
      try {
        const data: AgentMessage = JSON.parse(event.data)

        if (data.type === 'phase') {
          const phaseName = data.phase
          if (!phaseName) return

          setCurrentPhase(phaseName)

          if (data.state === 'active') {
            // Mark phase as active
            phaseStartTimes.set(phaseName, Date.now())
            setEvents((prev) =>
              prev.map((e) =>
                e.phase === phaseName
                  ? { ...e, status: 'active', timestamp: Date.now() }
                  : e
              )
            )
          } else if (data.state === 'done') {
            // Mark phase as done with duration
            const startTime = phaseStartTimes.get(phaseName)
            const duration = startTime ? Date.now() - startTime : undefined
            setEvents((prev) =>
              prev.map((e) =>
                e.phase === phaseName
                  ? { ...e, status: 'done', duration }
                  : e
              )
            )
          }
        } else if (data.type === 'log') {
          // Update message for current phase
          if (currentPhase && data.message) {
            setEvents((prev) =>
              prev.map((e) =>
                e.phase === currentPhase && e.status === 'active'
                  ? { ...e, message: data.message }
                  : e
              )
            )
          }

          // Handle errors
          if (data.level === 'error' && data.message) {
            setEvents((prev) =>
              prev.map((e) =>
                e.status === 'active'
                  ? { ...e, status: 'error', message: data.message }
                  : e
              )
            )
            setError(data.message)
          }
        } else if (data.type === 'status') {
          if (data.status === 'error' && data.message) {
            setError(data.message)
            setEvents((prev) =>
              prev.map((e) =>
                e.status === 'active'
                  ? { ...e, status: 'error', message: data.message }
                  : e
              )
            )
          }
        }
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err)
      }
    }

    ws.onerror = () => {
      setError('WebSocket connection error')
      setIsConnected(false)
    }

    ws.onclose = () => {
      setIsConnected(false)
    }

    return () => {
      ws.close()
    }
  }, [wsUrl, initializeTimeline])

  const reset = useCallback(() => {
    initializeTimeline()
    setCurrentPhase(undefined)
    setError(undefined)
  }, [initializeTimeline])

  return {
    events,
    currentPhase,
    isConnected,
    error,
    reset,
  }
}

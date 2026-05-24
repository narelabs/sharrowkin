'use client'

import { useEffect, useState } from 'react'
import { CheckCircle2, Circle, Loader2, XCircle } from 'lucide-react'

interface TimelineEvent {
  phase: string
  status: 'pending' | 'active' | 'done' | 'error'
  message?: string
  timestamp: number
  duration?: number
}

interface AgentTimelineProps {
  events: TimelineEvent[]
  currentPhase?: string
}

const PHASE_LABELS: Record<string, string> = {
  Observe: 'Сканирование workspace',
  Recall: 'Загрузка памяти',
  Reason: 'Генерация решения',
  Stabilize: 'Валидация и тесты',
  Commit: 'Сохранение результата',
}

const PHASE_DESCRIPTIONS: Record<string, string> = {
  Observe: 'AST-парсинг файлов и построение семантического графа',
  Recall: 'Извлечение контекста из DSM, RLD, MemoryField и TraceMemory',
  Reason: 'LLM генерирует патчи на основе контекста из памяти',
  Stabilize: 'Применение патчей, запуск тестов, retry при ошибках',
  Commit: 'Обновление памяти успешными паттернами',
}

export function AgentTimeline({ events, currentPhase }: AgentTimelineProps) {
  const [elapsedTime, setElapsedTime] = useState(0)
  const startTime = events[0]?.timestamp || Date.now()

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsedTime(Date.now() - startTime)
    }, 100)
    return () => clearInterval(interval)
  }, [startTime])

  const formatDuration = (ms: number) => {
    const seconds = Math.floor(ms / 1000)
    const deciseconds = Math.floor((ms % 1000) / 100)
    return `${seconds}.${deciseconds}s`
  }

  const getPhaseIcon = (status: TimelineEvent['status']) => {
    switch (status) {
      case 'done':
        return <CheckCircle2 className="h-5 w-5 text-green-500" />
      case 'active':
        return <Loader2 className="h-5 w-5 animate-spin text-blue-500" />
      case 'error':
        return <XCircle className="h-5 w-5 text-red-500" />
      default:
        return <Circle className="h-5 w-5 text-gray-300" />
    }
  }

  const getPhaseColor = (status: TimelineEvent['status']) => {
    switch (status) {
      case 'done':
        return 'border-green-500 bg-green-50'
      case 'active':
        return 'border-blue-500 bg-blue-50 shadow-lg'
      case 'error':
        return 'border-red-500 bg-red-50'
      default:
        return 'border-gray-200 bg-white'
    }
  }

  return (
    <div className="w-full space-y-4">
      {/* Header with elapsed time */}
      <div className="flex items-center justify-between rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <h3 className="text-lg font-semibold">Cognitive Cycle Progress</h3>
          <p className="text-sm text-gray-500">
            {currentPhase ? `Current: ${PHASE_LABELS[currentPhase] || currentPhase}` : 'Initializing...'}
          </p>
        </div>
        <div className="text-right">
          <div className="text-2xl font-mono font-bold text-blue-600">
            {formatDuration(elapsedTime)}
          </div>
          <div className="text-xs text-gray-500">elapsed</div>
        </div>
      </div>

      {/* Timeline */}
      <div className="space-y-3">
        {events.map((event, index) => (
          <div
            key={`${event.phase}-${index}`}
            className={`relative rounded-lg border-2 p-4 transition-all duration-300 ${getPhaseColor(event.status)}`}
          >
            {/* Connector line */}
            {index < events.length - 1 && (
              <div className="absolute left-6 top-full h-3 w-0.5 bg-gray-300" />
            )}

            <div className="flex items-start gap-4">
              {/* Icon */}
              <div className="flex-shrink-0 pt-0.5">
                {getPhaseIcon(event.status)}
              </div>

              {/* Content */}
              <div className="flex-1 space-y-1">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-gray-900">
                    {PHASE_LABELS[event.phase] || event.phase}
                  </h4>
                  {event.duration && (
                    <span className="text-sm font-mono text-gray-500">
                      {formatDuration(event.duration)}
                    </span>
                  )}
                </div>

                <p className="text-sm text-gray-600">
                  {PHASE_DESCRIPTIONS[event.phase] || event.message || 'Processing...'}
                </p>

                {event.message && event.status === 'active' && (
                  <div className="mt-2 rounded bg-white/50 p-2 text-xs text-gray-700">
                    {event.message}
                  </div>
                )}

                {event.status === 'error' && event.message && (
                  <div className="mt-2 rounded bg-red-100 p-2 text-xs text-red-700">
                    ⚠️ {event.message}
                  </div>
                )}

                {/* Progress bar for active phase */}
                {event.status === 'active' && (
                  <div className="mt-2 h-1 overflow-hidden rounded-full bg-gray-200">
                    <div className="h-full animate-pulse bg-blue-500" style={{ width: '60%' }} />
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-3 gap-4 rounded-lg border border-gray-200 bg-white p-4">
        <div className="text-center">
          <div className="text-2xl font-bold text-green-600">
            {events.filter(e => e.status === 'done').length}
          </div>
          <div className="text-xs text-gray-500">Completed</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-blue-600">
            {events.filter(e => e.status === 'active').length}
          </div>
          <div className="text-xs text-gray-500">Active</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-gray-400">
            {events.filter(e => e.status === 'pending').length}
          </div>
          <div className="text-xs text-gray-500">Pending</div>
        </div>
      </div>
    </div>
  )
}

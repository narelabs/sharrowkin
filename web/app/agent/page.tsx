'use client'

import { useState } from 'react'
import { AgentTimeline } from '@/components/AgentTimeline'
import { useAgentProgress } from '@/hooks/useAgentProgress'
import { Send, RotateCcw } from 'lucide-react'

export default function AgentPage() {
  const [task, setTask] = useState('')
  const [sessionId, setSessionId] = useState<string>()
  const [response, setResponse] = useState<string>()

  const wsUrl = sessionId
    ? `ws://localhost:8000/api/agent/ws?session_id=${sessionId}`
    : ''

  const { events, currentPhase, isConnected, error, reset } = useAgentProgress(wsUrl)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!task.trim()) return

    try {
      // Create new session
      const res = await fetch('http://localhost:8000/api/agent/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: task.trim(),
          workspace_path: '.',
        }),
      })

      const data = await res.json()
      setSessionId(data.session_id)
      setResponse(undefined)
      reset()
    } catch (err) {
      console.error('Failed to start agent:', err)
    }
  }

  const handleReset = () => {
    setTask('')
    setSessionId(undefined)
    setResponse(undefined)
    reset()
  }

  return (
    <div className="min-h-screen bg-gray-50 p-8">
      <div className="mx-auto max-w-4xl space-y-8">
        {/* Header */}
        <div className="text-center">
          <h1 className="text-4xl font-bold text-gray-900">Sharrowkin Agent</h1>
          <p className="mt-2 text-gray-600">
            5-фазный цикл автономного рассуждения с real-time прогрессом
          </p>
        </div>

        {/* Task Input */}
        <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="task" className="block text-sm font-medium text-gray-700">
                Задача для агента
              </label>
              <textarea
                id="task"
                value={task}
                onChange={(e) => setTask(e.target.value)}
                placeholder="Например: Изучи проект и объясни архитектуру"
                className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
                rows={3}
                disabled={!!sessionId}
              />
            </div>

            <div className="flex gap-2">
              <button
                type="submit"
                disabled={!task.trim() || !!sessionId}
                className="flex items-center gap-2 rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed"
              >
                <Send className="h-4 w-4" />
                Запустить агента
              </button>

              {sessionId && (
                <button
                  type="button"
                  onClick={handleReset}
                  className="flex items-center gap-2 rounded-md border border-gray-300 bg-white px-4 py-2 text-gray-700 hover:bg-gray-50"
                >
                  <RotateCcw className="h-4 w-4" />
                  Сбросить
                </button>
              )}
            </div>
          </form>

          {/* Connection Status */}
          {sessionId && (
            <div className="mt-4 flex items-center gap-2 text-sm">
              <div className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`} />
              <span className="text-gray-600">
                {isConnected ? 'Подключено к агенту' : 'Отключено'}
              </span>
              <span className="text-gray-400">•</span>
              <span className="font-mono text-xs text-gray-500">
                {sessionId.slice(0, 8)}...
              </span>
            </div>
          )}
        </div>

        {/* Timeline */}
        {sessionId && events.length > 0 && (
          <AgentTimeline events={events} currentPhase={currentPhase} />
        )}

        {/* Error Display */}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-4">
            <h3 className="font-semibold text-red-900">Ошибка</h3>
            <p className="mt-1 text-sm text-red-700">{error}</p>
          </div>
        )}

        {/* Response Display */}
        {response && (
          <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
            <h3 className="mb-4 text-lg font-semibold text-gray-900">Результат</h3>
            <div className="prose prose-sm max-w-none">
              <pre className="whitespace-pre-wrap text-sm text-gray-700">{response}</pre>
            </div>
          </div>
        )}

        {/* Info */}
        <div className="rounded-lg border border-blue-100 bg-blue-50 p-4 text-sm text-blue-900">
          <h4 className="font-semibold">Как это работает:</h4>
          <ul className="mt-2 space-y-1 text-blue-800">
            <li>• <strong>Observe</strong> — сканирует workspace и строит AST-граф</li>
            <li>• <strong>Recall</strong> — извлекает контекст из 4 систем памяти</li>
            <li>• <strong>Reason</strong> — генерирует решение через LLM</li>
            <li>• <strong>Stabilize</strong> — применяет патчи и запускает тесты</li>
            <li>• <strong>Commit</strong> — сохраняет успешные паттерны в память</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

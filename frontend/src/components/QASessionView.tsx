import { useState, useEffect, useRef } from 'react'
import { approveQASession, skipQASession } from '../api/qa_sessions'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

interface Props {
  projectId: number
  sessionId: string
  onComplete?: (status: string) => void
}

export function QASessionView({ projectId, sessionId, onComplete }: Props) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [hitlTicket, setHitlTicket] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [actioning, setActioning] = useState(false)
  const [totalCost, setTotalCost] = useState(0)
  const [showThoughts, setShowThoughts] = useState(false)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/qa-sessions/${sessionId}/stream`)

    es.onmessage = (evt) => {
      const event: AgentEvent = JSON.parse(evt.data)
      setEvents((prev) => [...prev, event])

      if (event.type === 'hitl_request' && event.ticket_id) {
        setHitlTicket(event.ticket_id)
      }
      if (event.type === 'session_status' && event.status !== 'hitl_waiting') {
        setHitlTicket(null)
      }
      if (event.type === 'qa_done' || event.type === 'coder_done') {
        setTotalCost((prev) => prev + (event.cost_usd ?? 0))
      }
      if (['done', 'error', 'budget_exceeded', 'timeout'].includes(event.type)) {
        setDone(true)
        es.close()
        onCompleteRef.current?.(event.status ?? event.type)
      }
    }

    es.onerror = () => {
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, sessionId])

  async function handleApprove() {
    setActioning(true)
    try {
      await approveQASession(projectId, sessionId)
      setHitlTicket(null)
    } finally {
      setActioning(false)
    }
  }

  async function handleSkip() {
    setActioning(true)
    try {
      await skipQASession(projectId, sessionId)
      setHitlTicket(null)
    } finally {
      setActioning(false)
    }
  }

  // Which agents are actively visible in the stream
  const lastStatus = events.findLast?.((e) => e.type === 'session_status')?.status ?? null

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3">
          {!done ? (
            <>
              {lastStatus?.startsWith('qa') && (
                <div className="flex items-center gap-1.5 text-sm text-violet-600">
                  <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse inline-block" />
                  <span className="font-medium">🧪 QA running…</span>
                </div>
              )}
              {lastStatus?.startsWith('coder') && (
                <div className="flex items-center gap-1.5 text-sm text-amber-600">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse inline-block" />
                  <span className="font-medium">🛠️ Coder running…</span>
                </div>
              )}
              {lastStatus === 'hitl_waiting' && (
                <div className="flex items-center gap-1.5 text-sm text-yellow-600">
                  <span className="animate-pulse">⏳</span>
                  <span className="font-medium">Awaiting your approval</span>
                </div>
              )}
              {!lastStatus && (
                <div className="flex items-center gap-1.5 text-sm text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-gray-300 animate-pulse inline-block" />
                  <span>Starting…</span>
                </div>
              )}
            </>
          ) : (
            <div className="flex items-center gap-1.5 text-sm text-emerald-600">
              <span>✓</span>
              <span className="font-medium">Session complete</span>
              {totalCost > 0 && (
                <span className="text-gray-400 font-normal">· ${totalCost.toFixed(4)}</span>
              )}
            </div>
          )}
        </div>

        <button
          type="button"
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors ${
            showThoughts
              ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
              : 'bg-gray-50 border-gray-200 text-gray-500 hover:border-gray-300'
          }`}
          onClick={() => setShowThoughts((p) => !p)}
        >
          {showThoughts ? '🧠 Hide thoughts' : '🧠 Show thoughts'}
        </button>
      </div>

      <AgentTimeline events={events} showThoughts={showThoughts} />

      {/* HITL approval card */}
      {hitlTicket && !done && (
        <div className="rounded-lg border border-yellow-200 bg-yellow-50 p-4 space-y-3">
          <div className="flex items-start gap-2">
            <span className="text-yellow-600 text-lg">⏳</span>
            <div>
              <p className="text-sm font-semibold text-yellow-800">Human-in-the-Loop approval required</p>
              <p className="text-xs text-yellow-700 mt-0.5">
                Bug ticket <code className="font-mono bg-yellow-100 px-1 rounded">{hitlTicket}</code> was filed.
                Approve the coder's fix attempt or skip this ticket.
              </p>
            </div>
          </div>
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              disabled={actioning}
              className="flex-1 bg-emerald-600 hover:bg-emerald-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
            >
              ✓ Approve Fix
            </button>
            <button
              onClick={handleSkip}
              disabled={actioning}
              className="flex-1 border border-gray-200 px-4 py-2 rounded-lg text-sm font-medium hover:bg-gray-50 disabled:opacity-50 transition-colors"
            >
              Skip
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

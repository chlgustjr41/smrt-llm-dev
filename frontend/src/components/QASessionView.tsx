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

  return (
    <div className="space-y-3">
      <AgentTimeline events={events} />

      {totalCost > 0 && (
        <p className="text-xs text-gray-400">Running cost: ${totalCost.toFixed(4)}</p>
      )}

      {hitlTicket && !done && (
        <div className="p-3 border border-yellow-300 bg-yellow-50 rounded">
          <p className="text-sm font-medium mb-2">
            Bug ticket <code>{hitlTicket}</code> filed. Approve fix attempt?
          </p>
          <div className="flex gap-2">
            <button
              onClick={handleApprove}
              disabled={actioning}
              className="bg-green-600 text-white px-3 py-1.5 rounded text-sm disabled:opacity-50"
            >
              Approve Fix
            </button>
            <button
              onClick={handleSkip}
              disabled={actioning}
              className="border px-3 py-1.5 rounded text-sm hover:bg-gray-100 disabled:opacity-50"
            >
              Skip
            </button>
          </div>
        </div>
      )}

      {done && <p className="text-xs text-gray-400">Session complete.</p>}
    </div>
  )
}

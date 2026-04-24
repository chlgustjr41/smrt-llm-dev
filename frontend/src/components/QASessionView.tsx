import { useState, useEffect, useRef } from 'react'
import { approveQASession, skipQASession } from '../api/qa_sessions'

interface QAEvent {
  type: string
  text?: string
  tool?: string
  agent?: string
  status?: string
  ticket_id?: string
  fix_attempt?: number
  message?: string
  output?: string
}

interface Props {
  projectId: number
  sessionId: string
}

export function QASessionView({ projectId, sessionId }: Props) {
  const [events, setEvents] = useState<QAEvent[]>([])
  const [hitlTicket, setHitlTicket] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [actioning, setActioning] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/qa-sessions/${sessionId}/stream`)

    es.onmessage = (evt) => {
      const event: QAEvent = JSON.parse(evt.data)
      setEvents((prev) => [...prev, event])

      if (event.type === 'hitl_request' && event.ticket_id) {
        setHitlTicket(event.ticket_id)
      }
      if (event.type === 'session_status' && event.status !== 'hitl_waiting') {
        setHitlTicket(null)
      }
      if (['done', 'error', 'budget_exceeded', 'timeout'].includes(event.type)) {
        setDone(true)
        es.close()
      }
    }

    es.onerror = () => {
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, sessionId])

  useEffect(() => {
    if (bottomRef.current && typeof bottomRef.current.scrollIntoView === 'function') {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [events])

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
    <div className="border rounded p-4 bg-gray-50 space-y-3">
      <div className="max-h-64 overflow-y-auto font-mono text-xs space-y-0.5">
        {events.map((evt, i) => {
          if (evt.type === 'qa_text_delta' || evt.type === 'coder_text_delta') {
            return <span key={i} className="text-gray-700">{evt.text}</span>
          }
          if (evt.type === 'tool_use') {
            return (
              <div key={i} className="text-blue-600">
                [{evt.agent}] → {evt.tool}
              </div>
            )
          }
          if (evt.type === 'session_status') {
            return (
              <div key={i} className="text-purple-700 font-semibold">
                ◆ {evt.status}{evt.fix_attempt !== undefined ? ` (attempt ${evt.fix_attempt})` : ''}
              </div>
            )
          }
          if (evt.type === 'recheck_output') {
            return (
              <pre key={i} className="text-yellow-700 whitespace-pre-wrap">
                {evt.output}
              </pre>
            )
          }
          if (evt.type === 'error') {
            return <div key={i} className="text-red-600">Error: {evt.message}</div>
          }
          return null
        })}
        <div ref={bottomRef} />
      </div>

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

      {done && (
        <p className="text-xs text-gray-400">Session complete.</p>
      )}
    </div>
  )
}

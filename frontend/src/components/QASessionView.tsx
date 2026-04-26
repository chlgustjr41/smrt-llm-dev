import { useState, useEffect, useRef, useMemo } from 'react'
import { approveQASession, skipQASession, getQASessionEvents } from '../api/qa_sessions'
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
  const [showThoughts, setShowThoughts] = useState(true)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    let cancelled = false
    let liveConnected = false

    // Fallback: read persisted events from JSONL when SSE is unavailable.
    // This covers: session already done, server restart, or tab switch during
    // a long session (the queue may have been drained by the previous SSE read).
    async function loadFromLog() {
      try {
        const logged = await getQASessionEvents(projectId, sessionId)
        if (cancelled || logged.length === 0) return
        setEvents(logged)
        const cost = logged
          .filter((e) => e.type === 'qa_done' || e.type === 'coder_done')
          .reduce((s, e) => s + (e.cost_usd ?? 0), 0)
        if (cost > 0) setTotalCost(cost)
        const lastDone = [...logged].reverse().find((e) =>
          ['done', 'error', 'budget_exceeded', 'timeout'].includes(e.type),
        )
        if (lastDone) {
          setDone(true)
          onCompleteRef.current?.(lastDone.status ?? lastDone.type)
        }
      } catch {
        // silently ignore — empty events list is fine
      }
      if (!cancelled && !liveConnected) setDone(true)
    }

    const es = new EventSource(`/api/projects/${projectId}/qa-sessions/${sessionId}/stream`)

    es.onmessage = (evt) => {
      if (cancelled) return
      liveConnected = true
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
      es.close()
      if (!cancelled) loadFromLog()
    }

    return () => {
      cancelled = true
      es.close()
    }
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

  const lastStatus = events.findLast?.((e) => e.type === 'session_status')?.status ?? null

  // Live thought: accumulate text since the last tool boundary for the ticker
  const liveThought = useMemo(() => {
    if (done) return ''
    let start = 0
    for (let i = events.length - 1; i >= 0; i--) {
      if (['session_status', 'tool_result', 'tool_use'].includes(events[i].type)) {
        start = i + 1
        break
      }
    }
    return events
      .slice(start)
      .filter((e) => ['text_delta', 'qa_text_delta', 'coder_text_delta'].includes(e.type))
      .map((e) => e.text ?? '')
      .join('')
      .slice(-160)
  }, [events, done])

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

      {/* Live thought ticker — shows last segment of agent reasoning in real-time */}
      {!done && liveThought && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-100 text-xs text-indigo-700 font-mono leading-relaxed">
          <span className="shrink-0 opacity-60 mt-px">💭</span>
          <span className="line-clamp-2 break-words whitespace-pre-wrap">{liveThought}</span>
        </div>
      )}

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

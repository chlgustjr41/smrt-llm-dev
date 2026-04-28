import { useState, useEffect, useRef, useMemo } from 'react'
import { getQASessionEvents, postSessionBudgetDecision } from '../api/qa_sessions'
import { AgentTimeline, type AgentEvent, ThinkingDots } from './AgentTimeline'

interface Props {
  projectId: number
  sessionId: string
  onComplete?: (status: string) => void
}

const TEXT_DELTA_TYPES = new Set(['text_delta', 'qa_text_delta', 'coder_text_delta'])

export function QASessionView({ projectId, sessionId, onComplete }: Props) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [done, setDone] = useState(false)
  const [finalStatus, setFinalStatus] = useState<string | null>(null)
  const [showThoughts, setShowThoughts] = useState(true)
  const [qaEarlyExit, setQaEarlyExit] = useState<string | null>(null)
  const [budgetPause, setBudgetPause] = useState<{ cost: number; budget: number } | null>(null)
  const [budgetDeciding, setBudgetDeciding] = useState(false)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  const ticketsFound = useMemo(() => {
    const ids = new Set(
      events
        .filter((e) => e.type === 'hitl_request' && e.ticket_id)
        .map((e) => e.ticket_id!),
    )
    return ids.size
  }, [events])

  useEffect(() => {
    let cancelled = false
    let liveConnected = false

    function markDone(status: string) {
      setFinalStatus(status)
      setDone(true)
      onCompleteRef.current?.(status)
    }

    async function loadFromLog() {
      try {
        const logged = await getQASessionEvents(projectId, sessionId)
        if (!cancelled && logged.length > 0) {
          setEvents(logged)
          const earlyExit = logged.find((e) => e.type === 'qa_early_exit')
          if (earlyExit) setQaEarlyExit(earlyExit.reasoning ?? 'QA determined fix is complete.')
          const lastDone = [...logged].reverse().find((e) =>
            ['done', 'error', 'budget_exceeded', 'timeout'].includes(e.type),
          )
          if (lastDone) {
            markDone(lastDone.status ?? lastDone.type)
            return
          }
        }
      } catch {
        // silently ignore
      }
      if (!cancelled && !liveConnected) markDone('unknown')
    }

    const es = new EventSource(`/api/projects/${projectId}/qa-sessions/${sessionId}/stream`)

    es.onmessage = (evt) => {
      if (cancelled) return
      liveConnected = true
      const event: AgentEvent = JSON.parse(evt.data)
      setEvents((prev) => [...prev, event])

      if (event.type === 'qa_early_exit') {
        setQaEarlyExit(event.reasoning ?? 'QA determined fix is complete.')
      }
      if (event.type === 'budget_pause') {
        setBudgetPause({ cost: event.cost_usd ?? 0, budget: event.budget_usd ?? 0 })
      } else if (event.type === 'budget_continue') {
        setBudgetPause(null)
        setBudgetDeciding(false)
      } else if (['done', 'error', 'budget_exceeded', 'timeout'].includes(event.type)) {
        setBudgetPause(null)
        markDone(event.status ?? event.type)
        es.close()
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

  const lastEvent = events.length > 0 ? events[events.length - 1] : null
  const lastSessionEvent = events.findLast?.((e) => e.type === 'session_status') ?? null
  const lastStatus = lastSessionEvent?.status ?? null
  const currentAttempt = lastSessionEvent?.fix_attempt ?? 0

  // Ambient generation state from the most recent event
  const isGenerating = !done && !!lastEvent && TEXT_DELTA_TYPES.has(lastEvent.type)
  const isCallingTool = !done && lastEvent?.type === 'tool_use'

  // ── Completion banner ──────────────────────────────────────────────────────
  function DoneBar() {
    if (finalStatus === 'error') {
      return (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3">
          <span className="text-red-500 text-lg leading-none mt-0.5">✗</span>
          <div>
            <p className="text-sm font-semibold text-red-700">Session failed</p>
            <p className="text-xs text-red-600 mt-0.5">
              The agent encountered an error. Check the events above for details, then start a new session.
            </p>
          </div>
        </div>
      )
    }
    if (finalStatus === 'budget_exceeded') {
      return (
        <div className="flex items-start gap-3 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3">
          <span className="text-amber-500 text-lg leading-none mt-0.5">⚠</span>
          <div>
            <p className="text-sm font-semibold text-amber-700">Budget limit reached</p>
            <p className="text-xs text-amber-600 mt-0.5">
              Partial results only — increase <code className="font-mono">BUDGET_PER_RUN_USD</code> in <code className="font-mono">.env</code> to run longer sessions.
            </p>
          </div>
        </div>
      )
    }
    if (finalStatus === 'unknown') {
      return (
        <div className="flex items-start gap-3 rounded-lg border border-gray-200 bg-gray-50 px-4 py-3">
          <span className="text-gray-400 text-lg leading-none mt-0.5">?</span>
          <div>
            <p className="text-sm font-semibold text-gray-600">Could not connect to session stream</p>
            <p className="text-xs text-gray-500 mt-0.5">
              The session may not have started, or already finished before connecting. Try starting a new session.
            </p>
          </div>
        </div>
      )
    }
    const summary = ticketsFound > 0
      ? `${ticketsFound} bug ticket${ticketsFound !== 1 ? 's' : ''} filed`
      : 'No bugs found this run'
    return (
      <div className="flex items-center gap-3 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3">
        <span className="text-emerald-500 text-lg leading-none">✓</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-emerald-700">Session complete</p>
          <p className="text-xs text-emerald-600 mt-0.5">{summary}</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-3 flex-wrap">
          {!done ? (
            <>
              {lastStatus?.startsWith('qa') && (
                <div className="flex items-center gap-1.5 text-sm text-violet-600">
                  <span className="w-2 h-2 rounded-full bg-violet-500 animate-pulse inline-block" />
                  <span className="font-medium">
                    {lastStatus === 'qa_advising' ? '💬 QA advising coder…' : '🧪 QA agent running…'}
                  </span>
                  {currentAttempt > 0 && (
                    <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-violet-100 text-violet-600">
                      attempt {currentAttempt + 1}
                    </span>
                  )}
                </div>
              )}
              {lastStatus?.startsWith('coder') && (
                <div className="flex items-center gap-1.5 text-sm text-amber-600">
                  <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse inline-block" />
                  <span className="font-medium">🛠️ Coder agent running…</span>
                  <span className="font-mono text-xs px-1.5 py-0.5 rounded bg-amber-100 text-amber-600">
                    fix attempt {currentAttempt + 1}
                  </span>
                </div>
              )}
              {lastStatus === 'hitl_waiting' && (
                <div className="flex items-center gap-1.5 text-sm text-yellow-600">
                  <span className="w-2 h-2 rounded-full bg-yellow-400 animate-pulse inline-block" />
                  <span className="font-medium">🔖 Filing ticket…</span>
                </div>
              )}
              {!lastStatus && (
                <div className="flex items-center gap-1.5 text-sm text-gray-400">
                  <span className="w-2 h-2 rounded-full bg-gray-300 animate-pulse inline-block" />
                  <span>Starting session…</span>
                </div>
              )}

              {/* Ambient generation state */}
              {(isGenerating || isCallingTool) && (
                <div className="flex items-center gap-1 text-xs text-gray-400 font-mono">
                  {isGenerating ? (
                    <>✍️ Generating<ThinkingDots /></>
                  ) : (
                    <>⚡ <span className="italic">{lastEvent?.tool ?? 'tool'}</span><ThinkingDots /></>
                  )}
                </div>
              )}
            </>
          ) : null}
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

      {budgetPause && (
        <div className="rounded-lg border border-amber-300 bg-amber-50 p-4 flex items-center justify-between gap-4">
          <div className="text-sm text-amber-800">
            <span className="font-semibold">Budget reached</span> — spent{' '}
            <span className="font-mono">${budgetPause.cost.toFixed(4)}</span> of{' '}
            <span className="font-mono">${budgetPause.budget.toFixed(2)}</span> limit.
            Continue with +20% grace or terminate?
          </div>
          <div className="flex gap-2 shrink-0">
            <button
              type="button"
              disabled={budgetDeciding}
              className="px-3 py-1.5 text-xs font-medium rounded bg-amber-500 text-white hover:bg-amber-600 disabled:opacity-50"
              onClick={async () => {
                setBudgetDeciding(true)
                await postSessionBudgetDecision(projectId, sessionId, 'continue').catch(() => null)
              }}
            >
              Continue
            </button>
            <button
              type="button"
              disabled={budgetDeciding}
              className="px-3 py-1.5 text-xs font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300 disabled:opacity-50"
              onClick={async () => {
                setBudgetDeciding(true)
                await postSessionBudgetDecision(projectId, sessionId, 'terminate').catch(() => null)
              }}
            >
              Terminate
            </button>
          </div>
        </div>
      )}

      <AgentTimeline events={events} showThoughts={showThoughts} />

      {/* QA early exit banner */}
      {qaEarlyExit && (
        <div className="flex items-start gap-3 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3 animate-fade-in">
          <span className="text-teal-500 text-lg leading-none mt-0.5">🤖</span>
          <div>
            <p className="text-sm font-semibold text-teal-700">QA Advisor satisfied — loop ended early</p>
            <p className="text-xs text-teal-600 mt-0.5 leading-relaxed">{qaEarlyExit}</p>
          </div>
        </div>
      )}

      {/* Completion banner */}
      {done && <DoneBar />}

    </div>
  )
}

import { useEffect, useRef, useState } from 'react'
import { getRunEvents } from '../api/runs'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

export function LiveAgentView({
  projectId,
  runId,
  onComplete,
}: {
  projectId: number
  runId: string
  onComplete?: (status: string) => void
}) {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState<string | null>(null)
  const [showThoughts, setShowThoughts] = useState(true)
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    let cancelled = false

    async function loadFromLog() {
      try {
        const logged = await getRunEvents(projectId, runId)
        if (!cancelled && logged.length > 0) {
          setEvents(logged)
          const doneEvent = logged.find((e) => e.type === 'done')
          if (doneEvent) {
            setSummary(
              `Audit complete — ${doneEvent.total_input_tokens?.toLocaleString()} in / ` +
                `${doneEvent.total_output_tokens?.toLocaleString()} out tokens` +
                (doneEvent.cost_usd !== undefined ? ` ($${doneEvent.cost_usd.toFixed(4)})` : ''),
            )
          }
        }
      } catch {
        // silently ignore — empty events list is fine
      }
      if (!cancelled) setDone(true)
    }

    const es = new EventSource(`/api/projects/${projectId}/runs/${runId}/stream`)

    es.onmessage = (e) => {
      if (cancelled) return
      const event = JSON.parse(e.data) as AgentEvent
      setEvents((prev) => [...prev, event])

      if (event.type === 'done') {
        setSummary(
          `Audit complete — ${event.total_input_tokens?.toLocaleString()} in / ` +
            `${event.total_output_tokens?.toLocaleString()} out tokens` +
            (event.cost_usd !== undefined ? ` ($${event.cost_usd.toFixed(4)})` : ''),
        )
        setDone(true)
        es.close()
        onCompleteRef.current?.('done')
      } else if (event.type === 'budget_exceeded') {
        setSummary(`Budget limit reached ($${event.cost_usd?.toFixed(4)})`)
        setDone(true)
        es.close()
        onCompleteRef.current?.('error')
      } else if (event.type === 'error') {
        setDone(true)
        es.close()
        onCompleteRef.current?.('error')
      }
    }

    es.onerror = () => {
      es.close()
      if (cancelled) return
      // Stream unavailable (run already completed or server restarted).
      // Fall back to the persisted event log so the timeline is still shown.
      loadFromLog()
    }

    return () => {
      cancelled = true
      es.close()
    }
  }, [projectId, runId])

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        {!done ? (
          <div className="flex items-center gap-2 text-sm text-blue-600">
            <span className="inline-block w-2 h-2 rounded-full bg-blue-500 animate-pulse" />
            <span className="font-medium">🔍 Reviewer running…</span>
          </div>
        ) : summary ? (
          <div className="flex items-center gap-2 text-sm text-emerald-600">
            <span>✓</span>
            <span>{summary}</span>
          </div>
        ) : (
          <div />
        )}
        <button
          type="button"
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-xs font-medium transition-colors ${
            showThoughts
              ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
              : 'bg-gray-50 border-gray-200 text-gray-500 hover:border-gray-300'
          }`}
          onClick={() => setShowThoughts((p) => !p)}
        >
          <span>{showThoughts ? '🧠 Hide thoughts' : '🧠 Show thoughts'}</span>
        </button>
      </div>

      <AgentTimeline events={events} defaultLabel="Reviewer" showThoughts={showThoughts} />
    </div>
  )
}

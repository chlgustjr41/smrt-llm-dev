import { useEffect, useRef, useState } from 'react'
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
  const onCompleteRef = useRef(onComplete)
  onCompleteRef.current = onComplete

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/runs/${runId}/stream`)

    es.onmessage = (e) => {
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
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, runId])

  return (
    <div className="space-y-3">
      <AgentTimeline events={events} defaultLabel="Reviewer" />
      {summary && <p className="text-sm text-gray-500 italic">{summary}</p>}
      {!done && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="animate-pulse">●</span> Agent running…
        </div>
      )}
    </div>
  )
}

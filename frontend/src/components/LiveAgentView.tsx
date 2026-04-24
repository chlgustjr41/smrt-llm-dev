import { useEffect, useState } from 'react'

interface SseEvent {
  type: string
  text?: string
  tool?: string
  input?: unknown
  result?: string
  message?: string
  total_input_tokens?: number
  total_output_tokens?: number
  cost_usd?: number
}

function EventRow({ event }: { event: SseEvent }) {
  switch (event.type) {
    case 'text_delta':
      return <span className="text-gray-800">{event.text}</span>

    case 'tool_use':
      return (
        <div className="bg-blue-50 border border-blue-200 rounded px-3 py-1 text-sm font-mono">
          <span className="text-blue-700 font-semibold">→ {event.tool}</span>
          {event.input && Object.keys(event.input as object).length > 0 && (
            <span className="text-blue-500 ml-2">{JSON.stringify(event.input)}</span>
          )}
        </div>
      )

    case 'tool_result':
      return (
        <div className="bg-gray-50 border border-gray-200 rounded px-3 py-1 text-sm font-mono text-gray-600">
          <span className="text-gray-400">← {event.tool}:</span> {event.result}
        </div>
      )

    case 'error':
      return (
        <div className="bg-red-50 border border-red-200 rounded px-3 py-1 text-sm text-red-700">
          Error: {event.message}
        </div>
      )

    default:
      return null
  }
}

export function LiveAgentView({
  projectId,
  runId,
  onComplete,
}: {
  projectId: number
  runId: string
  onComplete?: (status: string) => void
}) {
  const [events, setEvents] = useState<SseEvent[]>([])
  const [done, setDone] = useState(false)
  const [summary, setSummary] = useState<string | null>(null)

  useEffect(() => {
    const es = new EventSource(`/api/projects/${projectId}/runs/${runId}/stream`)

    es.onmessage = (e) => {
      const event = JSON.parse(e.data) as SseEvent
      setEvents((prev) => [...prev, event])

      if (event.type === 'done') {
        setSummary(
          `Audit complete — ${event.total_input_tokens?.toLocaleString()} in / ` +
            `${event.total_output_tokens?.toLocaleString()} out tokens` +
            (event.cost_usd !== undefined ? ` ($${event.cost_usd.toFixed(4)})` : ''),
        )
        setDone(true)
        es.close()
        onComplete?.('done')
      } else if (event.type === 'budget_exceeded') {
        setSummary(`Budget limit reached ($${event.cost_usd?.toFixed(4)})`)
        setDone(true)
        es.close()
        onComplete?.('error')
      } else if (event.type === 'error') {
        setDone(true)
        es.close()
        onComplete?.('error')
      }
    }

    es.onerror = () => {
      setDone(true)
      es.close()
    }

    return () => es.close()
  }, [projectId, runId])

  const textEvents = events.filter((e) => e.type === 'text_delta')
  const toolEvents = events.filter((e) => e.type === 'tool_use' || e.type === 'tool_result')

  return (
    <div className="space-y-3">
      {toolEvents.length > 0 && (
        <div className="space-y-1">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Tool calls</p>
          <div className="space-y-1">
            {toolEvents.map((event, i) => (
              <EventRow key={i} event={event} />
            ))}
          </div>
        </div>
      )}

      {textEvents.length > 0 && (
        <div className="border rounded p-3 bg-white text-sm leading-relaxed">
          {textEvents.map((e, i) => (
            <EventRow key={i} event={e} />
          ))}
        </div>
      )}

      {summary && <p className="text-sm text-gray-500 italic">{summary}</p>}

      {!done && (
        <div className="flex items-center gap-2 text-sm text-gray-400">
          <span className="animate-pulse">●</span> Agent running…
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { getRunEvents } from '../api/runs'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

export function PastRunViewer({ projectId, runId }: { projectId: number; runId: string }) {
  const [events, setEvents] = useState<AgentEvent[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleView() {
    setLoading(true)
    setError(null)
    try {
      const data = await getRunEvents(projectId, runId)
      setEvents(data)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load events')
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <p className="text-xs text-gray-400 p-2">Loading events…</p>
  if (error) return <p className="text-xs text-red-500 px-2 py-1">{error}</p>

  if (events !== null) {
    return (
      <div className="p-2">
        <AgentTimeline events={events} defaultLabel="Reviewer" />
      </div>
    )
  }

  return (
    <button
      onClick={handleView}
      className="text-xs text-blue-600 hover:underline px-2 py-1"
    >
      View events
    </button>
  )
}

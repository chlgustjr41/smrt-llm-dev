import { useState } from 'react'
import { getRunEvents } from '../api/runs'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

export function PastRunViewer({ projectId, runId }: { projectId: number; runId: string }) {
  const [events, setEvents] = useState<AgentEvent[] | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleView() {
    setLoading(true)
    try {
      const data = await getRunEvents(projectId, runId)
      setEvents(data)
    } finally {
      setLoading(false)
    }
  }

  if (loading) return <p className="text-xs text-gray-400 p-2">Loading events…</p>

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

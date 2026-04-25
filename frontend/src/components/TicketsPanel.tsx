import { useEffect, useState } from 'react'
import { listTickets, type Ticket } from '../api/tickets'

function TicketCard({ ticket }: { ticket: Ticket }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="border rounded overflow-hidden border-orange-200">
      <button
        className="w-full text-left px-3 py-2 flex items-center gap-2 bg-orange-50 hover:bg-orange-100"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="font-mono text-xs font-medium text-orange-800">{ticket.id}</span>
        <span className="text-sm text-orange-700 truncate ml-1">{ticket.title}</span>
        <span className="ml-auto text-gray-400 shrink-0">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <pre className="p-3 text-xs whitespace-pre-wrap text-gray-700 bg-white font-sans leading-relaxed">
          {ticket.content}
        </pre>
      )}
    </div>
  )
}

export function TicketsPanel({
  projectId,
  refreshKey,
}: {
  projectId: number
  refreshKey?: number
}) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    listTickets(projectId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setTickets(data) })
      .catch(() => { if (!controller.signal.aborted) setTickets([]) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId, refreshKey])

  if (loading) return <p className="text-xs text-gray-400">Loading tickets…</p>
  if (tickets.length === 0)
    return <p className="text-xs text-gray-400 italic">No bug tickets filed.</p>

  return (
    <div className="space-y-2">
      {tickets.map((t) => (
        <TicketCard key={t.id} ticket={t} />
      ))}
    </div>
  )
}

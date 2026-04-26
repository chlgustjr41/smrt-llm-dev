import { useEffect, useState } from 'react'
import { listTickets, type Ticket, type TicketStatus } from '../api/tickets'

type ColumnConfig = {
  status: TicketStatus
  label: string
  headerCls: string
  borderCls: string
  bgCls: string
  textCls: string
}

const COLUMNS: ColumnConfig[] = [
  {
    status: 'pending_confirmation',
    label: 'Pending Confirmation',
    headerCls: 'bg-orange-50',
    borderCls: 'border-orange-200',
    bgCls: 'bg-orange-50 hover:bg-orange-100',
    textCls: 'text-orange-800',
  },
  {
    status: 'in_progress',
    label: 'In Progress',
    headerCls: 'bg-blue-50',
    borderCls: 'border-blue-200',
    bgCls: 'bg-blue-50 hover:bg-blue-100',
    textCls: 'text-blue-800',
  },
  {
    status: 'needs_review',
    label: 'Needs Human Review',
    headerCls: 'bg-yellow-50',
    borderCls: 'border-yellow-200',
    bgCls: 'bg-yellow-50 hover:bg-yellow-100',
    textCls: 'text-yellow-800',
  },
  {
    status: 'closed',
    label: 'Closed',
    headerCls: 'bg-emerald-50',
    borderCls: 'border-emerald-200',
    bgCls: 'bg-emerald-50 hover:bg-emerald-100',
    textCls: 'text-emerald-800',
  },
]

function TicketCard({ ticket, col }: { ticket: Ticket; col: ColumnConfig }) {
  const [expanded, setExpanded] = useState(false)
  return (
    <div className={`border rounded overflow-hidden ${col.borderCls}`}>
      <button
        className={`w-full text-left px-3 py-2 flex items-center gap-2 ${col.bgCls}`}
        onClick={() => setExpanded((p) => !p)}
      >
        <span className={`font-mono text-xs font-medium ${col.textCls}`}>{ticket.id}</span>
        <span className={`text-sm truncate ml-1 ${col.textCls}`}>{ticket.title}</span>
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

function KanbanColumn({ col, tickets }: { col: ColumnConfig; tickets: Ticket[] }) {
  return (
    <div className={`flex flex-col rounded-xl border ${col.borderCls} overflow-hidden`}>
      <div className={`px-3 py-2 ${col.headerCls} border-b ${col.borderCls}`}>
        <span className={`text-xs font-semibold uppercase tracking-wide ${col.textCls}`}>
          {col.label}
        </span>
        <span className="ml-2 text-xs text-gray-400">{tickets.length}</span>
      </div>
      <div className="flex flex-col gap-2 p-2 flex-1 bg-gray-50 min-h-[4rem]">
        {tickets.length === 0 ? (
          <p className="text-xs text-gray-400 italic px-1 pt-1">None</p>
        ) : (
          tickets.map((t) => <TicketCard key={t.id} ticket={t} col={col} />)
        )}
      </div>
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
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
      {COLUMNS.map((col) => (
        <KanbanColumn
          key={col.status}
          col={col}
          tickets={tickets.filter((t) => t.status === col.status)}
        />
      ))}
    </div>
  )
}

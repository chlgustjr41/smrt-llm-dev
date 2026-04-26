import { useEffect, useRef, useState, useCallback } from 'react'
import Markdown from 'react-markdown'
import { listTickets, approveTicket, type Ticket, type TicketStatus } from '../api/tickets'
import { getCoderStatus, type CoderStatus } from '../api/coder'
import { acceptPR, rejectPR } from '../api/pr'

// ── Column config ─────────────────────────────────────────────────────────

type ColumnConfig = {
  status: TicketStatus
  label: string
  icon: string
  headerCls: string
  borderCls: string
  cardBg: string
  textCls: string
  accentCls: string
  acceptsDrop: boolean
}

const COLUMNS: ColumnConfig[] = [
  {
    status: 'pending_confirmation',
    label: 'Pending Confirmation',
    icon: '⏳',
    headerCls: 'bg-orange-50',
    borderCls: 'border-orange-200',
    cardBg: 'bg-white hover:bg-orange-50',
    textCls: 'text-orange-800',
    accentCls: 'bg-orange-100 text-orange-700',
    acceptsDrop: false,
  },
  {
    status: 'in_progress',
    label: 'In Progress',
    icon: '🛠️',
    headerCls: 'bg-blue-50',
    borderCls: 'border-blue-200',
    cardBg: 'bg-white hover:bg-blue-50',
    textCls: 'text-blue-800',
    accentCls: 'bg-blue-100 text-blue-700',
    acceptsDrop: true,
  },
  {
    status: 'needs_review',
    label: 'Needs Review',
    icon: '👁',
    headerCls: 'bg-yellow-50',
    borderCls: 'border-yellow-200',
    cardBg: 'bg-white hover:bg-yellow-50',
    textCls: 'text-yellow-800',
    accentCls: 'bg-yellow-100 text-yellow-700',
    acceptsDrop: false,
  },
  {
    status: 'closed',
    label: 'Closed',
    icon: '✓',
    headerCls: 'bg-emerald-50',
    borderCls: 'border-emerald-200',
    cardBg: 'bg-white hover:bg-emerald-50',
    textCls: 'text-emerald-800',
    accentCls: 'bg-emerald-100 text-emerald-700',
    acceptsDrop: false,
  },
]

// ── Ticket detail dialog ──────────────────────────────────────────────────

function TicketDialog({
  ticket,
  col,
  onClose,
  onAccept,
  onReject,
}: {
  ticket: Ticket
  col: ColumnConfig
  onClose: () => void
  onAccept?: () => void
  onReject?: () => void
}) {
  // Close on Escape
  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className={`flex items-start justify-between px-5 py-4 border-b ${col.borderCls} ${col.headerCls}`}>
          <div className="space-y-0.5">
            <span className={`inline-block font-mono text-xs px-2 py-0.5 rounded-full ${col.accentCls}`}>
              {ticket.id}
            </span>
            <h2 className="text-base font-semibold text-gray-900 mt-1">{ticket.title}</h2>
            <span className={`inline-flex items-center gap-1 text-xs font-medium ${col.textCls}`}>
              <span>{col.icon}</span>
              <span>{col.label}</span>
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl font-light leading-none mt-0.5 shrink-0"
          >
            ×
          </button>
        </div>

        {/* Body — markdown rendered */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="prose prose-sm max-w-none text-gray-700 [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_pre]:bg-gray-50 [&_pre]:border [&_pre]:border-gray-200 [&_pre]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs">
            <Markdown>{ticket.content}</Markdown>
          </div>
        </div>

        {/* Footer — PR review actions */}
        {ticket.status === 'needs_review' && (onAccept || onReject) && (
          <div className="flex items-center gap-3 px-5 py-3 border-t border-gray-100 bg-gray-50">
            <span className="text-xs text-gray-500 flex-1">Accept to merge the fix or reject to requeue it.</span>
            {onReject && (
              <button
                onClick={() => { onReject(); onClose() }}
                className="px-4 py-1.5 bg-red-500 hover:bg-red-600 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Reject
              </button>
            )}
            {onAccept && (
              <button
                onClick={() => { onAccept(); onClose() }}
                className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium rounded-lg transition-colors"
              >
                Accept
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Ticket card ────────────────────────────────────────────────────────────

function TicketCard({
  ticket,
  col,
  draggable,
  onClick,
}: {
  ticket: Ticket
  col: ColumnConfig
  draggable?: boolean
  onClick: () => void
}) {
  function onDragStart(e: React.DragEvent) {
    e.dataTransfer.setData('ticketId', ticket.id)
    e.dataTransfer.effectAllowed = 'move'
  }

  return (
    <div
      draggable={draggable}
      onDragStart={draggable ? onDragStart : undefined}
      onClick={onClick}
      className={`
        rounded-lg border ${col.borderCls} ${col.cardBg}
        px-3 py-2.5 cursor-pointer select-none transition-colors
        ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}
        shadow-sm hover:shadow-md
      `}
    >
      <div className="flex items-start gap-2">
        <span className={`font-mono text-[11px] shrink-0 mt-0.5 px-1.5 py-0.5 rounded ${col.accentCls}`}>
          {ticket.id}
        </span>
        <span className="text-sm text-gray-800 leading-snug line-clamp-2">{ticket.title}</span>
      </div>
      {draggable && (
        <p className="text-[10px] text-gray-400 mt-1.5 italic">Drag → In Progress to approve</p>
      )}
    </div>
  )
}

// ── Kanban column ─────────────────────────────────────────────────────────

function KanbanColumn({
  col,
  tickets,
  width,
  onDrop,
  onTicketClick,
}: {
  col: ColumnConfig
  tickets: Ticket[]
  width: number
  onDrop?: (ticketId: string) => void
  onTicketClick: (ticket: Ticket) => void
}) {
  const [dragOver, setDragOver] = useState(false)

  function handleDragOver(e: React.DragEvent) {
    if (!col.acceptsDrop) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(true)
  }

  function handleDragLeave() { setDragOver(false) }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const ticketId = e.dataTransfer.getData('ticketId')
    if (ticketId) onDrop?.(ticketId)
  }

  return (
    <div
      className="flex flex-col rounded-xl border overflow-hidden"
      style={{ width: `${width}%`, minWidth: '12%', flexShrink: 0 }}
    >
      {/* Column header */}
      <div className={`px-3 py-2.5 ${col.headerCls} border-b ${col.borderCls} flex items-center gap-2`}>
        <span className="text-sm">{col.icon}</span>
        <span className={`text-xs font-semibold ${col.textCls} flex-1`}>{col.label}</span>
        <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${col.accentCls}`}>
          {tickets.length}
        </span>
      </div>

      {/* Drop zone */}
      <div
        className={`flex flex-col gap-2 p-2 flex-1 transition-colors min-h-[8rem] ${
          dragOver ? 'bg-blue-50 ring-2 ring-blue-300 ring-inset' : 'bg-gray-50'
        }`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {col.acceptsDrop && tickets.length === 0 && (
          <div className={`flex-1 flex items-center justify-center rounded-lg border-2 border-dashed transition-colors ${
            dragOver ? 'border-blue-400' : 'border-gray-200'
          }`}>
            <p className="text-xs text-gray-400 italic text-center px-2">
              Drop tickets here<br />to approve for Coder
            </p>
          </div>
        )}
        {tickets.length > 0 &&
          tickets.map((t) => (
            <TicketCard
              key={t.id}
              ticket={t}
              col={col}
              draggable={col.status === 'pending_confirmation'}
              onClick={() => onTicketClick(t)}
            />
          ))}
        {!col.acceptsDrop && tickets.length === 0 && (
          <p className="text-xs text-gray-400 italic px-1 pt-1">None</p>
        )}
      </div>
    </div>
  )
}

// ── Resize handle ─────────────────────────────────────────────────────────

function ResizeHandle({
  colIndex,
  boardRef,
  colWidths,
  onWidthChange,
}: {
  colIndex: number
  boardRef: React.RefObject<HTMLDivElement | null>
  colWidths: number[]
  onWidthChange: (widths: number[]) => void
}) {
  const handleRef = useRef<HTMLDivElement>(null)
  const [dragging, setDragging] = useState(false)

  function onPointerDown(e: React.PointerEvent) {
    e.preventDefault()
    const handle = handleRef.current
    if (!handle) return
    handle.setPointerCapture(e.pointerId)
    setDragging(true)

    const startX = e.clientX
    const startWidths = [...colWidths]
    const totalWidth = boardRef.current?.offsetWidth ?? 800

    function onPointerMove(ev: PointerEvent) {
      const deltaX = ev.clientX - startX
      const deltaPct = (deltaX / totalWidth) * 100
      const newWidths = [...startWidths]
      newWidths[colIndex] = Math.max(10, startWidths[colIndex] + deltaPct)
      newWidths[colIndex + 1] = Math.max(10, startWidths[colIndex + 1] - deltaPct)
      // Re-normalise so they always sum to 100
      const total = newWidths.reduce((a, b) => a + b, 0)
      onWidthChange(newWidths.map((w) => (w / total) * 100))
    }

    function onPointerUp() {
      setDragging(false)
      handle.removeEventListener('pointermove', onPointerMove)
      handle.removeEventListener('pointerup', onPointerUp)
    }

    handle.addEventListener('pointermove', onPointerMove)
    handle.addEventListener('pointerup', onPointerUp)
  }

  return (
    <div
      ref={handleRef}
      onPointerDown={onPointerDown}
      className={`w-1.5 shrink-0 cursor-col-resize flex items-center justify-center group ${
        dragging ? 'bg-blue-200' : 'bg-transparent hover:bg-gray-200'
      } transition-colors rounded-full mx-0.5`}
    >
      <div className={`w-0.5 h-8 rounded-full transition-colors ${
        dragging ? 'bg-blue-400' : 'bg-gray-300 group-hover:bg-gray-400'
      }`} />
    </div>
  )
}

// ── Coder status banner ───────────────────────────────────────────────────

function CoderStatusBanner({
  projectId,
  inProgressCount,
}: {
  projectId: number
  inProgressCount: number
}) {
  const [status, setStatus] = useState<CoderStatus | null>(null)

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await getCoderStatus(projectId, signal)
      setStatus(s)
    } catch {
      // silently ignore — banner just won't update
    }
  }, [projectId])

  useEffect(() => {
    const ac = new AbortController()
    fetchStatus(ac.signal)
    const interval = setInterval(() => fetchStatus(), 8000)
    return () => { ac.abort(); clearInterval(interval) }
  }, [fetchStatus])

  if (!status) return null

  if (status.idle) {
    return (
      <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg border border-gray-200 bg-gray-50 text-sm">
        <span className="text-gray-400 text-base">⚙️</span>
        <span className="font-medium text-gray-500">Coder Agent</span>
        <span className="text-gray-400">—</span>
        <span className="text-gray-500">Idle</span>
        {inProgressCount > 0 && (
          <span className="ml-auto text-xs text-blue-600 font-medium">
            {inProgressCount} ticket{inProgressCount !== 1 ? 's' : ''} queued — start a QA session to begin
          </span>
        )}
      </div>
    )
  }

  const statusLabel =
    status.status === 'coder_running' ? 'Coding fix' :
    status.status === 'qa_running'    ? 'Running QA tests' :
    status.status ?? 'Working'

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 rounded-lg border border-amber-200 bg-amber-50 text-sm">
      <span className="w-2 h-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
      <span className="font-medium text-amber-800">Coder Agent</span>
      <span className="text-amber-600">—</span>
      <span className="text-amber-700">{statusLabel}</span>
      {status.ticket_id && (
        <span className="font-mono text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
          {status.ticket_id}
        </span>
      )}
      <span className="ml-auto font-mono text-[10px] text-amber-500 truncate max-w-[12rem]">
        {status.session_id}
      </span>
    </div>
  )
}

// ── Public component ───────────────────────────────────────────────────────

export function TicketsPanel({
  projectId,
  refreshKey,
  onReviewed,
}: {
  projectId: number
  refreshKey?: number
  onReviewed?: () => void
}) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTicket, setSelectedTicket] = useState<Ticket | null>(null)
  const [colWidths, setColWidths] = useState([25, 25, 25, 25])
  const boardRef = useRef<HTMLDivElement>(null)

  function refresh() {
    setLoading(true)
    listTickets(projectId)
      .then(setTickets)
      .catch(() => setTickets([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    listTickets(projectId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setTickets(data) })
      .catch(() => { if (!controller.signal.aborted) setTickets([]) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId, refreshKey])

  async function handleDrop(ticketId: string) {
    const ticket = tickets.find((t) => t.id === ticketId)
    if (!ticket || ticket.status !== 'pending_confirmation') return
    // Optimistically update status
    setTickets((prev) =>
      prev.map((t) => (t.id === ticketId ? { ...t, status: 'in_progress' } : t)),
    )
    try {
      await approveTicket(projectId, ticketId)
    } catch {
      // Roll back on failure
      refresh()
    }
  }

  async function handleAccept(ticket: Ticket) {
    await acceptPR(projectId, ticket.id)
    refresh()
    onReviewed?.()
  }

  async function handleReject(ticket: Ticket) {
    await rejectPR(projectId, ticket.id)
    refresh()
    onReviewed?.()
  }

  const inProgressCount = tickets.filter((t) => t.status === 'in_progress').length
  const selectedCol = selectedTicket
    ? (COLUMNS.find((c) => c.status === selectedTicket.status) ?? COLUMNS[0])
    : null

  if (loading) return <p className="text-xs text-gray-400 px-1 py-2">Loading tickets…</p>
  if (tickets.length === 0) {
    return <p className="text-xs text-gray-400 italic px-1 py-2">No bug tickets filed yet.</p>
  }

  return (
    <div className="space-y-3">
      {/* Coder status banner */}
      <CoderStatusBanner projectId={projectId} inProgressCount={inProgressCount} />

      {/* Kanban board — horizontally scrollable so columns always have room */}
      <div className="overflow-x-auto">
        <div
          ref={boardRef}
          className="flex gap-0 min-w-[600px]"
          style={{ width: '100%' }}
        >
          {COLUMNS.map((col, i) => (
            <div key={col.status} className="flex items-stretch">
              <KanbanColumn
                col={col}
                tickets={tickets.filter((t) => t.status === col.status)}
                width={colWidths[i]}
                onDrop={col.acceptsDrop ? handleDrop : undefined}
                onTicketClick={setSelectedTicket}
              />
              {i < COLUMNS.length - 1 && (
                <ResizeHandle
                  colIndex={i}
                  boardRef={boardRef}
                  colWidths={colWidths}
                  onWidthChange={setColWidths}
                />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Ticket detail dialog */}
      {selectedTicket && selectedCol && (
        <TicketDialog
          ticket={selectedTicket}
          col={selectedCol}
          onClose={() => setSelectedTicket(null)}
          onAccept={
            selectedTicket.status === 'needs_review'
              ? () => handleAccept(selectedTicket)
              : undefined
          }
          onReject={
            selectedTicket.status === 'needs_review'
              ? () => handleReject(selectedTicket)
              : undefined
          }
        />
      )}
    </div>
  )
}

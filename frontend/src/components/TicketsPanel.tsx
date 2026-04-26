import { useEffect, useRef, useState, useCallback } from 'react'
import Markdown from 'react-markdown'
import { listTickets, approveTicket, type Ticket, type TicketStatus } from '../api/tickets'
import { getCoderStatus, type CoderStatus } from '../api/coder'
import { getQASessionEvents } from '../api/qa_sessions'
import { acceptPR, rejectPR } from '../api/pr'
import { AgentTimeline, type AgentEvent } from './AgentTimeline'

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
    status: 'qa_review',
    label: 'QA Review',
    icon: '🔬',
    headerCls: 'bg-violet-50',
    borderCls: 'border-violet-200',
    cardBg: 'bg-white hover:bg-violet-50',
    textCls: 'text-violet-800',
    accentCls: 'bg-violet-100 text-violet-700',
    acceptsDrop: false,
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

// ── Expandable session events pane ────────────────────────────────────────

function SessionEventsPane({
  projectId,
  sessionId,
}: {
  projectId: number
  sessionId: string
}) {
  const [events, setEvents] = useState<AgentEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    getQASessionEvents(projectId, sessionId, ac.signal)
      .then(setEvents)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== 'AbortError') setError(e.message)
      })
    return () => ac.abort()
  }, [projectId, sessionId])

  if (error) return <p className="text-xs text-red-500 px-3 py-2">{error}</p>
  if (!events) return <p className="text-xs text-gray-400 px-3 py-2 animate-pulse">Loading events…</p>
  if (events.length === 0) return <p className="text-xs text-gray-400 italic px-3 py-2">No events recorded yet.</p>

  return (
    <div className="border-t border-gray-100 bg-gray-50 px-3 py-3 max-h-72 overflow-y-auto">
      <AgentTimeline events={events} showThoughts />
    </div>
  )
}

// ── Ticket detail dialog ──────────────────────────────────────────────────

function TicketDialog({
  ticket,
  col,
  projectId,
  onClose,
  onAccept,
  onReject,
}: {
  ticket: Ticket
  col: ColumnConfig
  projectId: number
  onClose: () => void
  onAccept?: () => void
  onReject?: () => void
}) {
  const [showEvents, setShowEvents] = useState(false)

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
        className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden"
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
          <div className="flex items-center gap-2 shrink-0 mt-0.5">
            {ticket.session_id && (
              <button
                onClick={() => setShowEvents((x) => !x)}
                className="text-xs px-2.5 py-1 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-100 transition-colors"
              >
                {showEvents ? '▲ Hide log' : '▼ Agent log'}
              </button>
            )}
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-gray-600 text-xl font-light leading-none"
            >
              ×
            </button>
          </div>
        </div>

        {/* Agent log pane (collapsible) */}
        {showEvents && ticket.session_id && (
          <div className="border-b border-gray-100 max-h-60 overflow-y-auto bg-gray-50 px-5 py-3">
            <SessionEventsPane projectId={projectId} sessionId={ticket.session_id} />
          </div>
        )}

        {/* Ticket content */}
        <div className="flex-1 overflow-y-auto p-5">
          <div className="prose prose-sm max-w-none text-gray-700 [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_pre]:bg-gray-50 [&_pre]:border [&_pre]:border-gray-200 [&_pre]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs">
            <Markdown>{ticket.content}</Markdown>
          </div>
        </div>

        {/* Accept / Reject actions */}
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
  projectId,
  draggable,
  onClick,
}: {
  ticket: Ticket
  col: ColumnConfig
  projectId: number
  draggable?: boolean
  onClick: () => void
}) {
  const [showLogs, setShowLogs] = useState(false)

  function onDragStart(e: React.DragEvent) {
    e.dataTransfer.setData('ticketId', ticket.id)
    e.dataTransfer.effectAllowed = 'move'
  }

  const hasSession = Boolean(ticket.session_id)
  const isActive = ticket.status === 'in_progress' || ticket.status === 'qa_review'

  return (
    <div className="rounded-lg border overflow-hidden shadow-sm hover:shadow-md transition-shadow">
      {/* Card body */}
      <div
        draggable={draggable}
        onDragStart={draggable ? onDragStart : undefined}
        onClick={onClick}
        className={`
          ${col.borderCls} ${col.cardBg}
          px-3 py-2.5 cursor-pointer select-none transition-colors
          ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}
        `}
      >
        <div className="flex items-start gap-2">
          <span className={`font-mono text-[11px] shrink-0 mt-0.5 px-1.5 py-0.5 rounded ${col.accentCls}`}>
            {ticket.id}
          </span>
          <span className="text-sm text-gray-800 leading-snug line-clamp-2 flex-1">{ticket.title}</span>
        </div>
        {draggable && (
          <p className="text-[10px] text-gray-400 mt-1.5 italic">Drag → In Progress to start Coder fix</p>
        )}
      </div>

      {/* Agent log toggle — shown when ticket has a session and is active/done */}
      {hasSession && (
        <div className={`border-t ${col.borderCls} px-2 py-1 flex items-center gap-2 ${col.headerCls}`}>
          {isActive && (
            <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse shrink-0 opacity-60" style={{ color: 'currentColor' }} />
          )}
          <button
            onClick={(e) => { e.stopPropagation(); setShowLogs((x) => !x) }}
            className={`text-[11px] font-medium flex-1 text-left ${col.textCls} hover:underline`}
          >
            {showLogs
              ? '▲ Hide agent log'
              : isActive
                ? `▼ ${ticket.status === 'qa_review' ? 'QA checking…' : 'Coder fixing…'} view log`
                : '▼ View agent log'
            }
          </button>
        </div>
      )}

      {/* Inline log pane */}
      {showLogs && ticket.session_id && (
        <SessionEventsPane projectId={projectId} sessionId={ticket.session_id} />
      )}
    </div>
  )
}

// ── Kanban column ─────────────────────────────────────────────────────────

function KanbanColumn({
  col,
  tickets,
  projectId,
  onDrop,
  onTicketClick,
}: {
  col: ColumnConfig
  tickets: Ticket[]
  projectId: number
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
    <div className="flex flex-col rounded-xl border overflow-hidden min-w-0">
      <div className={`px-3 py-2.5 ${col.headerCls} border-b ${col.borderCls} flex items-center gap-2`}>
        <span className="text-sm">{col.icon}</span>
        <span className={`text-xs font-semibold ${col.textCls} flex-1`}>{col.label}</span>
        <span className={`text-xs font-medium px-1.5 py-0.5 rounded-full ${col.accentCls}`}>
          {tickets.length}
        </span>
      </div>

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
              Drop tickets here<br />to start Coder fix
            </p>
          </div>
        )}
        {tickets.map((t) => (
          <TicketCard
            key={t.id}
            ticket={t}
            col={col}
            projectId={projectId}
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
    const totalFr = startWidths.reduce((a, b) => a + b, 0)
    const totalWidth = boardRef.current?.offsetWidth ?? 900

    function onPointerMove(ev: PointerEvent) {
      const deltaFr = ((ev.clientX - startX) / totalWidth) * totalFr
      const newWidths = [...startWidths]
      newWidths[colIndex] = Math.max(0.15, startWidths[colIndex] + deltaFr)
      newWidths[colIndex + 1] = Math.max(0.15, startWidths[colIndex + 1] - deltaFr)
      const newTotal = newWidths.reduce((a, b) => a + b, 0)
      onWidthChange(newWidths.map((w) => (w / newTotal) * totalFr))
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

// ── Loop status banner ────────────────────────────────────────────────────

function LoopStatusBanner({ projectId }: { projectId: number }) {
  const [status, setStatus] = useState<CoderStatus | null>(null)

  const fetchStatus = useCallback(async (signal?: AbortSignal) => {
    try {
      setStatus(await getCoderStatus(projectId, signal))
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

  if (!status || status.idle) return null

  const isCoderRunning = status.status === 'coder_running'
  const isQaChecking = status.status === 'qa_checking'

  const color = isCoderRunning
    ? { border: 'border-amber-200', bg: 'bg-amber-50', dot: 'bg-amber-500', text: 'text-amber-800', badge: 'bg-amber-100 text-amber-700' }
    : isQaChecking
      ? { border: 'border-violet-200', bg: 'bg-violet-50', dot: 'bg-violet-500', text: 'text-violet-800', badge: 'bg-violet-100 text-violet-700' }
      : { border: 'border-gray-200', bg: 'bg-gray-50', dot: 'bg-gray-400', text: 'text-gray-600', badge: 'bg-gray-100 text-gray-600' }

  const label = isCoderRunning
    ? 'Coder Agent — fixing bug'
    : isQaChecking
      ? 'QA Agent — verifying fix'
      : `Running (${status.status})`

  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border ${color.border} ${color.bg} text-sm`}>
      <span className={`w-2 h-2 rounded-full ${color.dot} animate-pulse shrink-0`} />
      <span className={`font-medium ${color.text}`}>{label}</span>
      {status.ticket_id && (
        <span className={`font-mono text-xs px-2 py-0.5 rounded-full ${color.badge}`}>
          {status.ticket_id}
        </span>
      )}
      <span className={`text-xs ${color.text} opacity-70 ml-auto`}>
        {isCoderRunning ? 'Editing source files…' : 'Running test suite…'}
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
  const [colWidths, setColWidths] = useState([1, 1, 1, 1, 1])
  const boardRef = useRef<HTMLDivElement>(null)

  const fetchTickets = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await listTickets(projectId, signal)
      if (!signal?.aborted) setTickets(data)
    } catch {
      if (!signal?.aborted) setTickets([])
    } finally {
      if (!signal?.aborted) setLoading(false)
    }
  }, [projectId])

  // Initial load + refresh on refreshKey change
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetchTickets(controller.signal)
    return () => controller.abort()
  }, [projectId, refreshKey, fetchTickets])

  // Poll every 8s while any ticket has an active session (coder/QA running)
  useEffect(() => {
    const hasActiveSession = tickets.some(
      (t) => t.session_id && (t.status === 'in_progress' || t.status === 'qa_review'),
    )
    if (!hasActiveSession) return
    const interval = setInterval(() => fetchTickets(), 8000)
    return () => clearInterval(interval)
  }, [tickets, fetchTickets])

  async function handleDrop(ticketId: string) {
    const ticket = tickets.find((t) => t.id === ticketId)
    if (!ticket || ticket.status !== 'pending_confirmation') return

    // Optimistically move to in_progress
    setTickets((prev) =>
      prev.map((t) => (t.id === ticketId ? { ...t, status: 'in_progress' } : t)),
    )
    try {
      const result = await approveTicket(projectId, ticketId)
      // Update the ticket with the real session_id returned from approve
      setTickets((prev) =>
        prev.map((t) =>
          t.id === ticketId
            ? { ...t, status: 'in_progress', session_id: result.session_id }
            : t,
        ),
      )
    } catch {
      await fetchTickets()
    }
  }

  async function handleAccept(ticket: Ticket) {
    await acceptPR(projectId, ticket.id)
    await fetchTickets()
    onReviewed?.()
  }

  async function handleReject(ticket: Ticket) {
    await rejectPR(projectId, ticket.id)
    await fetchTickets()
    onReviewed?.()
  }

  const selectedCol = selectedTicket
    ? (COLUMNS.find((c) => c.status === selectedTicket.status) ?? COLUMNS[0])
    : null

  if (loading) return <p className="text-xs text-gray-400 px-1 py-2">Loading tickets…</p>
  if (tickets.length === 0) {
    return <p className="text-xs text-gray-400 italic px-1 py-2">No bug tickets filed yet.</p>
  }

  return (
    <div className="space-y-3">
      {/* Active agent status banner */}
      <LoopStatusBanner projectId={projectId} />

      {/* Kanban board — CSS grid, fr units resolve against the board container */}
      <div className="overflow-x-auto">
        <div
          ref={boardRef}
          style={{
            display: 'grid',
            gridTemplateColumns: colWidths
              .map((w, i) => (i < colWidths.length - 1 ? `${w}fr 8px` : `${w}fr`))
              .join(' '),
            minWidth: '800px',
            width: '100%',
          }}
        >
          {COLUMNS.flatMap((col, i) => [
            <KanbanColumn
              key={col.status}
              col={col}
              tickets={tickets.filter((t) => t.status === col.status)}
              projectId={projectId}
              onDrop={col.acceptsDrop ? handleDrop : undefined}
              onTicketClick={setSelectedTicket}
            />,
            ...(i < COLUMNS.length - 1
              ? [
                  <ResizeHandle
                    key={`handle-${i}`}
                    colIndex={i}
                    boardRef={boardRef}
                    colWidths={colWidths}
                    onWidthChange={setColWidths}
                  />,
                ]
              : []),
          ])}
        </div>
      </div>

      {/* Ticket detail dialog */}
      {selectedTicket && selectedCol && (
        <TicketDialog
          ticket={selectedTicket}
          col={selectedCol}
          projectId={projectId}
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

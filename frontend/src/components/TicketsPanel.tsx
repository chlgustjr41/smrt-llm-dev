import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import Markdown from 'react-markdown'
import { listTickets, approveTicket, getTicketSessions, type Ticket, type TicketStatus, type TicketSession, type TicketFailureReport } from '../api/tickets'
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

// ── Status badge for sessions ─────────────────────────────────────────────

function sessionStatusBadge(status: string): string {
  const map: Record<string, string> = {
    coder_running: 'bg-amber-100 text-amber-700 border-amber-200',
    qa_checking: 'bg-violet-100 text-violet-700 border-violet-200',
    done: 'bg-emerald-100 text-emerald-700 border-emerald-200',
    error: 'bg-red-100 text-red-600 border-red-200',
    pending: 'bg-gray-100 text-gray-600 border-gray-200',
  }
  return map[status] ?? 'bg-gray-100 text-gray-500 border-gray-200'
}

function sessionStatusLabel(status: string): string {
  const map: Record<string, string> = {
    coder_running: '🛠️ Coder fixing',
    qa_checking: '🔬 QA verifying',
    done: '✓ Done',
    error: '✗ Error',
    pending: 'Pending',
  }
  return map[status] ?? status
}

function formatRelTime(iso: string | null): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const diff = Date.now() - d.getTime()
  const min = Math.floor(diff / 60_000)
  if (min < 1) return 'just now'
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

// ── Per-session event pane (polls JSONL for live sessions) ─────────────────

function SessionEventPane({
  projectId,
  session,
  isActive,
}: {
  projectId: number
  session: TicketSession
  isActive: boolean
}) {
  const [events, setEvents] = useState<AgentEvent[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [showThoughts, setShowThoughts] = useState(true)

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getQASessionEvents(projectId, session.session_id, signal)
      if (!signal?.aborted) setEvents(data)
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== 'AbortError') {
        setError(e.message)
      }
    }
  }, [projectId, session.session_id])

  // Initial load
  useEffect(() => {
    const ac = new AbortController()
    load(ac.signal)
    return () => ac.abort()
  }, [load])

  // Poll every 2 s while session is active so live events show up promptly
  useEffect(() => {
    if (!isActive) return
    const interval = setInterval(() => load(), 2000)
    return () => clearInterval(interval)
  }, [isActive, load])

  // Live thought ticker — last text segment since the most recent tool boundary
  const liveThought = useMemo(() => {
    if (!isActive || !events) return ''
    let start = 0
    for (let i = events.length - 1; i >= 0; i--) {
      if (['session_status', 'tool_result', 'tool_use'].includes(events[i].type)) {
        start = i + 1
        break
      }
    }
    return events
      .slice(start)
      .filter((e) => ['text_delta', 'qa_text_delta', 'coder_text_delta'].includes(e.type))
      .map((e) => e.text ?? '')
      .join('')
      .slice(-200)
  }, [events, isActive])

  if (error) return (
    <p className="text-xs text-red-500 px-3 py-2">{error}</p>
  )
  if (!events) return (
    <p className="text-xs text-gray-400 px-3 py-2 animate-pulse">Loading events…</p>
  )
  if (events.length === 0) return (
    <p className="text-xs text-gray-400 italic px-3 py-2">No events recorded yet.</p>
  )

  return (
    <div className="bg-gray-50 border-t border-gray-100 px-3 py-3 space-y-2.5">
      {/* Controls row */}
      <div className="flex items-center justify-between gap-2">
        {isActive && (
          <div className="flex items-center gap-1.5 text-xs text-amber-600">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            <span className="font-medium">Live — updates every 2 s</span>
          </div>
        )}
        <button
          type="button"
          className={`ml-auto inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium transition-colors ${
            showThoughts
              ? 'bg-indigo-50 border-indigo-200 text-indigo-700'
              : 'bg-white border-gray-200 text-gray-500 hover:border-gray-300'
          }`}
          onClick={() => setShowThoughts((p) => !p)}
        >
          🧠 {showThoughts ? 'Hide thoughts' : 'Show thoughts'}
        </button>
      </div>

      {/* Live thought ticker */}
      {isActive && liveThought && (
        <div className="flex items-start gap-2 px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-100 text-xs text-indigo-700 font-mono leading-relaxed">
          <span className="shrink-0 opacity-60 mt-px">💭</span>
          <span className="break-words whitespace-pre-wrap line-clamp-3">{liveThought}</span>
        </div>
      )}

      {/* Timeline (scrollable) */}
      <div className="max-h-96 overflow-y-auto pr-0.5">
        <AgentTimeline events={events} showThoughts={showThoughts} />
      </div>
    </div>
  )
}

// ── Per-ticket session history ────────────────────────────────────────────

function TicketSessionHistory({
  projectId,
  ticketId,
  activeSessionId,
}: {
  projectId: number
  ticketId: string
  activeSessionId: string | null
}) {
  const [sessions, setSessions] = useState<TicketSession[] | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(activeSessionId)

  useEffect(() => {
    const ac = new AbortController()
    getTicketSessions(projectId, ticketId, ac.signal)
      .then((s) => {
        setSessions(s)
        // Auto-expand the active session
        if (activeSessionId) setExpandedId(activeSessionId)
        else if (s.length > 0) setExpandedId(s[0].session_id)
      })
      .catch(() => setSessions([]))
    return () => ac.abort()
  }, [projectId, ticketId, activeSessionId])

  if (sessions === null) return (
    <div className="px-3 py-2 text-xs text-gray-400 animate-pulse">Loading session history…</div>
  )
  if (sessions.length === 0) return (
    <div className="px-3 py-2 text-xs text-gray-400 italic">No sessions recorded yet.</div>
  )

  return (
    <div className="divide-y divide-gray-100">
      {sessions.map((s, i) => {
        const isActive = s.session_id === activeSessionId
        const isOpen = expandedId === s.session_id

        return (
          <div key={s.session_id}>
            <button
              type="button"
              className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-gray-50 transition-colors"
              onClick={() => setExpandedId(isOpen ? null : s.session_id)}
            >
              <span className="text-[10px] text-gray-400 w-3 text-center shrink-0">
                {isOpen ? '▾' : '▸'}
              </span>
              <span className="text-xs font-medium text-gray-600 shrink-0">
                Session {sessions.length - i}
              </span>
              {isActive && (
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse shrink-0" />
              )}
              <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-medium ${sessionStatusBadge(s.status)}`}>
                {sessionStatusLabel(s.status)}
              </span>
              <span className="ml-auto text-[10px] text-gray-400 shrink-0">
                {formatRelTime(s.started_at)}
              </span>
            </button>

            {isOpen && (
              <SessionEventPane
                projectId={projectId}
                session={s}
                isActive={isActive}
              />
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Ticket detail dialog ──────────────────────────────────────────────────

function FailureReportBanner({ report }: { report: TicketFailureReport }) {
  const isNotBug = report.recommendation === 'possibly_not_a_bug'
  return (
    <div className={`border-b px-5 py-3 space-y-2 ${isNotBug ? 'bg-orange-50 border-orange-200' : 'bg-red-50 border-red-200'}`}>
      <div className="flex items-center gap-2">
        <span className={`text-sm font-semibold ${isNotBug ? 'text-orange-700' : 'text-red-700'}`}>
          {isNotBug ? '⚠ Possibly not a real bug' : '⚠ Fix loop exhausted — needs more attempts'}
        </span>
      </div>
      <p className={`text-xs leading-relaxed ${isNotBug ? 'text-orange-700' : 'text-red-700'}`}>
        {report.analysis}
      </p>
      <span className={`inline-block text-[11px] px-2 py-0.5 rounded-full font-medium border ${
        isNotBug
          ? 'bg-orange-100 border-orange-300 text-orange-800'
          : 'bg-blue-50 border-blue-200 text-blue-700'
      }`}>
        {isNotBug ? '📋 Recommend: review ticket validity or add targeted tests' : '🔄 Recommend: increase max_fix_attempts or review coder changes manually'}
      </span>
    </div>
  )
}

type DialogTab = 'description' | 'logs'

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
  const hasHistory = Boolean(ticket.session_id)
  const [activeTab, setActiveTab] = useState<DialogTab>(hasHistory ? 'logs' : 'description')

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  const isActive = ticket.status === 'in_progress' || ticket.status === 'qa_review'

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
              {isActive && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
              <span>{col.icon}</span>
              <span>{col.label}</span>
            </span>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl font-light leading-none shrink-0 mt-0.5"
          >
            ×
          </button>
        </div>

        {/* Failure report banner — only for loop-exhausted tickets */}
        {ticket.failure_report && <FailureReportBanner report={ticket.failure_report} />}

        {/* Tab bar */}
        <div className="flex border-b border-gray-100 px-5 gap-4 bg-white">
          <button
            type="button"
            onClick={() => setActiveTab('description')}
            className={`py-2.5 text-sm font-medium border-b-2 transition-colors ${
              activeTab === 'description'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Description
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('logs')}
            className={`py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
              activeTab === 'logs'
                ? 'border-blue-500 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            Agent Logs
            {isActive && <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />}
          </button>
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto">
          {activeTab === 'description' ? (
            <div className="p-5">
              <div className="prose prose-sm max-w-none text-gray-700 [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_pre]:bg-gray-50 [&_pre]:border [&_pre]:border-gray-200 [&_pre]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs">
                <Markdown>{ticket.content}</Markdown>
              </div>
            </div>
          ) : (
            <div className="bg-gray-50 min-h-full">
              {hasHistory ? (
                <TicketSessionHistory
                  projectId={projectId}
                  ticketId={ticket.id}
                  activeSessionId={isActive ? ticket.session_id : null}
                />
              ) : (
                <p className="text-xs text-gray-400 italic px-4 py-6">No agent sessions recorded yet.</p>
              )}
            </div>
          )}
        </div>

        {/* Accept / Reject — only for PR-ready needs_review (no failure_report) */}
        {ticket.status === 'needs_review' && !ticket.failure_report && (onAccept || onReject) && (
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

  const isCoderRunning = ticket.status === 'in_progress'
  const isQaRunning = ticket.status === 'qa_review'
  const isActive = isCoderRunning || isQaRunning
  const hasFailureReport = Boolean(ticket.failure_report)

  // Truncate title to ~40 chars for the card
  const shortTitle = ticket.title.length > 48 ? ticket.title.slice(0, 46) + '…' : ticket.title

  return (
    <div
      draggable={draggable}
      onDragStart={draggable ? onDragStart : undefined}
      onClick={onClick}
      className={`rounded-lg border ${col.borderCls} ${col.cardBg} px-3 py-2.5 cursor-pointer select-none shadow-sm hover:shadow-md transition-all ${draggable ? 'cursor-grab active:cursor-grabbing' : ''}`}
    >
      <div className="flex items-start gap-2">
        <span className={`font-mono text-[11px] shrink-0 mt-0.5 px-1.5 py-0.5 rounded ${col.accentCls}`}>
          {ticket.id}
        </span>
        <span className="text-sm text-gray-800 leading-snug flex-1">{shortTitle}</span>
      </div>

      {/* Agent status badge */}
      {isCoderRunning && (
        <div className="flex items-center gap-1.5 mt-2 px-2 py-1 rounded-md bg-amber-50 border border-amber-200">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse shrink-0" />
          <span className="text-[11px] font-medium text-amber-700">🛠️ Coder fixing…</span>
        </div>
      )}
      {isQaRunning && (
        <div className="flex items-center gap-1.5 mt-2 px-2 py-1 rounded-md bg-violet-50 border border-violet-200">
          <span className="w-1.5 h-1.5 rounded-full bg-violet-500 animate-pulse shrink-0" />
          <span className="text-[11px] font-medium text-violet-700">🔬 QA checking…</span>
        </div>
      )}

      {draggable && !isActive && (
        <p className="text-[10px] text-gray-400 mt-1.5 italic">Drag → In Progress to start Coder fix</p>
      )}
      {hasFailureReport && (
        <p className="text-[10px] text-red-500 mt-1.5 font-medium">
          ⚠ {ticket.failure_report?.recommendation === 'possibly_not_a_bug' ? 'Possibly not a bug' : 'Fix loop exhausted'}
          {' · click for insights'}
        </p>
      )}
      {ticket.session_id && !isActive && !hasFailureReport && (
        <p className="text-[10px] text-gray-400 mt-1">↗ Click to view agent history</p>
      )}
    </div>
  )
}

// ── Kanban column ─────────────────────────────────────────────────────────

function KanbanColumn({
  col,
  tickets,
  onDrop,
  onTicketClick,
}: {
  col: ColumnConfig
  tickets: Ticket[]
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
        className={`flex flex-col gap-2 p-2 flex-1 transition-colors min-h-[28rem] ${
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
      handle!.removeEventListener('pointermove', onPointerMove)
      handle!.removeEventListener('pointerup', onPointerUp)
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
      // silently ignore
    }
  }, [projectId])

  useEffect(() => {
    const ac = new AbortController()
    fetchStatus(ac.signal)
    const interval = setInterval(() => fetchStatus(), 5000)
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

  const detail = isCoderRunning
    ? 'Editing source files…'
    : 'Running test suite…'

  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border ${color.border} ${color.bg}`}>
      <span className={`w-2 h-2 rounded-full ${color.dot} animate-pulse shrink-0`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-sm font-medium ${color.text}`}>{label}</span>
          {status.ticket_id && (
            <span className={`font-mono text-xs px-2 py-0.5 rounded-full ${color.badge}`}>
              {status.ticket_id}
            </span>
          )}
        </div>
        <p className={`text-xs ${color.text} opacity-70 mt-0.5`}>{detail}</p>
      </div>
    </div>
  )
}

// ── TicketsTab inner component (used from ProjectDetailPage) ───────────────

function TicketsTab({ projectId, refreshKey, onReviewed }: { projectId: number; refreshKey?: number; onReviewed?: () => void }) {
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

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetchTickets(controller.signal)
    return () => controller.abort()
  }, [projectId, refreshKey, fetchTickets])

  // Poll every 5s while any ticket has an active session
  useEffect(() => {
    const hasActiveSession = tickets.some(
      (t) => t.session_id && (t.status === 'in_progress' || t.status === 'qa_review'),
    )
    if (!hasActiveSession) return
    const interval = setInterval(() => fetchTickets(), 5000)
    return () => clearInterval(interval)
  }, [tickets, fetchTickets])

  if (loading) return <p className="text-xs text-gray-400 px-1 py-2">Loading tickets…</p>
  if (tickets.length === 0) {
    return <p className="text-xs text-gray-400 italic px-1 py-2">No bug tickets filed yet. Run a QA session to discover bugs.</p>
  }

  return (
    <div className="space-y-3">
      <LoopStatusBanner projectId={projectId} />
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
              onDrop={col.acceptsDrop ? (tid) => handleDrop(tid, tickets, setTickets, projectId, fetchTickets) : undefined}
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
      {selectedTicket && (
        <TicketDialog
          ticket={selectedTicket}
          col={COLUMNS.find((c) => c.status === selectedTicket.status) ?? COLUMNS[0]}
          projectId={projectId}
          onClose={() => setSelectedTicket(null)}
          onAccept={
            selectedTicket.status === 'needs_review'
              ? () => {
                  acceptPR(projectId, selectedTicket.id).then(() => { fetchTickets(); onReviewed?.() })
                  setSelectedTicket(null)
                }
              : undefined
          }
          onReject={
            selectedTicket.status === 'needs_review'
              ? () => {
                  rejectPR(projectId, selectedTicket.id).then(() => fetchTickets())
                  setSelectedTicket(null)
                }
              : undefined
          }
        />
      )}
    </div>
  )
}

async function handleDrop(
  ticketId: string,
  tickets: Ticket[],
  setTickets: React.Dispatch<React.SetStateAction<Ticket[]>>,
  projectId: number,
  refetch: () => void,
) {
  const ticket = tickets.find((t) => t.id === ticketId)
  if (!ticket || ticket.status !== 'pending_confirmation') return
  setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: 'in_progress' } : t)))
  try {
    const result = await approveTicket(projectId, ticketId)
    setTickets((prev) =>
      prev.map((t) => t.id === ticketId ? { ...t, status: 'in_progress', session_id: result.session_id } : t),
    )
  } catch {
    refetch()
  }
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
  return <TicketsTab projectId={projectId} refreshKey={refreshKey} onReviewed={onReviewed} />
}

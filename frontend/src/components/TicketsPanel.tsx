import { useEffect, useRef, useState, useCallback, useMemo } from 'react'
import { GfmMarkdown } from './GfmMarkdown'
import { listTickets, approveTicket, cancelTicket, closeTicket, requeueTicket, resetTicket, getTicketSessions, getFixSummary, type Ticket, type TicketStatus, type TicketSession, type TicketFailureReport, type FixSummary, type FixSummaryChange } from '../api/tickets'
import { getCoderStatus, type CoderStatus } from '../api/coder'
import { getQASessionEvents } from '../api/qa_sessions'
import { acceptPR, rejectPR } from '../api/pr'
import { AgentTimeline, type AgentEvent, ExpandableLiveThought, ThinkingDots } from './AgentTimeline'

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
  acceptsDropFrom: TicketStatus[]
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
    acceptsDropFrom: [],
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
    acceptsDropFrom: ['pending_confirmation', 'needs_review'],
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
    acceptsDropFrom: [],
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
    acceptsDropFrom: [],
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
    acceptsDropFrom: ['needs_review'],
  },
]

// ── Status badge helpers ──────────────────────────────────────────────────

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

// ── Fix Summary tab ────────────────────────────────────────────────────────

const FILE_WRITE_TOOLS = new Set([
  'write_file', 'write_source_file', 'str_replace', 'patch_file', 'edit_file',
  'apply_patch', 'create_file', 'append_file', 'patch_source_file',
])

function extractFilePath(input: unknown): string | null {
  if (!input || typeof input !== 'object') return null
  const obj = input as Record<string, unknown>
  const p = obj.path ?? obj.file_path ?? obj.filename
  return typeof p === 'string' ? p : null
}

function extractChangeContent(tool: string, input: unknown): { kind: string; content: string } {
  if (!input || typeof input !== 'object') return { kind: 'unknown', content: '' }
  const obj = input as Record<string, unknown>
  if (tool === 'str_replace' || tool === 'patch_source_file') {
    const old = typeof obj.old_str === 'string' ? obj.old_str : ''
    const new_ = typeof obj.new_str === 'string' ? obj.new_str : ''
    return { kind: 'edit', content: `− ${old.slice(0, 300)}\n+ ${new_.slice(0, 300)}` }
  }
  if (tool === 'patch_file' || tool === 'apply_patch') {
    const patch = typeof obj.patch === 'string' ? obj.patch : ''
    return { kind: 'patch', content: patch.slice(0, 600) }
  }
  const content = typeof obj.content === 'string' ? obj.content : ''
  return { kind: 'write', content: content.slice(0, 600) }
}

interface FileChange {
  path: string
  tool: string
  reasoning: string
  kind: string
  content: string
  ts?: string
}

function groupFileChanges(events: AgentEvent[]): FileChange[] {
  const changes: FileChange[] = []
  let pendingText = ''
  for (const ev of events) {
    if (['text_delta', 'qa_text_delta', 'coder_text_delta'].includes(ev.type)) {
      pendingText += ev.text ?? ''
    } else if (ev.type === 'tool_use' && FILE_WRITE_TOOLS.has(ev.tool ?? '')) {
      const path = extractFilePath(ev.input)
      if (path) {
        const { kind, content } = extractChangeContent(ev.tool!, ev.input)
        changes.push({ path, tool: ev.tool!, reasoning: pendingText.slice(-400).trim(), kind, content, ts: ev.ts })
      }
      pendingText = ''
    } else if (ev.type === 'tool_use' || ev.type === 'tool_result' || ev.type === 'session_status') {
      pendingText = ''
    }
  }
  return changes
}

function FixSummaryTab({
  projectId,
  ticketId,
  sessionId,
}: {
  projectId: number
  ticketId: string
  sessionId?: string | null
}) {
  const [loading, setLoading] = useState(true)
  const [changes, setChanges] = useState<FileChange[]>([])
  const [recheckOutput, setRecheckOutput] = useState<string | null>(null)
  const [qaEarlyExit, setQaEarlyExit] = useState<string | null>(null)
  const [qaFinalSummary, setQaFinalSummary] = useState<string | null>(null)
  const [finalStatus, setFinalStatus] = useState<string | null>(null)
  const [completedAt, setCompletedAt] = useState<string | null>(null)
  const [source, setSource] = useState<'persisted' | 'reconstructed' | null>(null)
  const [expandedFile, setExpandedFile] = useState<number | null>(null)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        // Preferred path: server-persisted summary written at the end of the
        // fix loop. This survives event-log rotation and is O(1) to fetch.
        const persisted = await getFixSummary(projectId, ticketId).catch(() => null)
        if (!cancelled && persisted) {
          setChanges(persisted.changes.map((c: FixSummaryChange) => ({
            path: c.path,
            tool: c.tool,
            reasoning: c.reasoning,
            kind: c.kind,
            content: c.content,
            ts: c.ts ?? undefined,
          })))
          setRecheckOutput(persisted.recheck_output)
          setQaEarlyExit(persisted.qa_early_exit)
          setQaFinalSummary(persisted.qa_final_summary)
          setFinalStatus(persisted.final_status)
          setCompletedAt(persisted.completed_at)
          setSource('persisted')
          setLoading(false)
          return
        }

        // Fallback: rebuild from JSONL events (legacy path; covers active
        // sessions whose summary file hasn't been written yet).
        let targetId = sessionId ?? null
        if (!targetId) {
          const sessions = await getTicketSessions(projectId, ticketId)
          const done = sessions.find((s) => s.status === 'done') ?? sessions[0]
          if (!done) { setLoading(false); return }
          targetId = done.session_id
        }
        const events = await getQASessionEvents(projectId, targetId)
        if (!cancelled) {
          setChanges(groupFileChanges(events))
          const rc = [...events].reverse().find((e) => e.type === 'recheck_output')
          if (rc) setRecheckOutput(rc.output ?? null)
          const earlyExit = events.find((e) => e.type === 'qa_early_exit')
          if (earlyExit) setQaEarlyExit(earlyExit.reasoning ?? 'QA satisfied.')
          // Reconstruct the QA narrative from the last qa_final_summary event
          // when no persisted summary file exists yet (e.g. older sessions).
          const fs = [...events].reverse().find((e) => e.type === 'qa_final_summary')
          if (fs && typeof fs.summary === 'string' && fs.summary.trim()) {
            setQaFinalSummary(fs.summary)
          }
          setSource('reconstructed')
          setLoading(false)
        }
      } catch {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [projectId, ticketId, sessionId])

  if (loading) {
    return (
      <div className="flex items-center gap-2 px-5 py-8 text-sm text-gray-400">
        <span className="animate-spin">⟳</span>
        <span>Loading fix summary…</span>
      </div>
    )
  }

  // No persisted summary AND no reconstructed events — show a friendly empty
  // state. This is the normal state for tickets that haven't entered the fix
  // loop yet (e.g. fresh pending_confirmation).
  if (changes.length === 0 && !recheckOutput && !qaEarlyExit && !qaFinalSummary && !finalStatus) {
    return (
      <div className="px-5 py-8 text-sm text-gray-400 italic text-center">
        No fix session has been recorded for this ticket yet. Drag the ticket
        to <span className="font-medium">In Progress</span> to start one.
      </div>
    )
  }

  // Header banner: tells the user *which* session this summary is from and
  // whether the data came from the persistent store or was reconstructed
  // on-the-fly. Useful when verifying that a closed ticket still surfaces
  // its fix history after a server restart.
  const headerBanner = (finalStatus || completedAt) && (
    <div className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-600 flex items-center gap-2 flex-wrap">
      {finalStatus && (
        <span className="inline-flex items-center gap-1">
          <span className="text-gray-400">Final status:</span>
          <span className={`font-mono font-medium ${
            finalStatus === 'done' ? 'text-emerald-700'
            : finalStatus === 'loop_exhausted' ? 'text-yellow-700'
            : 'text-red-600'
          }`}>{finalStatus}</span>
        </span>
      )}
      {completedAt && (
        <span className="inline-flex items-center gap-1">
          <span className="text-gray-400">·</span>
          <span className="text-gray-500">{formatRelTime(completedAt)}</span>
        </span>
      )}
      {source === 'persisted' && (
        <span className="ml-auto text-[10px] text-gray-400 italic">
          📌 Persisted summary
        </span>
      )}
    </div>
  )

  // Deduplicate by path for the "Files changed" header
  const uniqueFiles = [...new Set(changes.map((c) => c.path))]

  return (
    <div className="p-5 space-y-4">
      {headerBanner}

      {/* QA Final Summary — the headline of the Fix Summary tab. This is the
          QA-written narrative compiled at the end of every fix loop (success
          or failure). It belongs at the very top because it's the "what
          should I know about this ticket?" answer for any reviewer. */}
      {qaFinalSummary && (
        <div className="rounded-lg border border-violet-200 bg-violet-50 px-4 py-3">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-violet-500">🧠</span>
            <p className="text-xs font-semibold text-violet-800 uppercase tracking-wide">
              QA Final Summary
            </p>
          </div>
          <div className="prose prose-sm max-w-none text-sm text-gray-800 leading-relaxed [&_h1]:text-base [&_h2]:text-sm [&_h2]:mt-3 [&_h2]:mb-1 [&_h2]:font-semibold [&_h2]:text-violet-900 [&_h3]:text-xs [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_code]:bg-white/70 [&_code]:px-1 [&_code]:rounded [&_code]:text-[12px] [&_pre]:bg-white/80 [&_pre]:border [&_pre]:border-violet-200 [&_pre]:rounded [&_pre]:p-2 [&_pre]:text-[11px] [&_table]:border-collapse [&_table]:w-full [&_th]:border [&_th]:border-violet-300 [&_th]:bg-white/70 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-violet-200 [&_td]:px-2 [&_td]:py-1">
            <GfmMarkdown>{qaFinalSummary}</GfmMarkdown>
          </div>
        </div>
      )}

      {/* QA early exit note */}
      {qaEarlyExit && (
        <div className="flex items-start gap-2 rounded-lg border border-teal-200 bg-teal-50 px-4 py-3">
          <span className="text-teal-500">🤖</span>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-semibold text-teal-700">QA Advisor satisfied — loop ended early</p>
            <div className="prose prose-xs max-w-none text-xs text-teal-700 mt-0.5 leading-relaxed [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_h1]:text-sm [&_h2]:text-xs [&_h3]:text-xs [&_code]:bg-teal-100 [&_code]:px-0.5 [&_code]:rounded [&_pre]:bg-teal-100/60 [&_pre]:border [&_pre]:border-teal-200 [&_pre]:rounded [&_pre]:p-2 [&_pre]:text-[11px] [&_table]:border-collapse [&_table]:w-full [&_th]:border [&_th]:border-teal-300 [&_th]:bg-teal-100/60 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-teal-200 [&_td]:px-2 [&_td]:py-1">
              <GfmMarkdown>{qaEarlyExit}</GfmMarkdown>
            </div>
          </div>
        </div>
      )}

      {/* Files changed summary */}
      {changes.length > 0 ? (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">
            {uniqueFiles.length} file{uniqueFiles.length !== 1 ? 's' : ''} changed
          </p>
          <div className="flex flex-wrap gap-1.5">
            {uniqueFiles.map((f) => (
              <span key={f} className="font-mono text-[11px] bg-blue-50 border border-blue-200 text-blue-700 px-2 py-0.5 rounded">
                {f.split('/').pop() ?? f}
              </span>
            ))}
          </div>
        </div>
      ) : (
        // Loop ended without any source-file modifications. Common when CASE C
        // (test_faulty) fires before the coder writes anything actionable.
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 text-xs text-gray-500 italic">
          No source files were modified during this fix session.
        </div>
      )}

      {/* Per-change detail — only render the section when there are changes */}
      {changes.length > 0 && (
      <div className="space-y-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Changes</p>
        {changes.map((change, i) => {
          const isOpen = expandedFile === i
          return (
            <div key={i} className="rounded-lg border border-gray-200 overflow-hidden">
              {/* Header */}
              <button
                type="button"
                className="w-full text-left px-3 py-2.5 flex items-center gap-2 bg-gray-50 hover:bg-gray-100 transition-colors"
                onClick={() => setExpandedFile(isOpen ? null : i)}
              >
                <span className="text-gray-400 text-[10px] w-3 text-center">{isOpen ? '▾' : '▸'}</span>
                <span className="font-mono text-xs text-gray-700 flex-1 truncate">{change.path}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  change.kind === 'edit' ? 'bg-amber-100 text-amber-700' :
                  change.kind === 'patch' ? 'bg-blue-100 text-blue-700' :
                  'bg-emerald-100 text-emerald-700'
                }`}>
                  {change.tool}
                </span>
                {change.ts && (
                  <span className="text-[10px] text-gray-400 shrink-0">
                    {new Date(change.ts).toLocaleTimeString()}
                  </span>
                )}
              </button>

              {/* Expanded detail */}
              {isOpen && (
                <div className="border-t border-gray-100 p-3 space-y-3 animate-fade-in">
                  {/* Agent reasoning */}
                  {change.reasoning && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">Why</p>
                      <div className="prose prose-xs max-w-none text-gray-600 text-xs bg-white border border-gray-100 rounded p-2 leading-relaxed [&_p]:my-0.5 [&_code]:bg-gray-100 [&_code]:px-0.5 [&_code]:rounded [&_table]:border-collapse [&_table]:w-full [&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-50 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-gray-200 [&_td]:px-2 [&_td]:py-1">
                        <GfmMarkdown>{change.reasoning}</GfmMarkdown>
                      </div>
                    </div>
                  )}

                  {/* Code content */}
                  {change.content && (
                    <div>
                      <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1">
                        {change.kind === 'edit' ? 'Diff (old → new)' : 'Content'}
                      </p>
                      <pre className={`text-xs p-2.5 rounded-md border whitespace-pre-wrap leading-relaxed font-mono max-h-72 overflow-y-auto ${
                        change.kind === 'edit'
                          ? 'bg-gray-900 text-gray-100 border-gray-700'
                          : 'bg-gray-50 text-gray-700 border-gray-200'
                      }`}>
                        {change.content}
                        {change.content.length >= 600 ? '\n…(truncated)' : ''}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>
      )}

      {/* Final recheck output */}
      {recheckOutput && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2">Final Test Run</p>
          <pre className={`text-xs p-2.5 rounded-md border whitespace-pre-wrap max-h-48 overflow-y-auto leading-relaxed ${
            recheckOutput.includes('passed') && !recheckOutput.includes('failed')
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : 'bg-red-50 border-red-200 text-red-800'
          }`}>
            {recheckOutput}
          </pre>
        </div>
      )}
    </div>
  )
}

// ── Per-session event pane (polls JSONL for live sessions) ─────────────────

const TEXT_DELTA_TYPES = new Set(['text_delta', 'qa_text_delta', 'coder_text_delta'])

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
  // Fingerprint set survives across load()/SSE so we can dedup events that
  // appear in both the JSONL snapshot AND the queue replay (the queue holds
  // events not yet drained by a previous SSE consumer).
  const seenFingerprints = useRef<Set<string>>(new Set())

  const fingerprint = (e: AgentEvent): string => {
    // ts is unique per event in practice (microsecond precision); fall back
    // to full JSON for events that somehow lack a timestamp.
    if (e.ts) return `${e.type}|${e.ts}|${(e.text ?? '').slice(0, 20)}`
    return JSON.stringify(e)
  }

  const appendEvents = useCallback((incoming: AgentEvent[]) => {
    const newOnes: AgentEvent[] = []
    for (const e of incoming) {
      const fp = fingerprint(e)
      if (!seenFingerprints.current.has(fp)) {
        seenFingerprints.current.add(fp)
        newOnes.push(e)
      }
    }
    setEvents((prev) => {
      if (newOnes.length === 0) {
        // First load returned nothing — drop the loading state by yielding []
        return prev ?? []
      }
      return prev ? [...prev, ...newOnes] : newOnes
    })
  }, [])

  const load = useCallback(async (signal?: AbortSignal) => {
    try {
      const data = await getQASessionEvents(projectId, session.session_id, signal)
      if (!signal?.aborted) appendEvents(data)
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== 'AbortError') {
        setError(e.message)
      }
    }
  }, [projectId, session.session_id, appendEvents])

  // Always load JSONL snapshot first — it's the authoritative persistent history.
  // For active sessions this gives us events that may have already been drained
  // from the queue by a previous SSE consumer (e.g., user closed and re-opened
  // the dialog).
  useEffect(() => {
    seenFingerprints.current = new Set()
    setEvents(null)
    const ac = new AbortController()
    load(ac.signal)
    return () => ac.abort()
  }, [load])

  // For active sessions, also subscribe to SSE for live events. Dedup via
  // fingerprint set ensures queue-backlog events that overlap with JSONL
  // don't appear twice.
  useEffect(() => {
    if (!isActive) return
    const es = new EventSource(
      `/api/projects/${projectId}/qa-sessions/${session.session_id}/stream`,
    )
    es.onmessage = (e) => {
      try {
        const event: AgentEvent = JSON.parse(e.data)
        appendEvents([event])
        if (event.type === 'done' || event.type === 'error') {
          es.close()
          // One final load() to capture any events written to JSONL between
          // our initial snapshot and the SSE close.
          load()
        }
      } catch {
        // ignore malformed frames
      }
    }
    es.onerror = () => {
      es.close()
      // SSE failed (often: session already completed, queue gone, 404).
      // Re-load JSONL for the final authoritative snapshot.
      load()
    }
    return () => es.close()
  }, [isActive, projectId, session.session_id, load, appendEvents])

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
      .filter((e) => TEXT_DELTA_TYPES.has(e.type))
      .map((e) => e.text ?? '')
      .join('')
  }, [events, isActive])

  // Ambient generation state
  const lastEvent = events && events.length > 0 ? events[events.length - 1] : null
  const isGenerating = isActive && !!lastEvent && TEXT_DELTA_TYPES.has(lastEvent.type)
  const isCallingTool = isActive && lastEvent?.type === 'tool_use'
  const isTestingPhase = isActive && lastEvent?.type === 'session_status' && lastEvent.status === 'qa_checking'

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
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="flex items-center gap-3">
          {isActive && (
            <div className="flex items-center gap-1.5 text-xs text-amber-600">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span className="font-medium">Live</span>
            </div>
          )}
          {/* Ambient generation state */}
          {(isGenerating || isCallingTool || isTestingPhase) && (
            <div className="flex items-center gap-1 text-xs text-gray-400 font-mono">
              {isTestingPhase ? (
                <>🧪 Testing<ThinkingDots /></>
              ) : isGenerating ? (
                <>✍️ Generating<ThinkingDots /></>
              ) : (
                <>⚡ <span className="italic">{lastEvent?.tool ?? 'tool'}</span><ThinkingDots /></>
              )}
            </div>
          )}
        </div>
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

      {/* Live thought ticker — expandable */}
      {isActive && liveThought && <ExpandableLiveThought text={liveThought} />}

      {/* Timeline (scrollable) */}
      <div className="max-h-[32rem] overflow-y-auto pr-0.5">
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
  isTicketActive,
}: {
  projectId: number
  ticketId: string
  activeSessionId: string | null
  isTicketActive: boolean
}) {
  const [sessions, setSessions] = useState<TicketSession[] | null>(null)
  const [expandedId, setExpandedId] = useState<string | null>(activeSessionId)
  // Tracks whether the user has explicitly clicked to expand/collapse a session.
  // Until they do, auto-expand the active (or most recent) session every time
  // we fetch — this guarantees real-time data hydrates without manual action.
  const userExpandedRef = useRef(false)

  const fetchSessions = useCallback(async (signal?: AbortSignal) => {
    try {
      const s = await getTicketSessions(projectId, ticketId, signal)
      if (signal?.aborted) return
      setSessions(s)
      if (!userExpandedRef.current) {
        const liveSession = s.find((x) => !x.completed_at)
        const targetId = activeSessionId ?? liveSession?.session_id ?? s[0]?.session_id ?? null
        if (targetId) setExpandedId(targetId)
      }
    } catch {
      if (!signal?.aborted) setSessions([])
    }
  }, [projectId, ticketId, activeSessionId])

  useEffect(() => {
    const ac = new AbortController()
    fetchSessions(ac.signal)
    return () => ac.abort()
  }, [fetchSessions])

  // While the ticket is actively being worked on, poll for newly created
  // sessions. Covers the race where the dialog opens before the backend has
  // committed the QASession row, AND the case where ticket.session_id was
  // null (legacy/orphan) but a real session is running.
  useEffect(() => {
    if (!isTicketActive) return
    // Stop polling once we have at least one session and an active one is found
    const haveActive = (sessions ?? []).some((s) => !s.completed_at)
    if (haveActive) return
    const interval = setInterval(() => fetchSessions(), 2000)
    return () => clearInterval(interval)
  }, [isTicketActive, sessions, fetchSessions])

  if (sessions === null) return (
    <div className="px-3 py-2 text-xs text-gray-400 animate-pulse">Loading session history…</div>
  )
  if (sessions.length === 0) {
    return isTicketActive ? (
      <div className="px-3 py-3 text-xs text-amber-600 flex items-center gap-2">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
        Waiting for the agent to start…
      </div>
    ) : (
      <div className="px-3 py-2 text-xs text-gray-400 italic">No sessions recorded yet.</div>
    )
  }

  return (
    <div className="divide-y divide-gray-100">
      {sessions.map((s, i) => {
        // A session is "live" when the parent ticket is active AND this session
        // hasn't been marked completed in the DB. Falling back to activeSessionId
        // alone misses freshly created sessions whose ID hasn't propagated to
        // listTickets yet (the polling cycle is 5 s).
        const isActive = isTicketActive && !s.completed_at
        const isOpen = expandedId === s.session_id

        return (
          <div key={s.session_id}>
            <button
              type="button"
              className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-gray-50 transition-colors"
              onClick={() => {
                userExpandedRef.current = true
                setExpandedId(isOpen ? null : s.session_id)
              }}
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
  // Per-recommendation theming. Each variant gets its own colour palette,
  // headline, and call-to-action so reviewers can tell at a glance whether
  // the ticket needs (a) more compute, (b) re-triage, or (c) a test rewrite.
  const meta = (() => {
    switch (report.recommendation) {
      case 'possibly_not_a_bug':
        return {
          containerCls: 'bg-orange-50 border-orange-200',
          textCls: 'text-orange-700',
          headline: '⚠ Possibly not a real bug',
          chipCls: 'bg-orange-100 border-orange-300 text-orange-800',
          chipText: '📋 Recommend: review ticket validity or add targeted tests',
        }
      case 'test_faulty':
        return {
          containerCls: 'bg-yellow-50 border-yellow-200',
          textCls: 'text-yellow-800',
          headline: '🧪 Generated test is faulty — needs update',
          chipCls: 'bg-yellow-100 border-yellow-300 text-yellow-900',
          chipText:
            '✏️ Recommend: update the test file as described, then re-queue this ticket',
        }
      default:
        return {
          containerCls: 'bg-red-50 border-red-200',
          textCls: 'text-red-700',
          headline: '⚠ Fix loop exhausted — needs more attempts',
          chipCls: 'bg-blue-50 border-blue-200 text-blue-700',
          chipText:
            '🔄 Recommend: increase max_fix_attempts or review coder changes manually',
        }
    }
  })()

  return (
    <div className={`border-b px-5 py-3 space-y-2 ${meta.containerCls}`}>
      <div className="flex items-center gap-2">
        <span className={`text-sm font-semibold ${meta.textCls}`}>{meta.headline}</span>
      </div>
      {/* Render the analysis through GfmMarkdown — for test_faulty cases the
          QA Advisor often includes a code block with the corrected test. */}
      <div className={`prose prose-xs max-w-none text-xs leading-relaxed ${meta.textCls} [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_pre]:bg-white/60 [&_pre]:border [&_pre]:border-current/20 [&_pre]:rounded [&_pre]:p-2 [&_pre]:text-[11px] [&_code]:bg-white/60 [&_code]:px-0.5 [&_code]:rounded`}>
        <GfmMarkdown>{report.analysis}</GfmMarkdown>
      </div>
      <span className={`inline-block text-[11px] px-2 py-0.5 rounded-full font-medium border ${meta.chipCls}`}>
        {meta.chipText}
      </span>
    </div>
  )
}

type DialogTab = 'description' | 'logs' | 'fix-summary'

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
  // Fix Summary is a durable, persisted artifact that is generated at the end
  // of every fix-loop run. Show the tab whenever any session has run for this
  // ticket — reviewers shouldn't lose access to "what changed" just because
  // the ticket bounced back to in_progress for another attempt.
  const showFixSummary = hasHistory
  // Prefer Fix Summary as the default tab when the loop has actually
  // concluded (needs_review / closed). For mid-flight tickets the live Agent
  // Logs view is more useful, so keep it as the default there.
  const isLoopFinished = ticket.status === 'needs_review' || ticket.status === 'closed'
  const defaultTab: DialogTab =
    showFixSummary && isLoopFinished ? 'fix-summary'
    : hasHistory ? 'logs'
    : 'description'
  const [activeTab, setActiveTab] = useState<DialogTab>(defaultTab)

  useEffect(() => {
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  // True while the QA→Coder loop is still working on this ticket. Used to
  // show the pulsing "active" dot in the dialog header and the live indicator
  // on the Agent Logs tab. Declared here so both the header span and the tab
  // bar can reference it.
  const isActive = ticket.status === 'in_progress' || ticket.status === 'qa_review'

  return (
    <div
      className="fixed inset-0 z-50 bg-black/40 flex items-center justify-center p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-3xl max-h-[92vh] flex flex-col overflow-hidden"
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
          {showFixSummary && hasHistory && (
            <button
              type="button"
              onClick={() => setActiveTab('fix-summary')}
              className={`py-2.5 text-sm font-medium border-b-2 transition-colors flex items-center gap-1.5 ${
                activeTab === 'fix-summary'
                  ? 'border-yellow-500 text-yellow-700'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              🔧 Fix Summary
            </button>
          )}
        </div>

        {/* Tab content — all three panels stay mounted; CSS hides inactive ones
            so FixSummaryTab begins fetching the instant the dialog opens */}
        <div className="flex-1 overflow-y-auto relative">
          <div className={activeTab !== 'description' ? 'hidden' : 'p-5'}>
            <div className="prose prose-sm max-w-none text-gray-700 [&_h1]:text-lg [&_h2]:text-base [&_h3]:text-sm [&_pre]:bg-gray-900 [&_pre]:text-gray-100 [&_pre]:border [&_pre]:border-gray-700 [&_pre]:rounded [&_pre_code]:bg-transparent [&_pre_code]:text-gray-100 [&_pre_code]:p-0 [&_code]:bg-gray-800 [&_code]:text-gray-100 [&_code]:px-1 [&_code]:rounded [&_code]:text-xs [&_table]:border-collapse [&_table]:w-full [&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-50 [&_th]:px-3 [&_th]:py-1.5 [&_th]:text-left [&_td]:border [&_td]:border-gray-200 [&_td]:px-3 [&_td]:py-1.5">
              <GfmMarkdown>{ticket.content}</GfmMarkdown>
            </div>
          </div>

          {showFixSummary && hasHistory && (
            <div className={activeTab !== 'fix-summary' ? 'hidden' : ''}>
              <FixSummaryTab
                projectId={projectId}
                ticketId={ticket.id}
                sessionId={ticket.session_id}
              />
            </div>
          )}

          <div className={activeTab !== 'logs' ? 'hidden' : 'bg-gray-50 min-h-full'}>
            {/* Always mount TicketSessionHistory: it queries by ticket_id, so it
                can find the active session even when the cached ticket.session_id
                is stale (e.g., dialog opened mid-drag, page refreshed mid-run). */}
            <TicketSessionHistory
              projectId={projectId}
              ticketId={ticket.id}
              activeSessionId={isActive ? ticket.session_id : null}
              isTicketActive={isActive}
            />
          </div>
        </div>

        {/* Accept / Reject */}
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
  onCancel,
  onReset,
  onClick,
}: {
  ticket: Ticket
  col: ColumnConfig
  draggable?: boolean
  onCancel?: () => void
  onReset?: () => void
  onClick: () => void
}) {
  function onDragStart(e: React.DragEvent) {
    e.dataTransfer.setData('ticketId', ticket.id)
    e.dataTransfer.setData('sourceStatus', ticket.status)
    e.dataTransfer.effectAllowed = 'move'
  }

  const isCoderRunning = ticket.status === 'in_progress'
  const isQaRunning = ticket.status === 'qa_review'
  const isActive = isCoderRunning || isQaRunning
  const hasFailureReport = Boolean(ticket.failure_report)

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

      {ticket.attempt_count > 0 && !isActive && (
        <div className="flex items-center gap-1.5 mt-2 flex-wrap">
          <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-gray-100 text-gray-600 border border-gray-200">
            🔄 {ticket.attempt_count} attempt{ticket.attempt_count !== 1 ? 's' : ''}
          </span>
          {ticket.failure_count > 0 && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-red-50 text-red-600 border border-red-200">
              ✗ {ticket.failure_count} failed
            </span>
          )}
        </div>
      )}

      {draggable && ticket.status === 'pending_confirmation' && (
        <p className="text-[10px] text-gray-400 mt-1.5 italic">Drag → In Progress to start Coder fix</p>
      )}
      {draggable && ticket.status === 'needs_review' && (
        <p className="text-[10px] text-yellow-500 mt-1.5 italic">Drag → In Progress to retry or → Closed to dismiss</p>
      )}
      {ticket.status === 'in_progress' && onCancel && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onCancel() }}
          className="mt-2 w-full text-[11px] font-medium text-red-500 hover:text-red-700 bg-red-50 hover:bg-red-100 border border-red-200 rounded-md px-2 py-1 transition-colors"
        >
          Cancel
        </button>
      )}
      {ticket.status !== 'pending_confirmation' && onReset && (
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onReset() }}
          className="mt-1.5 w-full text-[11px] font-medium text-gray-400 hover:text-gray-600 bg-gray-50 hover:bg-gray-100 border border-gray-200 rounded-md px-2 py-1 transition-colors"
        >
          ↺ Reset
        </button>
      )}
      {hasFailureReport && (() => {
        const rec = ticket.failure_report?.recommendation
        const label =
          rec === 'possibly_not_a_bug' ? 'Possibly not a bug'
          : rec === 'test_faulty' ? 'Test needs update'
          : 'Fix loop exhausted'
        const cls = rec === 'test_faulty' ? 'text-yellow-700' : 'text-red-500'
        const icon = rec === 'test_faulty' ? '🧪' : '⚠'
        return (
          <p className={`text-[10px] ${cls} mt-1.5 font-medium`}>
            {icon} {label}{' · click for insights'}
          </p>
        )
      })()}
      {ticket.status === 'needs_review' && !hasFailureReport && (
        <p className="text-[10px] text-yellow-600 mt-1">🔧 Click to view fix summary</p>
      )}
      {ticket.session_id && !isActive && !hasFailureReport && ticket.status !== 'needs_review' && (
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
  onCancel,
  onReset,
}: {
  col: ColumnConfig
  tickets: Ticket[]
  onDrop?: (ticketId: string, sourceStatus: TicketStatus) => void
  onTicketClick: (ticket: Ticket) => void
  onCancel?: (ticketId: string) => void
  onReset?: (ticketId: string) => void
}) {
  const [dragOver, setDragOver] = useState(false)

  function handleDragOver(e: React.DragEvent) {
    if (col.acceptsDropFrom.length === 0) return
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(true)
  }

  function handleDragLeave() { setDragOver(false) }

  function handleDrop(e: React.DragEvent) {
    e.preventDefault()
    setDragOver(false)
    const ticketId = e.dataTransfer.getData('ticketId')
    const sourceStatus = e.dataTransfer.getData('sourceStatus') as TicketStatus
    if (ticketId && col.acceptsDropFrom.includes(sourceStatus)) onDrop?.(ticketId, sourceStatus)
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
        {col.acceptsDropFrom.length > 0 && tickets.length === 0 && (
          <div className={`flex-1 flex items-center justify-center rounded-lg border-2 border-dashed transition-colors ${
            dragOver ? 'border-blue-400' : 'border-gray-200'
          }`}>
            <p className="text-xs text-gray-400 italic text-center px-2">
              {col.status === 'closed'
                ? <>Drop here<br />to close ticket</>
                : <>Drop tickets here<br />to start Coder fix</>}
            </p>
          </div>
        )}
        {tickets.map((t) => (
          <TicketCard
            key={t.id}
            ticket={t}
            col={col}
            draggable={col.status === 'pending_confirmation' || col.status === 'needs_review'}
            onCancel={col.status === 'in_progress' ? () => onCancel?.(t.id) : undefined}
            onReset={() => onReset?.(t.id)}
            onClick={() => onTicketClick(t)}
          />
        ))}
        {col.acceptsDropFrom.length === 0 && tickets.length === 0 && (
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

function LoopStatusBanner({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) {
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
  }, [fetchStatus, refreshKey])

  if (!status || status.idle) return null

  const isCoderRunning = status.status === 'coder_running'
  const isQaChecking = status.status === 'qa_checking'
  const isQaAdvising = status.status === 'qa_advising'

  const color = isCoderRunning
    ? { border: 'border-amber-200', bg: 'bg-amber-50', dot: 'bg-amber-500', text: 'text-amber-800', badge: 'bg-amber-100 text-amber-700' }
    : (isQaChecking || isQaAdvising)
      ? { border: 'border-violet-200', bg: 'bg-violet-50', dot: 'bg-violet-500', text: 'text-violet-800', badge: 'bg-violet-100 text-violet-700' }
      : { border: 'border-gray-200', bg: 'bg-gray-50', dot: 'bg-gray-400', text: 'text-gray-600', badge: 'bg-gray-100 text-gray-600' }

  const agentName = isCoderRunning ? 'Coder Agent' : 'QA Agent'
  const modelShort = status.model ? status.model.replace(/^claude-/, '') : null
  const label = isCoderRunning
    ? `${agentName} — fixing bug`
    : isQaAdvising
      ? `${agentName} — advising coder`
      : isQaChecking
        ? `${agentName} — verifying fix`
        : `Running (${status.status})`

  const detail = isCoderRunning
    ? 'Editing source files…'
    : isQaAdvising
      ? 'Analyzing failed tests and preparing guidance…'
      : 'Running test suite…'

  return (
    <div className={`flex items-center gap-3 px-4 py-2.5 rounded-lg border ${color.border} ${color.bg}`}>
      <span className={`w-2 h-2 rounded-full ${color.dot} animate-pulse shrink-0`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`text-sm font-medium ${color.text}`}>{label}</span>
          {modelShort && (
            <span className={`font-mono text-xs px-1.5 py-0.5 rounded ${color.badge} opacity-80`}>
              {modelShort}
            </span>
          )}
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

// ── TicketsTab inner component ─────────────────────────────────────────────

function TicketsTab({ projectId, refreshKey, onReviewed }: { projectId: number; refreshKey?: number; onReviewed?: () => void }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTicketId, setSelectedTicketId] = useState<string | null>(null)
  const selectedTicket = selectedTicketId ? (tickets.find((t) => t.id === selectedTicketId) ?? null) : null
  const [colWidths, setColWidths] = useState([1, 1, 1, 1, 1])
  const [bannerRefreshKey, setBannerRefreshKey] = useState(0)
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

  useEffect(() => {
    const hasActiveSession = tickets.some(
      (t) => t.session_id && (t.status === 'in_progress' || t.status === 'qa_review'),
    )
    if (!hasActiveSession) return
    const interval = setInterval(() => fetchTickets(), 5000)
    return () => clearInterval(interval)
  }, [tickets, fetchTickets])

  async function handleCancel(ticketId: string) {
    setTickets((prev) => prev.map((t) => t.id === ticketId ? { ...t, status: 'needs_review' } : t))
    try {
      await cancelTicket(projectId, ticketId)
    } catch {
      // ignore — backend is idempotent; re-fetch below will correct state
    }
    fetchTickets()
  }

  async function handleReset(ticketId: string) {
    setTickets((prev) => prev.map((t) => t.id === ticketId ? { ...t, status: 'pending_confirmation', session_id: null, attempt_count: 0, failure_count: 0 } : t))
    try {
      await resetTicket(projectId, ticketId)
    } catch {
      // re-fetch will correct state if reset failed
    }
    fetchTickets()
  }

  if (loading) return <p className="text-xs text-gray-400 px-1 py-2">Loading tickets…</p>
  if (tickets.length === 0) {
    return <p className="text-xs text-gray-400 italic px-1 py-2">No bug tickets filed yet. Run a QA session to discover bugs.</p>
  }

  return (
    <div className="space-y-3">
      <LoopStatusBanner projectId={projectId} refreshKey={bannerRefreshKey} />
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
              onDrop={col.acceptsDropFrom.length > 0
                ? (tid, src) => handleDrop(tid, src, col.status, tickets, setTickets, projectId, fetchTickets, () => setBannerRefreshKey((k) => k + 1))
                : undefined}
              onTicketClick={(t) => setSelectedTicketId(t.id)}
              onCancel={col.status === 'in_progress' ? handleCancel : undefined}
              onReset={handleReset}
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
          onClose={() => setSelectedTicketId(null)}
          onAccept={
            selectedTicket.status === 'needs_review'
              ? () => {
                  acceptPR(projectId, selectedTicket.id).then(() => { fetchTickets(); onReviewed?.() })
                  setSelectedTicketId(null)
                }
              : undefined
          }
          onReject={
            selectedTicket.status === 'needs_review'
              ? () => {
                  rejectPR(projectId, selectedTicket.id).then(() => fetchTickets())
                  setSelectedTicketId(null)
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
  sourceStatus: TicketStatus,
  targetStatus: TicketStatus,
  tickets: Ticket[],
  setTickets: React.Dispatch<React.SetStateAction<Ticket[]>>,
  projectId: number,
  refetch: () => void,
  refreshBanner: () => void,
) {
  const ticket = tickets.find((t) => t.id === ticketId)
  if (!ticket) return

  if (sourceStatus === 'pending_confirmation' && targetStatus === 'in_progress') {
    setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: 'in_progress' } : t)))
    try {
      const result = await approveTicket(projectId, ticketId)
      setTickets((prev) =>
        prev.map((t) => t.id === ticketId ? { ...t, status: 'in_progress', session_id: result.session_id } : t),
      )
      // Sync real backend state immediately and refresh the status banner
      refetch()
      refreshBanner()
    } catch {
      refetch()
    }
  } else if (sourceStatus === 'needs_review' && targetStatus === 'in_progress') {
    setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: 'in_progress' } : t)))
    try {
      const result = await requeueTicket(projectId, ticketId)
      setTickets((prev) =>
        prev.map((t) => t.id === ticketId ? { ...t, status: 'in_progress', session_id: result.session_id } : t),
      )
      refetch()
      refreshBanner()
    } catch {
      refetch()
    }
  } else if (sourceStatus === 'needs_review' && targetStatus === 'closed') {
    setTickets((prev) => prev.map((t) => (t.id === ticketId ? { ...t, status: 'closed' } : t)))
    try {
      await closeTicket(projectId, ticketId)
    } catch {
      refetch()
    }
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

import { useState, useMemo, useEffect, useRef } from 'react'
import { GfmMarkdown } from './GfmMarkdown'

export interface AgentEvent {
  type: string
  text?: string
  tool?: string
  agent?: string
  input?: unknown
  result?: string
  message?: string
  status?: string
  fix_attempt?: number
  attempt?: number
  max_attempts?: number
  recheck?: string
  output?: string
  ts?: string
  ticket_id?: string
  total_input_tokens?: number
  total_output_tokens?: number
  cost_usd?: number
  budget_usd?: number
  reasoning?: string
  phase?: string
  summary?: string
}

interface ToolCallPair {
  use: AgentEvent
  result: AgentEvent | null
  reasoning: string
}

interface AgentPhase {
  id: string
  label: string
  agentType: string
  startTs?: string
  textEvents: AgentEvent[]
  // Text grouped by tool-call boundaries: each entry is the chunk of agent
  // "thoughts" emitted between two tool calls (or between a phase boundary
  // and the next tool call). Joined with blank-line separators for display so
  // each separate reasoning step gets visual breathing room.
  textSegments: string[]
  toolPairs: ToolCallPair[]
  recheckEvent: AgentEvent | null
  rejectionEvent: AgentEvent | null
  errorEvent: AgentEvent | null
  pytestRunning: boolean
}

// ── Agent brand colours ────────────────────────────────────────────────────

const AGENT_META: Record<
  string,
  { icon: string; label: string; chip: string; header: string; border: string; tool: string }
> = {
  reviewer: {
    icon: '🔍',
    label: 'Reviewer',
    chip: 'bg-blue-100 text-blue-700 border-blue-200',
    header: 'bg-blue-50 border-blue-200',
    border: 'border-blue-200',
    tool: 'text-blue-700',
  },
  qa: {
    icon: '🧪',
    label: 'QA Agent',
    chip: 'bg-violet-100 text-violet-700 border-violet-200',
    header: 'bg-violet-50 border-violet-200',
    border: 'border-violet-200',
    tool: 'text-violet-700',
  },
  coder: {
    icon: '🛠️',
    label: 'Coder',
    chip: 'bg-amber-100 text-amber-700 border-amber-200',
    header: 'bg-amber-50 border-amber-200',
    border: 'border-amber-200',
    tool: 'text-amber-700',
  },
  system: {
    icon: '⚙️',
    label: 'System',
    chip: 'bg-gray-100 text-gray-600 border-gray-200',
    header: 'bg-gray-50 border-gray-200',
    border: 'border-gray-200',
    tool: 'text-gray-600',
  },
}

// ── Shared animated helpers (exported for reuse) ───────────────────────────

/** Cycling dot ellipsis: "" → "." → ".." → "..." */
export function ThinkingDots() {
  const [count, setCount] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setCount((c) => (c + 1) % 4), 400)
    return () => clearInterval(id)
  }, [])
  return <span className="inline-block w-3.5 text-left">{'.'.repeat(count)}</span>
}

/** Expandable live thought ticker — used in QASessionView and SessionEventPane.
 *
 * Streams a "tail -f" view of the agent's most recent thoughts. When the text
 * grows beyond the collapsed clip height, the view auto-scrolls so the tail
 * (most recent content) is always visible — readers care about *what the
 * agent is thinking right now*, not what it said when the run began.
 * `line-clamp` would do the opposite (show the head and hide the tail), which
 * is why we use `max-h + overflow-y` plus a scrollTop effect. */
export function ExpandableLiveThought({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false)
  const isLong = text.length > 140
  const scrollRef = useRef<HTMLDivElement>(null)

  // Tail-follow: every time text changes (or expansion toggles), pin the view
  // to the bottom so the newest tokens stay visible.
  useEffect(() => {
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [text, expanded])

  return (
    <div
      className={`flex items-start gap-2 px-3 py-2 rounded-lg bg-indigo-50 border border-indigo-100 text-xs text-indigo-700 font-mono leading-relaxed transition-all ${isLong ? 'cursor-pointer hover:bg-indigo-100/70' : ''}`}
      onClick={() => isLong && setExpanded((p) => !p)}
      title={isLong ? (expanded ? 'Click to collapse' : 'Click to expand') : undefined}
    >
      <span className="shrink-0 opacity-60 mt-px animate-pulse">💭</span>
      <div
        ref={scrollRef}
        className={`break-words whitespace-pre-wrap flex-1 animate-fade-in overflow-y-auto ${
          expanded ? 'max-h-64' : 'max-h-12'
        }`}
      >
        {text}
        {/* blinking cursor signals active generation */}
        <span className="ml-0.5 animate-blink opacity-60">▋</span>
      </div>
      {isLong && (
        <span className="shrink-0 text-indigo-400 text-[10px] mt-0.5 select-none">
          {expanded ? '↑' : '↓'}
        </span>
      )}
    </div>
  )
}

// ── Phase helpers ──────────────────────────────────────────────────────────

function makePhaseLabel(status: string, fixAttempt?: number): string {
  const attempt = fixAttempt !== undefined ? ` — Attempt ${fixAttempt + 1}` : ''
  switch (status) {
    case 'qa_running':           return `QA Agent${attempt}`
    case 'qa_advising':          return `QA Advisor${attempt}`
    case 'qa_summarizing':       return 'QA Final Summary'
    case 'reviewer_summarizing': return 'Reviewer Final Summary'
    case 'qa_checking':          return `QA Verify${attempt}`
    case 'coder_running':        return `Coder${attempt}`
    case 'hitl_waiting':         return 'Awaiting Approval'
    case 'done':                 return 'Complete'
    case 'error':                return 'Error'
    case 'skipped':              return 'Skipped'
    default:                     return status
  }
}

function agentFromStatus(status: string): string {
  if (status.startsWith('coder'))    return 'coder'
  if (status.startsWith('reviewer')) return 'reviewer'
  if (status.startsWith('qa'))       return 'qa'
  return 'system'
}

function stripMarkdown(text: string): string {
  return text
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`(.+?)`/g, '$1')
    .replace(/^[-*]\s+/gm, '')
    .replace(/\n+/g, ' ')
    .trim()
}

function makePhase(
  id: string,
  label: string,
  agentType: string,
  startTs?: string,
): AgentPhase {
  return {
    id,
    label,
    agentType,
    startTs,
    textEvents: [],
    textSegments: [],
    toolPairs: [],
    recheckEvent: null,
    rejectionEvent: null,
    errorEvent: null,
    pytestRunning: false,
  }
}

function groupIntoPhases(events: AgentEvent[], defaultLabel: string): AgentPhase[] {
  const phases: AgentPhase[] = []
  let toolUseQueue: Array<{ event: AgentEvent; reasoning: string }> = []
  let pendingText = ''

  let current: AgentPhase = makePhase(
    'default',
    defaultLabel,
    defaultLabel.toLowerCase().includes('reviewer') ? 'reviewer' : 'qa',
  )

  function flushSegment() {
    // Capture the run of text since the last tool_use (or phase start) as a
    // discrete segment. Joining segments with a blank line gives readers a
    // clear break between successive reasoning steps.
    const trimmed = pendingText.trim()
    if (trimmed) current.textSegments.push(trimmed)
    pendingText = ''
  }

  for (const event of events) {
    if (event.type === 'session_status' && event.status) {
      flushSegment()
      toolUseQueue.forEach(({ event: use, reasoning }) =>
        current.toolPairs.push({ use, result: null, reasoning }),
      )
      toolUseQueue = []
      if (
        current.textEvents.length > 0 ||
        current.toolPairs.length > 0 ||
        current.recheckEvent ||
        current.errorEvent
      ) {
        phases.push(current)
      }
      // Terminal statuses get a dedicated banner above the timeline (the
      // green "Session complete" or yellow "Needs Review" failure-report
      // card) — suppressing the empty in-timeline phase avoids duplicate
      // signaling and reduces visual noise. Use a sentinel phase (no startTs,
      // no events) that the final push check will skip.
      if (event.status === 'done' || event.status === 'loop_exhausted') {
        current = makePhase(`terminal-${event.status}`, '', 'system')
      } else {
        current = makePhase(
          `${event.status}-${event.fix_attempt ?? 0}-${phases.length}`,
          makePhaseLabel(event.status, event.fix_attempt),
          agentFromStatus(event.status),
          event.ts,
        )
      }
    } else if (event.type === 'pytest_running') {
      current.pytestRunning = true
    } else if (event.type === 'pytest_done') {
      current.pytestRunning = false
    } else if (['text_delta', 'qa_text_delta', 'coder_text_delta', 'reviewer_text_delta'].includes(event.type)) {
      current.textEvents.push(event)
      pendingText += event.text ?? ''
    } else if (event.type === 'tool_use') {
      // A tool call ends the current text segment — push it before queuing
      // the tool, and grab a copy as the tool's "Why" reasoning.
      const reasoning = pendingText
      flushSegment()
      toolUseQueue.push({ event, reasoning })
    } else if (event.type === 'tool_result') {
      const queued = toolUseQueue.shift()
      if (queued) current.toolPairs.push({ use: queued.event, result: event, reasoning: queued.reasoning })
    } else if (event.type === 'recheck_output') {
      current.recheckEvent = event
    } else if (event.type === 'fix_attempt_failed') {
      current.rejectionEvent = event
    } else if (event.type === 'error') {
      current.errorEvent = event
    }
  }

  // Final flush of trailing text and any orphan tool_use blocks that never
  // received a result.
  flushSegment()
  toolUseQueue.forEach(({ event: use, reasoning }) =>
    current.toolPairs.push({ use, result: null, reasoning }),
  )
  // Always push phases explicitly started by a session_status event (startTs set),
  // so live in-progress phases (e.g. qa_advising with no text yet) appear immediately.
  // The terminal-done sentinel has no startTs, so it is naturally skipped here.
  if (
    current.textEvents.length > 0 ||
    current.toolPairs.length > 0 ||
    current.recheckEvent ||
    current.errorEvent ||
    !!current.startTs
  ) {
    phases.push(current)
  }

  return phases
}

// ── Sub-components ─────────────────────────────────────────────────────────

function ToolCallRow({ pair, agentType }: { pair: ToolCallPair; agentType: string }) {
  const [expanded, setExpanded] = useState(false)
  const meta = AGENT_META[agentType] ?? AGENT_META.system

  const inputStr = (() => {
    try { return JSON.stringify(pair.use.input, null, 2) } catch { return '[input]' }
  })()
  const inputPreview = (() => {
    try { return JSON.stringify(pair.use.input).slice(0, 80) } catch { return '[input]' }
  })()

  const reasoningPreview = pair.reasoning
    ? stripMarkdown(pair.reasoning).slice(0, 80)
    : ''

  return (
    <div className={`rounded-md border text-xs font-mono ${meta.border} overflow-hidden`}>
      <button
        type="button"
        className="w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0 text-center">{expanded ? '▾' : '▸'}</span>
        <span className={`font-semibold shrink-0 ${meta.tool}`}>{pair.use.tool}</span>
        {!expanded && (
          <>
            {reasoningPreview ? (
              <span className="text-gray-400 truncate italic opacity-60 font-sans">
                — {reasoningPreview}
              </span>
            ) : (
              <span className="text-gray-400 truncate opacity-70">{inputPreview}</span>
            )}
          </>
        )}
        {pair.result && (
          <span className="ml-auto shrink-0 text-gray-400">
            {pair.result.result && pair.result.result.length > 0 ? '✓' : '—'}
          </span>
        )}
        {pair.use.ts && (
          <span className="text-gray-400 shrink-0 text-[10px]">
            {new Date(pair.use.ts).toLocaleTimeString()}
          </span>
        )}
      </button>

      {expanded && (
        <div className="border-t bg-gray-50 px-3 py-2.5 space-y-3 animate-fade-in">
          {pair.reasoning && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-sans">Why</p>
              <div className="prose prose-xs max-w-none text-gray-600 text-xs leading-relaxed bg-white border border-gray-100 rounded p-2 max-h-48 overflow-y-auto font-sans [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_h1]:text-sm [&_h2]:text-xs [&_h3]:text-xs [&_code]:bg-gray-100 [&_code]:px-0.5 [&_code]:rounded [&_table]:border-collapse [&_table]:w-full [&_th]:border [&_th]:border-gray-300 [&_th]:bg-gray-50 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-gray-200 [&_td]:px-2 [&_td]:py-1">
                <GfmMarkdown>{pair.reasoning}</GfmMarkdown>
              </div>
            </div>
          )}

          <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-sans">Input</p>
            <pre className="whitespace-pre-wrap text-gray-700 text-xs leading-relaxed bg-white border border-gray-100 rounded p-2">
              {inputStr}
            </pre>
          </div>

          {pair.result && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-sans">Result</p>
              <pre className="whitespace-pre-wrap text-gray-600 text-xs leading-relaxed max-h-56 overflow-y-auto bg-white border border-gray-100 rounded p-2">
                {pair.result.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/** Renders accumulated agent thoughts as collapsible markdown prose.
 *  Has two levels of expansion: scrollable (default) and fully expanded.
 *
 *  When in clipped (scrollable) mode, the inner viewport auto-scrolls to the
 *  bottom whenever the text changes, so the latest reasoning is always
 *  visible without the user having to scroll manually — same "tail -f" feel
 *  as the live thought ticker above. */
function ThoughtBubble({ text, agentType }: { text: string; agentType: string }) {
  const [open, setOpen] = useState(true)
  const [fullyExpanded, setFullyExpanded] = useState(false)
  const meta = AGENT_META[agentType] ?? AGENT_META.system
  const scrollRef = useRef<HTMLDivElement>(null)

  // Tail-follow when collapsed/clipped. We skip the auto-scroll when fully
  // expanded so the user can scroll up freely without us yanking them down.
  useEffect(() => {
    if (!open || fullyExpanded) return
    const el = scrollRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [text, open, fullyExpanded])

  if (!text.trim()) return null

  const CLIP_HEIGHT = 'max-h-64'

  return (
    <div className={`rounded-md border overflow-hidden ${meta.header} ${meta.border}`}>
      <button
        type="button"
        className={`w-full text-left px-3 py-2 flex items-center gap-2 hover:brightness-95 transition-colors ${meta.header}`}
        onClick={() => setOpen((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0 text-center text-[10px]">{open ? '▾' : '▸'}</span>
        <p className={`text-[10px] uppercase tracking-wider opacity-60 ${meta.tool}`}>
          {meta.icon} {meta.label} thoughts
        </p>
        <span className={`ml-auto text-[10px] ${meta.tool} opacity-50`}>
          {open ? 'collapse' : 'expand'}
        </span>
      </button>

      {open && (
        <div className="animate-fade-in">
          {/* prose content — clipped by default, fully expandable */}
          <div
            ref={scrollRef}
            className={`px-3 pb-1 overflow-y-auto transition-all ${fullyExpanded ? '' : CLIP_HEIGHT}`}
          >
            <div className="prose prose-xs max-w-none text-gray-700 [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0 [&_code]:bg-white/60 [&_code]:px-0.5 [&_code]:rounded text-xs leading-relaxed pt-2 [&_table]:border-collapse [&_table]:w-full [&_th]:border [&_th]:border-gray-300 [&_th]:bg-white/40 [&_th]:px-2 [&_th]:py-1 [&_th]:text-left [&_td]:border [&_td]:border-gray-200 [&_td]:px-2 [&_td]:py-1">
              <GfmMarkdown>{text}</GfmMarkdown>
            </div>
          </div>

          {/* "Show all / Show less" toggle at bottom — always visible */}
          <div className={`flex justify-center pb-2 pt-1 ${meta.header}`}>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setFullyExpanded((p) => !p) }}
              className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${meta.tool} opacity-50 hover:opacity-80 ${meta.header} ${meta.border}`}
            >
              {fullyExpanded ? '↑ Show less' : '↓ Show all'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

function AgentBadge({ agentType, label }: { agentType: string; label: string }) {
  const meta = AGENT_META[agentType] ?? AGENT_META.system
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[11px] font-medium ${meta.chip}`}>
      <span>{meta.icon}</span>
      <span>{label}</span>
    </span>
  )
}

function PhaseSection({
  phase,
  showThoughts,
  collapseSignal,
}: {
  phase: AgentPhase
  showThoughts: boolean
  /** Bumped when the parent Collapse-all/Expand-all toggle fires. The signal
   *  is { value, version } — when `version` changes, the section adopts the
   *  new collapsed state. After that the user can still toggle individually
   *  by clicking the header (local state takes back over until the next
   *  signal bump). */
  collapseSignal?: { value: boolean; version: number }
}) {
  const [collapsed, setCollapsed] = useState(false)
  // React to parent collapse-all signals. Only the version change triggers a
  // sync — that way per-phase clicks between signals aren't fighting the
  // parent state.
  useEffect(() => {
    if (collapseSignal) setCollapsed(collapseSignal.value)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapseSignal?.version])
  // Join segments with a blank line so each reasoning chunk is separated
  // visually in the rendered markdown (paragraph break).
  const text = phase.textSegments.length > 0
    ? phase.textSegments.join('\n\n')
    : phase.textEvents.map((e) => e.text ?? '').join('')
  const meta = AGENT_META[phase.agentType] ?? AGENT_META.system

  const statusDecoration =
    phase.label === 'Complete' ? (
      <span className="ml-auto text-emerald-500 text-xs font-medium">✓ Done</span>
    ) : phase.label === 'Error' ? (
      <span className="ml-auto text-red-500 text-xs font-medium">✗ Error</span>
    ) : phase.label === 'Awaiting Approval' ? (
      <span className="ml-auto text-yellow-600 text-xs font-medium animate-pulse">⏳ HITL</span>
    ) : phase.startTs ? (
      <span className="ml-auto text-[10px] text-gray-400">
        {new Date(phase.startTs).toLocaleTimeString()}
      </span>
    ) : null

  return (
    <div className={`rounded-lg border shadow-sm overflow-hidden ${meta.border}`}>
      <button
        type="button"
        className={`w-full text-left px-4 py-2.5 flex items-center gap-2.5 ${meta.header} transition-colors hover:brightness-95`}
        onClick={() => setCollapsed((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0 text-center text-[10px]">
          {collapsed ? '▸' : '▾'}
        </span>
        <AgentBadge agentType={phase.agentType} label={phase.label} />
        {statusDecoration}
      </button>

      {!collapsed && (
        <div className="bg-white p-3 space-y-2.5">
          {showThoughts && text && (
            <ThoughtBubble text={text} agentType={phase.agentType} />
          )}

          {phase.toolPairs.map((pair, i) => (
            <ToolCallRow
              key={`${pair.use.tool}-${pair.use.ts ?? i}`}
              pair={pair}
              agentType={phase.agentType}
            />
          ))}

          {phase.rejectionEvent && (
            <div className="bg-red-50 border border-red-200 rounded-md p-2.5 text-xs space-y-1">
              <p className="text-[10px] uppercase tracking-wider text-red-400 font-medium">
                ✗ QA rejected — fix attempt {phase.rejectionEvent.attempt ?? '?'} of {phase.rejectionEvent.max_attempts ?? '?'}
              </p>
              {phase.rejectionEvent.recheck && (
                <pre className="whitespace-pre-wrap text-red-700 text-xs leading-relaxed max-h-36 overflow-y-auto bg-red-50 border border-red-100 rounded p-1.5 font-mono">
                  {phase.rejectionEvent.recheck}
                </pre>
              )}
            </div>
          )}

          {phase.recheckEvent && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5">
                Pytest recheck
              </p>
              <pre
                className={`text-xs p-2.5 rounded-md border whitespace-pre-wrap max-h-56 overflow-y-auto leading-relaxed ${
                  phase.recheckEvent.output?.includes('passed') &&
                  !phase.recheckEvent.output?.includes('failed')
                    ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                    : 'bg-red-50 border-red-200 text-red-800'
                }`}
              >
                {phase.recheckEvent.output}
              </pre>
            </div>
          )}

          {phase.errorEvent && (
            <div className="bg-red-50 border border-red-200 rounded-md p-2.5 text-xs text-red-700 flex items-start gap-2">
              <span>✗</span>
              <span>{phase.errorEvent.message}</span>
            </div>
          )}

          {!text &&
            phase.toolPairs.length === 0 &&
            !phase.recheckEvent &&
            !phase.errorEvent && (
              <p className="text-xs text-gray-400 italic py-1">
                {phase.pytestRunning
                  ? '🧪 Running pytest… (this may take 30–60 s on large suites)'
                  : phase.startTs
                  ? (phase.label.includes('Verify') ? '🧪 Running tests…' : 'Awaiting activity…')
                  : 'No tool activity recorded.'}
              </p>
            )}
        </div>
      )}
    </div>
  )
}

function QACoderThread({
  phases,
  showThoughts,
  collapseSignal,
}: {
  phases: AgentPhase[]
  showThoughts: boolean
  collapseSignal?: { value: boolean; version: number }
}) {
  const [expanded, setExpanded] = useState(true)
  // The parent's collapse-all signal collapses the wrapper itself in addition
  // to propagating to nested PhaseSections.
  useEffect(() => {
    if (collapseSignal) setExpanded(!collapseSignal.value)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [collapseSignal?.version])
  const attemptLabel = phases[0]?.label.match(/Attempt (\d+)/)?.[1]

  return (
    <div className="rounded-lg border border-dashed border-gray-300 overflow-hidden">
      <button
        type="button"
        className="w-full text-left px-4 py-2.5 flex items-center gap-2 bg-gray-50 hover:bg-gray-100 transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="text-gray-400 w-3 text-[10px] text-center">{expanded ? '▾' : '▸'}</span>
        <span className="text-xs font-semibold text-gray-600">
          🔄 QA ↔ Coder Loop {attemptLabel ? `— Attempt ${attemptLabel}` : ''}
        </span>
        <span className="text-[10px] text-gray-400 ml-1">
          ({phases.length} turn{phases.length !== 1 ? 's' : ''})
        </span>
        <span className="ml-auto flex items-center gap-1">
          <span className="inline-block w-2 h-2 rounded-full bg-violet-400" title="QA" />
          <span className="text-gray-300 text-[8px]">↔</span>
          <span className="inline-block w-2 h-2 rounded-full bg-amber-400" title="Coder" />
        </span>
      </button>
      {expanded && (
        <div className="p-3 space-y-2 bg-white">
          {phases.map((phase) => (
            <PhaseSection
              key={phase.id}
              phase={phase}
              showThoughts={showThoughts}
              collapseSignal={collapseSignal}
            />
          ))}
        </div>
      )}
    </div>
  )
}

function clusterPhases(phases: AgentPhase[]): Array<
  | { kind: 'single'; phase: AgentPhase }
  | { kind: 'loop'; phases: AgentPhase[] }
> {
  const clusters: Array<
    { kind: 'single'; phase: AgentPhase } | { kind: 'loop'; phases: AgentPhase[] }
  > = []
  let loopBuffer: AgentPhase[] = []

  function flushLoop() {
    if (loopBuffer.length === 0) return
    if (loopBuffer.length === 1) {
      clusters.push({ kind: 'single', phase: loopBuffer[0] })
    } else {
      clusters.push({ kind: 'loop', phases: [...loopBuffer] })
    }
    loopBuffer = []
  }

  for (const phase of phases) {
    if (phase.agentType === 'qa' || phase.agentType === 'coder') {
      loopBuffer.push(phase)
    } else {
      flushLoop()
      clusters.push({ kind: 'single', phase })
    }
  }
  flushLoop()

  return clusters
}

// ── Public component ───────────────────────────────────────────────────────

export function AgentTimeline({
  events,
  defaultLabel = 'Agent',
  showThoughts = false,
}: {
  events: AgentEvent[]
  defaultLabel?: string
  showThoughts?: boolean
}) {
  const phases = useMemo(
    () => groupIntoPhases(events, defaultLabel),
    [events, defaultLabel],
  )

  const clusters = useMemo(() => clusterPhases(phases), [phases])

  // Master collapse state. We use a {value, version} pair so each click
  // produces a NEW signal even when the value hasn't changed (e.g. user
  // expanded one phase manually then clicks "Expand all" — the signal
  // version bumps and PhaseSections re-sync). version=0 means "no signal
  // sent yet", so freshly-mounted phases keep their default expanded state.
  const [collapseSignal, setCollapseSignal] = useState<{ value: boolean; version: number }>({
    value: false,
    version: 0,
  })
  const sendCollapseSignal = (value: boolean) =>
    setCollapseSignal((prev) => ({ value, version: prev.version + 1 }))

  if (phases.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center">
        <p className="text-sm text-gray-400 italic">Waiting for events…</p>
      </div>
    )
  }

  // Only show the master toggle when there's actually more than one phase to
  // collapse — for a single-phase timeline the per-card toggle is enough.
  const showMasterToggle = phases.length > 1

  return (
    <div className="space-y-2">
      {showMasterToggle && (
        <div className="flex items-center justify-end gap-1 -mb-1">
          <button
            type="button"
            onClick={() => sendCollapseSignal(true)}
            className="text-[10px] px-2 py-0.5 rounded-full border border-gray-200 bg-white text-gray-500 hover:text-gray-700 hover:border-gray-300 transition-colors"
            title="Collapse every phase below"
          >
            ▸ Collapse all
          </button>
          <button
            type="button"
            onClick={() => sendCollapseSignal(false)}
            className="text-[10px] px-2 py-0.5 rounded-full border border-gray-200 bg-white text-gray-500 hover:text-gray-700 hover:border-gray-300 transition-colors"
            title="Expand every phase below"
          >
            ▾ Expand all
          </button>
        </div>
      )}
      {clusters.map((cluster, i) =>
        cluster.kind === 'single' ? (
          <PhaseSection
            key={cluster.phase.id}
            phase={cluster.phase}
            showThoughts={showThoughts}
            collapseSignal={collapseSignal}
          />
        ) : (
          <QACoderThread
            key={`loop-${i}`}
            phases={cluster.phases}
            showThoughts={showThoughts}
            collapseSignal={collapseSignal}
          />
        ),
      )}
    </div>
  )
}

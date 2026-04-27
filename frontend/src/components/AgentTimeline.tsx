import { useState, useMemo } from 'react'
import Markdown from 'react-markdown'

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
  output?: string
  ts?: string
  ticket_id?: string
  total_input_tokens?: number
  total_output_tokens?: number
  cost_usd?: number
}

interface ToolCallPair {
  use: AgentEvent
  result: AgentEvent | null
  reasoning: string // agent text that immediately preceded this tool call
}

interface AgentPhase {
  id: string
  label: string
  agentType: string
  startTs?: string
  textEvents: AgentEvent[]
  toolPairs: ToolCallPair[]
  recheckEvent: AgentEvent | null
  errorEvent: AgentEvent | null
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

// ── Phase helpers ──────────────────────────────────────────────────────────

function makePhaseLabel(status: string, fixAttempt?: number): string {
  const attempt = fixAttempt !== undefined ? ` — Attempt ${fixAttempt + 1}` : ''
  switch (status) {
    case 'qa_running':    return `QA Agent${attempt}`
    case 'coder_running': return `Coder${attempt}`
    case 'hitl_waiting':  return 'Awaiting Approval'
    case 'done':          return 'Complete'
    case 'error':         return 'Error'
    case 'skipped':       return 'Skipped'
    default:              return status
  }
}

function agentFromStatus(status: string): string {
  if (status.startsWith('coder')) return 'coder'
  if (status.startsWith('qa'))    return 'qa'
  return 'system'
}

// Strip markdown syntax for single-line previews
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

function groupIntoPhases(events: AgentEvent[], defaultLabel: string): AgentPhase[] {
  const phases: AgentPhase[] = []
  // Stores pending tool-use events together with the reasoning text that preceded them
  let toolUseQueue: Array<{ event: AgentEvent; reasoning: string }> = []
  let pendingText = '' // accumulates text_delta between tool calls

  let current: AgentPhase = {
    id: 'default',
    label: defaultLabel,
    agentType: defaultLabel.toLowerCase().includes('reviewer') ? 'reviewer' : 'qa',
    textEvents: [],
    toolPairs: [],
    recheckEvent: null,
    errorEvent: null,
  }

  for (const event of events) {
    if (event.type === 'session_status' && event.status) {
      toolUseQueue.forEach(({ event: use, reasoning }) =>
        current.toolPairs.push({ use, result: null, reasoning }),
      )
      toolUseQueue = []
      pendingText = ''
      if (
        current.textEvents.length > 0 ||
        current.toolPairs.length > 0 ||
        current.recheckEvent ||
        current.errorEvent
      ) {
        phases.push(current)
      }
      current = {
        id: `${event.status}-${event.fix_attempt ?? 0}-${phases.length}`,
        label: makePhaseLabel(event.status, event.fix_attempt),
        agentType: agentFromStatus(event.status),
        startTs: event.ts,
        textEvents: [],
        toolPairs: [],
        recheckEvent: null,
        errorEvent: null,
      }
    } else if (['text_delta', 'qa_text_delta', 'coder_text_delta'].includes(event.type)) {
      current.textEvents.push(event)
      pendingText += event.text ?? ''
    } else if (event.type === 'tool_use') {
      // Capture everything the agent said since the last tool call as its reasoning
      toolUseQueue.push({ event, reasoning: pendingText })
      pendingText = ''
    } else if (event.type === 'tool_result') {
      const queued = toolUseQueue.shift()
      if (queued) current.toolPairs.push({ use: queued.event, result: event, reasoning: queued.reasoning })
    } else if (event.type === 'recheck_output') {
      current.recheckEvent = event
    } else if (event.type === 'error') {
      current.errorEvent = event
    }
  }

  toolUseQueue.forEach(({ event: use, reasoning }) =>
    current.toolPairs.push({ use, result: null, reasoning }),
  )
  if (
    current.textEvents.length > 0 ||
    current.toolPairs.length > 0 ||
    current.recheckEvent ||
    current.errorEvent
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
        <div className="border-t bg-gray-50 px-3 py-2.5 space-y-3">
          {/* Why — agent's reasoning for this tool call, rendered as markdown */}
          {pair.reasoning && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-sans">
                Why
              </p>
              <div className="prose prose-xs max-w-none text-gray-600 text-xs leading-relaxed bg-white border border-gray-100 rounded p-2 max-h-48 overflow-y-auto font-sans [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1 [&_li]:my-0 [&_h1]:text-sm [&_h2]:text-xs [&_h3]:text-xs [&_code]:bg-gray-100 [&_code]:px-0.5 [&_code]:rounded">
                <Markdown>{pair.reasoning}</Markdown>
              </div>
            </div>
          )}

          {/* Input */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-sans">
              Input
            </p>
            <pre className="whitespace-pre-wrap text-gray-700 text-xs leading-relaxed bg-white border border-gray-100 rounded p-2">
              {inputStr}
            </pre>
          </div>

          {/* Result */}
          {pair.result && (
            <div>
              <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-sans">
                Result
              </p>
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

// Renders agent thoughts as markdown prose
function ThoughtBubble({ text, agentType }: { text: string; agentType: string }) {
  const meta = AGENT_META[agentType] ?? AGENT_META.system
  if (!text.trim()) return null
  return (
    <div className={`rounded-md border px-3 py-2.5 text-xs leading-relaxed ${meta.header} ${meta.border}`}>
      <p className={`text-[10px] uppercase tracking-wider mb-1.5 opacity-60 ${meta.tool}`}>
        {meta.icon} {meta.label} thoughts
      </p>
      <div className="prose prose-xs max-w-none text-gray-700 [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0 [&_code]:bg-white/60 [&_code]:px-0.5 [&_code]:rounded">
        <Markdown>{text}</Markdown>
      </div>
    </div>
  )
}

// Status badge for phase headers
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
}: {
  phase: AgentPhase
  showThoughts: boolean
}) {
  const [collapsed, setCollapsed] = useState(false)
  const text = phase.textEvents.map((e) => e.text ?? '').join('')
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
          {/* Full thought stream (markdown) — visible only when showThoughts is on */}
          {showThoughts && text && (
            <ThoughtBubble text={text} agentType={phase.agentType} />
          )}

          {/* Tool call pairs — always shown; each includes its own Why section */}
          {phase.toolPairs.map((pair, i) => (
            <ToolCallRow
              key={`${pair.use.tool}-${pair.use.ts ?? i}`}
              pair={pair}
              agentType={phase.agentType}
            />
          ))}

          {/* Pytest recheck output */}
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

          {/* Error event */}
          {phase.errorEvent && (
            <div className="bg-red-50 border border-red-200 rounded-md p-2.5 text-xs text-red-700 flex items-start gap-2">
              <span>✗</span>
              <span>{phase.errorEvent.message}</span>
            </div>
          )}

          {/* Empty placeholder */}
          {!showThoughts &&
            !text &&
            phase.toolPairs.length === 0 &&
            !phase.recheckEvent &&
            !phase.errorEvent && (
              <p className="text-xs text-gray-400 italic py-1">No tool activity recorded.</p>
            )}
        </div>
      )}
    </div>
  )
}

// QA-Coder interaction loop — groups consecutive qa/coder phases together
function QACoderThread({
  phases,
  showThoughts,
}: {
  phases: AgentPhase[]
  showThoughts: boolean
}) {
  const [expanded, setExpanded] = useState(true)
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
            <PhaseSection key={phase.id} phase={phase} showThoughts={showThoughts} />
          ))}
        </div>
      )}
    </div>
  )
}

// Groups phases into reviewer phases and qa-coder loop clusters
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
  // Always group all events so reasoning can be extracted from text_delta events
  // even when showThoughts is off. The showThoughts flag only controls the
  // ThoughtBubble rendering inside PhaseSection.
  const phases = useMemo(
    () => groupIntoPhases(events, defaultLabel),
    [events, defaultLabel],
  )

  const clusters = useMemo(() => clusterPhases(phases), [phases])

  if (phases.length === 0) {
    return (
      <div className="rounded-lg border border-dashed border-gray-200 p-6 text-center">
        <p className="text-sm text-gray-400 italic">Waiting for events…</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {clusters.map((cluster, i) =>
        cluster.kind === 'single' ? (
          <PhaseSection key={cluster.phase.id} phase={cluster.phase} showThoughts={showThoughts} />
        ) : (
          <QACoderThread key={`loop-${i}`} phases={cluster.phases} showThoughts={showThoughts} />
        ),
      )}
    </div>
  )
}

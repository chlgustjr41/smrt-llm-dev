import { useState, useMemo } from 'react'

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

function makePhaseLabel(status: string, fixAttempt?: number): string {
  const attempt = fixAttempt !== undefined ? ` — Attempt ${fixAttempt}` : ''
  switch (status) {
    case 'qa_running':
      return `QA Agent${attempt}`
    case 'coder_running':
      return `Coder Agent${attempt}`
    case 'hitl_waiting':
      return 'Awaiting Approval'
    case 'done':
      return 'Complete'
    case 'error':
      return 'Error'
    case 'skipped':
      return 'Skipped'
    default:
      return status
  }
}

function agentFromStatus(status: string): string {
  if (status.startsWith('coder')) return 'coder'
  if (status.startsWith('qa')) return 'qa'
  return 'system'
}

function groupIntoPhases(events: AgentEvent[], defaultLabel: string): AgentPhase[] {
  const phases: AgentPhase[] = []
  let toolUseQueue: AgentEvent[] = []
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
      toolUseQueue.forEach((use) => current.toolPairs.push({ use, result: null }))
      toolUseQueue = []
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
    } else if (event.type === 'tool_use') {
      toolUseQueue.push(event)
    } else if (event.type === 'tool_result') {
      const use = toolUseQueue.shift()
      if (use) {
        current.toolPairs.push({ use, result: event })
      }
    } else if (event.type === 'recheck_output') {
      current.recheckEvent = event
    } else if (event.type === 'error') {
      current.errorEvent = event
    }
  }

  toolUseQueue.forEach((use) => current.toolPairs.push({ use, result: null }))
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

const AGENT_STYLES = {
  reviewer: {
    header: 'bg-blue-50 border-blue-200',
    text: 'text-blue-800',
    border: 'border-blue-200',
    tool: 'text-blue-700',
  },
  qa: {
    header: 'bg-purple-50 border-purple-200',
    text: 'text-purple-800',
    border: 'border-purple-200',
    tool: 'text-purple-700',
  },
  coder: {
    header: 'bg-orange-50 border-orange-200',
    text: 'text-orange-800',
    border: 'border-orange-200',
    tool: 'text-orange-700',
  },
  system: {
    header: 'bg-gray-50 border-gray-200',
    text: 'text-gray-700',
    border: 'border-gray-200',
    tool: 'text-gray-600',
  },
}

function ToolCallRow({ pair }: { pair: ToolCallPair }) {
  const [expanded, setExpanded] = useState(false)
  const style =
    AGENT_STYLES[pair.use.agent as keyof typeof AGENT_STYLES] ?? AGENT_STYLES.system

  return (
    <div className={`border rounded text-xs font-mono ${style.border}`}>
      <button
        className="w-full text-left px-3 py-1.5 flex items-center gap-2 hover:bg-gray-50"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0">{expanded ? '▼' : '▶'}</span>
        <span className={`font-semibold ${style.tool}`}>{pair.use.tool}</span>
        {!expanded && (
          <span className="text-gray-400 truncate">
            {JSON.stringify(pair.use.input).slice(0, 80)}
          </span>
        )}
        {pair.use.ts && (
          <span className="ml-auto text-gray-400 shrink-0">
            {new Date(pair.use.ts).toLocaleTimeString()}
          </span>
        )}
      </button>
      {expanded && (
        <div className="border-t px-3 py-2 space-y-2 bg-gray-50">
          <div>
            <p className="text-gray-400 text-xs mb-1">Input</p>
            <pre className="whitespace-pre-wrap text-gray-700 text-xs">
              {JSON.stringify(pair.use.input, null, 2)}
            </pre>
          </div>
          {pair.result && (
            <div>
              <p className="text-gray-400 text-xs mb-1">Result</p>
              <pre className="whitespace-pre-wrap text-gray-600 text-xs max-h-48 overflow-y-auto">
                {pair.result.result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function PhaseSection({ phase, defaultOpen }: { phase: AgentPhase; defaultOpen: boolean }) {
  const [collapsed, setCollapsed] = useState(!defaultOpen)
  const style =
    AGENT_STYLES[phase.agentType as keyof typeof AGENT_STYLES] ?? AGENT_STYLES.system
  const text = phase.textEvents.map((e) => e.text ?? '').join('')

  return (
    <div className={`border rounded overflow-hidden ${style.border}`}>
      <button
        className={`w-full text-left px-3 py-2 flex items-center gap-2 border-b ${style.header}`}
        onClick={() => setCollapsed((p) => !p)}
      >
        <span className="text-gray-400 w-3 shrink-0">{collapsed ? '▶' : '▼'}</span>
        <span className={`font-semibold text-sm ${style.text}`}>{phase.label}</span>
        {phase.startTs && (
          <span className="ml-auto text-xs text-gray-400">
            {new Date(phase.startTs).toLocaleTimeString()}
          </span>
        )}
      </button>
      {!collapsed && (
        <div className="p-3 space-y-2 bg-white">
          {text && (
            <div className="text-xs text-gray-700 leading-relaxed bg-gray-50 rounded p-2 max-h-32 overflow-y-auto">
              {text}
            </div>
          )}
          {phase.toolPairs.map((pair, i) => (
            <ToolCallRow key={i} pair={pair} />
          ))}
          {phase.recheckEvent && (
            <div>
              <p className="text-xs text-gray-500 mb-1 font-medium">Pytest recheck</p>
              <pre
                className={`text-xs p-2 rounded border whitespace-pre-wrap max-h-48 overflow-y-auto ${
                  phase.recheckEvent.output?.includes('passed') &&
                  !phase.recheckEvent.output?.includes('failed')
                    ? 'bg-green-50 border-green-200 text-green-800'
                    : 'bg-red-50 border-red-200 text-red-800'
                }`}
              >
                {phase.recheckEvent.output}
              </pre>
            </div>
          )}
          {phase.errorEvent && (
            <div className="bg-red-50 border border-red-200 rounded p-2 text-xs text-red-700">
              Error: {phase.errorEvent.message}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function AgentTimeline({
  events,
  defaultLabel = 'Agent',
}: {
  events: AgentEvent[]
  defaultLabel?: string
}) {
  const phases = useMemo(() => groupIntoPhases(events, defaultLabel), [events, defaultLabel])

  if (phases.length === 0) {
    return <p className="text-xs text-gray-400 italic">Waiting for events…</p>
  }

  return (
    <div className="space-y-2">
      {phases.map((phase) => (
        <PhaseSection key={phase.id} phase={phase} defaultOpen={true} />
      ))}
    </div>
  )
}

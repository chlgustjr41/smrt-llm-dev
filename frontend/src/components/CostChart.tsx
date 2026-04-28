import { useState, useEffect } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from 'recharts'
import { getRunCosts, type RunCostEntry } from '../api/stats'

const SUBAGENT_COLORS = {
  Reviewer: '#3b82f6',
  QA: '#8b5cf6',
  Coder: '#f59e0b',
}

function modelShort(model: string | null | undefined): string {
  if (!model) return ''
  // Shorten "claude-sonnet-4-6" → "sonnet-4-6"
  return model.replace(/^claude-/, '')
}

function CostTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string; payload: Record<string, unknown> }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const total = payload.reduce((s, p) => s + p.value, 0)
  const entry = payload[0]?.payload as RunCostEntry & { name: string }
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs space-y-1.5 min-w-[180px]">
      <p className="font-mono text-gray-500 mb-2">{label}</p>
      {payload.map((p) => {
        const modelKey = p.name === 'Reviewer' ? 'reviewer_model' : p.name === 'QA' ? 'qa_model' : 'coder_model'
        const model = (entry as Record<string, unknown>)[modelKey] as string | null
        return (
          <div key={p.name} className="space-y-0.5">
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
                <span className="text-gray-600">{p.name}</span>
              </div>
              <span className="font-mono font-medium text-gray-800">${p.value.toFixed(6)}</span>
            </div>
            {model && (
              <div className="pl-3.5">
                <span className="font-mono text-[10px] text-gray-400">{modelShort(model)}</span>
              </div>
            )}
          </div>
        )
      })}
      <div className="border-t border-gray-100 pt-1.5 flex justify-between">
        <span className="text-gray-500">Total</span>
        <span className="font-mono font-semibold text-gray-800">${total.toFixed(6)}</span>
      </div>
    </div>
  )
}

function TokenBadge({ input, output }: { input?: number; output?: number }) {
  if (!input && !output) return null
  return (
    <div className="text-[9px] font-mono text-gray-400 mt-0.5">
      {input ? `↑${(input / 1000).toFixed(1)}k` : ''}{input && output ? ' ' : ''}{output ? `↓${(output / 1000).toFixed(1)}k` : ''}
    </div>
  )
}

export function CostChart({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) {
  const [data, setData] = useState<RunCostEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setData(null)
    setError(null)
    getRunCosts(projectId, controller.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId, refreshKey])

  if (error) return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      {error}
    </div>
  )
  if (!data) return (
    <div className="h-56 flex items-center justify-center">
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <span className="animate-spin">⟳</span> Loading cost data…
      </div>
    </div>
  )
  if (data.length === 0) return (
    <div className="rounded-lg border border-dashed border-gray-200 py-8 text-center text-sm text-gray-400 italic">
      No audit runs recorded yet. Start an audit to see cost breakdown.
    </div>
  )

  const chartData = data.map((entry) => {
    const label = entry.ticket_id
      ? entry.ticket_id
      : entry.type === 'qa_session'
        ? `QA:${entry.run_id.slice(0, 6)}`
        : `Rev:${entry.run_id.slice(0, 6)}`
    return {
      name: label,
      Reviewer: entry.reviewer_cost_usd,
      QA: entry.qa_cost_usd,
      Coder: entry.coder_cost_usd,
      reviewer_model: entry.reviewer_model,
      qa_model: entry.qa_model,
      coder_model: entry.coder_model,
      started_at: entry.started_at ? new Date(entry.started_at).toLocaleDateString() : null,
    }
  })

  const reviewerTotal = data.reduce((s, r) => s + r.reviewer_cost_usd, 0)
  const qaTotal = data.reduce((s, r) => s + r.qa_cost_usd, 0)
  const coderTotal = data.reduce((s, r) => s + r.coder_cost_usd, 0)
  const grandTotal = reviewerTotal + qaTotal + coderTotal

  // Aggregate tokens and last-seen model per agent
  const revIn = data.reduce((s, r) => s + (r.reviewer_input_tokens || 0), 0)
  const revOut = data.reduce((s, r) => s + (r.reviewer_output_tokens || 0), 0)
  const qaIn = data.reduce((s, r) => s + (r.qa_input_tokens || 0), 0)
  const qaOut = data.reduce((s, r) => s + (r.qa_output_tokens || 0), 0)
  const coderIn = data.reduce((s, r) => s + (r.coder_input_tokens || 0), 0)
  const coderOut = data.reduce((s, r) => s + (r.coder_output_tokens || 0), 0)
  const revModel = [...data].reverse().find((r) => r.reviewer_model)?.reviewer_model
  const qaModel = [...data].reverse().find((r) => r.qa_model)?.qa_model
  const coderModel = [...data].reverse().find((r) => r.coder_model)?.coder_model

  const summaryAgents = [
    { label: 'Reviewer', value: reviewerTotal, color: SUBAGENT_COLORS.Reviewer, model: revModel, inT: revIn, outT: revOut },
    { label: 'QA', value: qaTotal, color: SUBAGENT_COLORS.QA, model: qaModel, inT: qaIn, outT: qaOut },
    { label: 'Coder', value: coderTotal, color: SUBAGENT_COLORS.Coder, model: coderModel, inT: coderIn, outT: coderOut },
    { label: 'Total', value: grandTotal, color: '#111827', model: null, inT: revIn + qaIn + coderIn, outT: revOut + qaOut + coderOut },
  ]

  return (
    <div className="space-y-3">
      {/* Per-agent accumulated totals */}
      <div className="grid grid-cols-4 gap-2 text-xs">
        {summaryAgents.map(({ label, value, color, model, inT, outT }) => (
          <div key={label} className="rounded-lg bg-gray-50 border border-gray-100 px-2 py-1.5 text-center">
            <div className="flex items-center justify-center gap-1 mb-0.5">
              {label !== 'Total' && <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: color }} />}
              <span className="text-gray-400 font-medium">{label}</span>
            </div>
            <span className="font-mono font-semibold" style={{ color }}>${value.toFixed(4)}</span>
            {model && (
              <div className="mt-0.5 text-[9px] font-mono text-gray-400 truncate" title={model}>
                {modelShort(model)}
              </div>
            )}
            <TokenBadge input={inT} output={outT} />
          </div>
        ))}
      </div>

      <div className="h-56 rounded-lg overflow-hidden">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 4, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" vertical={false} />
            <XAxis
              dataKey="name"
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              tickFormatter={(v: number) => `$${v.toFixed(3)}`}
              axisLine={false}
              tickLine={false}
              width={60}
            />
            <Tooltip content={<CostTooltip />} />
            <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" iconSize={8} />
            <Bar dataKey="Reviewer" fill={SUBAGENT_COLORS.Reviewer} stackId="a" radius={[0, 0, 0, 0]} />
            <Bar dataKey="QA" fill={SUBAGENT_COLORS.QA} stackId="a" />
            <Bar dataKey="Coder" fill={SUBAGENT_COLORS.Coder} stackId="a" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

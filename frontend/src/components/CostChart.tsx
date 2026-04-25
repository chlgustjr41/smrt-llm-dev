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

function CostTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ name: string; value: number; color: string }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const total = payload.reduce((s, p) => s + p.value, 0)
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs space-y-1.5">
      <p className="font-mono text-gray-500 mb-2">{label}</p>
      {payload.map((p) => (
        <div key={p.name} className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ background: p.color }} />
            <span className="text-gray-600">{p.name}</span>
          </div>
          <span className="font-mono font-medium text-gray-800">${p.value.toFixed(6)}</span>
        </div>
      ))}
      <div className="border-t border-gray-100 pt-1.5 flex justify-between">
        <span className="text-gray-500">Total</span>
        <span className="font-mono font-semibold text-gray-800">${total.toFixed(6)}</span>
      </div>
    </div>
  )
}

export function CostChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<RunCostEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getRunCosts(projectId, controller.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

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

  const chartData = data.map((entry) => ({
    name: entry.run_id.slice(0, 8),
    Reviewer: entry.reviewer_cost_usd,
    QA: entry.qa_cost_usd,
    Coder: entry.coder_cost_usd,
    started_at: entry.started_at
      ? new Date(entry.started_at).toLocaleDateString()
      : null,
  }))

  const totalCost = data.reduce(
    (s, r) => s + r.reviewer_cost_usd + r.qa_cost_usd + r.coder_cost_usd,
    0,
  )

  return (
    <div className="space-y-3">
      {/* Summary stat */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="text-sm">
          <span className="text-gray-400 mr-1">Total cost:</span>
          <span className="font-mono font-semibold text-gray-800">${totalCost.toFixed(4)}</span>
        </div>
        <div className="text-sm">
          <span className="text-gray-400 mr-1">Runs:</span>
          <span className="font-semibold text-gray-800">{data.length}</span>
        </div>
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
            <Legend
              wrapperStyle={{ fontSize: 11 }}
              iconType="circle"
              iconSize={8}
            />
            <Bar dataKey="Reviewer" fill={SUBAGENT_COLORS.Reviewer} stackId="a" radius={[0, 0, 0, 0]} />
            <Bar dataKey="QA" fill={SUBAGENT_COLORS.QA} stackId="a" />
            <Bar dataKey="Coder" fill={SUBAGENT_COLORS.Coder} stackId="a" radius={[3, 3, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

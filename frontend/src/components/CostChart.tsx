import { useState, useEffect } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts'
import { getRunCosts, type RunCostEntry } from '../api/stats'

export function CostChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<RunCostEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getRunCosts(projectId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (!data) return <p className="text-xs text-gray-400">Loading cost data…</p>
  if (data.length === 0)
    return <p className="text-xs text-gray-400 italic">No audit runs recorded yet.</p>

  const chartData = data.map((entry) => ({
    name: entry.run_id.slice(0, 8),
    Reviewer: entry.reviewer_cost_usd,
    QA: entry.qa_cost_usd,
    Coder: entry.coder_cost_usd,
  }))

  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
          <XAxis dataKey="name" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11 }} tickFormatter={(v: number) => `$${v.toFixed(4)}`} />
          <Tooltip formatter={(v: number) => `$${v.toFixed(6)}`} />
          <Legend />
          <Bar dataKey="Reviewer" name="Reviewer" fill="#3b82f6" stackId="a" />
          <Bar dataKey="QA" name="QA" fill="#a855f7" stackId="a" />
          <Bar dataKey="Coder" name="Coder" fill="#22c55e" stackId="a" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

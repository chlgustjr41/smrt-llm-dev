import { useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { getDocScoreHistory, type DocScoreEntry } from '../api/stats'

interface ChartPoint {
  date: string
  score: number
  ep_documented: number
  ep_total: number
  mod_documented: number
  mod_total: number
}

function ScoreTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ value: number; payload: ChartPoint }>
  label?: string
}) {
  if (!active || !payload?.length) return null
  const pt = payload[0].payload
  return (
    <div className="bg-white border border-gray-200 rounded-lg shadow-lg p-3 text-xs space-y-1.5">
      <p className="text-gray-500 mb-2">{label}</p>
      <div className="flex items-center justify-between gap-4">
        <span className="text-gray-600">Score</span>
        <span className="font-mono font-semibold text-indigo-700">{pt.score.toFixed(1)}</span>
      </div>
      <div className="border-t border-gray-100 pt-1.5 space-y-1 text-gray-500">
        <p>Endpoints: {pt.ep_documented}/{pt.ep_total}</p>
        <p>Modules: {pt.mod_documented}/{pt.mod_total}</p>
      </div>
    </div>
  )
}

function ScoreBadge({ score }: { score: number }) {
  const cls = score >= 75
    ? 'bg-emerald-100 text-emerald-700'
    : score >= 40
    ? 'bg-amber-100 text-amber-700'
    : 'bg-red-100 text-red-600'
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-semibold ${cls}`}>
      {score.toFixed(1)}
    </span>
  )
}

export function DocScoreChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<DocScoreEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getDocScoreHistory(projectId, controller.signal)
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
    <div className="h-48 flex items-center justify-center">
      <div className="flex items-center gap-2 text-sm text-gray-400">
        <span className="animate-spin">⟳</span> Loading doc scores…
      </div>
    </div>
  )
  if (data.length === 0) return (
    <div className="rounded-lg border border-dashed border-gray-200 py-8 text-center text-sm text-gray-400 italic">
      No documentation score history yet. Run an audit to generate docs.
    </div>
  )

  const chartData: ChartPoint[] = data.map((entry) => ({
    date: new Date(entry.ts).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }),
    score: entry.score,
    ep_documented: entry.ep_documented,
    ep_total: entry.ep_total,
    mod_documented: entry.mod_documented,
    mod_total: entry.mod_total,
  }))

  const latest = data[data.length - 1]
  const trend = data.length >= 2
    ? data[data.length - 1].score - data[data.length - 2].score
    : null

  return (
    <div className="space-y-3">
      {/* Summary */}
      <div className="flex items-center gap-4 flex-wrap">
        <div className="flex items-center gap-2 text-sm">
          <span className="text-gray-400">Latest score:</span>
          <ScoreBadge score={latest.score} />
        </div>
        {trend !== null && (
          <div className="text-sm">
            <span className="text-gray-400 mr-1">Trend:</span>
            <span className={trend >= 0 ? 'text-emerald-600 font-medium' : 'text-red-500 font-medium'}>
              {trend >= 0 ? '+' : ''}{trend.toFixed(1)}
            </span>
          </div>
        )}
        <div className="text-xs text-gray-400 ml-auto">
          Score = (endpoints documented × 50%) + (modules documented × 50%)
        </div>
      </div>

      <div className="h-48">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 4, right: 8, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
            />
            <YAxis
              domain={[0, 100]}
              tick={{ fontSize: 10, fill: '#9ca3af' }}
              axisLine={false}
              tickLine={false}
              width={30}
            />
            <ReferenceLine y={75} stroke="#d1fae5" strokeDasharray="4 4" label={{ value: 'Good', fontSize: 9, fill: '#6ee7b7' }} />
            <ReferenceLine y={40} stroke="#fef3c7" strokeDasharray="4 4" label={{ value: 'Fair', fontSize: 9, fill: '#fcd34d' }} />
            <Tooltip content={<ScoreTooltip />} />
            <Line
              type="monotone"
              dataKey="score"
              stroke="#6366f1"
              strokeWidth={2}
              dot={{ fill: '#6366f1', r: 4, strokeWidth: 0 }}
              activeDot={{ r: 6, fill: '#4f46e5' }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

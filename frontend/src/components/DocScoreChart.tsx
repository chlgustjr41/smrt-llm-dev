import { useState, useEffect } from 'react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from 'recharts'
import { getDocScoreHistory, type DocScoreEntry } from '../api/stats'

interface ChartPoint {
  date: string
  score: number
}

export function DocScoreChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<DocScoreEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getDocScoreHistory(projectId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (!data) return <p className="text-xs text-gray-400">Loading doc scores…</p>
  if (data.length === 0)
    return (
      <p className="text-xs text-gray-400 italic">
        No documentation score history yet.
      </p>
    )

  const chartData: ChartPoint[] = data.map((entry) => ({
    date: new Date(entry.ts).toLocaleDateString(),
    score: entry.score,
  }))

  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart data={chartData}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="date" />
        <YAxis domain={[0, 100]} label={{ value: 'Score', angle: -90, position: 'insideLeft' }} />
        <Tooltip />
        <Line
          type="monotone"
          dataKey="score"
          stroke="#6366f1"
          dot={true}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}

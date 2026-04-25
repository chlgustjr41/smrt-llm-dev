import { useState, useEffect } from 'react'
import { Treemap, ResponsiveContainer } from 'recharts'
import { getHeatmap, type HeatmapEntry } from '../api/stats'

interface TreeNode {
  name: string
  size: number
  bugs_resolved: number
  path: string
}

interface SelectedCell {
  name: string
  size: number
  bugs_resolved: number
  path: string
}

function bugColor(bugs: number): string {
  if (bugs === 0) return '#e5e7eb'
  if (bugs === 1) return '#fbbf24'
  return '#ef4444'
}

function CustomContent(props: any) {
  const { x, y, width, height, name, bugs_resolved } = props
  if (width < 2 || height < 2) return null
  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={bugColor(bugs_resolved ?? 0)}
        stroke="#fff"
        strokeWidth={1}
      />
      {width > 40 && height > 20 && (
        <text
          x={x + width / 2}
          y={y + height / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize={10}
          fill="#111"
          style={{ pointerEvents: 'none' }}
        >
          {name}
        </text>
      )}
    </g>
  )
}

export function HeatmapChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<HeatmapEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<SelectedCell | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getHeatmap(projectId, controller.signal)
      .then(setData)
      .catch((e) => {
        if (e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (!data) return <p className="text-xs text-gray-400">Loading heatmap…</p>
  if (data.length === 0)
    return <p className="text-xs text-gray-400 italic">No source files found.</p>

  const treeData: TreeNode[] = data.map((entry) => ({
    name: entry.file,
    size: entry.loc,
    bugs_resolved: entry.bugs_resolved,
    path: entry.file,
  }))

  function handleClick(node: any) {
    const cell: SelectedCell = {
      name: node.name,
      size: node.size,
      bugs_resolved: node.bugs_resolved,
      path: node.path,
    }
    setSelected((prev) =>
      prev && prev.name === cell.name ? null : cell,
    )
  }

  return (
    <div>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={treeData}
            dataKey="size"
            content={<CustomContent />}
            onClick={handleClick}
          />
        </ResponsiveContainer>
      </div>
      {selected && (
        <div className="mt-2 rounded border border-gray-200 bg-gray-50 p-3 text-xs">
          <p className="font-mono font-semibold text-gray-800">{selected.path}</p>
          <p className="text-gray-600">
            LOC: <span className="font-medium text-gray-800">{selected.size}</span>
          </p>
          <p className="text-gray-600">
            Bugs resolved:{' '}
            <span className="font-medium text-gray-800">{selected.bugs_resolved}</span>
          </p>
        </div>
      )}
    </div>
  )
}

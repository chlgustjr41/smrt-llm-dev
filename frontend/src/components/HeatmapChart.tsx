import { useState, useEffect } from 'react'
import { Treemap, ResponsiveContainer } from 'recharts'
import { getHeatmap, type HeatmapEntry } from '../api/stats'

interface TreeNode {
  name: string
  size: number
  bugs_resolved: number
  path: string
}

function bugColor(bugs: number): string {
  if (bugs === 0) return '#f3f4f6'
  if (bugs === 1) return '#fbbf24'
  if (bugs === 2) return '#f97316'
  return '#ef4444'
}

interface CustomContentProps {
  x?: number
  y?: number
  width?: number
  height?: number
  name?: string
  bugs_resolved?: number
}

function CustomContent({ x = 0, y = 0, width = 0, height = 0, name = '', bugs_resolved = 0 }: CustomContentProps) {
  if (width < 4 || height < 4) return null
  const fill = bugColor(bugs_resolved)
  const textColor = bugs_resolved >= 2 ? '#fff' : '#111827'

  return (
    <g>
      <rect
        x={x + 1}
        y={y + 1}
        width={width - 2}
        height={height - 2}
        rx={3}
        fill={fill}
        stroke="#fff"
        strokeWidth={2}
      />
      {width > 50 && height > 24 && (
        <>
          <text
            x={x + width / 2}
            y={y + height / 2 - 5}
            textAnchor="middle"
            dominantBaseline="middle"
            fontSize={10}
            fill={textColor}
            style={{ pointerEvents: 'none', userSelect: 'none' }}
          >
            {name.split('/').pop()}
          </text>
          {bugs_resolved > 0 && (
            <text
              x={x + width / 2}
              y={y + height / 2 + 9}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={9}
              fill={textColor}
              opacity={0.8}
              style={{ pointerEvents: 'none', userSelect: 'none' }}
            >
              {bugs_resolved} bug{bugs_resolved !== 1 ? 's' : ''}
            </text>
          )}
        </>
      )}
    </g>
  )
}

export function HeatmapChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<HeatmapEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<TreeNode | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    getHeatmap(projectId, controller.signal)
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
        <span className="animate-spin">⟳</span> Loading heatmap…
      </div>
    </div>
  )
  if (data.length === 0) return (
    <div className="rounded-lg border border-dashed border-gray-200 py-8 text-center text-sm text-gray-400 italic">
      No source files found in this project yet.
    </div>
  )

  const treeData: TreeNode[] = data.map((entry) => ({
    name: entry.file,
    size: entry.loc,
    bugs_resolved: entry.bugs_resolved,
    path: entry.file,
  }))

  function handleClick(node: TreeNode) {
    setSelected((prev) => prev && prev.name === node.name ? null : node)
  }

  // Legend entries
  const legend = [
    { color: '#f3f4f6', label: '0 bugs', border: '#d1d5db' },
    { color: '#fbbf24', label: '1 bug', border: 'transparent' },
    { color: '#f97316', label: '2 bugs', border: 'transparent' },
    { color: '#ef4444', label: '3+ bugs', border: 'transparent' },
  ]

  return (
    <div className="space-y-3">
      {/* Legend */}
      <div className="flex items-center gap-3 flex-wrap">
        {legend.map(({ color, label, border }) => (
          <div key={label} className="flex items-center gap-1.5 text-xs text-gray-500">
            <span
              className="inline-block w-3 h-3 rounded-sm"
              style={{ background: color, border: `1px solid ${border}` }}
            />
            {label}
          </div>
        ))}
        <span className="text-xs text-gray-400 ml-auto">Click a cell for details</span>
      </div>

      {/* Treemap */}
      <div className="h-56 rounded-lg overflow-hidden border border-gray-100">
        <ResponsiveContainer width="100%" height="100%">
          <Treemap
            data={treeData}
            dataKey="size"
            content={(props) => <CustomContent {...(props as CustomContentProps)} />}
            onClick={(node) => handleClick(node as TreeNode)}
          />
        </ResponsiveContainer>
      </div>

      {/* Selected file detail */}
      {selected && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-1.5">
          <p className="font-mono text-xs font-semibold text-gray-800 break-all">{selected.path}</p>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span><strong className="text-gray-700">{selected.size.toLocaleString()}</strong> lines</span>
            <span>
              <strong className={selected.bugs_resolved > 0 ? 'text-red-600' : 'text-gray-700'}>
                {selected.bugs_resolved}
              </strong>{' '}
              bug{selected.bugs_resolved !== 1 ? 's' : ''} resolved
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

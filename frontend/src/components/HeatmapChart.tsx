import { useState, useEffect, useRef } from 'react'
import { getHeatmap, type HeatmapEntry } from '../api/stats'

interface TreeNode {
  name: string
  size: number
  bugs_resolved: number
  path: string
}

interface LayoutRect extends TreeNode {
  x: number
  y: number
  w: number
  h: number
}

function bugColor(bugs: number): string {
  if (bugs === 0) return '#f3f4f6'
  if (bugs === 1) return '#fbbf24'
  if (bugs === 2) return '#f97316'
  return '#ef4444'
}

function squarify(nodes: TreeNode[], x: number, y: number, w: number, h: number): LayoutRect[] {
  if (!nodes.length) return []
  if (nodes.length === 1) return [{ ...nodes[0], x, y, w, h }]

  const total = nodes.reduce((s, n) => s + n.size, 0)
  let splitSize = 0
  let splitIdx = 0
  while (splitIdx < nodes.length - 1 && splitSize < total / 2) {
    splitSize += nodes[splitIdx].size
    splitIdx++
  }

  const ratio = splitSize / total
  if (w >= h) {
    const splitW = w * ratio
    return [
      ...squarify(nodes.slice(0, splitIdx), x, y, splitW, h),
      ...squarify(nodes.slice(splitIdx), x + splitW, y, w - splitW, h),
    ]
  } else {
    const splitH = h * ratio
    return [
      ...squarify(nodes.slice(0, splitIdx), x, y, w, splitH),
      ...squarify(nodes.slice(splitIdx), x, y + splitH, w, h - splitH),
    ]
  }
}

const SVG_H = 224
const LEGEND = [
  { color: '#f3f4f6', label: '0 bugs', border: '#d1d5db' },
  { color: '#fbbf24', label: '1 bug', border: 'transparent' },
  { color: '#f97316', label: '2 bugs', border: 'transparent' },
  { color: '#ef4444', label: '3+ bugs', border: 'transparent' },
]

export function HeatmapChart({ projectId }: { projectId: number }) {
  const [data, setData] = useState<HeatmapEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<TreeNode | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [svgWidth, setSvgWidth] = useState(600)

  useEffect(() => {
    const controller = new AbortController()
    getHeatmap(projectId, controller.signal)
      .then(setData)
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== 'AbortError') setError(e.message)
      })
    return () => controller.abort()
  }, [projectId])

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      setSvgWidth(Math.max(entries[0].contentRect.width, 200))
    })
    ro.observe(el)
    setSvgWidth(Math.max(el.offsetWidth, 200))
    return () => ro.disconnect()
  }, [])

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

  const nodes: TreeNode[] = [...data]
    .sort((a, b) => b.loc - a.loc)
    .map((e) => ({ name: e.file, size: e.loc, bugs_resolved: e.bugs_resolved, path: e.file }))
  const rects = squarify(nodes, 0, 0, svgWidth, SVG_H)

  function handleClick(rect: LayoutRect) {
    setSelected((prev) => prev?.name === rect.name ? null : rect)
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-3 flex-wrap">
        {LEGEND.map(({ color, label, border }) => (
          <div key={label} className="flex items-center gap-1.5 text-xs text-gray-500">
            <span className="inline-block w-3 h-3 rounded-sm" style={{ background: color, border: `1px solid ${border}` }} />
            {label}
          </div>
        ))}
        <span className="text-xs text-gray-400 ml-auto">Click a cell for details</span>
      </div>

      <div ref={containerRef} className="rounded-lg overflow-hidden border border-gray-100" style={{ height: SVG_H }}>
        <svg width={svgWidth} height={SVG_H} data-testid="treemap">
          {rects.map((rect) => {
            const fill = bugColor(rect.bugs_resolved)
            const textColor = rect.bugs_resolved >= 2 ? '#fff' : '#111827'
            const isSelected = selected?.name === rect.name
            return (
              <g
                key={rect.name}
                data-testid="treemap-cell"
                data-name={rect.name}
                onClick={() => handleClick(rect)}
                style={{ cursor: 'pointer' }}
              >
                <rect
                  x={rect.x + 1} y={rect.y + 1}
                  width={Math.max(0, rect.w - 2)} height={Math.max(0, rect.h - 2)}
                  rx={3}
                  fill={fill}
                  stroke={isSelected ? '#2563eb' : '#fff'}
                  strokeWidth={isSelected ? 2 : 1}
                />
                {rect.w > 50 && rect.h > 24 && (
                  <>
                    <text
                      x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 - 5}
                      textAnchor="middle" dominantBaseline="middle"
                      fontSize={10} fill={textColor}
                      style={{ pointerEvents: 'none', userSelect: 'none' }}
                    >
                      {rect.name.split('/').pop()}
                    </text>
                    {rect.bugs_resolved > 0 && (
                      <text
                        x={rect.x + rect.w / 2} y={rect.y + rect.h / 2 + 9}
                        textAnchor="middle" dominantBaseline="middle"
                        fontSize={9} fill={textColor} opacity={0.8}
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >
                        {rect.bugs_resolved} bug{rect.bugs_resolved !== 1 ? 's' : ''}
                      </text>
                    )}
                  </>
                )}
              </g>
            )
          })}
        </svg>
      </div>

      {selected && (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 space-y-1.5">
          <p className="font-mono text-xs font-semibold text-gray-800 break-all">{selected.path}</p>
          <div className="flex items-center gap-4 text-xs text-gray-500">
            <span><strong className="text-gray-700">{selected.size.toLocaleString()}</strong> lines</span>
            <span>
              <strong className={selected.bugs_resolved > 0 ? 'text-red-600' : 'text-gray-700'}>
                {selected.bugs_resolved}
              </strong>{' '}
              bugs resolved
            </span>
          </div>
        </div>
      )}
    </div>
  )
}

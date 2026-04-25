import { useEffect, useState } from 'react'
import { listProvenance, type ProvenanceEntry } from '../api/provenance'

function ProvenanceCard({ entry }: { entry: ProvenanceEntry }) {
  const [expanded, setExpanded] = useState(false)

  const formattedTs = entry.ts
    ? new Date(entry.ts).toLocaleString()
    : null

  return (
    <div data-testid="provenance-entry" className="border rounded overflow-hidden border-indigo-200">
      <button
        className="w-full text-left px-3 py-2 flex items-center gap-2 bg-indigo-50 hover:bg-indigo-100"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="font-mono text-xs font-medium text-indigo-800">{entry.ticket}</span>
        <span className="text-sm text-indigo-700 truncate ml-1">{entry.subagent}</span>
        <span className="text-xs text-gray-500 ml-1">({entry.attempts} attempt{entry.attempts !== 1 ? 's' : ''})</span>
        <span className="ml-auto text-gray-400 shrink-0">{expanded ? '▼' : '▶'}</span>
      </button>
      {expanded && (
        <div data-testid="provenance-detail" className="p-3 text-xs text-gray-700 bg-white space-y-2">
          {formattedTs && (
            <p className="text-gray-400">{formattedTs}</p>
          )}
          <div>
            <p className="font-semibold text-gray-600 mb-1">Reasoning:</p>
            <p>{entry.reasoning}</p>
          </div>
          <div>
            <p className="font-semibold text-gray-600 mb-1">Sources consulted:</p>
            {entry.sources_consulted.length > 0 ? (
              <ul className="list-disc list-inside space-y-0.5">
                {entry.sources_consulted.map((src) => (
                  <li key={src} className="font-mono">{src}</li>
                ))}
              </ul>
            ) : (
              <p className="italic text-gray-400">(none)</p>
            )}
          </div>
          <div>
            <p className="font-semibold text-gray-600 mb-1">Related lessons:</p>
            {entry.related_lessons_applied.length > 0 ? (
              <ul className="list-disc list-inside space-y-0.5">
                {entry.related_lessons_applied.map((lesson) => (
                  <li key={lesson}>{lesson}</li>
                ))}
              </ul>
            ) : (
              <p className="italic text-gray-400">(none)</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

export function ProvenancePanel({ projectId }: { projectId: number }) {
  const [items, setItems] = useState<ProvenanceEntry[] | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setError(null)
    listProvenance(projectId, controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setItems(data)
        }
      })
      .catch((e: unknown) => {
        if (e instanceof Error && e.name === 'AbortError') return
        setError('Failed to load provenance.')
      })
      .finally(() => {
        setLoading(false)
      })
    return () => controller.abort()
  }, [projectId])

  if (loading) return <p className="text-xs text-gray-400">Loading provenance…</p>
  if (error) return <p className="text-xs text-red-500">{error}</p>
  if (!items || items.length === 0)
    return <p className="text-xs text-gray-400 italic">No provenance entries yet.</p>

  return (
    <div className="space-y-2">
      {items.map((entry) => (
        <ProvenanceCard key={`${entry.ticket}-${entry.subagent}-${entry.ts ?? ''}`} entry={entry} />
      ))}
    </div>
  )
}

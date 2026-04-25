import { useEffect, useState } from 'react'
import Markdown from 'react-markdown'
import { listProvenance, type ProvenanceEntry } from '../api/provenance'

const SUBAGENT_META: Record<string, { icon: string; chip: string }> = {
  coder_agent:    { icon: '🛠️', chip: 'bg-amber-100 text-amber-700 border-amber-200' },
  reviewer_agent: { icon: '🔍', chip: 'bg-blue-100 text-blue-700 border-blue-200' },
  qa_agent:       { icon: '🧪', chip: 'bg-violet-100 text-violet-700 border-violet-200' },
}

function defaultMeta(agent: string) {
  return SUBAGENT_META[agent] ?? { icon: '⚙️', chip: 'bg-gray-100 text-gray-600 border-gray-200' }
}

function AttemptBadge({ n }: { n: number }) {
  return (
    <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium bg-gray-100 text-gray-500 border border-gray-200">
      {n} attempt{n !== 1 ? 's' : ''}
    </span>
  )
}

function ProvenanceCard({ entry }: { entry: ProvenanceEntry }) {
  const [expanded, setExpanded] = useState(false)
  const meta = defaultMeta(entry.subagent)
  const formattedTs = entry.ts ? new Date(entry.ts).toLocaleString() : null

  return (
    <div data-testid="provenance-entry" className="rounded-lg border border-gray-200 shadow-sm overflow-hidden">
      {/* Header row */}
      <button
        type="button"
        className="w-full text-left px-4 py-3 flex items-center gap-2.5 bg-white hover:bg-gray-50 transition-colors"
        onClick={() => setExpanded((p) => !p)}
      >
        <span className="text-base">{meta.icon}</span>
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full border text-[11px] font-medium ${meta.chip}`}>
          {entry.subagent.replace('_agent', '')}
        </span>
        <span className="font-mono text-xs font-semibold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded">
          {entry.ticket}
        </span>
        <AttemptBadge n={entry.attempts} />
        {formattedTs && (
          <span className="ml-auto text-[10px] text-gray-400 shrink-0">{formattedTs}</span>
        )}
        <span className="text-gray-400 text-[10px] shrink-0 ml-1">{expanded ? '▾' : '▸'}</span>
      </button>

      {/* Expanded detail */}
      {expanded && (
        <div data-testid="provenance-detail" className="border-t border-gray-100 bg-gray-50 px-4 py-3 space-y-4 text-xs text-gray-700">
          {/* Reasoning — rendered as markdown */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-medium">Reasoning</p>
            <div className="prose prose-xs max-w-none bg-white border border-gray-100 rounded-md px-3 py-2 text-gray-700
                           [&_p]:my-1 [&_ul]:my-1 [&_li]:my-0 [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:rounded">
              <Markdown>{entry.reasoning}</Markdown>
            </div>
          </div>

          {/* Sources consulted */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-medium">Sources consulted</p>
            {entry.sources_consulted.length > 0 ? (
              <ul className="space-y-1">
                {entry.sources_consulted.map((src) => (
                  <li key={src} className="flex items-center gap-2">
                    <span className="text-gray-300">📄</span>
                    <span className="font-mono text-[11px] text-gray-600 break-all">{src}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="italic text-gray-400">(none)</p>
            )}
          </div>

          {/* Related lessons */}
          <div>
            <p className="text-[10px] uppercase tracking-wider text-gray-400 mb-1.5 font-medium">Related lessons applied</p>
            {entry.related_lessons_applied.length > 0 ? (
              <ul className="space-y-1">
                {entry.related_lessons_applied.map((lesson) => (
                  <li key={lesson} className="flex items-start gap-2">
                    <span className="text-indigo-400 mt-0.5 shrink-0">✓</span>
                    <div className="prose prose-xs max-w-none [&_p]:my-0">
                      <Markdown>{lesson}</Markdown>
                    </div>
                  </li>
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
        if (!controller.signal.aborted) setItems(data)
      })
      .catch((e: unknown) => {
        if (e instanceof Error && e.name === 'AbortError') return
        setError(e instanceof Error ? e.message : 'Failed to load provenance.')
      })
      .finally(() => setLoading(false))
    return () => controller.abort()
  }, [projectId])

  if (loading) return (
    <div className="flex items-center gap-2 text-sm text-gray-400 py-2">
      <span className="animate-spin">⟳</span> Loading provenance…
    </div>
  )
  if (error) return (
    <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
      {error}
    </div>
  )
  if (!items || items.length === 0) return (
    <div className="rounded-lg border border-dashed border-gray-200 py-8 text-center text-sm text-gray-400 italic">
      No provenance entries yet. Entries appear after agent runs complete.
    </div>
  )

  return (
    <div className="space-y-2">
      {items.map((entry) => (
        <ProvenanceCard
          key={`${entry.ticket}-${entry.subagent}-${entry.ts ?? ''}`}
          entry={entry}
        />
      ))}
    </div>
  )
}

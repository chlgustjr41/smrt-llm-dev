import { useState, useEffect } from 'react'
import { listDocs, type DocFile } from '../api/docs'

const BACKENDS = [
  { id: 'github', label: 'GitHub', enabled: true },
  { id: 'obsidian', label: 'Obsidian', enabled: true },
  { id: 'jira', label: 'Jira', enabled: false },
  { id: 'confluence', label: 'Confluence', enabled: false },
] as const

export function DocPanel({ projectId }: { projectId: number }) {
  const [files, setFiles] = useState<DocFile[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    listDocs(projectId, controller.signal)
      .then((data) => { if (!controller.signal.aborted) setFiles(data) })
      .catch(() => { if (!controller.signal.aborted) setFiles([]) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId])

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {BACKENDS.map((b) => (
          <span
            key={b.id}
            className={`px-2 py-1 rounded text-xs font-medium ${
              b.enabled ? 'bg-green-100 text-green-700' : 'bg-gray-100 text-gray-400'
            }`}
          >
            {b.enabled ? `✓ ${b.label}` : `${b.label} (coming soon)`}
          </span>
        ))}
      </div>
      {loading ? (
        <p className="text-xs text-gray-400">Loading docs…</p>
      ) : files.length === 0 ? (
        <p className="text-xs text-gray-400 italic">
          No documentation generated yet. Run Init Audit to generate.
        </p>
      ) : (
        <ul className="text-xs space-y-1 font-mono">
          {files.map((f) => (
            <li key={f.path} className="text-gray-600">
              {f.path}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

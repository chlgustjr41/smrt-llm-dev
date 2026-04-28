import { useState, useEffect } from 'react'
import { listDirectory, type FsEntry } from '../api/filesystem'

interface Props {
  onSelect: (path: string) => void
  onClose: () => void
}

export function FileBrowser({ onSelect, onClose }: Props) {
  const [currentPath, setCurrentPath] = useState('/workspace')
  const [entries, setEntries] = useState<FsEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    listDirectory(currentPath)
      .then(setEntries)
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false))
  }, [currentPath])

  function parentPath(): string | null {
    if (currentPath === '/') return null
    const parent = currentPath.split('/').slice(0, -1).join('/') || '/'
    return parent
  }

  function breadcrumbs(): { label: string; path: string }[] {
    if (currentPath === '/') return [{ label: '/', path: '/' }]
    const parts = currentPath.split('/').filter(Boolean)
    return [
      { label: '/', path: '/' },
      ...parts.map((part, i) => ({
        label: part,
        path: '/' + parts.slice(0, i + 1).join('/'),
      })),
    ]
  }

  const parent = parentPath()

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 flex flex-col overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b">
          <h2 className="text-sm font-semibold text-gray-700">Select Project Folder</h2>
          <button
            type="button"
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 text-xl leading-none px-1"
          >
            ×
          </button>
        </div>

        {/* Breadcrumb bar */}
        <div className="flex items-center gap-1 px-3 py-2 border-b bg-gray-50 text-sm overflow-x-auto">
          {breadcrumbs().map((crumb, i) => (
            <span key={crumb.path} className="flex items-center gap-1 shrink-0">
              {i > 0 && <span className="text-gray-400">/</span>}
              <button
                type="button"
                onClick={() => setCurrentPath(crumb.path)}
                className="text-blue-600 hover:underline whitespace-nowrap"
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </div>

        {/* Directory listing */}
        <div className="max-h-72 overflow-y-auto">
          {loading ? (
            <p className="px-3 py-6 text-sm text-gray-400 text-center">Loading…</p>
          ) : error ? (
            <p className="px-3 py-6 text-sm text-red-500 text-center">{error}</p>
          ) : (
            <ul className="divide-y divide-gray-50">
              {/* Parent directory row */}
              {parent !== null && (
                <li>
                  <button
                    type="button"
                    onClick={() => setCurrentPath(parent)}
                    className="w-full text-left px-4 py-2.5 text-sm hover:bg-gray-100 flex items-center gap-2 transition-colors text-gray-500"
                  >
                    <span>📂</span>
                    <span className="font-mono">..</span>
                    <span className="text-xs text-gray-400 ml-1">(parent directory)</span>
                  </button>
                </li>
              )}
              {entries.length === 0 && (
                <li className="px-3 py-6 text-sm text-gray-400 text-center">Empty directory</li>
              )}
              {entries.map((entry: FsEntry) => (
                <li key={entry.path}>
                  {entry.is_dir ? (
                    <button
                      type="button"
                      onClick={() => setCurrentPath(entry.path)}
                      className="w-full text-left px-4 py-2.5 text-sm hover:bg-blue-50 flex items-center gap-2 transition-colors"
                    >
                      <span className="text-yellow-500">📁</span>
                      <span className="text-gray-800">{entry.name}</span>
                    </button>
                  ) : (
                    <span className="flex px-4 py-2.5 text-sm text-gray-400 items-center gap-2">
                      <span>📄</span>
                      {entry.name}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="border-t px-4 py-3 flex items-center justify-between bg-gray-50">
          <span className="text-xs text-gray-500 truncate mr-2 font-mono">{currentPath}</span>
          <div className="flex gap-2 shrink-0">
            <button
              type="button"
              onClick={onClose}
              className="text-sm px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition-colors"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={() => onSelect(currentPath)}
              className="bg-blue-600 text-white text-sm px-3 py-1.5 rounded-lg hover:bg-blue-700 transition-colors"
            >
              Select this folder
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

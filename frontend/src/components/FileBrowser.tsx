import { useState, useEffect } from 'react'
import { listDirectory, type FsEntry } from '../api/filesystem'

interface Props {
  onSelect: (path: string) => void
}

export function FileBrowser({ onSelect }: Props) {
  const [currentPath, setCurrentPath] = useState('/workspace')
  const [entries, setEntries] = useState<FsEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    listDirectory(currentPath)
      .then(setEntries)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [currentPath])

  // Build breadcrumb segments from the current path
  function breadcrumbs(): { label: string; path: string }[] {
    const parts = currentPath.split('/').filter(Boolean)
    return parts.map((part, i) => ({
      label: part,
      path: '/' + parts.slice(0, i + 1).join('/'),
    }))
  }

  function navigate(path: string) {
    setCurrentPath(path)
  }

  return (
    <div className="border rounded bg-white shadow-sm">
      {/* Breadcrumb bar */}
      <div className="flex items-center gap-1 px-3 py-2 border-b bg-gray-50 text-sm overflow-x-auto">
        <button
          onClick={() => navigate('/workspace')}
          className="text-blue-600 hover:underline whitespace-nowrap"
        >
          workspace
        </button>
        {breadcrumbs().slice(1).map((crumb) => (
          <span key={crumb.path} className="flex items-center gap-1">
            <span className="text-gray-400">/</span>
            <button
              onClick={() => navigate(crumb.path)}
              className="text-blue-600 hover:underline whitespace-nowrap"
            >
              {crumb.label}
            </button>
          </span>
        ))}
      </div>

      {/* Directory listing */}
      <div className="max-h-48 overflow-y-auto">
        {loading ? (
          <p className="px-3 py-4 text-sm text-gray-400">Loading…</p>
        ) : error ? (
          <p className="px-3 py-4 text-sm text-red-500">{error}</p>
        ) : entries.length === 0 ? (
          <p className="px-3 py-4 text-sm text-gray-400">Empty directory</p>
        ) : (
          <ul>
            {entries.map((entry) => (
              <li key={entry.path}>
                {entry.is_dir ? (
                  <button
                    onClick={() => navigate(entry.path)}
                    className="w-full text-left px-3 py-1.5 text-sm hover:bg-blue-50 flex items-center gap-2"
                  >
                    <span className="text-yellow-500">📁</span>
                    {entry.name}
                  </button>
                ) : (
                  <span className="block px-3 py-1.5 text-sm text-gray-400 flex items-center gap-2">
                    <span>📄</span>
                    {entry.name}
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Select current directory button */}
      <div className="border-t px-3 py-2 flex items-center justify-between bg-gray-50">
        <span className="text-xs text-gray-500 truncate mr-2">{currentPath}</span>
        <button
          onClick={() => onSelect(currentPath)}
          className="shrink-0 bg-blue-600 text-white text-xs px-3 py-1 rounded hover:bg-blue-700"
        >
          Select this folder
        </button>
      </div>
    </div>
  )
}

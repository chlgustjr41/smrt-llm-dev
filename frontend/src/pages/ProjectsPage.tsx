import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listProjects, registerProject, deleteProject, type Project } from '../api/projects'
import { FileBrowser } from '../components/FileBrowser'

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [showBrowser, setShowBrowser] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [deleting, setDeleting] = useState<number | null>(null)

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleDelete(id: number) {
    if (!confirm('Delete this project and all its runs?')) return
    setDeleting(id)
    try {
      await deleteProject(id)
      setProjects((prev) => prev.filter((p) => p.id !== id))
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Delete failed')
    } finally {
      setDeleting(null)
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    if (!path) return
    setSubmitting(true)
    setError(null)
    try {
      const project = await registerProject(name, path)
      setProjects((prev) => [...prev, project])
      setName('')
      setPath('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Registration failed')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-2xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">SMRT Agent — Projects</h1>

      <form onSubmit={handleRegister} className="mb-8 space-y-3">
        <input
          className="block w-full border rounded px-3 py-2"
          placeholder="Project name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />

        {/* Path picker */}
        <div className="flex gap-2">
          <input
            className="block flex-1 border rounded px-3 py-2 bg-gray-50 text-sm font-mono"
            placeholder="Click Browse… to select a folder"
            value={path}
            readOnly
          />
          <button
            type="button"
            onClick={() => setShowBrowser(true)}
            className="shrink-0 border rounded px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
          >
            Browse…
          </button>
        </div>

        <button
          type="submit"
          disabled={submitting || !path || !name}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {submitting ? 'Registering…' : 'Register project'}
        </button>
      </form>

      {error && <p className="text-red-600 mb-4">{error}</p>}

      {loading ? (
        <p>Loading projects…</p>
      ) : projects.length === 0 ? (
        <p className="text-gray-500">No projects registered yet.</p>
      ) : (
        <ul className="space-y-2">
          {projects.map((p) => (
            <li key={p.id} className="border rounded p-3 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <Link
                  to={`/projects/${p.id}`}
                  className="font-medium text-blue-600 hover:underline"
                >
                  {p.name}
                </Link>
                <p className="text-gray-400 text-xs truncate">{p.canonical_path}</p>
              </div>
              <button
                type="button"
                onClick={() => handleDelete(p.id)}
                disabled={deleting === p.id}
                className="shrink-0 text-sm text-red-500 hover:text-red-700 disabled:opacity-40"
              >
                {deleting === p.id ? '…' : 'Delete'}
              </button>
            </li>
          ))}
        </ul>
      )}

      {/* Modal file browser — rendered outside the form so it can't trigger form submission */}
      {showBrowser && (
        <FileBrowser
          onSelect={(selected) => {
            setPath(selected)
            setShowBrowser(false)
          }}
          onClose={() => setShowBrowser(false)}
        />
      )}
    </div>
  )
}

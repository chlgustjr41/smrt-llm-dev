import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listProjects, registerProject, type Project } from '../api/projects'

export function ProjectsPage() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [name, setName] = useState('')
  const [path, setPath] = useState('')
  const [submitting, setSubmitting] = useState(false)

  useEffect(() => {
    listProjects()
      .then(setProjects)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
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
        <input
          className="block w-full border rounded px-3 py-2"
          placeholder="Absolute path to project"
          value={path}
          onChange={(e) => setPath(e.target.value)}
          required
        />
        <button
          type="submit"
          disabled={submitting}
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
            <li key={p.id} className="border rounded p-3 flex items-center justify-between">
              <Link
                to={`/projects/${p.id}`}
                className="font-medium text-blue-600 hover:underline"
              >
                {p.name}
              </Link>
              <span className="text-gray-500 text-sm">{p.canonical_path}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

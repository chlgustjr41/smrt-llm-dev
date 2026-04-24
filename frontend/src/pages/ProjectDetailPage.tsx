import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProject, type Project } from '../api/projects'
import { createRun } from '../api/runs'
import { LiveAgentView } from '../components/LiveAgentView'

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)

  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)

  useEffect(() => {
    getProject(projectId)
      .then(setProject)
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [projectId])

  async function handleRunAudit() {
    setStarting(true)
    setError(null)
    try {
      const run = await createRun(projectId)
      setRunId(run.run_id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start run')
    } finally {
      setStarting(false)
    }
  }

  if (loading) return <p className="p-6">Loading project…</p>
  if (error && !project) return <p className="p-6 text-red-600">{error}</p>
  if (!project) return null

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link to="/" className="text-blue-600 hover:underline text-sm mb-4 block">
        ← All projects
      </Link>

      <h1 className="text-2xl font-bold mb-1">{project.name}</h1>
      <p className="text-gray-500 text-sm mb-6">{project.canonical_path}</p>

      {!runId && (
        <button
          onClick={handleRunAudit}
          disabled={starting}
          className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
        >
          {starting ? 'Starting…' : 'Run Init Audit'}
        </button>
      )}

      {error && <p className="text-red-600 mt-3">{error}</p>}

      {runId && (
        <div className="mt-6">
          <p className="text-xs text-gray-400 mb-2">Run: {runId}</p>
          <LiveAgentView projectId={projectId} runId={runId} />
        </div>
      )}
    </div>
  )
}

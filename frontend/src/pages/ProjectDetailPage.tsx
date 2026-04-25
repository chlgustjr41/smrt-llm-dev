import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProject, listRuns, type Project, type AgentRunSummary } from '../api/projects'
import { createRun } from '../api/runs'
import { LiveAgentView } from '../components/LiveAgentView'
import { createQASession } from '../api/qa_sessions'
import { QASessionView } from '../components/QASessionView'
import { TicketsPanel } from '../components/TicketsPanel'
import { PastRunViewer } from '../components/PastRunViewer'

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === 'done'
      ? 'bg-green-100 text-green-700'
      : status === 'running' || status === 'qa_running' || status === 'coder_running'
      ? 'bg-blue-100 text-blue-700'
      : status === 'error'
      ? 'bg-red-100 text-red-700'
      : status === 'skipped'
      ? 'bg-gray-100 text-gray-500'
      : status === 'hitl_waiting'
      ? 'bg-yellow-100 text-yellow-700'
      : 'bg-gray-100 text-gray-600'
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${cls}`}>
      {(status === 'running' || status === 'qa_running' || status === 'coder_running') && (
        <span className="animate-pulse">●</span>
      )}
      {status}
    </span>
  )
}

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)

  const [project, setProject] = useState<Project | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [starting, setStarting] = useState(false)
  const [pastRuns, setPastRuns] = useState<AgentRunSummary[]>([])
  const [qaSessionId, setQaSessionId] = useState<string | null>(null)
  const [qaStatus, setQaStatus] = useState<string | null>(null)
  const [startingQA, setStartingQA] = useState(false)
  const [ticketsRefreshKey, setTicketsRefreshKey] = useState(0)

  useEffect(() => {
    Promise.all([getProject(projectId), listRuns(projectId)])
      .then(([proj, runs]) => {
        setProject(proj)
        setPastRuns(runs)
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load'))
      .finally(() => setLoading(false))
  }, [projectId])

  async function handleRunAudit() {
    setStarting(true)
    setError(null)
    try {
      const run = await createRun(projectId)
      setRunId(run.run_id)
      setPastRuns((prev) => [
        {
          id: 0,
          run_id: run.run_id,
          project_id: projectId,
          status: 'running',
          total_input_tokens: 0,
          total_output_tokens: 0,
          started_at: new Date().toISOString(),
          completed_at: null,
        },
        ...prev,
      ])
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start run')
    } finally {
      setStarting(false)
    }
  }

  function handleRunComplete(status: string) {
    if (!runId) return
    setPastRuns((prev) => prev.map((r) => (r.run_id === runId ? { ...r, status } : r)))
  }

  function handleQAComplete(status: string) {
    setQaStatus(status)
    setTicketsRefreshKey((k) => k + 1)
  }

  async function handleRunQA() {
    setStartingQA(true)
    setQaStatus(null)
    setError(null)
    try {
      const session = await createQASession(projectId)
      setQaSessionId(session.session_id)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to start QA session')
    } finally {
      setStartingQA(false)
    }
  }

  if (loading) return <p className="p-6">Loading project…</p>
  if (error && !project) return <p className="p-6 text-red-600">{error}</p>
  if (!project) return null

  const activeRunStatus = runId ? pastRuns.find((r) => r.run_id === runId)?.status : null

  return (
    <div className="max-w-3xl mx-auto p-6">
      <Link to="/" className="text-blue-600 hover:underline text-sm mb-4 block">
        ← All projects
      </Link>

      <h1 className="text-2xl font-bold mb-1">{project.name}</h1>
      <p className="text-gray-500 text-sm mb-6">{project.canonical_path}</p>

      {/* ── Init Audit ── */}
      <div className="flex items-center gap-3 mb-2">
        {!runId ? (
          <button
            onClick={handleRunAudit}
            disabled={starting}
            className="bg-blue-600 text-white px-4 py-2 rounded disabled:opacity-50"
          >
            {starting ? 'Starting…' : 'Run Init Audit'}
          </button>
        ) : (
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-400 font-mono truncate max-w-[16rem]">{runId}</span>
            {activeRunStatus && <StatusBadge status={activeRunStatus} />}
          </div>
        )}
      </div>

      {error && <p className="text-red-600 mt-3">{error}</p>}

      {runId && (
        <div className="mt-4">
          <LiveAgentView projectId={projectId} runId={runId} onComplete={handleRunComplete} />
        </div>
      )}

      {/* ── Run history ── */}
      {pastRuns.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2">
            Run history
          </h2>
          <table className="w-full text-sm border rounded overflow-hidden">
            <thead className="bg-gray-50 text-gray-500 text-xs uppercase">
              <tr>
                <th className="text-left px-3 py-2">Run ID</th>
                <th className="text-left px-3 py-2">Status</th>
                <th className="text-right px-3 py-2">In tokens</th>
                <th className="text-right px-3 py-2">Out tokens</th>
                <th className="text-left px-3 py-2">Started</th>
              </tr>
            </thead>
            <tbody>
              {pastRuns.map((run) => (
                <React.Fragment key={run.run_id}>
                  <tr className="border-t hover:bg-gray-50">
                    <td className="px-3 py-2 font-mono text-xs text-gray-600 truncate max-w-[12rem]">
                      {run.run_id}
                    </td>
                    <td className="px-3 py-2">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600">
                      {run.total_input_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-right text-gray-600">
                      {run.total_output_tokens.toLocaleString()}
                    </td>
                    <td className="px-3 py-2 text-gray-400 text-xs">
                      {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                    </td>
                  </tr>
                  <tr className="border-t bg-gray-50">
                    <td colSpan={5} className="px-3">
                      <PastRunViewer projectId={projectId} runId={run.run_id} />
                    </td>
                  </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── QA / Test Session ── */}
      <div className="mt-8 border-t pt-6">
        <div className="flex items-center gap-3 mb-3">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide">
            QA / Test Session
          </h2>
          {qaSessionId && !qaStatus && <StatusBadge status="running" />}
          {qaStatus && <StatusBadge status={qaStatus} />}
        </div>

        {!qaSessionId || qaStatus ? (
          <button
            onClick={handleRunQA}
            disabled={startingQA}
            className="bg-purple-600 text-white px-4 py-2 rounded disabled:opacity-50"
          >
            {startingQA ? 'Starting…' : qaStatus ? 'Run New QA Session' : 'Run QA Session'}
          </button>
        ) : null}

        {qaSessionId && (
          <div className={qaStatus ? 'mt-4 opacity-60 pointer-events-none' : 'mt-4'}>
            <QASessionView
              projectId={projectId}
              sessionId={qaSessionId}
              onComplete={handleQAComplete}
            />
          </div>
        )}
      </div>

      {/* ── Bug Tickets ── */}
      <div className="mt-8 border-t pt-6">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-3">
          Bug Tickets
        </h2>
        <TicketsPanel projectId={projectId} refreshKey={ticketsRefreshKey} />
      </div>
    </div>
  )
}

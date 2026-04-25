import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProject, listRuns, type Project, type AgentRunSummary } from '../api/projects'
import { createRun } from '../api/runs'
import { LiveAgentView } from '../components/LiveAgentView'
import { createQASession } from '../api/qa_sessions'
import { QASessionView } from '../components/QASessionView'
import { TicketsPanel } from '../components/TicketsPanel'
import { PastRunViewer } from '../components/PastRunViewer'
import { DocPanel } from '../components/DocPanel'
import { CostChart } from '../components/CostChart'
import { HeatmapChart } from '../components/HeatmapChart'
import { DocScoreChart } from '../components/DocScoreChart'
import { ProvenancePanel } from '../components/ProvenancePanel'

// ── Shared UI primitives ──────────────────────────────────────────────────

function Card({ children, className = '' }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`rounded-xl border border-gray-200 bg-white shadow-sm ${className}`}>
      {children}
    </div>
  )
}

function CardHeader({ title, action }: { title: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">{title}</h2>
      {action}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    done: 'bg-emerald-100 text-emerald-700',
    running: 'bg-blue-100 text-blue-700',
    qa_running: 'bg-violet-100 text-violet-700',
    coder_running: 'bg-amber-100 text-amber-700',
    error: 'bg-red-100 text-red-600',
    skipped: 'bg-gray-100 text-gray-500',
    hitl_waiting: 'bg-yellow-100 text-yellow-700',
  }
  const cls = map[status] ?? 'bg-gray-100 text-gray-500'
  const isRunning = ['running', 'qa_running', 'coder_running'].includes(status)

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${cls}`}>
      {isRunning && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
      {status}
    </span>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

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

  if (loading) return (
    <div className="max-w-4xl mx-auto p-8 flex items-center gap-3 text-gray-400">
      <span className="animate-spin text-lg">⟳</span>
      <span>Loading project…</span>
    </div>
  )
  if (error && !project) return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
    </div>
  )
  if (!project) return null

  const activeRunStatus = runId ? pastRuns.find((r) => r.run_id === runId)?.status : null

  return (
    <div className="max-w-4xl mx-auto px-6 py-8 space-y-6">
      {/* Breadcrumb */}
      <Link to="/" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 transition-colors">
        ← All projects
      </Link>

      {/* Project header */}
      <div className="space-y-1">
        <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
        <p className="font-mono text-sm text-gray-400">{project.canonical_path}</p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
      )}

      {/* ── Init Audit ── */}
      <Card>
        <CardHeader
          title="Init Audit"
          action={
            !runId ? (
              <button
                onClick={handleRunAudit}
                disabled={starting}
                className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
              >
                {starting ? (
                  <><span className="animate-spin">⟳</span> Starting…</>
                ) : (
                  <><span>🔍</span> Run Init Audit</>
                )}
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="font-mono text-xs text-gray-400 truncate max-w-[14rem]">{runId}</span>
                {activeRunStatus && <StatusBadge status={activeRunStatus} />}
              </div>
            )
          }
        />
        {runId ? (
          <div className="p-5">
            <LiveAgentView projectId={projectId} runId={runId} onComplete={handleRunComplete} />
          </div>
        ) : (
          <div className="px-5 py-4 text-sm text-gray-400">
            Run the init audit to analyze your codebase, generate documentation, and discover issues.
          </div>
        )}
      </Card>

      {/* ── Run history ── */}
      {pastRuns.length > 0 && (
        <Card>
          <CardHeader title="Run History" />
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 text-xs text-gray-400 uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-2.5">Run ID</th>
                  <th className="text-left px-4 py-2.5">Status</th>
                  <th className="text-right px-4 py-2.5">In tokens</th>
                  <th className="text-right px-4 py-2.5">Out tokens</th>
                  <th className="text-left px-4 py-2.5">Started</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {pastRuns.map((run) => (
                  <React.Fragment key={run.run_id}>
                    <tr className="hover:bg-gray-50 transition-colors">
                      <td className="px-4 py-2.5 font-mono text-xs text-gray-500 truncate max-w-[12rem]">
                        {run.run_id}
                      </td>
                      <td className="px-4 py-2.5">
                        <StatusBadge status={run.status} />
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-500 tabular-nums">
                        {run.total_input_tokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5 text-right text-gray-500 tabular-nums">
                        {run.total_output_tokens.toLocaleString()}
                      </td>
                      <td className="px-4 py-2.5 text-gray-400 text-xs">
                        {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                    <tr className="bg-gray-50">
                      <td colSpan={5} className="px-4 py-2">
                        <PastRunViewer projectId={projectId} runId={run.run_id} />
                      </td>
                    </tr>
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* ── QA / Test Session ── */}
      <Card>
        <CardHeader
          title="QA / Test Session"
          action={
            <div className="flex items-center gap-3">
              {qaSessionId && !qaStatus && <StatusBadge status="qa_running" />}
              {qaStatus && <StatusBadge status={qaStatus} />}
              {(!qaSessionId || qaStatus) && (
                <button
                  onClick={handleRunQA}
                  disabled={startingQA}
                  className="inline-flex items-center gap-2 bg-violet-600 hover:bg-violet-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
                >
                  {startingQA ? (
                    <><span className="animate-spin">⟳</span> Starting…</>
                  ) : (
                    <><span>🧪</span> {qaStatus ? 'Run New QA Session' : 'Run QA Session'}</>
                  )}
                </button>
              )}
            </div>
          }
        />
        {qaSessionId ? (
          <div className={`p-5 ${qaStatus ? 'opacity-60 pointer-events-none' : ''}`}>
            <QASessionView
              projectId={projectId}
              sessionId={qaSessionId}
              onComplete={handleQAComplete}
            />
          </div>
        ) : (
          <div className="px-5 py-4 text-sm text-gray-400">
            Run a QA session to have agents automatically test, file bug tickets, and generate fixes.
          </div>
        )}
      </Card>

      {/* ── Bug Tickets ── */}
      <Card>
        <CardHeader title="Bug Tickets" />
        <div className="p-5">
          <TicketsPanel projectId={projectId} refreshKey={ticketsRefreshKey} />
        </div>
      </Card>

      {/* ── Dashboards ── */}
      <div className="space-y-4">
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide px-1">Dashboards</h2>

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card>
            <CardHeader title="Audit Cost Breakdown" />
            <div className="p-5">
              <CostChart projectId={projectId} />
            </div>
          </Card>

          <Card>
            <CardHeader title="Documentation Completeness" />
            <div className="p-5">
              <DocScoreChart projectId={projectId} />
            </div>
          </Card>
        </div>

        <Card>
          <CardHeader title="Bug-Hunt Heatmap" />
          <div className="p-5">
            <HeatmapChart projectId={projectId} />
          </div>
        </Card>

        <Card>
          <CardHeader title="Change Provenance" />
          <div className="p-5">
            <ProvenancePanel projectId={projectId} />
          </div>
        </Card>
      </div>

      {/* ── Documentation ── */}
      <Card>
        <CardHeader title="Documentation" />
        <div className="p-5">
          <DocPanel projectId={projectId} />
        </div>
      </Card>
    </div>
  )
}

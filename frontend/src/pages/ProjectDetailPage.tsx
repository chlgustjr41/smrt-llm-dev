import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProject, listRuns, type Project, type AgentRunSummary } from '../api/projects'
import { getConfig, patchConfig, type ProjectConfig } from '../api/config'
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
import { getTestStatus, type TestStatusEntry } from '../api/stats'

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

// ── Tests tab ─────────────────────────────────────────────────────────────

type TestFilter = 'all' | 'passing' | 'failing'

function testStatusBadgeClass(status: TestStatusEntry['status']): string {
  const map: Record<string, string> = {
    green_stable: 'bg-emerald-100 text-emerald-700',
    green: 'bg-green-100 text-green-700',
    red: 'bg-red-100 text-red-600',
    flaky: 'bg-yellow-100 text-yellow-700',
  }
  return map[status] ?? 'bg-gray-100 text-gray-500'
}

function RunDot({ result }: { result: string }) {
  if (result === 'pass') {
    return <span className="inline-block w-2.5 h-2.5 rounded-sm bg-emerald-500" title="pass" />
  }
  if (result === 'fail') {
    return <span className="inline-block w-2.5 h-2.5 rounded-sm bg-red-500" title="fail" />
  }
  return <span className="inline-block w-2.5 h-2.5 rounded-sm bg-yellow-400" title={result} />
}

function formatRelativeTime(isoDate: string | null): string {
  if (!isoDate) return '—'
  const d = new Date(isoDate)
  if (isNaN(d.getTime())) return isoDate
  const diffMs = Date.now() - d.getTime()
  const diffMin = Math.floor(diffMs / 60_000)
  if (diffMin < 1) return 'just now'
  if (diffMin < 60) return `${diffMin}m ago`
  const diffHr = Math.floor(diffMin / 60)
  if (diffHr < 24) return `${diffHr}h ago`
  const diffDays = Math.floor(diffHr / 24)
  if (diffDays < 30) return `${diffDays}d ago`
  return d.toLocaleDateString()
}

function TestsTab({ projectId }: { projectId: number }) {
  const [tests, setTests] = useState<TestStatusEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<TestFilter>('all')

  useEffect(() => {
    const ac = new AbortController()
    setLoading(true)
    setError(null)
    getTestStatus(projectId, ac.signal)
      .then((data) => {
        setTests(data)
        setLoading(false)
      })
      .catch((e) => {
        if ((e as Error).name !== 'AbortError') {
          setError(e instanceof Error ? e.message : 'Failed to load test status')
          setLoading(false)
        }
      })
    return () => ac.abort()
  }, [projectId])

  const filtered = tests.filter((t) => {
    if (filter === 'passing') return t.status === 'green' || t.status === 'green_stable'
    if (filter === 'failing') return t.status === 'red' || t.status === 'flaky'
    return true
  })

  const filterBtnCls = (f: TestFilter) =>
    `px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
      filter === f
        ? 'bg-blue-600 text-white'
        : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
    }`

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-gray-400 py-8">
        <span className="animate-spin text-lg">⟳</span>
        <span>Loading test status…</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
        {error}
      </div>
    )
  }

  return (
    <Card>
      <CardHeader
        title="Test History"
        action={
          <div className="flex gap-1">
            <button className={filterBtnCls('all')} onClick={() => setFilter('all')}>All</button>
            <button className={filterBtnCls('passing')} onClick={() => setFilter('passing')}>Passing</button>
            <button className={filterBtnCls('failing')} onClick={() => setFilter('failing')}>Failing / Flaky</button>
          </div>
        }
      />
      {filtered.length === 0 ? (
        <div className="px-5 py-8 text-sm text-gray-400 text-center">
          {tests.length === 0
            ? 'No test history yet. Run a QA session to generate tests.'
            : 'No tests match the current filter.'}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 text-xs text-gray-400 uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-2.5">Test</th>
                <th className="text-left px-4 py-2.5">Status</th>
                <th className="text-left px-4 py-2.5">Last Runs</th>
                <th className="text-left px-4 py-2.5">Cadence</th>
                <th className="text-left px-4 py-2.5">Last Run</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {filtered.map((t) => (
                <tr key={t.name} className="hover:bg-gray-50 transition-colors">
                  <td className="px-4 py-2.5 max-w-xs">
                    <span
                      className="font-mono text-xs text-gray-700 truncate block"
                      title={t.name}
                    >
                      {t.name}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium ${testStatusBadgeClass(t.status)}`}>
                      {t.status}
                    </span>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex gap-0.5 items-center">
                      {(t.last_runs ?? []).slice(-5).map((r, i) => (
                        <RunDot key={i} result={r} />
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-xs text-gray-500">
                    {t.promoted_to ?? '—'}
                  </td>
                  <td className="px-4 py-2.5 text-xs text-gray-400">
                    {formatRelativeTime(t.last_run_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

// ── Config tab ────────────────────────────────────────────────────────────

const MODEL_OPTIONS = [
  { value: 'claude-opus-4-7', label: 'claude-opus-4-7' },
  { value: 'claude-sonnet-4-6', label: 'claude-sonnet-4-6' },
  { value: 'claude-haiku-4-5-20251001', label: 'claude-haiku-4-5-20251001' },
]

const CADENCE_OPTIONS = [
  { value: 'daily_0300', label: 'Daily at 3am' },
  { value: 'hourly', label: 'Hourly' },
  { value: 'manual', label: 'Manual only' },
]

const CONFIG_DEFAULTS: ProjectConfig = {
  reviewer_model: 'claude-opus-4-7',
  qa_model: 'claude-sonnet-4-6',
  coder_model: 'claude-sonnet-4-6',
  max_fix_attempts: 5,
  max_questions_per_attempt: 1,
  scheduler_cadence: 'daily_0300',
  thought_process_mode: false,
}

function ConfigTab({ projectId }: { projectId: number }) {
  const [config, setConfig] = useState<ProjectConfig>(CONFIG_DEFAULTS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    getConfig(projectId)
      .then(setConfig)
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Failed to load config'))
  }, [projectId])

  function handleChange(field: keyof ProjectConfig, value: string | number | boolean) {
    setConfig((prev) => ({ ...prev, [field]: value }))
  }

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const updated = await patchConfig(projectId, config)
      setConfig(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'Failed to save config')
    } finally {
      setSaving(false)
    }
  }

  if (loadError) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
        {loadError}
      </div>
    )
  }

  const labelCls = 'block text-sm font-medium text-gray-700 mb-1'
  const inputCls = 'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
  const selectCls = inputCls

  return (
    <Card>
      <CardHeader title="Project Configuration" />
      <div className="p-5 space-y-5">
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {/* Reviewer Model */}
          <div>
            <label className={labelCls}>Reviewer Model</label>
            <select
              className={selectCls}
              value={config.reviewer_model}
              onChange={(e) => handleChange('reviewer_model', e.target.value)}
            >
              {MODEL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* QA Model */}
          <div>
            <label className={labelCls}>QA Model</label>
            <select
              className={selectCls}
              value={config.qa_model}
              onChange={(e) => handleChange('qa_model', e.target.value)}
            >
              {MODEL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Coder Model */}
          <div>
            <label className={labelCls}>Coder Model</label>
            <select
              className={selectCls}
              value={config.coder_model}
              onChange={(e) => handleChange('coder_model', e.target.value)}
            >
              {MODEL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Scheduler Cadence */}
          <div>
            <label className={labelCls}>Scheduler Cadence</label>
            <select
              className={selectCls}
              value={config.scheduler_cadence}
              onChange={(e) => handleChange('scheduler_cadence', e.target.value)}
            >
              {CADENCE_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Max Fix Attempts */}
          <div>
            <label className={labelCls}>Max Fix Attempts</label>
            <input
              type="number"
              min={1}
              max={10}
              className={inputCls}
              value={config.max_fix_attempts}
              onChange={(e) => handleChange('max_fix_attempts', Number(e.target.value))}
            />
          </div>

          {/* Max Questions per Attempt */}
          <div>
            <label className={labelCls}>Max Questions per Attempt</label>
            <input
              type="number"
              min={0}
              max={5}
              className={inputCls}
              value={config.max_questions_per_attempt}
              onChange={(e) => handleChange('max_questions_per_attempt', Number(e.target.value))}
            />
          </div>
        </div>

        {/* Thought-Process Mode */}
        <div className="flex items-center gap-3">
          <input
            id="thought-process-mode"
            type="checkbox"
            className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
            checked={config.thought_process_mode}
            onChange={(e) => handleChange('thought_process_mode', e.target.checked)}
          />
          <label htmlFor="thought-process-mode" className="text-sm font-medium text-gray-700">
            Thought-Process Mode
          </label>
        </div>

        {saveError && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">
            {saveError}
          </div>
        )}

        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
          >
            {saving ? 'Saving…' : 'Save'}
          </button>
          {saved && (
            <span className="text-sm text-emerald-600 font-medium">Saved!</span>
          )}
        </div>
      </div>
    </Card>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)

  const [activeTab, setActiveTab] = useState<'overview' | 'config' | 'tests'>('overview')
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

      {/* Tab bar */}
      <div className="flex gap-1 border-b border-gray-200">
        {(['overview', 'tests', 'config'] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-2 text-sm font-medium capitalize transition-colors border-b-2 -mb-px ${
              activeTab === tab
                ? 'border-blue-600 text-blue-600'
                : 'border-transparent text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab}
          </button>
        ))}
      </div>

      {activeTab === 'config' && <ConfigTab projectId={projectId} />}
      {activeTab === 'tests' && <TestsTab projectId={projectId} />}

      {activeTab === 'overview' && <>

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

      </>}
    </div>
  )
}

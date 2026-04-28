import React, { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { getProject, listRuns, type Project, type AgentRunSummary } from '../api/projects'
import { getConfig, patchConfig, type ProjectConfig } from '../api/config'
import { createRun } from '../api/runs'
import { getLlmProvider, type LlmProvider } from '../api/llm'
import { LiveAgentView } from '../components/LiveAgentView'
import { createQASession, getLatestQASession } from '../api/qa_sessions'
import { QASessionView } from '../components/QASessionView'
import { TicketsPanel } from '../components/TicketsPanel'
import { PastRunViewer } from '../components/PastRunViewer'
import { DocPanel } from '../components/DocPanel'
import { listTickets, type Ticket } from '../api/tickets'
import { getTestStatus, type TestStatusEntry, type TestFunction } from '../api/stats'

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
    pending: 'bg-gray-100 text-gray-500',
    done: 'bg-emerald-100 text-emerald-700',
    running: 'bg-blue-100 text-blue-700',
    qa_running: 'bg-violet-100 text-violet-700',
    coder_running: 'bg-amber-100 text-amber-700',
    error: 'bg-red-100 text-red-600',
    budget_exceeded: 'bg-red-100 text-red-600',
    skipped: 'bg-gray-100 text-gray-500',
    hitl_waiting: 'bg-yellow-100 text-yellow-700',
    loop_exhausted: 'bg-orange-100 text-orange-700',
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

function CoverageBar({ pct }: { pct: number }) {
  const color = pct >= 80 ? 'bg-emerald-500' : pct >= 50 ? 'bg-amber-400' : 'bg-red-400'
  return (
    <div className="flex items-center gap-2 min-w-0">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="font-mono text-[11px] text-gray-600 shrink-0">{pct.toFixed(1)}%</span>
    </div>
  )
}

function getRelatedTestFiles(
  sourceFile: string,
  tests: TestStatusEntry[],
  fileTests?: Record<string, string[]>,
): TestStatusEntry[] {
  const basename = sourceFile.split('/').pop()?.split('\\').pop() ?? sourceFile

  // Use coverage context when available — deduplicate to unique test files
  if (fileTests?.[basename]?.length) {
    const seen = new Set<string>()
    const result: TestStatusEntry[] = []
    for (const nodeId of fileTests[basename]) {
      const filePart = nodeId.split('::')[0]
      const fileName = filePart.split('/').pop()?.split('\\').pop() ?? filePart
      if (seen.has(fileName)) continue
      seen.add(fileName)
      const entry = tests.find((t) => t.name === fileName)
      if (entry) result.push(entry)
    }
    if (result.length) return result
  }

  // Fallback: name-stem heuristic
  const stem = basename.replace(/\.(py|ts|js|tsx|jsx)$/, '')
  if (!stem || stem.length < 3) return []
  const lower = stem.toLowerCase()
  return tests.filter((t) => t.name.toLowerCase().includes(lower))
}

function FileCoverageRow({
  file,
  pct,
  tests,
  fileTests,
}: {
  file: string
  pct: number
  tests: TestStatusEntry[]
  fileTests?: Record<string, string[]>
}) {
  const [hovered, setHovered] = useState(false)
  const basename = file.split('/').pop()?.split('\\').pop() ?? file
  const coveringTests = getRelatedTestFiles(file, tests, fileTests)
  const fromContext = !!(fileTests?.[basename]?.length)

  return (
    <div
      className="relative grid grid-cols-[1fr_auto] gap-3 items-center group"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <span className="font-mono text-xs text-gray-600 truncate cursor-default" title={file}>{file}</span>
      <div className="w-40">
        <CoverageBar pct={pct} />
      </div>

      {/* Hover tooltip — test files that cover this source file */}
      {hovered && coveringTests.length > 0 && (
        <div className="absolute left-0 top-full mt-1 z-20 bg-white border border-gray-200 rounded-lg shadow-lg p-2.5 min-w-56 max-w-xs animate-fade-in">
          <p className="text-[10px] uppercase tracking-wider text-gray-400 font-medium mb-1.5">
            {fromContext
              ? `${coveringTests.length} test file${coveringTests.length !== 1 ? 's' : ''} covering this`
              : `Related test files (${coveringTests.length})`}
          </p>
          <div className="space-y-1 max-h-48 overflow-y-auto">
            {coveringTests.map((t, i) => (
              <div key={i} className="flex items-center gap-1.5">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                  t.status === 'red' ? 'bg-red-500' :
                  t.status === 'flaky' ? 'bg-yellow-400' :
                  'bg-emerald-500'
                }`} />
                <span className="font-mono text-[11px] text-gray-700 flex-1 truncate">{t.name}</span>
                <span className={`text-[10px] px-1 rounded shrink-0 ${
                  t.status === 'red' ? 'text-red-600 bg-red-50' :
                  t.status === 'flaky' ? 'text-yellow-700 bg-yellow-50' :
                  'text-emerald-700 bg-emerald-50'
                }`}>
                  {t.status.replace('_', ' ')}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
      {hovered && coveringTests.length === 0 && (
        <div className="absolute left-0 top-full mt-1 z-20 bg-white border border-gray-200 rounded-lg shadow-lg px-3 py-2 text-[11px] text-gray-400 animate-fade-in whitespace-nowrap">
          No covering test files found
        </div>
      )}
    </div>
  )
}

function TestFunctionList({ fns }: { fns: TestFunction[] }) {
  if (!fns.length) return null
  return (
    <ul className="mt-2 space-y-1 pl-1">
      {fns.map((f) => (
        <li key={f.fn} className="text-xs text-gray-600">
          <span className="inline-block w-1 h-1 rounded-full bg-gray-300 mr-2 mb-0.5 align-middle" />
          <span className="font-medium">{f.description}</span>
          {f.docstring && (
            <span className="text-gray-400 ml-1.5 italic truncate" title={f.docstring}>
              — {f.docstring.split('\n')[0].slice(0, 80)}
            </span>
          )}
        </li>
      ))}
    </ul>
  )
}

function TestsTab({ projectId }: { projectId: number }) {
  const [response, setResponse] = useState<{ tests: TestStatusEntry[]; overall_coverage: number | null; file_coverage: Record<string, number>; file_tests?: Record<string, string[]> } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState<TestFilter>('all')
  const [expandedTests, setExpandedTests] = useState<Set<string>>(new Set())

  useEffect(() => {
    const ac = new AbortController()
    setLoading(true)
    setError(null)
    getTestStatus(projectId, ac.signal)
      .then((data) => {
        setResponse(data)
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

  const tests = response?.tests ?? []
  const overallCoverage = response?.overall_coverage ?? null
  const fileCoverage = response?.file_coverage ?? {}
  const fileTests = response?.file_tests

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

  function toggleExpand(name: string) {
    setExpandedTests((prev) => {
      const next = new Set(prev)
      next.has(name) ? next.delete(name) : next.add(name)
      return next
    })
  }

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

  // Filter to project files only — exclude test files and pytest helpers
  const fileCoverageEntries = Object.entries(fileCoverage)
    .filter(([file]) => {
      const name = file.split('/').pop()?.split('\\').pop() ?? file
      if (name.startsWith('test_') || name.endsWith('_test.py')) return false
      if (name === 'conftest.py') return false
      return true
    })
    .sort((a, b) => a[1] - b[1])

  return (
    <div className="space-y-4">
      {/* Coverage summary banner */}
      {overallCoverage !== null && (
        <Card>
          <div className="px-5 py-4">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">Code Coverage</h3>
              <span className={`font-mono text-lg font-bold ${
                overallCoverage >= 80 ? 'text-emerald-600' : overallCoverage >= 50 ? 'text-amber-600' : 'text-red-600'
              }`}>{overallCoverage.toFixed(1)}%</span>
            </div>
            <CoverageBar pct={overallCoverage} />
            {fileCoverageEntries.length > 0 && (
              <div className="mt-4 space-y-1.5">
                <p className="text-[11px] text-gray-400 uppercase tracking-wide mb-2">
                  Per-file coverage <span className="normal-case font-normal">
                    (hover to see which test files cover it)
                  </span>
                </p>
                {fileCoverageEntries.map(([file, pct]) => (
                  <FileCoverageRow key={file} file={file} pct={pct} tests={tests} fileTests={fileTests} />
                ))}
              </div>
            )}
          </div>
        </Card>
      )}

      {/* Test file cards */}
      <Card>
        <CardHeader
          title="Test Files"
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
          <div className="divide-y divide-gray-100">
            {filtered.map((t) => {
              const isExpanded = expandedTests.has(t.name)
              const hasFunctions = (t.functions?.length ?? 0) > 0
              return (
                <div key={t.name} className="px-5 py-3">
                  <div
                    className={`flex items-start gap-3 ${hasFunctions ? 'cursor-pointer' : ''}`}
                    onClick={() => hasFunctions && toggleExpand(t.name)}
                  >
                    {/* Expand toggle */}
                    <span className="text-[10px] text-gray-400 mt-1 w-3 shrink-0">
                      {hasFunctions ? (isExpanded ? '▾' : '▸') : '·'}
                    </span>

                    {/* File name */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-mono text-xs text-gray-700" title={t.name}>{t.name}</span>
                        <span className={`inline-flex px-1.5 py-0.5 rounded-full text-[10px] font-medium ${testStatusBadgeClass(t.status)}`}>
                          {t.status}
                        </span>
                        {hasFunctions && (
                          <span className="text-[10px] text-gray-400">
                            {t.functions!.length} test{t.functions!.length !== 1 ? 's' : ''}
                          </span>
                        )}
                      </div>
                      {isExpanded && hasFunctions && <TestFunctionList fns={t.functions!} />}
                    </div>

                    {/* Right column: runs + time */}
                    <div className="shrink-0 text-right space-y-1">
                      <div className="flex gap-0.5 items-center justify-end">
                        {(t.last_runs ?? []).slice(-5).map((r, i) => (
                          <RunDot key={i} result={r} />
                        ))}
                      </div>
                      <div className="text-[10px] text-gray-400">{formatRelativeTime(t.last_run_at)}</div>
                      {t.promoted_to && (
                        <div className="text-[10px] text-gray-400">{t.promoted_to}</div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        )}
      </Card>
    </div>
  )
}

// ── Runs tab ──────────────────────────────────────────────────────────────

function RunsTab({
  projectId,
  pastRuns,
}: {
  projectId: number
  pastRuns: AgentRunSummary[]
}) {

  if (pastRuns.length === 0) {
    return (
      <Card>
        <CardHeader title="Run History" />
        <div className="px-5 py-8 text-sm text-gray-400 text-center">
          No runs yet. Click &lsquo;Run Init Audit&rsquo; in the Overview tab.
        </div>
      </Card>
    )
  }

  return (
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
            {pastRuns.map((run) => {
              return (
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
              )
            })}
          </tbody>
        </table>
      </div>
    </Card>
  )
}

// ── Docs tab ──────────────────────────────────────────────────────────────

function DocsTab({ projectId }: { projectId: number }) {
  const [regenMsg, setRegenMsg] = useState<string | null>(null)

  async function handleRegenAll() {
    const confirmed = window.confirm(
      'This will re-run the documentation agent for all endpoints and modules. Continue?'
    )
    if (!confirmed) return
    try {
      await createRun(projectId)
      setRegenMsg('Regeneration started — switch to the Overview tab to monitor progress.')
    } catch (e: unknown) {
      setRegenMsg(e instanceof Error ? e.message : 'Failed to start regeneration')
    }
  }

  return (
    <Card>
      <CardHeader
        title="Documentation"
        action={
          <button
            onClick={handleRegenAll}
            className="inline-flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors"
          >
            Regenerate All
          </button>
        }
      />
      {regenMsg && (
        <div className="mx-5 mt-4 rounded-lg border border-blue-200 bg-blue-50 px-4 py-3 text-sm text-blue-700">
          {regenMsg}
        </div>
      )}
      <div className="p-5">
        <DocPanel projectId={projectId} />
      </div>
    </Card>
  )
}

// ── Tickets summary (dashboard widget) ───────────────────────────────────

const TICKET_STATUS_META: Record<string, { label: string; cls: string }> = {
  pending_confirmation: { label: 'Pending', cls: 'bg-yellow-100 text-yellow-700' },
  in_progress:         { label: 'In Progress', cls: 'bg-blue-100 text-blue-700' },
  qa_review:           { label: 'QA Review', cls: 'bg-violet-100 text-violet-700' },
  needs_review:        { label: 'Needs Review', cls: 'bg-orange-100 text-orange-700' },
  closed:              { label: 'Closed', cls: 'bg-emerald-100 text-emerald-700' },
}

function TicketsSummary({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) {
  const [tickets, setTickets] = useState<Ticket[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    setLoading(true)
    listTickets(projectId, ac.signal)
      .then((t) => { setTickets(t); setLoading(false) })
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== 'AbortError') {
          setError(e.message)
          setLoading(false)
        }
      })
    return () => ac.abort()
  }, [projectId, refreshKey])

  if (loading) return (
    <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
      <span className="animate-spin">⟳</span> Loading…
    </div>
  )
  if (error) return <div className="text-sm text-red-500">{error}</div>
  if (tickets.length === 0) return (
    <p className="text-sm text-gray-400 italic py-2">No tickets yet.</p>
  )

  const counts = tickets.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-400 mb-2">{tickets.length} total</div>
      {Object.entries(TICKET_STATUS_META).map(([status, meta]) => {
        const count = counts[status] ?? 0
        if (count === 0) return null
        return (
          <div key={status} className="flex items-center justify-between gap-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${meta.cls}`}>
              {meta.label}
            </span>
            <div className="flex-1 mx-2 h-1.5 rounded-full bg-gray-100 overflow-hidden">
              <div
                className="h-full rounded-full bg-current opacity-40"
                style={{ width: `${Math.round((count / tickets.length) * 100)}%` }}
              />
            </div>
            <span className="text-sm font-semibold text-gray-700 tabular-nums w-5 text-right">{count}</span>
          </div>
        )
      })}
    </div>
  )
}

// ── Tests summary (dashboard widget) ─────────────────────────────────────

const TEST_STATUS_META: Record<string, { label: string; cls: string; barCls: string }> = {
  green_stable: { label: 'Stable', cls: 'bg-emerald-100 text-emerald-700', barCls: 'bg-emerald-500' },
  green:        { label: 'Passing', cls: 'bg-green-100 text-green-700', barCls: 'bg-green-400' },
  flaky:        { label: 'Flaky', cls: 'bg-yellow-100 text-yellow-700', barCls: 'bg-yellow-400' },
  red:          { label: 'Failing', cls: 'bg-red-100 text-red-600', barCls: 'bg-red-500' },
}

function TestsSummary({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) {
  const [tests, setTests] = useState<TestStatusEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const ac = new AbortController()
    setLoading(true)
    getTestStatus(projectId, ac.signal)
      .then((r) => { setTests(r.tests); setLoading(false) })
      .catch((e: unknown) => {
        if (e instanceof Error && e.name !== 'AbortError') {
          setError(e.message)
          setLoading(false)
        }
      })
    return () => ac.abort()
  }, [projectId, refreshKey])

  if (loading) return (
    <div className="flex items-center gap-2 text-sm text-gray-400 py-4">
      <span className="animate-spin">⟳</span> Loading…
    </div>
  )
  if (error) return <div className="text-sm text-red-500">{error}</div>
  if (tests.length === 0) return (
    <p className="text-sm text-gray-400 italic py-2">No tests tracked yet.</p>
  )

  const counts = tests.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] ?? 0) + 1
    return acc
  }, {})

  return (
    <div className="space-y-2">
      <div className="text-xs text-gray-400 mb-2">{tests.length} total</div>
      {Object.entries(TEST_STATUS_META).map(([status, meta]) => {
        const count = counts[status] ?? 0
        if (count === 0) return null
        return (
          <div key={status} className="flex items-center justify-between gap-2">
            <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${meta.cls}`}>
              {meta.label}
            </span>
            <div className="flex-1 mx-2 h-1.5 rounded-full bg-gray-100 overflow-hidden">
              <div
                className={`h-full rounded-full ${meta.barCls}`}
                style={{ width: `${Math.round((count / tests.length) * 100)}%` }}
              />
            </div>
            <span className="text-sm font-semibold text-gray-700 tabular-nums w-5 text-right">{count}</span>
          </div>
        )
      })}
    </div>
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
  use_local_llm: false,
}

function ConfigTab({
  projectId,
  llmProvider,
  onConfigUpdate,
}: {
  projectId: number
  llmProvider?: LlmProvider | null
  onConfigUpdate?: (config: ProjectConfig) => void
}) {
  const [config, setConfig] = useState<ProjectConfig>(CONFIG_DEFAULTS)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)

  useEffect(() => {
    getConfig(projectId)
      .then((c) => {
        setConfig(c)
        onConfigUpdate?.(c)
      })
      .catch((e) => setLoadError(e instanceof Error ? e.message : 'Failed to load config'))
  }, [projectId])

  function handleChange(field: keyof ProjectConfig, value: string | number | boolean) {
    setConfig((prev) => ({ ...prev, [field]: value }))
  }

  async function handleUseLocalToggle(value: boolean) {
    setConfig((prev) => ({ ...prev, use_local_llm: value }))
    setSaveError(null)
    try {
      const updated = await patchConfig(projectId, { use_local_llm: value })
      setConfig(updated)
      onConfigUpdate?.(updated)
      setSaved(true)
      setTimeout(() => setSaved(false), 1500)
    } catch (e: unknown) {
      setSaveError(e instanceof Error ? e.message : 'Failed to save')
      setConfig((prev) => ({ ...prev, use_local_llm: !value }))
    }
  }

  async function handleSave() {
    setSaving(true)
    setSaveError(null)
    setSaved(false)
    try {
      const updated = await patchConfig(projectId, config)
      setConfig(updated)
      onConfigUpdate?.(updated)
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

  const useLocal = config.use_local_llm
  const labelCls = 'block text-sm font-medium text-gray-700 mb-1'
  const inputCls = 'w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500'
  const selectCls = inputCls
  const disabledSelectCls = `${selectCls} opacity-40 cursor-not-allowed bg-gray-50`

  return (
    <Card>
      <CardHeader title="Project Configuration" />
      <div className="p-5 space-y-5">

        {/* Use Local LLM toggle */}
        <div className="rounded-lg border border-gray-200 bg-gray-50 px-4 py-3 space-y-2">
          <div className="flex items-center gap-3">
            <input
              id="use-local-llm"
              type="checkbox"
              className="h-4 w-4 rounded border-gray-300 text-emerald-600 focus:ring-emerald-500"
              checked={config.use_local_llm}
              onChange={(e) => handleUseLocalToggle(e.target.checked)}
            />
            <label htmlFor="use-local-llm" className="text-sm font-medium text-gray-700">
              Use Local LLM (LM Studio / OpenAI-compatible)
            </label>
          </div>
          {useLocal && (
            <p className="text-xs text-emerald-700 pl-7">
              {llmProvider?.model
                ? <>Active model: <span className="font-mono font-semibold">{llmProvider.model}</span> — configured via <span className="font-mono">LOCAL_LLM_MODEL</span> in <span className="font-mono">.env</span>. Anthropic model selects below are ignored.</>
                : <>Local model active — configured via <span className="font-mono">LOCAL_LLM_MODEL</span> in <span className="font-mono">.env</span>. Anthropic model selects below are ignored.</>
              }
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          {/* Reviewer Model */}
          <div className={useLocal ? 'opacity-50' : ''}>
            <label className={labelCls}>Reviewer Model</label>
            <select
              className={useLocal ? disabledSelectCls : selectCls}
              disabled={useLocal}
              value={config.reviewer_model}
              onChange={(e) => handleChange('reviewer_model', e.target.value)}
            >
              {MODEL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* QA Model */}
          <div className={useLocal ? 'opacity-50' : ''}>
            <label className={labelCls}>QA Model</label>
            <select
              className={useLocal ? disabledSelectCls : selectCls}
              disabled={useLocal}
              value={config.qa_model}
              onChange={(e) => handleChange('qa_model', e.target.value)}
            >
              {MODEL_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
          </div>

          {/* Coder Model */}
          <div className={useLocal ? 'opacity-50' : ''}>
            <label className={labelCls}>Coder Model</label>
            <select
              className={useLocal ? disabledSelectCls : selectCls}
              disabled={useLocal}
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
          <label htmlFor="thought-process-mode" className="flex items-center gap-1.5 text-sm font-medium text-gray-700">
            Thought-Process Mode
            <span
              className="relative group cursor-default"
              aria-label="What is Thought-Process Mode?"
            >
              <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-gray-200 text-gray-500 text-[10px] font-bold leading-none select-none">?</span>
              <span className="pointer-events-none absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 rounded-lg bg-gray-900 px-3 py-2 text-xs text-gray-100 shadow-lg opacity-0 group-hover:opacity-100 transition-opacity z-50">
                When enabled, the agent log shows each agent's internal reasoning text in real time — the "thinking out loud" stream before it takes action. Useful for debugging unexpected decisions. Has no effect on agent behaviour.
                <span className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-gray-900" />
              </span>
            </span>
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

// ── Tickets tab ───────────────────────────────────────────────────────────

function TicketsTab({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) {
  return (
    <Card>
      <CardHeader title="Bug Tickets" />
      <div className="p-2">
        <TicketsPanel projectId={projectId} refreshKey={refreshKey} />
      </div>
    </Card>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────

export function ProjectDetailPage() {
  const { id } = useParams<{ id: string }>()
  const projectId = Number(id)

  const [activeTab, setActiveTab] = useState<'overview' | 'tickets' | 'runs' | 'docs' | 'tests' | 'config'>('overview')
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
  const [dashboardRefreshKey, setDashboardRefreshKey] = useState(0)
  const [llmProvider, setLlmProvider] = useState<LlmProvider | null>(null)
  const [projectConfig, setProjectConfig] = useState<ProjectConfig | null>(null)

  useEffect(() => {
    getLlmProvider().then(setLlmProvider).catch(() => {})
  }, [])

  useEffect(() => {
    const controller = new AbortController()
    Promise.all([
      getProject(projectId),
      listRuns(projectId, controller.signal),
      getLatestQASession(projectId, controller.signal),
      getConfig(projectId),
    ])
      .then(([proj, runs, latestQA, cfg]) => {
        if (controller.signal.aborted) return
        setProject(proj)
        setPastRuns(runs)
        setProjectConfig(cfg)
        // Hydrate reviewer timeline with the most recent run
        if (runs.length > 0) setRunId(runs[0].run_id)
        // Hydrate QA session card — works even after tab switches or page refresh
        if (latestQA.session_id) {
          setQaSessionId(latestQA.session_id)
          if (latestQA.status && ['done', 'error', 'budget_exceeded'].includes(latestQA.status)) {
            setQaStatus(latestQA.status)
          }
        }
      })
      .catch((e) => {
        if (controller.signal.aborted) return
        setError(e instanceof Error ? e.message : 'Failed to load')
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId])

  async function handleRunAudit() {
    setStarting(true)
    setError(null)
    setRunId(null) // unmount LiveAgentView before remounting with new run
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
    // Optimistic update — immediately reflect the terminal status in the UI.
    setPastRuns((prev) => prev.map((r) => (r.run_id === runId ? { ...r, status } : r)))
    setDashboardRefreshKey((k) => k + 1)
    // Delayed refetch — the backend writes the final DB status right after the
    // "done" SSE event is queued, so a small delay ensures the DB has caught up
    // before we re-read it (avoids overwriting the optimistic update with stale "running").
    setTimeout(() => listRuns(projectId).then(setPastRuns).catch(() => {}), 2500)
  }

  function handleQAComplete(status: string) {
    setQaStatus(status)
    setTicketsRefreshKey((k) => k + 1)
    setDashboardRefreshKey((k) => k + 1)
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
    <div className="py-8">
      {/* Always-constrained header: breadcrumb, title, tab bar */}
      <div className="max-w-4xl mx-auto px-6 space-y-6">
        {/* Breadcrumb */}
        <Link to="/" className="inline-flex items-center gap-1 text-sm text-gray-400 hover:text-gray-600 transition-colors">
          ← All projects
        </Link>

        {/* Project header */}
        <div className="space-y-1">
          <div className="flex items-center gap-3 flex-wrap">
            <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
            {(() => {
              // Use per-project config when available; fall back to global provider
              const isLocal = projectConfig !== null
                ? projectConfig.use_local_llm
                : llmProvider?.provider === 'local'
              if (isLocal === null || isLocal === undefined) return null
              return isLocal ? (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-emerald-50 border border-emerald-200 text-emerald-700">
                  🏠 Local LLM{llmProvider?.model ? ` · ${llmProvider.model}` : ''}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium bg-violet-50 border border-violet-200 text-violet-700">
                  ☁ Anthropic
                </span>
              )
            })()}
          </div>
          <p className="font-mono text-sm text-gray-400">{project.canonical_path}</p>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 border-b border-gray-200">
          {(
            [
              ['overview', 'Overview'],
              ['tickets', 'Tickets'],
              ['runs', 'Runs'],
              ['docs', 'Docs'],
              ['tests', 'Tests'],
              ['config', 'Config'],
            ] as const
          ).map(([tab, label]) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                activeTab === tab
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-gray-500 hover:text-gray-700'
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tickets — full-width, conditionally rendered */}
      {activeTab === 'tickets' && (
        <div className="w-full px-4 mt-6">
          <TicketsTab projectId={projectId} refreshKey={ticketsRefreshKey} />
        </div>
      )}

      {/* Constrained tabs — always mounted so Overview SSE connections survive tab switches */}
      <div className={`max-w-4xl mx-auto px-6 mt-6${activeTab === 'tickets' ? ' hidden' : ''}`}>
        {activeTab === 'config' && <ConfigTab projectId={projectId} llmProvider={llmProvider} onConfigUpdate={setProjectConfig} />}
        {activeTab === 'tests' && <TestsTab projectId={projectId} />}
        {activeTab === 'runs' && <RunsTab projectId={projectId} pastRuns={pastRuns} />}
        {activeTab === 'docs' && <DocsTab projectId={projectId} />}

        {/* Overview — always mounted; CSS hidden keeps SSE and accumulated events alive */}
        <div className={`space-y-6${activeTab !== 'overview' ? ' hidden' : ''}`}>

          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600">{error}</div>
          )}

          {/* ── Init Audit ── */}
          <Card>
            <CardHeader
              title="Init Audit"
              action={
                <div className="flex items-center gap-3">
                  {runId && (
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-gray-400 truncate max-w-[12rem]">{runId}</span>
                      {activeRunStatus && <StatusBadge status={activeRunStatus} />}
                    </div>
                  )}
                  {(!runId || !activeRunStatus || ['done', 'error', 'skipped'].includes(activeRunStatus)) && (
                    <button
                      onClick={handleRunAudit}
                      disabled={starting}
                      className="inline-flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium disabled:opacity-50 transition-colors"
                    >
                      {starting ? (
                        <><span className="animate-spin">⟳</span> Starting…</>
                      ) : runId ? (
                        <><span>🔍</span> New Audit</>
                      ) : (
                        <><span>🔍</span> Run Init Audit</>
                      )}
                    </button>
                  )}
                </div>
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
              <div className="p-5">
                <QASessionView
                  key={qaSessionId}
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

          {/* ── Dashboards ── */}
          <div className="space-y-4">
            <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wide px-1">Dashboards</h2>

            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Card>
                <CardHeader title="Ticket Status" />
                <div className="p-5">
                  <TicketsSummary projectId={projectId} refreshKey={dashboardRefreshKey} />
                </div>
              </Card>

              <Card>
                <CardHeader title="Test Status" />
                <div className="p-5">
                  <TestsSummary projectId={projectId} refreshKey={dashboardRefreshKey} />
                </div>
              </Card>
            </div>
          </div>

        </div>
      </div>
    </div>
  )
}

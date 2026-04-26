import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ProjectDetailPage } from '../pages/ProjectDetailPage'

vi.mock('../components/LiveAgentView', () => ({
  LiveAgentView: ({ runId }: { runId: string }) => (
    <div data-testid="live-agent-view">LiveAgentView:{runId}</div>
  ),
}))

vi.mock('../components/QASessionView', () => ({
  QASessionView: ({ sessionId, onComplete }: { sessionId: string; onComplete?: (status: string) => void }) => (
    <div data-testid="qa-session-view">
      QASessionView:{sessionId}
      <button onClick={() => onComplete?.('done')}>complete-qa</button>
    </div>
  ),
}))

vi.mock('../components/TicketsPanel', () => ({
  TicketsPanel: ({ projectId, refreshKey }: { projectId: number; refreshKey?: number }) => (
    <div data-testid="tickets-panel">TicketsPanel:{projectId}:{refreshKey ?? 0}</div>
  ),
}))

vi.mock('../components/PastRunViewer', () => ({
  PastRunViewer: ({ runId }: { runId: string }) => (
    <div data-testid="past-run-viewer">PastRunViewer:{runId}</div>
  ),
}))

vi.mock('../components/DocPanel', () => ({
  DocPanel: ({ projectId }: { projectId: number }) => (
    <div data-testid="doc-panel">DocPanel:{projectId}</div>
  ),
}))

vi.mock('../components/CostChart', () => ({
  CostChart: ({ projectId }: { projectId: number }) => (
    <div data-testid="cost-chart">CostChart:{projectId}</div>
  ),
}))

vi.mock('../components/HeatmapChart', () => ({
  HeatmapChart: ({ projectId }: { projectId: number }) => (
    <div data-testid="heatmap-chart">HeatmapChart:{projectId}</div>
  ),
}))

vi.mock('../components/DocScoreChart', () => ({
  DocScoreChart: ({ projectId }: { projectId: number }) => (
    <div data-testid="doc-score-chart">DocScoreChart:{projectId}</div>
  ),
}))

vi.mock('../components/ProvenancePanel', () => ({
  ProvenancePanel: ({ projectId }: { projectId: number }) => (
    <div data-testid="provenance-panel">ProvenancePanel:{projectId}</div>
  ),
}))

const server = setupServer(
  http.get('http://localhost/api/projects/1', () =>
    HttpResponse.json({
      id: 1,
      name: 'todo-api',
      canonical_path: '/d/projects/todo-api',
      created_at: '2026-04-24T00:00:00Z',
    }),
  ),
  http.get('http://localhost/api/projects/1/runs', () => HttpResponse.json([])),
  http.post('http://localhost/api/projects/1/runs', () =>
    HttpResponse.json({ run_id: 'run-xyz', status: 'pending' }, { status: 202 }),
  ),
  http.post('http://localhost/api/projects/1/qa-sessions', () =>
    HttpResponse.json({ session_id: 'sess-xyz', status: 'pending' }, { status: 202 }),
  ),
  http.get('http://localhost/api/projects/1/tests', () =>
    HttpResponse.json({ version: 1, tests: [] }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/projects/1']}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectDetailPage', () => {
  it('shows project name after loading', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('todo-api')).toBeInTheDocument())
  })

  it('shows Run Init Audit button', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run init audit/i })).toBeInTheDocument(),
    )
  })

  it('shows LiveAgentView after clicking Run Init Audit', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /run init audit/i }))
    await user.click(screen.getByRole('button', { name: /run init audit/i }))
    await waitFor(() =>
      expect(screen.getByTestId('live-agent-view')).toBeInTheDocument(),
    )
  })

  it('shows Run QA Session button', async () => {
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run qa session/i })).toBeInTheDocument(),
    )
  })

  it('starts a QA session when button clicked', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /run qa session/i }))
    await user.click(screen.getByRole('button', { name: /run qa session/i }))
    await waitFor(() => expect(screen.getByTestId('qa-session-view')).toBeInTheDocument())
  })

  it('renders the TicketsPanel section', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('tickets-panel')).toBeInTheDocument())
  })

  it('increments ticketsRefreshKey when QA session completes', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /run qa session/i }))
    await user.click(screen.getByRole('button', { name: /run qa session/i }))
    await waitFor(() => screen.getByTestId('qa-session-view'))
    expect(screen.getByText(/TicketsPanel:1:0/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /complete-qa/i }))
    await waitFor(() =>
      expect(screen.getByText(/TicketsPanel:1:1/)).toBeInTheDocument()
    )
  })

  it('shows PastRunViewer in run history when past runs exist', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/runs', () =>
        HttpResponse.json([
          {
            id: 1,
            run_id: 'run-old-123',
            project_id: 1,
            status: 'done',
            total_input_tokens: 100,
            total_output_tokens: 50,
            started_at: '2026-04-24T00:00:00Z',
            completed_at: '2026-04-24T00:01:00Z',
          },
        ]),
      ),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /^runs$/i }))
    await user.click(screen.getByRole('button', { name: /^runs$/i }))
    await waitFor(() => expect(screen.getByTestId('past-run-viewer')).toBeInTheDocument())
    expect(screen.getByText(/PastRunViewer:run-old-123/)).toBeInTheDocument()
  })

  it('renders the DocPanel section', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /^docs$/i }))
    await user.click(screen.getByRole('button', { name: /^docs$/i }))
    await waitFor(() => expect(screen.getByTestId('doc-panel')).toBeInTheDocument())
  })

  it('renders the CostChart dashboard section', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('cost-chart')).toBeInTheDocument())
  })

  it('renders the HeatmapChart dashboard section', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('heatmap-chart')).toBeInTheDocument())
  })

  it('renders the DocScoreChart dashboard section', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('doc-score-chart')).toBeInTheDocument())
  })

  it('renders the ProvenancePanel dashboard section', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByTestId('provenance-panel')).toBeInTheDocument())
  })

  it('shows Tests tab in the tab bar', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('button', { name: /^tests$/i })).toBeInTheDocument())
  })

  it('shows empty state when Tests tab has no test data', async () => {
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /^tests$/i }))
    await user.click(screen.getByRole('button', { name: /^tests$/i }))
    await waitFor(() =>
      expect(screen.getByText(/no test history yet/i)).toBeInTheDocument(),
    )
  })

  it('shows test rows when Tests tab has data', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/tests', () =>
        HttpResponse.json({
          version: 1,
          tests: [
            {
              name: 'tests/generated/test_bug_0042.py::test_password_hash_not_leaked',
              status: 'green',
              last_run_at: '2026-04-24T03:00:00Z',
              promoted_to: 'per_checkup',
              last_runs: ['pass', 'pass', 'fail', 'pass', 'pass'],
            },
          ],
        }),
      ),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /^tests$/i }))
    await user.click(screen.getByRole('button', { name: /^tests$/i }))
    await waitFor(() =>
      expect(screen.getByText(/test_password_hash_not_leaked/i)).toBeInTheDocument(),
    )
    expect(screen.getByText('per_checkup')).toBeInTheDocument()
  })

  it('filters Tests tab to passing only', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/tests', () =>
        HttpResponse.json({
          version: 1,
          tests: [
            {
              name: 'tests/test_passing.py::test_ok',
              status: 'green_stable',
              last_run_at: null,
              promoted_to: 'daily',
              last_runs: ['pass', 'pass'],
            },
            {
              name: 'tests/test_failing.py::test_bad',
              status: 'red',
              last_run_at: null,
              promoted_to: null,
              last_runs: ['fail', 'fail'],
            },
          ],
        }),
      ),
    )
    const user = userEvent.setup()
    renderPage()
    await waitFor(() => screen.getByRole('button', { name: /^tests$/i }))
    await user.click(screen.getByRole('button', { name: /^tests$/i }))
    await waitFor(() => screen.getByText(/test_passing/i))
    expect(screen.getByText(/test_failing/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^passing$/i }))
    await waitFor(() => expect(screen.queryByText(/test_failing/i)).not.toBeInTheDocument())
    expect(screen.getByText(/test_passing/i)).toBeInTheDocument()
  })
})

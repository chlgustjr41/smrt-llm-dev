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
    renderPage()
    await waitFor(() => expect(screen.getByTestId('past-run-viewer')).toBeInTheDocument())
    expect(screen.getByText(/PastRunViewer:run-old-123/)).toBeInTheDocument()
  })
})

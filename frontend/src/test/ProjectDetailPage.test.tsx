import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ProjectDetailPage } from '../pages/ProjectDetailPage'

// Stub EventSource so LiveAgentView doesn't crash in jsdom
class NoopEventSource {
  onmessage: null = null
  onerror: null = null
  constructor(_url: string) {}
  close() {}
}
vi.stubGlobal('EventSource', NoopEventSource)

const mockProject = {
  id: 1,
  name: 'todo-api',
  canonical_path: '/workspace/eval-fixtures/todo-api',
  created_at: '2026-04-24T00:00:00Z',
}

const server = setupServer(
  http.get('http://localhost/api/projects/1', () => HttpResponse.json(mockProject)),
  http.get('http://localhost/api/projects/1/runs', () => HttpResponse.json([])),
  http.post('http://localhost/api/projects/1/runs', () =>
    HttpResponse.json({ run_id: 'test-run-uuid-1234', status: 'pending' }, { status: 202 }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

function renderDetailPage(id = '1') {
  return render(
    <MemoryRouter initialEntries={[`/projects/${id}`]}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

describe('ProjectDetailPage', () => {
  it('shows loading then project name', async () => {
    renderDetailPage()
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('todo-api')).toBeInTheDocument())
  })

  it('shows canonical path', async () => {
    renderDetailPage()
    await waitFor(() =>
      expect(screen.getByText('/workspace/eval-fixtures/todo-api')).toBeInTheDocument(),
    )
  })

  it('shows Run Init Audit button', async () => {
    renderDetailPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /run init audit/i })).toBeInTheDocument(),
    )
  })

  it('starts a run when button is clicked and shows run id', async () => {
    const user = userEvent.setup()
    renderDetailPage()
    await waitFor(() => screen.getByRole('button', { name: /run init audit/i }))
    await user.click(screen.getByRole('button', { name: /run init audit/i }))
    await waitFor(() => expect(screen.getAllByText(/test-run-uuid-1234/i).length).toBeGreaterThan(0))
  })
})

import { createQASession } from '../api/qa_sessions'

it('qa_sessions api module exports createQASession', () => {
  expect(typeof createQASession).toBe('function')
})

vi.mock('../components/QASessionView', () => ({
  QASessionView: ({ sessionId }: { sessionId: string }) => (
    <div data-testid="qa-view">{sessionId}</div>
  ),
}))

it('shows Run QA Session button', async () => {
  renderDetailPage()
  await waitFor(() =>
    expect(screen.getByRole('button', { name: /run qa session/i })).toBeInTheDocument()
  )
})

it('starts a QA session when button clicked', async () => {
  server.use(
    http.post('http://localhost/api/projects/1/qa-sessions', () =>
      HttpResponse.json({ session_id: 'qa-sess-uuid-5678', status: 'pending' }, { status: 202 }),
    ),
  )
  const user = userEvent.setup()
  renderDetailPage()
  await waitFor(() => screen.getByRole('button', { name: /run qa session/i }))
  await user.click(screen.getByRole('button', { name: /run qa session/i }))
  await waitFor(() => expect(screen.getByTestId('qa-view')).toBeInTheDocument())
})

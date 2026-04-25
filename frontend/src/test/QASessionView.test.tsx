import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { QASessionView } from '../components/QASessionView'

// SSE event sequences to replay
type SSEScenario = Array<object>
let _sseScenario: SSEScenario = []

class MockEventSource {
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  private _closed = false

  constructor(_url: string) {
    setTimeout(() => this._replay(), 10)
  }

  _replay() {
    for (const evt of _sseScenario) {
      if (this._closed) break
      this.onmessage?.({ data: JSON.stringify(evt) })
    }
  }

  close() { this._closed = true }
}

vi.stubGlobal('EventSource', MockEventSource)

const server = setupServer(
  http.post('http://localhost/api/projects/1/qa-sessions/sess-1/approve', () =>
    HttpResponse.json({ decision: 'approve' }),
  ),
  http.post('http://localhost/api/projects/1/qa-sessions/sess-1/skip', () =>
    HttpResponse.json({ decision: 'skip' }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => { server.resetHandlers(); _sseScenario = [] })
afterAll(() => server.close())

describe('QASessionView', () => {
  it('renders QA text delta events', async () => {
    _sseScenario = [
      { type: 'qa_text_delta', text: 'Running tests...' },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/Running tests/)).toBeInTheDocument())
  })

  it('shows HITL buttons on hitl_request event', async () => {
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'session_status', status: 'hitl_waiting' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByRole('button', { name: /approve fix/i })).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /skip/i })).toBeInTheDocument()
  })

  it('calls approve API when Approve clicked and hides HITL panel', async () => {
    const user = userEvent.setup()
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'session_status', status: 'hitl_waiting' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => screen.getByRole('button', { name: /approve fix/i }))
    await user.click(screen.getByRole('button', { name: /approve fix/i }))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /approve fix/i })).not.toBeInTheDocument()
    )
  })

  it('calls skip API when Skip clicked and hides HITL panel', async () => {
    const user = userEvent.setup()
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'session_status', status: 'hitl_waiting' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => screen.getByRole('button', { name: /skip/i }))
    await user.click(screen.getByRole('button', { name: /skip/i }))
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /skip/i })).not.toBeInTheDocument()
    )
  })

  it('shows session complete after done event', async () => {
    _sseScenario = [{ type: 'done', status: 'done' }]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/session complete/i)).toBeInTheDocument())
  })

  it('shows tool input after expanding a tool call in the timeline', async () => {
    const user = userEvent.setup()
    _sseScenario = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts: new Date().toISOString() },
      { type: 'tool_use', tool: 'list_files', input: { subdir: '' }, agent: 'qa' },
      { type: 'tool_result', tool: 'list_files', result: '["main.py"]', agent: 'qa' },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => screen.getByText(/list_files/))
    expect(screen.queryByText(/\["main\.py"\]/)).not.toBeInTheDocument()
    await user.click(screen.getByText(/list_files/))
    expect(screen.getByText(/\["main\.py"\]/)).toBeInTheDocument()
  })
})

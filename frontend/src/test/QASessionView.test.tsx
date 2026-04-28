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
  it('renders QA text delta events when thoughts are shown', async () => {
    _sseScenario = [
      { type: 'qa_text_delta', text: 'Running tests...' },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    // thoughts visible by default (showThoughts starts true)
    await waitFor(() => expect(screen.getByText(/Running tests/)).toBeInTheDocument())
  })

  it('does not auto-approve on hitl_request — ticket stays pending_confirmation', async () => {
    let approvedCalled = false
    server.use(
      http.post('http://localhost/api/projects/1/qa-sessions/sess-1/approve', () => {
        approvedCalled = true
        return HttpResponse.json({ decision: 'approve' })
      }),
    )
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/session complete/i)).toBeInTheDocument())
    expect(approvedCalled).toBe(false)
  })

  it('shows ticket count in completion banner when tickets were filed', async () => {
    _sseScenario = [
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-001', fix_attempt: 0 },
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-24-002', fix_attempt: 0 },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/2 bug tickets filed/i)).toBeInTheDocument())
  })

  it('shows session complete after done event', async () => {
    _sseScenario = [{ type: 'done', status: 'done' }]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/session complete/i)).toBeInTheDocument())
  })

  it('counts tickets from write_bug_ticket tool results, not just hitl_request', async () => {
    // Production scenario: QA agent writes 3 tickets via write_bug_ticket but
    // only one hitl_request fires at the end of the session. The completion
    // banner should reflect the *true* count of tickets filed.
    _sseScenario = [
      { type: 'tool_use', tool: 'write_bug_ticket', agent: 'qa', input: { title: 't1' } },
      { type: 'tool_result', tool: 'write_bug_ticket', agent: 'qa', result: '2026-04-28-001' },
      { type: 'tool_use', tool: 'write_bug_ticket', agent: 'qa', input: { title: 't2' } },
      { type: 'tool_result', tool: 'write_bug_ticket', agent: 'qa', result: '2026-04-28-002' },
      { type: 'tool_use', tool: 'write_bug_ticket', agent: 'qa', input: { title: 't3' } },
      { type: 'tool_result', tool: 'write_bug_ticket', agent: 'qa', result: '2026-04-28-003' },
      { type: 'hitl_request', session_id: 'sess-1', ticket_id: '2026-04-28-003', fix_attempt: 0 },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/3 bug tickets filed/i)).toBeInTheDocument())
  })

  it('does not show an empty "Complete" expandable tab after the QA run ends', async () => {
    _sseScenario = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts: new Date().toISOString() },
      { type: 'qa_text_delta', text: 'Found issues', agent: 'qa' },
      { type: 'session_status', status: 'done', ts: new Date().toISOString() },
      { type: 'done', status: 'done' },
    ]
    render(<QASessionView projectId={1} sessionId="sess-1" />)
    await waitFor(() => expect(screen.getByText(/session complete/i)).toBeInTheDocument())
    // The success banner is the only "complete" indicator — the timeline
    // should not also have an empty Complete card.
    expect(screen.queryByText(/^Complete$/)).not.toBeInTheDocument()
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

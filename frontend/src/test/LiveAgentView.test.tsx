import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { LiveAgentView } from '../components/LiveAgentView'

class MockEventSource {
  static instance: MockEventSource | null = null
  url: string
  onmessage: ((e: { data: string }) => void) | null = null
  onerror: (() => void) | null = null
  readyState = 1
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instance = this
  }

  close() {
    this.closed = true
    this.readyState = 2
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

beforeEach(() => {
  MockEventSource.instance = null
  vi.stubGlobal('EventSource', MockEventSource)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LiveAgentView', () => {
  it('connects to the correct SSE URL', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    expect(MockEventSource.instance?.url).toBe('/api/projects/1/runs/run-abc-123/stream')
  })

  it('renders text_delta events', async () => {
    const user = userEvent.setup()
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'text_delta',
        text: 'Analyzing source tree…',
        agent: 'reviewer',
      })
    })
    // text_delta hidden by default; click Show thoughts to reveal
    await user.click(screen.getByText('Show thoughts'))
    expect(screen.getByText('Analyzing source tree…')).toBeInTheDocument()
  })

  it('renders tool_use events showing tool name', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'tool_use',
        tool: 'list_files',
        input: {},
        agent: 'reviewer',
      })
    })
    expect(screen.getByText(/list_files/i)).toBeInTheDocument()
  })

  it('shows tool result after expanding a tool call row', async () => {
    const user = userEvent.setup()
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'tool_use',
        tool: 'list_files',
        input: { subdir: '' },
        agent: 'reviewer',
      })
      MockEventSource.instance?.emit({
        type: 'tool_result',
        tool: 'list_files',
        result: 'src/main.py',
        agent: 'reviewer',
      })
    })
    expect(screen.getByText(/list_files/i)).toBeInTheDocument()
    expect(screen.queryByText(/src\/main\.py/i)).not.toBeInTheDocument()
    await user.click(screen.getByText(/list_files/i))
    expect(screen.getByText(/src\/main\.py/i)).toBeInTheDocument()
  })

  it('shows Audit complete on done event and closes connection', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'done',
        total_input_tokens: 1000,
        total_output_tokens: 500,
        cost_usd: 0.0105,
      })
    })
    expect(screen.getByText(/audit complete/i)).toBeInTheDocument()
    expect(MockEventSource.instance?.closed).toBe(true)
  })

  it('shows budget warning on budget_exceeded event', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({ type: 'budget_exceeded', cost_usd: 1.51 })
    })
    expect(screen.getByText(/budget/i)).toBeInTheDocument()
  })

  it('closes connection on unmount', () => {
    const { unmount } = render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    unmount()
    expect(MockEventSource.instance?.closed).toBe(true)
  })

  it('toggles thought visibility when Show thoughts button clicked', async () => {
    const user = userEvent.setup()
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'text_delta',
        text: 'Toggle thought text',
        agent: 'reviewer',
      })
    })
    // Initially hidden
    expect(screen.queryByText('Toggle thought text')).not.toBeInTheDocument()
    // Click Show thoughts — now visible
    await user.click(screen.getByText('Show thoughts'))
    expect(screen.getByText('Toggle thought text')).toBeInTheDocument()
    // Click Hide thoughts — hidden again
    await user.click(screen.getByText('Hide thoughts'))
    expect(screen.queryByText('Toggle thought text')).not.toBeInTheDocument()
  })
})

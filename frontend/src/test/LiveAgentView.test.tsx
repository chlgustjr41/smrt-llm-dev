import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
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

  it('renders text_delta events', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({ type: 'text_delta', text: 'Analyzing source tree…' })
    })
    expect(screen.getByText('Analyzing source tree…')).toBeInTheDocument()
  })

  it('renders tool_use events', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({ type: 'tool_use', tool: 'list_files', input: {} })
    })
    expect(screen.getByText(/list_files/i)).toBeInTheDocument()
  })

  it('renders tool_result events', () => {
    render(<LiveAgentView projectId={1} runId="run-abc-123" />)
    act(() => {
      MockEventSource.instance?.emit({
        type: 'tool_result',
        tool: 'list_files',
        result: 'src/main.py',
      })
    })
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
})

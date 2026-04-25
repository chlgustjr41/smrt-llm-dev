import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { AgentTimeline, type AgentEvent } from '../components/AgentTimeline'

describe('AgentTimeline', () => {
  it('shows waiting message with empty event array', () => {
    render(<AgentTimeline events={[]} />)
    expect(screen.getByText(/waiting for events/i)).toBeInTheDocument()
  })

  it('renders text delta content in a phase', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'Analyzing code structure…', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" showThoughts={true} />)
    expect(screen.getByText(/Analyzing code structure…/)).toBeInTheDocument()
  })

  it('shows tool name in collapsed tool call row', () => {
    const events: AgentEvent[] = [
      { type: 'tool_use', tool: 'list_files', input: { subdir: '' }, agent: 'reviewer' },
      { type: 'tool_result', tool: 'list_files', result: '["main.py"]', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    expect(screen.getByText(/list_files/)).toBeInTheDocument()
  })

  it('expands a tool call to show input and result', async () => {
    const user = userEvent.setup()
    const events: AgentEvent[] = [
      {
        type: 'tool_use',
        tool: 'read_file',
        input: { path: 'src/main.py' },
        agent: 'reviewer',
        ts: '2026-04-24T12:00:00.000Z',
      },
      {
        type: 'tool_result',
        tool: 'read_file',
        result: 'from fastapi import FastAPI',
        agent: 'reviewer',
        ts: '2026-04-24T12:00:01.000Z',
      },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    await user.click(screen.getByText(/read_file/))
    expect(screen.getByText(/src\/main\.py/)).toBeInTheDocument()
    expect(screen.getByText(/from fastapi import FastAPI/)).toBeInTheDocument()
  })

  it('renders separate phases for qa_running and coder_running session_status events', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts },
      { type: 'qa_text_delta', text: 'Running QA tests…', agent: 'qa' },
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'coder_text_delta', text: 'Fixing the bug…', agent: 'coder' },
    ]
    render(<AgentTimeline events={events} showThoughts={true} />)
    expect(screen.getAllByText(/QA Agent/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Coder/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Running QA tests…/)).toBeInTheDocument()
    expect(screen.getByText(/Fixing the bug…/)).toBeInTheDocument()
  })

  it('renders recheck_output in a code block with green styling when tests pass', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'recheck_output', output: '2 passed in 0.5s', ts },
    ]
    render(<AgentTimeline events={events} />)
    const pre = screen.getByText(/2 passed in 0\.5s/)
    expect(pre).toBeInTheDocument()
    expect(pre).toHaveClass('bg-emerald-50')
  })

  it('hides text_delta events by default', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'Hidden thought content', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" />)
    expect(screen.queryByText(/Hidden thought content/)).not.toBeInTheDocument()
  })

  it('hides qa_text_delta and coder_text_delta events by default', () => {
    const events = [
      { type: 'qa_text_delta', content: 'qa-thought-hidden', ts: '2026-01-01T00:00:00Z' },
      { type: 'coder_text_delta', content: 'coder-thought-hidden', ts: '2026-01-01T00:00:01Z' },
    ]
    render(<AgentTimeline events={events} />)
    expect(screen.queryByText('qa-thought-hidden')).not.toBeInTheDocument()
    expect(screen.queryByText('coder-thought-hidden')).not.toBeInTheDocument()
  })

  it('shows text_delta events when showThoughts is true', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'Visible thought content', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" showThoughts={true} />)
    expect(screen.getByText(/Visible thought content/)).toBeInTheDocument()
  })
})

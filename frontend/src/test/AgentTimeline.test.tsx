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

  it('does not render an empty "Complete" phase after a session_status=done event', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts },
      { type: 'qa_text_delta', text: 'Running tests…', agent: 'qa' },
      { type: 'session_status', status: 'done', ts },
    ]
    render(<AgentTimeline events={events} showThoughts={true} />)
    // QA Agent phase still renders…
    expect(screen.getAllByText(/QA Agent/).length).toBeGreaterThan(0)
    // …but no Complete tab is added by the timeline.
    expect(screen.queryByText(/^Complete$/)).not.toBeInTheDocument()
    expect(screen.queryByText(/✓ Done/)).not.toBeInTheDocument()
  })

  it('does not render a "loop_exhausted" phase card on Needs Review tickets', () => {
    // Simulates the Agent Logs view of a ticket that ended in loop_exhausted
    // (Needs Review column). The failure-report banner shown above the timeline
    // already conveys "this ended" — an empty bottom phase card is noise.
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'coder_text_delta', text: 'Trying to fix…', agent: 'coder' },
      { type: 'session_status', status: 'qa_checking', fix_attempt: 0, ts },
      { type: 'recheck_output', output: '1 failed', ts },
      { type: 'session_status', status: 'loop_exhausted', ts },
    ]
    render(<AgentTimeline events={events} showThoughts={true} />)
    // Coder + QA Verify phases still render.
    expect(screen.getAllByText(/Coder/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/QA Verify/).length).toBeGreaterThan(0)
    // No empty terminal card.
    expect(screen.queryByText(/^loop_exhausted$/)).not.toBeInTheDocument()
  })

  it('shows a Collapse all / Expand all toggle when there are multiple phases', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts },
      { type: 'qa_text_delta', text: 'a', agent: 'qa' },
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'coder_text_delta', text: 'b', agent: 'coder' },
    ]
    render(<AgentTimeline events={events} showThoughts={true} />)
    expect(screen.getByText(/Collapse all/)).toBeInTheDocument()
    expect(screen.getByText(/Expand all/)).toBeInTheDocument()
  })

  it('hides the master toggle when there is only one phase', () => {
    const events: AgentEvent[] = [
      { type: 'text_delta', text: 'lone phase', agent: 'reviewer' },
    ]
    render(<AgentTimeline events={events} defaultLabel="Reviewer" showThoughts={true} />)
    expect(screen.queryByText(/Collapse all/)).not.toBeInTheDocument()
  })

  it('collapses all phase cards when the master Collapse all is clicked', async () => {
    const user = userEvent.setup()
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts },
      { type: 'qa_text_delta', text: 'thought-A', agent: 'qa' },
      { type: 'session_status', status: 'coder_running', fix_attempt: 0, ts },
      { type: 'coder_text_delta', text: 'thought-B', agent: 'coder' },
    ]
    render(<AgentTimeline events={events} showThoughts={true} />)
    // Phases render expanded by default → both thought texts visible.
    expect(screen.getByText(/thought-A/)).toBeInTheDocument()
    expect(screen.getByText(/thought-B/)).toBeInTheDocument()
    await user.click(screen.getByText(/Collapse all/))
    // Once collapsed the inner thought bubbles disappear from the DOM.
    expect(screen.queryByText(/thought-A/)).not.toBeInTheDocument()
    expect(screen.queryByText(/thought-B/)).not.toBeInTheDocument()
    // Re-expand brings them back.
    await user.click(screen.getByText(/Expand all/))
    expect(screen.getByText(/thought-A/)).toBeInTheDocument()
    expect(screen.getByText(/thought-B/)).toBeInTheDocument()
  })

  it('separates thought segments with a blank line between tool calls', () => {
    const ts = new Date().toISOString()
    const events: AgentEvent[] = [
      { type: 'session_status', status: 'qa_running', fix_attempt: 0, ts },
      { type: 'qa_text_delta', text: 'First reasoning step.', agent: 'qa' },
      { type: 'tool_use', tool: 'list_files', input: {}, agent: 'qa', ts },
      { type: 'tool_result', tool: 'list_files', result: '[]', agent: 'qa', ts },
      { type: 'qa_text_delta', text: 'Second reasoning step.', agent: 'qa' },
    ]
    render(<AgentTimeline events={events} showThoughts={true} />)
    // Both segments render. The "first" string appears twice — once in the
    // ThoughtBubble and once in the tool's collapsed "Why" preview.
    expect(screen.getAllByText(/First reasoning step/).length).toBeGreaterThan(0)
    expect(screen.getByText(/Second reasoning step/)).toBeInTheDocument()
    // Inside the ThoughtBubble (the prose container), the two segments should
    // land in distinct <p> elements — that's how markdown renders a paragraph
    // break, which is what segment-separation produces.
    const second = screen.getByText(/Second reasoning step/)
    const secondParagraph = second.closest('p')
    expect(secondParagraph).not.toBeNull()
    // The bubble that contains "Second reasoning step" should have a sibling
    // paragraph with "First reasoning step" — they are separate <p> nodes
    // because the segments are joined with \n\n.
    const bubble = secondParagraph!.parentElement
    const firstP = bubble!.querySelector('p:first-child')
    expect(firstP?.textContent).toMatch(/First reasoning step/)
    expect(firstP).not.toBe(secondParagraph)
  })
})

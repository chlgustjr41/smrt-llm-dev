import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { PastRunViewer } from '../components/PastRunViewer'
import * as runsApi from '../api/runs'

vi.mock('../components/AgentTimeline', () => ({
  AgentTimeline: ({ events }: { events: unknown[] }) => (
    <div data-testid="agent-timeline">events:{events.length}</div>
  ),
}))

describe('PastRunViewer', () => {
  afterEach(() => vi.restoreAllMocks())

  it('shows View events button initially', () => {
    render(<PastRunViewer projectId={1} runId="run-abc" />)
    expect(screen.getByRole('button', { name: /view events/i })).toBeInTheDocument()
  })

  it('fetches and renders events when button clicked', async () => {
    const user = userEvent.setup()
    vi.spyOn(runsApi, 'getRunEvents').mockResolvedValue([
      { type: 'text_delta', text: 'hello', agent: 'reviewer' },
    ])
    render(<PastRunViewer projectId={1} runId="run-abc" />)
    await user.click(screen.getByRole('button', { name: /view events/i }))
    await waitFor(() =>
      expect(screen.getByTestId('agent-timeline')).toBeInTheDocument()
    )
    expect(screen.getByText(/events:1/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /view events/i })).not.toBeInTheDocument()
  })

  it('shows error message when fetch fails', async () => {
    const user = userEvent.setup()
    vi.spyOn(runsApi, 'getRunEvents').mockRejectedValue(new Error('500 Internal Server Error'))
    render(<PastRunViewer projectId={1} runId="run-abc" />)
    await user.click(screen.getByRole('button', { name: /view events/i }))
    await waitFor(() =>
      expect(screen.getByText(/500 Internal Server Error/i)).toBeInTheDocument()
    )
    expect(screen.queryByRole('button', { name: /view events/i })).not.toBeInTheDocument()
  })
})

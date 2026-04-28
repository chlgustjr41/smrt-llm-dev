import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { TicketsPanel } from '../components/TicketsPanel'

const mockTickets = [
  {
    id: '2026-04-24-001',
    title: 'GET /items returns 404',
    content: 'Fix was applied.',
    status: 'needs_review' as const,
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/tickets', () =>
    HttpResponse.json(mockTickets),
  ),
  http.get('http://localhost/api/projects/1/coder/status', () =>
    HttpResponse.json({ idle: true, session_id: null, status: null, ticket_id: null }),
  ),
  http.post('http://localhost/api/projects/1/pr/2026-04-24-001/accept', () =>
    HttpResponse.json({ ticket_id: '2026-04-24-001', status: 'accepted' }),
  ),
  http.post('http://localhost/api/projects/1/pr/2026-04-24-001/reject', () =>
    HttpResponse.json({ ticket_id: '2026-04-24-001', status: 'rejected' }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('TicketsPanel PR actions', () => {
  it('shows needs_review ticket in the Needs Review column', async () => {
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('Needs Review'))
    expect(screen.getByText('2026-04-24-001')).toBeInTheDocument()
  })

  it('shows Accept and Reject buttons when needs_review ticket is clicked', async () => {
    const user = userEvent.setup()
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('2026-04-24-001'))
    // Click the ticket card — opens the detail dialog
    await user.click(screen.getAllByText('2026-04-24-001')[0])
    expect(screen.getByRole('button', { name: /accept/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reject/i })).toBeInTheDocument()
  })

  it('calls accept endpoint and triggers onReviewed callback', async () => {
    const user = userEvent.setup()
    const onReviewed = vi.fn()
    render(<TicketsPanel projectId={1} onReviewed={onReviewed} />)
    await waitFor(() => screen.getByText('2026-04-24-001'))
    await user.click(screen.getAllByText('2026-04-24-001')[0])
    // Override GET after initial load so the refresh after accept returns closed
    server.use(
      http.get('http://localhost/api/projects/1/tickets', () =>
        HttpResponse.json([{ ...mockTickets[0], status: 'closed' }]),
      ),
    )
    await user.click(screen.getByRole('button', { name: /accept/i }))
    await waitFor(() => expect(onReviewed).toHaveBeenCalled())
  })
})

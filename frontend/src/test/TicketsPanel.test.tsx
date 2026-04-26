import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { TicketsPanel } from '../components/TicketsPanel'

const mockTickets = [
  {
    id: '2026-04-24-001',
    title: 'GET /items returns 404',
    content: '# GET /items returns 404\nThe endpoint is missing from the router.',
    status: 'pending_confirmation',
    session_id: null,
  },
  {
    id: '2026-04-24-002',
    title: 'POST /items ignores body',
    content: '# POST /items ignores body\nInput data is discarded.',
    status: 'closed',
    session_id: null,
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/tickets', () =>
    HttpResponse.json(mockTickets),
  ),
  http.get('http://localhost/api/projects/1/coder/status', () =>
    HttpResponse.json({ idle: true, session_id: null, status: null, ticket_id: null }),
  ),
  http.post('http://localhost/api/projects/1/tickets/:ticketId/approve', ({ params }) =>
    HttpResponse.json({
      ticket_id: params.ticketId,
      session_id: 'test-session-123',
      status: 'in_progress',
    }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('TicketsPanel', () => {
  it('shows no-tickets message when the list is empty', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/tickets', () => HttpResponse.json([])),
    )
    render(<TicketsPanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no bug tickets/i)).toBeInTheDocument(),
    )
  })

  it('lists ticket IDs and titles', async () => {
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText('2026-04-24-001')).toBeInTheDocument())
    expect(screen.getByText(/GET \/items returns 404/)).toBeInTheDocument()
    expect(screen.getByText('2026-04-24-002')).toBeInTheDocument()
  })

  it('expands a ticket to show full content when clicked', async () => {
    const user = userEvent.setup()
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('2026-04-24-001'))
    expect(screen.queryByText(/The endpoint is missing from the router/)).not.toBeInTheDocument()
    await user.click(screen.getByText('2026-04-24-001'))
    expect(screen.getByText(/The endpoint is missing from the router/)).toBeInTheDocument()
  })

  it('re-fetches when refreshKey changes', async () => {
    const { rerender } = render(<TicketsPanel projectId={1} refreshKey={0} />)
    await waitFor(() => screen.getByText('2026-04-24-001'))

    server.use(
      http.get('http://localhost/api/projects/1/tickets', () =>
        HttpResponse.json([
          {
            id: '2026-04-24-003',
            title: 'New ticket',
            content: '# New ticket\nNew content.',
            status: 'pending_confirmation',
            session_id: null,
          },
        ]),
      ),
    )

    rerender(<TicketsPanel projectId={1} refreshKey={1} />)
    await waitFor(() => expect(screen.getByText('2026-04-24-003')).toBeInTheDocument())
  })

  it('renders tickets in correct kanban columns', async () => {
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('Pending Confirmation'))
    expect(screen.getByText('Closed')).toBeInTheDocument()
    expect(screen.getByText('2026-04-24-001')).toBeInTheDocument()
    expect(screen.getByText('2026-04-24-002')).toBeInTheDocument()
  })

  it('shows all 5 kanban column headers', async () => {
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('Pending Confirmation'))
    expect(screen.getByText('In Progress')).toBeInTheDocument()
    expect(screen.getByText('QA Review')).toBeInTheDocument()
    expect(screen.getByText('Needs Review')).toBeInTheDocument()
    expect(screen.getByText('Closed')).toBeInTheDocument()
  })

  it('shows agent log toggle on ticket card when session_id is present', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/tickets', () =>
        HttpResponse.json([
          {
            id: '2026-04-24-004',
            title: 'Active fix ticket',
            content: '# Active fix\nBeing fixed now.',
            status: 'in_progress',
            session_id: 'active-session-abc',
          },
        ]),
      ),
    )
    render(<TicketsPanel projectId={1} />)
    await waitFor(() => screen.getByText('2026-04-24-004'))
    expect(screen.getByText(/Coder fixing/i)).toBeInTheDocument()
  })
})

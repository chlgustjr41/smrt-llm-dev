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
  },
  {
    id: '2026-04-24-002',
    title: 'POST /items ignores body',
    content: '# POST /items ignores body\nInput data is discarded.',
    status: 'closed',
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/tickets', () =>
    HttpResponse.json(mockTickets),
  ),
  http.get('http://localhost/api/projects/1/coder/status', () =>
    HttpResponse.json({ idle: true, session_id: null, status: null, ticket_id: null }),
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
    expect(screen.getByText('2026-04-24-001')).toBeInTheDocument()  // pending col
    expect(screen.getByText('2026-04-24-002')).toBeInTheDocument()  // closed col
  })
})

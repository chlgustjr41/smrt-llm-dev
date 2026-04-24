import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { MemoryRouter } from 'react-router-dom'
import { ProjectsPage } from '../pages/ProjectsPage'

// Stub FileBrowser so the registration test doesn't need real filesystem API.
// It renders a single button that calls onSelect with a fixed path.
vi.mock('../components/FileBrowser', () => ({
  FileBrowser: ({ onSelect }: { onSelect: (path: string) => void }) => (
    <button onClick={() => onSelect('/workspace/test-project')}>Pick folder</button>
  ),
}))

const mockProjects = [
  { id: 1, name: 'todo-api', canonical_path: '/d/projects/todo-api', created_at: '2026-04-23T00:00:00Z' },
]

const server = setupServer(
  http.get('http://localhost/api/projects', () => {
    return HttpResponse.json(mockProjects)
  }),
  http.post('http://localhost/api/projects', async ({ request }) => {
    const body = (await request.json()) as { name: string; path: string }
    return HttpResponse.json(
      { id: 2, name: body.name, canonical_path: body.path, created_at: '2026-04-23T00:00:01Z' },
      { status: 201 },
    )
  }),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('ProjectsPage', () => {
  it('lists projects fetched from the API', async () => {
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText('todo-api')).toBeInTheDocument())
  })

  it('shows empty state when no projects', async () => {
    server.use(http.get('http://localhost/api/projects', () => HttpResponse.json([])))
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/no projects/i)).toBeInTheDocument())
  })

  it('registers a new project and appends it to the list', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    await waitFor(() => screen.getByText('todo-api'))

    await user.type(screen.getByPlaceholderText(/project name/i), 'my-app')
    // Open the file browser stub and select a folder
    await user.click(screen.getByRole('button', { name: /browse/i }))
    await user.click(screen.getByRole('button', { name: /pick folder/i }))
    await user.click(screen.getByRole('button', { name: /register project/i }))

    await waitFor(() => expect(screen.getByText('my-app')).toBeInTheDocument())
  })
})

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

  // ── Dashboard decoration: the page should always teach the user what
  // SMRT does and how to use it. These guards prevent future refactors
  // from quietly stripping the educational content.

  it('shows the system tagline and the three agent roles in the hero', async () => {
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    // System name is the page H1.
    expect(screen.getByRole('heading', { level: 1, name: /SMRT Agent/ })).toBeInTheDocument()
    // The agent-cards section must be present.
    expect(screen.getByText(/three specialized agents/i)).toBeInTheDocument()
    // Each agent name appears in MULTIPLE places (card label + body copy
    // referencing them) — getAllByText asserts they're surfaced and lets
    // future copy reorganize without breaking this test.
    expect(screen.getAllByText(/Reviewer/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/QA Agent/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/Coder/).length).toBeGreaterThan(0)
  })

  it('explains the QA ↔ Coder loop and the human gates', async () => {
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    expect(screen.getByText(/how the qa.*coder loop works/i)).toBeInTheDocument()
    // Both human-gate badges must be present so the loop story is complete.
    expect(screen.getByText(/you approve/i)).toBeInTheDocument()
    expect(screen.getByText(/you merge/i)).toBeInTheDocument()
  })

  it('shows the "What\'s new" strip with the recent feature additions', async () => {
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    expect(screen.getByText(/what's new/i)).toBeInTheDocument()
    // Each card title — these are the user-facing features the dashboard
    // promises so a refactor can't accidentally drop the section.
    expect(screen.getByText(/Reviewer-written Fix Summaries/i)).toBeInTheDocument()
    expect(screen.getByText(/Doc generation toggle/i)).toBeInTheDocument()
    expect(screen.getByText(/Doc updates applied on Accept/i)).toBeInTheDocument()
    expect(screen.getByText(/QA Advisor with three verdicts/i)).toBeInTheDocument()
  })

  it('renders a 4-step Quick Start guide', async () => {
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    expect(screen.getByText(/quick start/i)).toBeInTheDocument()
    // Step titles — covers register / audit / qa session / approve flows.
    expect(screen.getByText(/Register a project/)).toBeInTheDocument()
    expect(screen.getByText(/Run the Init Audit/)).toBeInTheDocument()
    expect(screen.getByText(/Run a QA Session/)).toBeInTheDocument()
    expect(screen.getByText(/Approve fixes via the kanban board/)).toBeInTheDocument()
  })

  it('promotes the registration form for first-time users (empty project list)', async () => {
    server.use(http.get('http://localhost/api/projects', () => HttpResponse.json([])))
    render(<MemoryRouter><ProjectsPage /></MemoryRouter>)
    // The form section should be highlighted as the call-to-action.
    await waitFor(() =>
      expect(screen.getByText(/register your first project/i)).toBeInTheDocument(),
    )
    // The bundled fixture is referenced in BOTH the quick-start guide and
    // the first-time onboarding tip — assert at least one occurrence.
    expect(screen.getAllByText(/eval-fixtures\/todo-api/).length).toBeGreaterThan(0)
  })
})

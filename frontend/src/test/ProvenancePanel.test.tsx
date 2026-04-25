import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { ProvenancePanel } from '../components/ProvenancePanel'
import type { ProvenanceEntry } from '../api/provenance'

const mockEntries: ProvenanceEntry[] = [
  {
    ticket: 'BUG-0042',
    subagent: 'coder_agent',
    reasoning: 'Fixed null pointer by adding guard clause',
    sources_consulted: ['src/api/main.py', 'docs/api/GET_items.md'],
    attempts: 2,
    related_lessons_applied: ['always check for None before accessing attributes'],
    ts: '2026-04-24T10:00:00Z',
  },
  {
    ticket: 'BUG-0043',
    subagent: 'reviewer_agent',
    reasoning: 'Identified missing input validation',
    sources_consulted: [],
    attempts: 1,
    related_lessons_applied: [],
  },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/provenance', () =>
    HttpResponse.json({ entries: mockEntries }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('ProvenancePanel', () => {
  it('shows loading state initially', () => {
    render(<ProvenancePanel projectId={1} />)
    expect(screen.getByText(/loading provenance/i)).toBeInTheDocument()
  })

  it('shows provenance entries with ticket, subagent, and attempts visible', async () => {
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() => expect(screen.getByText('BUG-0042')).toBeInTheDocument())
    expect(screen.getByText('coder')).toBeInTheDocument()
    expect(screen.getByText('BUG-0043')).toBeInTheDocument()
    expect(screen.getByText('reviewer')).toBeInTheDocument()
  })

  it('shows empty state when no entries', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/provenance', () =>
        HttpResponse.json({ entries: [] }),
      ),
    )
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no provenance entries yet/i)).toBeInTheDocument(),
    )
  })

  it('shows error state on fetch failure', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/provenance', () =>
        HttpResponse.error(),
      ),
    )
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/failed to fetch/i)).toBeInTheDocument(),
    )
  })

  it('expands detail section on click and shows reasoning text', async () => {
    const user = userEvent.setup()
    render(<ProvenancePanel projectId={1} />)
    await waitFor(() => screen.getByText('BUG-0042'))

    // Detail should not be visible before click
    expect(
      screen.queryByTestId('provenance-detail'),
    ).not.toBeInTheDocument()

    // Click the first entry's button to expand
    const entryButtons = screen.getAllByRole('button')
    await user.click(entryButtons[0])

    // Reasoning text should now be visible
    expect(
      screen.getByText('Fixed null pointer by adding guard clause'),
    ).toBeInTheDocument()
    expect(screen.getByTestId('provenance-detail')).toBeInTheDocument()
  })
})

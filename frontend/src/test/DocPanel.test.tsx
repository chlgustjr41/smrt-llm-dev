import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DocPanel } from '../components/DocPanel'

const mockFiles = [
  { backend: 'obsidian', path: 'docs/api/GET_items.md' },
  { backend: 'obsidian', path: 'docs/modules/todo-api.md' },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/docs', () =>
    HttpResponse.json({ files: mockFiles }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('DocPanel', () => {
  it('shows Obsidian as enabled chip', async () => {
    render(<DocPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText(/✓ Obsidian/i)).toBeInTheDocument())
  })

  it('shows GitHub, Jira and Confluence as coming soon', async () => {
    render(<DocPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText(/✓ Obsidian/i)).toBeInTheDocument())
    expect(screen.getByText(/GitHub.*coming soon/i)).toBeInTheDocument()
    expect(screen.getByText(/Jira.*coming soon/i)).toBeInTheDocument()
    expect(screen.getByText(/Confluence.*coming soon/i)).toBeInTheDocument()
  })

  it('lists generated doc files', async () => {
    render(<DocPanel projectId={1} />)
    await waitFor(() => expect(screen.getByText('docs/api/GET_items.md')).toBeInTheDocument())
    expect(screen.getByText('docs/modules/todo-api.md')).toBeInTheDocument()
  })

  it('shows no-docs message when list is empty', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/docs', () =>
        HttpResponse.json({ files: [] }),
      ),
    )
    render(<DocPanel projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no documentation generated/i)).toBeInTheDocument(),
    )
  })
})

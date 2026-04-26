import { describe, it, expect, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { HeatmapChart } from '../components/HeatmapChart'

// jsdom doesn't implement ResizeObserver — provide a no-op stub
global.ResizeObserver = class {
  observe() {}
  unobserve() {}
  disconnect() {}
}

const mockData = [
  { file: 'src/api/main.py', loc: 200, bugs_resolved: 3 },
  { file: 'src/utils/helpers.py', loc: 50, bugs_resolved: 0 },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/stats/heatmap', () =>
    HttpResponse.json({ files: mockData }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('HeatmapChart', () => {
  it('shows loading state initially', () => {
    render(<HeatmapChart projectId={1} />)
    expect(screen.getByText(/loading heatmap/i)).toBeInTheDocument()
  })

  it('shows treemap cells after data loads', async () => {
    render(<HeatmapChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('treemap')).toBeInTheDocument())
    const cells = screen.getAllByTestId('treemap-cell')
    expect(cells.length).toBe(2)
    // Largest file (200 LOC) sorts first
    expect(cells[0]).toHaveAttribute('data-name', 'src/api/main.py')
    expect(cells[1]).toHaveAttribute('data-name', 'src/utils/helpers.py')
  })

  it('shows empty state when no data', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/heatmap', () =>
        HttpResponse.json({ files: [] }),
      ),
    )
    render(<HeatmapChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no source files found/i)).toBeInTheDocument(),
    )
  })

  it('shows error state on fetch failure', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/heatmap', () =>
        HttpResponse.error(),
      ),
    )
    render(<HeatmapChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/failed to fetch/i)).toBeInTheDocument(),
    )
  })

  it('shows detail panel when a cell is clicked and toggles on second click', async () => {
    const user = userEvent.setup()
    render(<HeatmapChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('treemap')).toBeInTheDocument())

    const cells = screen.getAllByTestId('treemap-cell')
    // Click first cell — should show detail panel with the file's full path
    await user.click(cells[0])
    expect(screen.getByText('src/api/main.py')).toBeInTheDocument()
    expect(screen.getByText(/bugs resolved/i)).toBeInTheDocument()

    // Click same cell again to deselect
    await user.click(cells[0])
    expect(screen.queryByText(/bugs resolved/i)).not.toBeInTheDocument()
  })
})

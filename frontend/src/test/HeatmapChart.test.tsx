import React from 'react'
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { HeatmapChart } from '../components/HeatmapChart'

vi.mock('recharts', () => ({
  Treemap: ({ data, onClick }: { data: Array<{ name: string; size: number; bugs_resolved: number; path: string }>; onClick?: (node: any) => void }) => (
    <div data-testid="treemap">
      {data?.map((d, i) => (
        <div
          key={i}
          data-testid="treemap-cell"
          data-name={d.name}
          onClick={() => onClick?.({ name: d.name, size: d.size, bugs_resolved: d.bugs_resolved, path: d.path })}
        >
          {d.name}
        </div>
      ))}
    </div>
  ),
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

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
    expect(screen.getByText('src/api/main.py')).toBeInTheDocument()
    expect(screen.getByText('src/utils/helpers.py')).toBeInTheDocument()
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
    // Click first cell (src/api/main.py)
    await user.click(cells[0])
    // Detail panel should be visible (LOC label only appears in detail panel)
    expect(screen.getByText(/LOC:/i)).toBeInTheDocument()
    // Detail panel should show LOC and bugs_resolved values
    expect(screen.getByText(/200/)).toBeInTheDocument()
    expect(screen.getByText(/3/)).toBeInTheDocument()

    // Click same cell again to deselect
    await user.click(cells[0])
    // Detail panel should be gone — the detail panel has a specific structure
    // Check that the detail panel container is no longer rendered
    expect(screen.queryByText(/LOC/i)).not.toBeInTheDocument()
  })
})

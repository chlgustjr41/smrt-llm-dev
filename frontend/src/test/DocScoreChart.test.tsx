import React from 'react'
import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { DocScoreChart } from '../components/DocScoreChart'
import type { DocScoreEntry } from '../api/stats'

vi.mock('recharts', () => ({
  LineChart: ({ data }: { data: Array<{ date: string; score: number }> }) => (
    <div data-testid="line-chart">
      {data?.map((d, i) => (
        <div key={i} data-testid="line-point" data-score={d.score}>{d.score}</div>
      ))}
    </div>
  ),
  Line: () => null,
  XAxis: ({ dataKey }: { dataKey: string }) => <div data-testid="x-axis" data-key={dataKey} />,
  YAxis: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CartesianGrid: () => null,
}))

const mockData: DocScoreEntry[] = [
  { ts: '2026-04-24T10:00:00Z', score: 42.5, ep_documented: 3, ep_total: 6, mod_documented: 1, mod_total: 2 },
  { ts: '2026-04-24T11:00:00Z', score: 75.0, ep_documented: 5, ep_total: 6, mod_documented: 2, mod_total: 2 },
]

const server = setupServer(
  http.get('http://localhost/api/projects/1/stats/doc-completeness', () =>
    HttpResponse.json({ history: mockData }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('DocScoreChart', () => {
  it('shows loading state initially', () => {
    render(<DocScoreChart projectId={1} />)
    expect(screen.getByText(/loading doc scores/i)).toBeInTheDocument()
  })

  it('shows line chart after data loads', async () => {
    render(<DocScoreChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('line-chart')).toBeInTheDocument())
    const points = screen.getAllByTestId('line-point')
    expect(points).toHaveLength(2)
    expect(points[0]).toHaveAttribute('data-score', '42.5')
    expect(points[1]).toHaveAttribute('data-score', '75')
  })

  it('shows empty state when no data', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/doc-completeness', () =>
        HttpResponse.json({ history: [] }),
      ),
    )
    render(<DocScoreChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no documentation score history yet/i)).toBeInTheDocument(),
    )
  })

  it('shows error state on fetch failure', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/doc-completeness', () =>
        HttpResponse.error(),
      ),
    )
    render(<DocScoreChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/failed to fetch/i)).toBeInTheDocument(),
    )
  })

  it('renders correct number of data points', async () => {
    render(<DocScoreChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('line-chart')).toBeInTheDocument())
    // Verify both score values are rendered as data points in the chart
    expect(screen.getByText('42.5')).toBeInTheDocument()
    expect(screen.getByText('75')).toBeInTheDocument()
    // Verify the data points have the score attribute set correctly
    const points = screen.getAllByTestId('line-point')
    const scores = points.map((p) => p.getAttribute('data-score'))
    expect(scores).toContain('42.5')
    expect(scores).toContain('75')
  })
})

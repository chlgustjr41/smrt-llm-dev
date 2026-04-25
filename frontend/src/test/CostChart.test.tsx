import { describe, it, expect, vi, beforeAll, afterEach, afterAll } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { http, HttpResponse } from 'msw'
import { setupServer } from 'msw/node'
import { CostChart } from '../components/CostChart'

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  BarChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="bar-chart">{children}</div>
  ),
  Bar: ({ name }: { name: string }) => <div data-testid={`bar-${name}`} />,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Legend: () => null,
}))

const mockRun = {
  run_id: 'run-abc-123456',
  started_at: '2026-04-25T00:00:00Z',
  reviewer_cost_usd: 0.00015,
  qa_cost_usd: 0.0,
  coder_cost_usd: 0.0,
  reviewer_input_tokens: 1000,
  reviewer_output_tokens: 500,
}

const server = setupServer(
  http.get('http://localhost/api/projects/1/stats/cost', () =>
    HttpResponse.json({ runs: [mockRun] }),
  ),
)

beforeAll(() => server.listen())
afterEach(() => server.resetHandlers())
afterAll(() => server.close())

describe('CostChart', () => {
  it('renders bar chart when data is available', async () => {
    render(<CostChart projectId={1} />)
    await waitFor(() => expect(screen.getByTestId('bar-chart')).toBeInTheDocument())
  })

  it('shows Reviewer, QA, and Coder bars', async () => {
    render(<CostChart projectId={1} />)
    await waitFor(() => screen.getByTestId('bar-chart'))
    expect(screen.getByTestId('bar-Reviewer')).toBeInTheDocument()
    expect(screen.getByTestId('bar-QA')).toBeInTheDocument()
    expect(screen.getByTestId('bar-Coder')).toBeInTheDocument()
  })

  it('shows empty state when no runs', async () => {
    server.use(
      http.get('http://localhost/api/projects/1/stats/cost', () =>
        HttpResponse.json({ runs: [] }),
      ),
    )
    render(<CostChart projectId={1} />)
    await waitFor(() =>
      expect(screen.getByText(/no audit runs/i)).toBeInTheDocument(),
    )
  })

  it('shows loading initially', () => {
    render(<CostChart projectId={1} />)
    expect(screen.getByText(/loading/i)).toBeInTheDocument()
  })
})

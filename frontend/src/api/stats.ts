import { apiFetch } from './client'

export interface RunCostEntry {
  run_id: string
  type?: 'reviewer_run' | 'qa_session'
  ticket_id?: string | null
  started_at: string | null
  reviewer_cost_usd: number
  qa_cost_usd: number
  coder_cost_usd: number
  reviewer_model?: string | null
  qa_model?: string | null
  coder_model?: string | null
  reviewer_input_tokens: number
  reviewer_output_tokens: number
  qa_input_tokens?: number
  qa_output_tokens?: number
  coder_input_tokens?: number
  coder_output_tokens?: number
}

export interface DocScoreEntry {
  ts: string
  score: number
  ep_documented: number
  ep_total: number
  mod_documented: number
  mod_total: number
}

export async function getRunCosts(
  projectId: number,
  signal?: AbortSignal,
): Promise<RunCostEntry[]> {
  const data = await apiFetch<{ runs: RunCostEntry[] }>(
    `/projects/${projectId}/stats/cost`,
    { signal },
  )
  return data.runs
}

export async function getDocScoreHistory(
  projectId: number,
  signal?: AbortSignal,
): Promise<DocScoreEntry[]> {
  const data = await apiFetch<{ history: DocScoreEntry[] }>(
    `/projects/${projectId}/stats/doc-completeness`,
    { signal },
  )
  return data.history
}

export interface TestFunction {
  fn: string
  description: string
  docstring: string
}

export interface TestStatusEntry {
  name: string
  status: 'green_stable' | 'green' | 'red' | 'flaky'
  last_run_at: string | null
  promoted_to: 'per_checkup' | 'daily' | 'weekly' | null
  last_runs: string[]
  functions?: TestFunction[]
  coverage_pct?: number | null
}

export interface TestsResponse {
  tests: TestStatusEntry[]
  version: number
  overall_coverage: number | null
  file_coverage: Record<string, number>
  /** source basename → test node IDs that covered it (from --cov-context=test) */
  file_tests?: Record<string, string[]>
}

export async function getTestStatus(
  projectId: number,
  signal?: AbortSignal,
): Promise<TestsResponse> {
  return apiFetch<TestsResponse>(`/projects/${projectId}/tests`, { signal })
}

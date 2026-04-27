import { apiFetch } from './client'

export interface RunCostEntry {
  run_id: string
  type?: 'reviewer_run' | 'qa_session'
  ticket_id?: string | null
  started_at: string | null
  reviewer_cost_usd: number
  qa_cost_usd: number
  coder_cost_usd: number
  reviewer_input_tokens: number
  reviewer_output_tokens: number
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

export interface TestStatusEntry {
  name: string
  status: 'green_stable' | 'green' | 'red' | 'flaky'
  last_run_at: string | null
  promoted_to: 'per_checkup' | 'daily' | 'weekly' | null
  last_runs: string[]
}

export async function getTestStatus(
  projectId: number,
  signal?: AbortSignal,
): Promise<TestStatusEntry[]> {
  const data = await apiFetch<{ tests: TestStatusEntry[]; version: number }>(
    `/projects/${projectId}/tests`,
    { signal },
  )
  return data.tests
}

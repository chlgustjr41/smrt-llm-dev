import { apiFetch } from './client'

export interface RunCostEntry {
  run_id: string
  started_at: string | null
  reviewer_cost_usd: number
  qa_cost_usd: number
  coder_cost_usd: number
  reviewer_input_tokens: number
  reviewer_output_tokens: number
}

export interface HeatmapEntry {
  file: string
  loc: number
  bugs_resolved: number
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

export async function getHeatmap(
  projectId: number,
  signal?: AbortSignal,
): Promise<HeatmapEntry[]> {
  const data = await apiFetch<{ files: HeatmapEntry[] }>(
    `/projects/${projectId}/stats/heatmap`,
    { signal },
  )
  return data.files
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

import { apiFetch } from './client'

export interface ProvenanceEntry {
  ticket: string
  subagent: string
  reasoning: string
  sources_consulted: string[]
  attempts: number
  related_lessons_applied: string[]
  ts?: string
}

export async function listProvenance(
  projectId: number,
  signal?: AbortSignal,
): Promise<ProvenanceEntry[]> {
  const data = await apiFetch<{ entries: ProvenanceEntry[] }>(
    `/projects/${projectId}/provenance`,
    { signal },
  )
  return data.entries
}

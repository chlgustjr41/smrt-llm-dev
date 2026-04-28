import { apiFetch } from './client'
import type { AgentEvent } from '../components/AgentTimeline'

export interface AgentRun {
  run_id: string
  status: 'pending' | 'running' | 'done' | 'error'
}

export function createRun(projectId: number): Promise<AgentRun> {
  return apiFetch<AgentRun>(`/projects/${projectId}/runs`, { method: 'POST' })
}

export async function getRunEvents(projectId: number, runId: string): Promise<AgentEvent[]> {
  const data = await apiFetch<{ events: AgentEvent[] }>(`/projects/${projectId}/runs/${runId}/events`)
  return data.events
}

export function postRunBudgetDecision(
  projectId: number,
  runId: string,
  decision: 'continue' | 'terminate',
): Promise<{ run_id: string; decision: string }> {
  return apiFetch(`/projects/${projectId}/runs/${runId}/budget-decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}

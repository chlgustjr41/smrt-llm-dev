import { apiFetch } from './client'

export interface AgentRun {
  run_id: string
  status: 'pending' | 'running' | 'done' | 'error'
}

export function createRun(projectId: number): Promise<AgentRun> {
  return apiFetch<AgentRun>(`/projects/${projectId}/runs`, { method: 'POST' })
}

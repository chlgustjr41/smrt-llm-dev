import { apiFetch } from './client'

export interface CoderStatus {
  idle: boolean
  session_id: string | null
  status: string | null
  ticket_id: string | null
  model: string | null
}

export async function getCoderStatus(projectId: number, signal?: AbortSignal): Promise<CoderStatus> {
  return apiFetch<CoderStatus>(`/projects/${projectId}/coder/status`, { signal })
}

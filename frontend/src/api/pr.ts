import { apiFetch } from './client'

export interface PendingPR {
  ticket_id: string
  session_id: string
  recheck_output: string
  fixed_at: string
}

export async function getPendingPRs(projectId: number): Promise<PendingPR[]> {
  return apiFetch<PendingPR[]>(`/projects/${projectId}/pr/pending`)
}

export async function acceptPR(projectId: number, ticketId: string): Promise<{ ticket_id: string; status: string }> {
  return apiFetch(`/projects/${projectId}/pr/${ticketId}/accept`, { method: 'POST' })
}

export async function rejectPR(projectId: number, ticketId: string): Promise<{ ticket_id: string; status: string }> {
  return apiFetch(`/projects/${projectId}/pr/${ticketId}/reject`, { method: 'POST' })
}

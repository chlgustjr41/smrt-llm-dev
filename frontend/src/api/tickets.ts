import { apiFetch } from './client'

export interface Ticket {
  id: string
  title: string
  content: string
}

export async function listTickets(projectId: number, signal?: AbortSignal): Promise<Ticket[]> {
  return apiFetch<Ticket[]>(`/projects/${projectId}/tickets`, { signal })
}

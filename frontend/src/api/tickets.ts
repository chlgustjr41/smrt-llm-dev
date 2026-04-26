import { apiFetch } from './client'

export type TicketStatus = 'pending_confirmation' | 'in_progress' | 'needs_review' | 'closed'

export interface Ticket {
  id: string
  title: string
  content: string
  status: TicketStatus
}

export async function listTickets(projectId: number, signal?: AbortSignal): Promise<Ticket[]> {
  return apiFetch<Ticket[]>(`/projects/${projectId}/tickets`, { signal })
}

export async function approveTicket(projectId: number, ticketId: string): Promise<void> {
  await apiFetch(`/projects/${projectId}/tickets/${ticketId}/approve`, { method: 'POST' })
}

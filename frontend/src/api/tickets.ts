import { apiFetch } from './client'

export type TicketStatus = 'pending_confirmation' | 'in_progress' | 'qa_review' | 'needs_review' | 'closed'

export interface TicketFailureReport {
  recommendation: 'needs_more_attempts' | 'possibly_not_a_bug'
  analysis: string
}

export interface Ticket {
  id: string
  title: string
  content: string
  status: TicketStatus
  session_id: string | null
  failure_report?: TicketFailureReport | null
}

export interface ApproveTicketResult {
  ticket_id: string
  session_id: string
  status: string
}

export interface TicketSession {
  session_id: string
  status: string
  fix_attempt: number
  started_at: string | null
  completed_at: string | null
}

export async function listTickets(projectId: number, signal?: AbortSignal): Promise<Ticket[]> {
  return apiFetch<Ticket[]>(`/projects/${projectId}/tickets`, { signal })
}

export async function approveTicket(projectId: number, ticketId: string): Promise<ApproveTicketResult> {
  return apiFetch<ApproveTicketResult>(`/projects/${projectId}/tickets/${ticketId}/approve`, { method: 'POST' })
}

export async function getTicketSessions(
  projectId: number,
  ticketId: string,
  signal?: AbortSignal,
): Promise<TicketSession[]> {
  return apiFetch<TicketSession[]>(`/projects/${projectId}/tickets/${ticketId}/sessions`, { signal })
}

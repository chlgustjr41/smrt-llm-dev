import { apiFetch } from './client'

export type TicketStatus = 'pending_confirmation' | 'in_progress' | 'qa_review' | 'needs_review' | 'closed'

export interface TicketFailureReport {
  recommendation: 'needs_more_attempts' | 'possibly_not_a_bug' | 'test_faulty'
  analysis: string
}

export interface Ticket {
  id: string
  title: string
  content: string
  status: TicketStatus
  session_id: string | null
  failure_report?: TicketFailureReport | null
  attempt_count: number
  failure_count: number
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

export interface FixSummaryChange {
  path: string
  tool: string
  reasoning: string
  kind: string  // 'edit' | 'patch' | 'write' | 'unknown'
  content: string
  ts?: string | null
}

export interface ProposedDocUpdate {
  /** README.md, .smrt/Project.md, or docs/<...>.md only. Other paths are
   *  rejected by the backend's accept-PR applier. */
  path: string
  /** Free-form rationale the Reviewer wrote — surfaced to the user so they
   *  understand WHY the file should change before accepting. */
  reason: string
  /** FULL replacement contents of the file. The backend writes verbatim on
   *  Accept; we never apply diffs. */
  new_content: string
}

export interface FixSummary {
  ticket_id: string
  session_id: string
  final_status: string
  pr_ready: boolean
  recommendation: string | null
  analysis: string | null
  qa_early_exit: string | null
  /** Legacy field — populated by sessions written before the Reviewer took
   *  over the final summary. Frontend falls back to this when
   *  reviewer_final_summary is null so old tickets still render their
   *  headline narrative. */
  qa_final_summary: string | null
  /** The Reviewer's compiled narrative — the headline of the persisted
   *  Fix Summary for new sessions. */
  reviewer_final_summary: string | null
  /** Doc-update proposals the Reviewer queued during its final pass.
   *  Applied to disk when the user accepts the ticket from Needs Review. */
  proposed_doc_updates: ProposedDocUpdate[]
  recheck_output: string | null
  changes: FixSummaryChange[]
  completed_at: string
}

export async function listTickets(projectId: number, signal?: AbortSignal): Promise<Ticket[]> {
  return apiFetch<Ticket[]>(`/projects/${projectId}/tickets`, { signal })
}

export async function approveTicket(projectId: number, ticketId: string): Promise<ApproveTicketResult> {
  return apiFetch<ApproveTicketResult>(`/projects/${projectId}/tickets/${ticketId}/approve`, { method: 'POST' })
}

export async function cancelTicket(projectId: number, ticketId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/projects/${projectId}/tickets/${ticketId}/cancel`, { method: 'POST' })
}

export async function closeTicket(projectId: number, ticketId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/projects/${projectId}/tickets/${ticketId}/close`, { method: 'POST' })
}

export async function requeueTicket(projectId: number, ticketId: string): Promise<ApproveTicketResult> {
  return apiFetch<ApproveTicketResult>(`/projects/${projectId}/tickets/${ticketId}/requeue`, { method: 'POST' })
}

export async function getTicketSessions(
  projectId: number,
  ticketId: string,
  signal?: AbortSignal,
): Promise<TicketSession[]> {
  return apiFetch<TicketSession[]>(`/projects/${projectId}/tickets/${ticketId}/sessions`, { signal })
}

export async function resetTicket(projectId: number, ticketId: string): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/projects/${projectId}/tickets/${ticketId}/reset`, { method: 'POST' })
}

/** Fetch the persisted fix summary for the most recent fix session of a
 *  ticket. Returns null when no summary has been recorded yet — the API uses
 *  `{summary: null}` rather than 404 so callers can branch without try/catch. */
export async function getFixSummary(
  projectId: number,
  ticketId: string,
  signal?: AbortSignal,
): Promise<FixSummary | null> {
  const resp = await apiFetch<{ summary: FixSummary | null }>(
    `/projects/${projectId}/tickets/${ticketId}/fix-summary`,
    { signal },
  )
  return resp.summary
}

import { apiFetch } from './client'
import type { AgentEvent } from '../components/AgentTimeline'

export interface QASessionCreated {
  session_id: string
  status: string
}

export interface QASessionLatest {
  session_id: string | null
  status: string | null
  started_at: string | null
  completed_at: string | null
}

export interface HITLDecision {
  decision: 'approve' | 'skip'
}

export function createQASession(projectId: number): Promise<QASessionCreated> {
  return apiFetch<QASessionCreated>(`/projects/${projectId}/qa-sessions`, { method: 'POST' })
}

export function getLatestQASession(projectId: number, signal?: AbortSignal): Promise<QASessionLatest> {
  return apiFetch<QASessionLatest>(`/projects/${projectId}/qa-sessions/latest`, { signal })
}

export function approveQASession(projectId: number, sessionId: string): Promise<HITLDecision> {
  return apiFetch<HITLDecision>(`/projects/${projectId}/qa-sessions/${sessionId}/approve`, {
    method: 'POST',
  })
}

export function skipQASession(projectId: number, sessionId: string): Promise<HITLDecision> {
  return apiFetch<HITLDecision>(`/projects/${projectId}/qa-sessions/${sessionId}/skip`, {
    method: 'POST',
  })
}

export function postSessionBudgetDecision(
  projectId: number,
  sessionId: string,
  decision: 'continue' | 'terminate',
): Promise<{ session_id: string; decision: string }> {
  return apiFetch(`/projects/${projectId}/qa-sessions/${sessionId}/budget-decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}

export async function getQASessionEvents(
  projectId: number,
  sessionId: string,
  signal?: AbortSignal,
): Promise<AgentEvent[]> {
  const data = await apiFetch<{ events: AgentEvent[] }>(
    `/projects/${projectId}/qa-sessions/${sessionId}/events`,
    { signal },
  )
  return data.events
}

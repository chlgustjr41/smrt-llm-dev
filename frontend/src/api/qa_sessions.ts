import { apiFetch } from './client'

export interface QASessionCreated {
  session_id: string
  status: string
}

export interface HITLDecision {
  decision: 'approve' | 'skip'
}

export function createQASession(projectId: number): Promise<QASessionCreated> {
  return apiFetch<QASessionCreated>(`/projects/${projectId}/qa-sessions`, { method: 'POST' })
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

import { apiFetch } from './client'

export interface Project {
  id: number
  name: string
  canonical_path: string
  created_at: string
}

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>('/projects')
}

export function registerProject(name: string, path: string): Promise<Project> {
  return apiFetch<Project>('/projects', {
    method: 'POST',
    body: JSON.stringify({ name, path }),
  })
}

export function getProject(id: number): Promise<Project> {
  return apiFetch<Project>(`/projects/${id}`)
}

export function deleteProject(id: number): Promise<void> {
  return apiFetch<void>(`/projects/${id}`, { method: 'DELETE' })
}

export interface AgentRunSummary {
  id: number
  run_id: string
  project_id: number
  status: string
  total_input_tokens: number
  total_output_tokens: number
  started_at: string | null
  completed_at: string | null
}

export function listRuns(projectId: number, signal?: AbortSignal): Promise<AgentRunSummary[]> {
  return apiFetch<AgentRunSummary[]>(`/projects/${projectId}/runs`, { signal })
}

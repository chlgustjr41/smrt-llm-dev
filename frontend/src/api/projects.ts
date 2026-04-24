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

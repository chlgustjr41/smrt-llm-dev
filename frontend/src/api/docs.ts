import { apiFetch } from './client'

export interface DocFile {
  backend: 'github' | 'obsidian'
  path: string
}

export async function listDocs(projectId: number, signal?: AbortSignal): Promise<DocFile[]> {
  const data = await apiFetch<{ files: DocFile[] }>(`/projects/${projectId}/docs`, { signal })
  return data.files
}

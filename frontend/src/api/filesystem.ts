import { apiFetch } from './client'

export interface FsEntry {
  name: string
  path: string
  is_dir: boolean
}

export function listDirectory(path: string = '/workspace'): Promise<FsEntry[]> {
  return apiFetch<FsEntry[]>(`/filesystem?path=${encodeURIComponent(path)}`)
}

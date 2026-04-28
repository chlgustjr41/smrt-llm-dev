import { apiFetch } from './client'

export interface ProjectConfig {
  reviewer_model: string
  qa_model: string
  coder_model: string
  max_fix_attempts: number
  max_questions_per_attempt: number
  scheduler_cadence: string
  thought_process_mode: boolean
  use_local_llm: boolean
}

export function getConfig(projectId: number): Promise<ProjectConfig> {
  return apiFetch<ProjectConfig>(`/projects/${projectId}/config`)
}

export function patchConfig(
  projectId: number,
  config: Partial<ProjectConfig>,
): Promise<ProjectConfig> {
  return apiFetch<ProjectConfig>(`/projects/${projectId}/config`, {
    method: 'PATCH',
    body: JSON.stringify(config),
  })
}

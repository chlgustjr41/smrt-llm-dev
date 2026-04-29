import { apiFetch } from './client'
import type { AgentEvent } from '../components/AgentTimeline'

export interface AgentRun {
  run_id: string
  status: 'pending' | 'running' | 'done' | 'error'
}

export interface CreateRunOptions {
  /** When true (the default), the Reviewer agent also writes README.md
   *  (if missing/sparse) and technical docs into `docs/`. When false, the
   *  Reviewer only writes `.smrt/Project.md` and the post-run Obsidian
   *  doc generator is skipped — useful for an inspection-only pass that
   *  doesn't touch the user's repo files. */
  generateDocs?: boolean
}

export function createRun(
  projectId: number,
  options: CreateRunOptions = {},
): Promise<AgentRun> {
  const generateDocs = options.generateDocs ?? true
  return apiFetch<AgentRun>(`/projects/${projectId}/runs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ generate_docs: generateDocs }),
  })
}

export async function getRunEvents(projectId: number, runId: string): Promise<AgentEvent[]> {
  const data = await apiFetch<{ events: AgentEvent[] }>(`/projects/${projectId}/runs/${runId}/events`)
  return data.events
}

export function postRunBudgetDecision(
  projectId: number,
  runId: string,
  decision: 'continue' | 'terminate',
): Promise<{ run_id: string; decision: string }> {
  return apiFetch(`/projects/${projectId}/runs/${runId}/budget-decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decision }),
  })
}

/** Cancel a running Init Audit. Idempotent — returns the cancelled state
 *  even if the run already finished naturally. The backend emits a
 *  `cancelled` SSE event and updates the AgentRun row's status. */
export function cancelRun(
  projectId: number,
  runId: string,
): Promise<{ run_id: string; cancelled: boolean; status: string }> {
  return apiFetch(`/projects/${projectId}/runs/${runId}/cancel`, {
    method: 'POST',
  })
}

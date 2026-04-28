import { apiFetch } from './client'

export interface LlmProvider {
  provider: 'anthropic' | 'local'
  base_url?: string
  model?: string
}

export async function getLlmProvider(): Promise<LlmProvider> {
  return apiFetch<LlmProvider>('/llm-provider')
}

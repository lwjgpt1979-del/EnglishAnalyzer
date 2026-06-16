import { request } from '@/utils/request'

export interface MyFeedback {
  id: string; kind: string; content: string; images: string[]
  status: string; note: string | null; created_at: string | null
}
export function submitFeedback(body: { kind: string; content: string; images?: string[]; contact?: string }): Promise<{ id: string; status: string }> {
  return request('/api/v1/feedback/suggestions', { method: 'POST', data: body })
}
export function myFeedback(): Promise<{ total: number; items: MyFeedback[] }> {
  return request('/api/v1/feedback/suggestions', { method: 'GET' })
}

import { request } from '@/utils/request'
import type { EssayDetail, EssayList } from '@/types/api'

export function createEssay(payload: { original_text: string; title?: string; essay_type?: string }): Promise<EssayDetail> {
  return request<EssayDetail>('/api/v1/essays', { method: 'POST', data: payload })
}
export function getEssays(): Promise<EssayList> {
  return request<EssayList>('/api/v1/essays', { method: 'GET' })
}
export function getEssay(id: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}`, { method: 'GET' })
}

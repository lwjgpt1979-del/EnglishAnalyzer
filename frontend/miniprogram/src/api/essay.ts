import { request } from '@/utils/request'
import type { EssayDetail, EssayList, EssayTemplates } from '@/types/api'

export function createEssay(payload: { original_text: string; title?: string; essay_type?: string }): Promise<EssayDetail> {
  return request<EssayDetail>('/api/v1/essays', { method: 'POST', data: payload })
}
export function getEssays(): Promise<EssayList> {
  return request<EssayList>('/api/v1/essays', { method: 'GET' })
}
export function getEssay(id: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}`, { method: 'GET' })
}
export function repolishEssay(id: string, revisedText: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}/repolish`, { method: 'POST', data: { revised_text: revisedText } })
}
export function getEssayTemplates(essayType?: string): Promise<EssayTemplates> {
  const data: Record<string, string> = {}
  if (essayType) data.essay_type = essayType
  return request<EssayTemplates>('/api/v1/essays/templates', { method: 'GET', data })
}

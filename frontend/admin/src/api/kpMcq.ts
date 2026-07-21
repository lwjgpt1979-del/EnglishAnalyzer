import request, { unwrap } from './request'

export interface KpMcqItem {
  id: string
  word_id: string
  word: string
  dimension: string
  dimension_label: string
  stem: string
  options: string[]
  answer: string
  explanation: string
  report_count: number
  created_at: string | null
}
export interface KpMcqList { items: KpMcqItem[]; total: number; threshold: number }
export interface KpMcqSnapshot { stem: string; options: string[]; answer: string; explanation: string; report_count?: number }
export interface KpMcqRevision {
  id: string
  before: KpMcqSnapshot | null
  after: KpMcqSnapshot | null
  trigger: 'auto' | 'manual'
  by_admin_id: string | null
  reason: string
  created_at: string | null
}

export function listKpMcqs(params: { min_report?: number; skip?: number; limit?: number }): Promise<KpMcqList> {
  return unwrap<KpMcqList>(request.get('/admin/kp-mcqs', { params }))
}
export function fixKpMcq(id: string): Promise<KpMcqItem> {
  return unwrap<KpMcqItem>(request.post(`/admin/kp-mcqs/${id}/fix`))
}
export function editKpMcq(id: string, body: { stem: string; options: string[]; answer: string; explanation: string }): Promise<KpMcqItem> {
  return unwrap<KpMcqItem>(request.put(`/admin/kp-mcqs/${id}`, body))
}
export function deleteKpMcq(id: string): Promise<{ ok: boolean }> {
  return unwrap<{ ok: boolean }>(request.delete(`/admin/kp-mcqs/${id}`))
}
export function batchDeleteKpMcq(ids: string[]): Promise<{ deleted: number }> {
  return unwrap<{ deleted: number }>(request.post('/admin/kp-mcqs/batch-delete', { ids }))
}
export function kpMcqRevisions(id: string): Promise<KpMcqRevision[]> {
  return unwrap<KpMcqRevision[]>(request.get(`/admin/kp-mcqs/${id}/revisions`))
}
export function getKpMcqThreshold(): Promise<{ threshold: number }> {
  return unwrap<{ threshold: number }>(request.get('/admin/kp-mcqs/threshold/value'))
}
export function setKpMcqThreshold(threshold: number): Promise<{ threshold: number }> {
  return unwrap<{ threshold: number }>(request.put('/admin/kp-mcqs/threshold/value', { threshold }))
}

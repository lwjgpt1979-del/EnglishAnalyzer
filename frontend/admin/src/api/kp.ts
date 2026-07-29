import request, { unwrap } from './request'

/** 考点后台复核:有凭证举报 / 下架·恢复 / AI 修正 / 编辑删除 */
export interface KpEvidence {
  count?: number
  latest_reason?: string
  latest_reason_label?: string
  latest_detail?: string
  latest_suggested?: string
}
export interface KpRelationItem {
  id: string
  word_id: string
  word: string
  sense_id: string | null
  gloss: string
  dim: string
  dim_label: string
  text: string
  zh: string
  note: string
  source?: string
  report_count: number
  hidden?: boolean
  hidden_at?: string | null
  hide_note?: string
  hide_origin?: 'ai_prehide' | 'manual' | ''
  evidence?: KpEvidence
  created_at: string | null
}
export interface KpRelationList { items: KpRelationItem[]; total: number; threshold: number }
export interface KpRelationReportItem {
  id: string
  reason: string
  reason_label: string
  detail: string
  suggested: string
  student_id: string
  created_at: string | null
}
export interface KpReviewRecord {
  id: string
  before: Array<{ id: string; dim: string; text: string; zh: string | null; note: string | null; report_count?: number }> | null
  after: { deleted: string[]; fixed: string[]; trigger?: string } | null
  created_at: string | null
}

export function listReportedKp(params: {
  min_report?: number; skip?: number; limit?: number
  hidden?: 'exclude' | 'only' | 'all'
  hide_origin?: 'ai_prehide' | 'manual' | ''
}): Promise<KpRelationList> {
  return unwrap<KpRelationList>(request.get('/admin/kp-relations', { params }))
}
export function listKpRelationReports(relationId: string): Promise<KpRelationReportItem[]> {
  return unwrap<KpRelationReportItem[]>(request.get(`/admin/kp-relations/${relationId}/reports`))
}
export function hideKpRelation(id: string, note = ''): Promise<KpRelationItem> {
  return unwrap<KpRelationItem>(request.post(`/admin/kp-relations/${id}/hide`, { note }))
}
export function unhideKpRelation(id: string): Promise<KpRelationItem> {
  return unwrap<KpRelationItem>(request.post(`/admin/kp-relations/${id}/unhide`))
}
export function batchHideKpRelation(ids: string[], note = ''): Promise<{ hidden: number }> {
  return unwrap<{ hidden: number }>(request.post('/admin/kp-relations/batch-hide', { ids, note }))
}
export function fixReportedKp(wordId: string): Promise<{ fixed: boolean; deleted?: number; fixed_n?: number; no_reported?: boolean }> {
  return unwrap(request.post(`/admin/kp-relations/${wordId}/fix`))
}
export function editKpRelation(id: string, body: { text: string; zh: string; note: string }): Promise<KpRelationItem> {
  return unwrap<KpRelationItem>(request.put(`/admin/kp-relations/${id}`, body))
}
export function deleteKpRelation(id: string): Promise<{ ok: boolean }> {
  return unwrap<{ ok: boolean }>(request.delete(`/admin/kp-relations/${id}`))
}
export function batchDeleteKpRelation(ids: string[]): Promise<{ deleted: number }> {
  return unwrap<{ deleted: number }>(request.post('/admin/kp-relations/batch-delete', { ids }))
}
export function kpReviewRecords(wordId: string): Promise<KpReviewRecord[]> {
  return unwrap<KpReviewRecord[]>(request.get(`/admin/kp-relations/${wordId}/reviews`))
}
export function getKpThreshold(): Promise<{ threshold: number }> {
  return unwrap<{ threshold: number }>(request.get('/admin/kp-relations/threshold/value'))
}
export function setKpThreshold(threshold: number): Promise<{ threshold: number }> {
  return unwrap<{ threshold: number }>(request.put('/admin/kp-relations/threshold/value', { threshold }))
}

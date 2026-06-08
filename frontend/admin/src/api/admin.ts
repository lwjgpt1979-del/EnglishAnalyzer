import request, { unwrap } from './request'
import type {
  AdminQuestionListOut,
  AdminQuestionItem,
  AdminContentListOut,
  AdminContentItem,
  AdminOverview,
  SemesterPricing,
  ReviewStatus,
  AdminCurriculumUnit,
  AdminVocabMediaItem,
  AdminVocabMediaListOut,
  AdminTeacherItem,
  AdminTeacherListOut,
} from '../types'

// ── 数据大盘 ────────────────────────────────────────────────
export function getOverview() {
  return unwrap<AdminOverview>(request.get('/admin/overview'))
}

// ── 仿真题审核 ──────────────────────────────────────────────
export function listQuestions(params: {
  status: ReviewStatus
  kp_id?: string
  skip?: number
  limit?: number
}) {
  return unwrap<AdminQuestionListOut>(
    request.get('/admin/questions', { params }),
  )
}

export function reviewQuestion(id: string, approve: boolean) {
  return unwrap<AdminQuestionItem>(
    request.post(`/admin/questions/${id}/review`, { approve }),
  )
}

// ── 知识点内容审核/编辑 ─────────────────────────────────────
export function listContents(params: {
  status: ReviewStatus
  kp_id?: string
  skip?: number
  limit?: number
}) {
  return unwrap<AdminContentListOut>(
    request.get('/admin/contents', { params }),
  )
}

export function reviewContent(id: string, approve: boolean) {
  return unwrap<AdminContentItem>(
    request.post(`/admin/contents/${id}/review`, { approve }),
  )
}

export function updateContent(id: string, body: { content_md?: string; audio_url?: string }) {
  return unwrap<AdminContentItem>(
    request.put(`/admin/contents/${id}`, body),
  )
}

// ── 定价 ────────────────────────────────────────────────────
export function getPricing() {
  return unwrap<SemesterPricing>(request.get('/admin/pricing'))
}

export function updatePricing(body: SemesterPricing) {
  return unwrap<SemesterPricing>(request.put('/admin/pricing', body))
}

export function getEssayTemplates() {
  return unwrap<Record<string, { template: string; samples: string[] }>>(request.get('/admin/essay-templates'))
}

export function updateEssayTemplates(payload: Record<string, { template: string; samples: string[] }>) {
  return unwrap<Record<string, { template: string; samples: string[] }>>(request.put('/admin/essay-templates', payload))
}

// ── 机构入驻审核（D-123）──
export interface AdminInstitution {
  id: string; name: string; contact_phone: string
  province_code: string; city_code: string; address: string
  status: string; created_at: string
}

export function createInstitution(data: {
  name: string; contact_phone: string; province_code: string; city_code: string; address: string
}): Promise<AdminInstitution> {
  return unwrap<AdminInstitution>(request.post('/admin/institutions', data))
}
export function listInstitutions(status?: string): Promise<AdminInstitution[]> {
  const q = status ? `?status=${status}` : ''
  return unwrap<AdminInstitution[]>(request.get(`/admin/institutions${q}`))
}
export function approveInstitution(id: string, adminUsername: string): Promise<{ institution_id: string; admin_username: string; password: string }> {
  return unwrap(request.post(`/admin/institutions/${id}/approve`, { admin_username: adminUsername }))
}
export function rejectInstitution(id: string): Promise<AdminInstitution> {
  return unwrap<AdminInstitution>(request.post(`/admin/institutions/${id}/reject`))
}

// ── 教师认证管理 ──────────────────────────────────────────────────────────────
export function listTeachersForAdmin(params: {
  cert_status?: string
  skip?: number
  limit?: number
}): Promise<AdminTeacherListOut> {
  return unwrap<AdminTeacherListOut>(request.get('/admin/teachers', { params }))
}

export function reviewTeacherCert(
  teacherId: string,
  approve: boolean,
  reason?: string,
): Promise<AdminTeacherItem> {
  return unwrap<AdminTeacherItem>(
    request.post(`/admin/teachers/${teacherId}/review`, { approve, reason }),
  )
}

// ── 词力通媒体管理 ────────────────────────────────────────────────────────────
export function listVocabMedia(params: {
  media_status?: string
  skip?: number
  limit?: number
}): Promise<AdminVocabMediaListOut> {
  return unwrap<AdminVocabMediaListOut>(request.get('/admin/vocab', { params }))
}

export function generateVocabMedia(wordId: string): Promise<AdminVocabMediaItem> {
  return unwrap<AdminVocabMediaItem>(request.post(`/admin/vocab/${wordId}/generate-media`))
}

export function reviewVocabMedia(wordId: string, approve: boolean): Promise<AdminVocabMediaItem> {
  return unwrap<AdminVocabMediaItem>(request.post(`/admin/vocab/${wordId}/media/review`, { approve }))
}

export function updateVocabMedia(
  wordId: string,
  body: { en_description?: string; image_urls?: string[]; word_audio_url?: string; en_desc_audio_url?: string },
): Promise<AdminVocabMediaItem> {
  return unwrap<AdminVocabMediaItem>(request.put(`/admin/vocab/${wordId}/media`, body))
}

// ── 课程单元管理 ──────────────────────────────────────────────────────────────
export function listCurriculumUnits(): Promise<AdminCurriculumUnit[]> {
  return unwrap<AdminCurriculumUnit[]>(request.get('/admin/curriculum/units'))
}

export interface GenerateUnitResult {
  unit_id: string
  kp_count: number
  content_count: number
  content_rate: number
}

export function generateUnitContent(unitId: string): Promise<GenerateUnitResult> {
  return unwrap<GenerateUnitResult>(
    request.post(`/admin/curriculum/units/${unitId}/generate`)
  )
}

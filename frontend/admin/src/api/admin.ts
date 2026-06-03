import request, { unwrap } from './request'
import type {
  AdminQuestionListOut,
  AdminQuestionItem,
  AdminContentListOut,
  AdminContentItem,
  AdminOverview,
  SemesterPricing,
  ReviewStatus,
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

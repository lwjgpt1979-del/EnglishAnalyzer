import { request } from '@/utils/request'
import type {
  AiAnalysisOut,
  ConfirmOcrTextRequest,
  OcrStatusOut,
  WrongQuestionCreate,
  WrongQuestionListOut,
  WrongQuestionOut,
} from '@/types/api'

export function createWrongQuestion(data: WrongQuestionCreate): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>('/api/v1/wrong-questions/', {
    method: 'POST',
    data,
  })
}

export function listWrongQuestions(skip = 0, limit = 20, source = '', tag = ''): Promise<WrongQuestionListOut> {
  const params = new URLSearchParams({ skip: String(skip), limit: String(limit) })
  if (source) params.set('source', source)
  if (tag) params.set('tag', tag)
  return request<WrongQuestionListOut>(`/api/v1/wrong-questions/?${params.toString()}`)
}

/** M38 批量补标：将有 AI 分析但缺 tags 的错题自动打知识点标签 */
export function autoTagWrongQuestions(): Promise<{ processed: number }> {
  return request<{ processed: number }>('/api/v1/wrong-questions/auto-tag', { method: 'POST' })
}

/** M3 关联视图：按知识点查当前学生的相关错题（D-093） */
export function listWrongQuestionsByKp(
  kpId: string,
  skip = 0,
  limit = 20,
): Promise<WrongQuestionListOut> {
  return request<WrongQuestionListOut>(
    `/api/v1/wrong-questions/by-kp/${kpId}?skip=${skip}&limit=${limit}`,
  )
}

export function getWrongQuestion(id: string): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}`)
}

export function markMastered(id: string, isMastered: boolean): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/mastered`, {
    method: 'PATCH',
    data: { is_mastered: isMastered },
  })
}

export function analyzeWrongQuestion(id: string): Promise<AiAnalysisOut> {
  return request<AiAnalysisOut>(`/api/v1/wrong-questions/${id}/analyze`, {
    method: 'POST',
  })
}

export function listAnalyses(id: string): Promise<AiAnalysisOut[]> {
  return request<AiAnalysisOut[]>(`/api/v1/wrong-questions/${id}/analyses`)
}

/** 触发 OCR 识别 */
export function triggerOcr(id: string): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/ocr`, {
    method: 'POST',
  })
}

/** 查询 OCR 任务状态 */
export function getOcrStatus(id: string): Promise<OcrStatusOut> {
  return request<OcrStatusOut>(`/api/v1/wrong-questions/${id}/ocr`)
}

/** 手动确认/覆盖 OCR 识别结果 */
export function confirmOcrText(
  id: string,
  data: ConfirmOcrTextRequest,
): Promise<WrongQuestionOut> {
  return request<WrongQuestionOut>(`/api/v1/wrong-questions/${id}/text`, {
    method: 'PATCH',
    data,
  })
}

export interface PaperWrongItem {
  id: string
  stem: string | null
  question_type: string | null
  is_mastered: boolean
  source_label: string
}

export interface PaperWrongListOut {
  items: PaperWrongItem[]
  total: number
}

export function listPaperWrongs(skip = 0, limit = 20): Promise<PaperWrongListOut> {
  return request<PaperWrongListOut>(`/api/v1/user-papers/wrongs?skip=${skip}&limit=${limit}`, {
    method: 'GET',
  })
}

// ── M36: SM-2 复习计划 ────────────────────────────────────────────────────────

export interface ReviewStats {
  total_unmastered: number
  due_today: number
  new_unscheduled: number
}

export interface WrongQuestionReviewItem {
  id: string
  question_text: string | null
  student_answer: string | null
  correct_answer: string | null
  question_type: string | null
  review_count: number
  easiness_factor: number
  review_interval_days: number
  next_review_at: string | null
  last_review_at: string | null
  is_mastered: boolean
}

export interface ReviewQueueOut {
  due_items: WrongQuestionReviewItem[]
  stats: ReviewStats
}

export function getReviewQueue(): Promise<ReviewQueueOut> {
  return request<ReviewQueueOut>('/api/v1/wrong-questions/review-queue', { method: 'GET' })
}

export function submitReview(wqId: string, quality: number): Promise<WrongQuestionReviewItem> {
  return request<WrongQuestionReviewItem>(`/api/v1/wrong-questions/${wqId}/review`, {
    method: 'POST',
    data: { quality },
  })
}

/** 内容质量反馈（§5.5）：诊断/题目有误上报 */
export function reportContentFeedback(data: {
  target_type: 'diagnosis' | 'question'; target_id?: string; snippet?: string; reason?: string
}): Promise<{ id: string; status: string }> {
  return request('/api/v1/users/feedback', { method: 'POST', data })
}

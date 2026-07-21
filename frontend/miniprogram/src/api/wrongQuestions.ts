import { request } from '@/utils/request'
import type { WrongQuestionListOut, WrongQuestionOut } from '@/types/api'

/** 关联视图：按知识点查当前学生的相关错题（读 wrong_record） */
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

// ── SM-2 复习计划(wrong_record) ───────────────────────────────────────────────

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
  options: string[] | null
  explanation: string | null
  source: 'platform' | 'uploaded' | null
  review_count: number
  easiness_factor: number
  review_interval_days: number
  next_review_at: string | null
  last_review_at: string | null
  is_mastered: boolean
  source_label?: string | null
  source_route?: string | null
  error_type?: string | null
}
// 复习标注错因类型(记混/粗心/不会)→ 落库供错因画像
export function setErrorType(wqId: string, errorType: 'confused' | 'careless' | 'unknown'): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/v1/wrong-questions/${wqId}/error-type`, { method: 'POST', data: { error_type: errorType } })
}

export interface ReviewQueueOut {
  due_items: WrongQuestionReviewItem[]
  stats: ReviewStats
}

/** 错题重做/复习客观判分结果 */
export interface RedoResult {
  is_correct: boolean
  correct_answer: string | null
  explanation: string | null
  mastered: boolean
  next_review_at: string | null
  review_count: number
}

export function getReviewQueue(): Promise<ReviewQueueOut> {
  return request<ReviewQueueOut>('/api/v1/wrong-questions/review-queue', { method: 'GET' })
}

/** 统一错题中心:一份错题(wrong_record),按语法/词汇筛选。kind: ''|grammar|vocab */
export interface WrongCenterItem {
  id: string
  question_id: string
  q_scope: string
  node_id: string | null
  stem: string | null
  student_answer: string | null
  correct_answer: string | null
  explanation: string | null
  question_type: string | null
  kp_kind: 'grammar' | 'vocab' | null
  kp_name: string | null
  source_label: string
  source_id: string | null
  source_route: string | null
  is_mastered: boolean
  lifecycle: 'pending' | 'reviewing' | 'mastered'
  review_count: number
  practice_count: number
  practice_correct: number
  next_review_at: string | null
  created_at: string | null
}
export function listWrongCenter(kind = '', status = '', skip = 0, limit = 20): Promise<{ items: WrongCenterItem[]; total: number }> {
  // 小程序运行时无 URLSearchParams,手拼 query
  let qs = `skip=${skip}&limit=${limit}`
  if (kind) qs += `&kind=${encodeURIComponent(kind)}`
  if (status) qs += `&status=${encodeURIComponent(status)}`
  return request(`/api/v1/wrong-center/list?${qs}`)
}

/** 状态 chip 计数(全部/待巩固/巩固中/已掌握),随 kind 变 */
export interface WrongCenterCounts { all: number; pending: number; reviewing: number; mastered: number }
export function getWrongCenterCounts(kind = ''): Promise<WrongCenterCounts> {
  return request(`/api/v1/wrong-center/counts${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`)
}

/** 错题「练同类仿真题」(统一入口,按 wrong_record 派发)。questions 含 answer/explanation 供即时判分 */
export interface PracticeQuestion { id: string; stem: string; options: string[] | null; answer: string | null; explanation: string | null }
export function practiceWrongCenter(wrongRecordId: string): Promise<{ knowledge_point: string; questions: PracticeQuestion[] }> {
  return request(`/api/v1/wrong-center/practice/${wrongRecordId}`, { method: 'POST' })
}

/** 练同类一轮做完回写成绩(记 practice + 语法推进 SM-2) */
export interface PracticeResult { lifecycle: string; is_mastered: boolean; just_mastered: boolean; practice_count: number; practice_correct: number; review_count: number; next_review_at: string | null }
export function recordPracticeResult(wrongRecordId: string, total: number, correct: number, advanceReview = false): Promise<PracticeResult> {
  return request(`/api/v1/wrong-center/practice-result/${wrongRecordId}`, { method: 'POST', data: { total, correct, advance_review: advanceReview } })
}

/** 词汇错题「学这个词」:富词卡 + 仿真练习 5 题(纯选择,全局缓存)。5 题全对 → 判掌握。 */
export interface VocabSimCard {
  id: string; word: string; phonetic: string | null; def_zh: string
  example: string | null; example_zh: string | null
  phrase: { en: string; zh: string | null } | null
  audio_url: string | null; image_urls: string[] | null
}
export interface VocabSimPayload {
  wrong_record_id: string
  card: VocabSimCard
  questions: PracticeQuestion[]
  mastered: boolean
}
export function getVocabSim(wrongRecordId: string): Promise<VocabSimPayload> {
  return request(`/api/v1/wrong-center/vocab-sim/${wrongRecordId}`, { method: 'GET' })
}
export interface VocabSimResult { mastered: boolean; wrong_mastered: boolean; lifecycle: string }
export function submitVocabSimResult(wrongRecordId: string, total: number, correct: number): Promise<VocabSimResult> {
  return request(`/api/v1/wrong-center/vocab-sim-result/${wrongRecordId}`, { method: 'POST', data: { total, correct } })
}

// 错题关系网(以词为中心):某词的全局考点(dims,含关系词)+ 主错题(考它)/次错题(它当干扰)
export interface WordNetKpItem { text: string; zh: string; note: string; word_id: string | null }
export interface WordNetDim { key: string; label: string; relational: boolean; items: WordNetKpItem[] }
export interface WordNetErr {
  wrong_record_id: string; stem: string; student_answer: string
  correct_answer: string; source: string; question_type: string
}
export interface WordNet {
  word_id: string | null; word: string; zh: string; is_phrase: boolean
  sense_id: string | null; gloss: string
  senses: Array<{ sense_id: string | null; gloss: string; pos: string }>
  answers?: Array<{ word_id: string; word: string; zh: string; kind: 'correct' | 'wrong' | 'other'; switchable?: boolean }>   // 各选项值:蓝正确/红错选/灰其他;switchable=有错题记录才可切
  dims: WordNetDim[]; main: WordNetErr[]; secondary: WordNetErr[]
}
export function getWordNetOfRecord(wrongRecordId: string): Promise<WordNet> {
  return request(`/api/v1/wrong-center/${wrongRecordId}/word-net`, { method: 'GET' })
}
export function getWordNet(wordId: string): Promise<WordNet> {
  return request(`/api/v1/wrong-center/word-net/${wordId}`, { method: 'GET' })
}

/** 复习队列：客观重做那道错题（答对推进 SM-2，答错归零重排） */
export function submitReview(wqId: string, userAnswer: string): Promise<RedoResult> {
  return request<RedoResult>(`/api/v1/wrong-questions/${wqId}/review`, {
    method: 'POST',
    data: { user_answer: userAnswer },
  })
}

/** 错题详情：主动重做订正（答对→立即掌握；答错→今日重排复习） */
export function redoWrong(wqId: string, userAnswer: string): Promise<RedoResult> {
  return request<RedoResult>(`/api/v1/wrong-questions/${wqId}/redo`, {
    method: 'POST',
    data: { user_answer: userAnswer },
  })
}

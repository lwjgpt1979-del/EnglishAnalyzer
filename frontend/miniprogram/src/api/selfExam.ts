import { request } from '@/utils/request'
import type { ExamResultOut } from '@/types/api'

export interface SelfExamQuota {
  is_promax: boolean
  used: number
  limit: number
  remaining: number
}

export interface SelfExamQuestion {
  id: string
  question_type: string
  stem: string
  options?: string[] | null
  difficulty?: number | null
}

export interface SelfExamOut {
  id: string
  status: string
  time_limit_sec: number
  weak_kps: string[]
  questions: SelfExamQuestion[]
  total?: number | null
  correct_count?: number | null
  accuracy?: number | null
  created_at: string
}

export interface SelfExamBrief {
  id: string
  status: string
  total?: number | null
  correct_count?: number | null
  accuracy?: number | null
  created_at: string
}

export function getSelfExamQuota(): Promise<SelfExamQuota> {
  return request<SelfExamQuota>('/api/v1/self-exam/quota', { method: 'GET' })
}

export function generateSelfExam(): Promise<SelfExamOut> {
  return request<SelfExamOut>('/api/v1/self-exam/generate', { method: 'POST' })
}

export function getSelfExam(id: string): Promise<SelfExamOut> {
  return request<SelfExamOut>(`/api/v1/self-exam/${id}`, { method: 'GET' })
}

export function submitSelfExam(
  id: string, answers: { question_id: string; user_answer: string }[],
): Promise<{ result: ExamResultOut; exam: SelfExamBrief }> {
  return request(`/api/v1/self-exam/${id}/submit`, { method: 'POST', data: { answers } })
}

export function getSelfExamHistory(): Promise<SelfExamBrief[]> {
  return request<SelfExamBrief[]>('/api/v1/self-exam/history', { method: 'GET' })
}

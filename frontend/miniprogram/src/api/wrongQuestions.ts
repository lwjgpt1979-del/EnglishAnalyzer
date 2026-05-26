import { request } from '@/utils/request'
import type {
  AiAnalysisOut,
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

export function listWrongQuestions(skip = 0, limit = 20): Promise<WrongQuestionListOut> {
  return request<WrongQuestionListOut>(
    `/api/v1/wrong-questions/?skip=${skip}&limit=${limit}`,
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

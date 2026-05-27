import { request } from '@/utils/request'
import type {
  PracticeQuestionOut,
  SubmitAnswerResult,
  PracticeHistoryOut,
  PracticeStatsOut,
} from '@/types/api'

export function generateQuestions(
  knowledgePoint: string | null,
  count = 5,
  difficulty = 3,
): Promise<PracticeQuestionOut[]> {
  return request<PracticeQuestionOut[]>('/api/v1/practice/generate', {
    method: 'POST',
    data: { knowledge_point: knowledgePoint, count, difficulty },
  })
}

export function submitAnswer(
  questionId: string,
  answer: string,
  timeSpentSec?: number,
): Promise<SubmitAnswerResult> {
  return request<SubmitAnswerResult>('/api/v1/practice/submit', {
    method: 'POST',
    data: { question_id: questionId, answer, time_spent_sec: timeSpentSec ?? null },
  })
}

export function getPracticeHistory(skip = 0, limit = 20): Promise<PracticeHistoryOut> {
  return request<PracticeHistoryOut>(`/api/v1/practice/history?skip=${skip}&limit=${limit}`)
}

export function getPracticeStats(): Promise<PracticeStatsOut> {
  return request<PracticeStatsOut>('/api/v1/practice/stats')
}

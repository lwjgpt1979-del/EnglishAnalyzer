import { request } from '@/utils/request'
import type {
  SimQuestionOut,
  PracticeAttemptIn,
  PracticeResultOut,
  ExamAttemptIn,
  ExamResultOut,
  KPAccuracyOut,
  ExamHistoryOut,
  ExamRankOut,
} from '@/types/api'

export function listPracticeQuestions(kpId: string, limit = 5): Promise<SimQuestionOut[]> {
  return request<SimQuestionOut[]>(
    `/api/v1/questions/kp/${kpId}/practice-questions`,
    { method: 'GET', data: { limit } },
  )
}

export function submitAttempt(body: PracticeAttemptIn): Promise<PracticeResultOut> {
  return request<PracticeResultOut>('/api/v1/questions/practice-attempts', {
    method: 'POST',
    data: body,
  })
}

export function submitExam(body: ExamAttemptIn): Promise<ExamResultOut> {
  return request<ExamResultOut>('/api/v1/questions/exam-attempts', {
    method: 'POST',
    data: body,
  })
}

export function getKpAccuracy(): Promise<KPAccuracyOut> {
  return request<KPAccuracyOut>('/api/v1/questions/kp-accuracy')
}

export function getExamHistory(limit = 20): Promise<ExamHistoryOut> {
  return request<ExamHistoryOut>('/api/v1/questions/exam-history', {
    method: 'GET',
    data: { limit },
  })
}

export function getExamRank(): Promise<ExamRankOut> {
  return request<ExamRankOut>('/api/v1/questions/exam-rank')
}

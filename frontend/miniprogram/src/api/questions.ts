import { request } from '@/utils/request'
import type { SimQuestionOut, PracticeAttemptIn, PracticeResultOut } from '@/types/api'

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

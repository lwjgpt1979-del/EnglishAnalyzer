import { request } from '@/utils/request'
import type { VocabDailyTask, VocabAnswerResult } from '@/types/api'

export function getDailyTask(): Promise<VocabDailyTask> {
  return request<VocabDailyTask>('/api/v1/vocabulary/daily-task', { method: 'GET' })
}

export function submitVocabAnswer(
  wordId: string,
  correct: boolean,
  hesitant = false,
): Promise<VocabAnswerResult> {
  return request<VocabAnswerResult>('/api/v1/vocabulary/answer', {
    method: 'POST',
    data: { word_id: wordId, correct, hesitant },
  })
}

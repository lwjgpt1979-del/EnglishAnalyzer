import { request } from '@/utils/request'
import type {
  VocabDailyTask,
  VocabAnswerResult,
  VocabWrongList,
  VocabCheckinResult,
} from '@/types/api'

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

export function getWrongWords(): Promise<VocabWrongList> {
  return request<VocabWrongList>('/api/v1/vocabulary/wrong-words', { method: 'GET' })
}

export function checkin(newWordsCount: number, reviewDone: boolean): Promise<VocabCheckinResult> {
  return request<VocabCheckinResult>('/api/v1/vocabulary/checkin', {
    method: 'POST',
    data: { new_words_count: newWordsCount, review_done: reviewDone },
  })
}

import { request } from '@/utils/request'
import type {
  VocabDailyTask,
  VocabAnswerResult,
  VocabWrongList,
  VocabCheckinResult,
  VocabStudentCalendar,
  VocabMakeUpResult,
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

export function checkin(): Promise<VocabCheckinResult> {
  return request<VocabCheckinResult>('/api/v1/vocabulary/checkin', { method: 'POST' })
}

export function getCheckinCalendar(year?: number, month?: number): Promise<VocabStudentCalendar> {
  const data: Record<string, number> = {}
  if (year) data.year = year
  if (month) data.month = month
  return request<VocabStudentCalendar>('/api/v1/vocabulary/checkin/calendar', { method: 'GET', data })
}

export function makeUpCheckin(date: string): Promise<VocabMakeUpResult> {
  return request<VocabMakeUpResult>('/api/v1/vocabulary/checkin/make-up', {
    method: 'POST', data: { date },
  })
}

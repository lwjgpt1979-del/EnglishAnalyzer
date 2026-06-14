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

export interface VocabSettings { words_per_group: number; reps_per_group: number; wrong_carry_threshold: number }
export function getVocabSettings(): Promise<VocabSettings> {
  return request<VocabSettings>('/api/v1/vocabulary/settings', { method: 'GET' })
}
export function setVocabSettings(s: VocabSettings): Promise<VocabSettings> {
  return request<VocabSettings>('/api/v1/vocabulary/settings', { method: 'PUT', data: s })
}

export interface AddWordResult { added: boolean; found: boolean; word?: string; already?: boolean; message?: string }
export function addVocabWord(word: string): Promise<AddWordResult> {
  return request<AddWordResult>('/api/v1/vocabulary/add-word', { method: 'POST', data: { word } })
}

export interface ShadowWordScore { word: string; score: number }
export interface ShadowScoreResult {
  overall: number
  level: string
  words: ShadowWordScore[]
  tip: string
}

/** 跟读发音评分（带录音 base64；空则后端走 dev-mock） */
export function shadowScore(
  referenceText: string, audio = '', audioFormat = 'mp3',
): Promise<ShadowScoreResult> {
  return request<ShadowScoreResult>('/api/v1/vocabulary/shadow-score', {
    method: 'POST',
    data: { reference_text: referenceText, audio, audio_format: audioFormat },
  })
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

export function checkin(wrongCount = 0): Promise<VocabCheckinResult> {
  return request<VocabCheckinResult>('/api/v1/vocabulary/checkin', { method: 'POST', data: { wrong_count: wrongCount } })
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

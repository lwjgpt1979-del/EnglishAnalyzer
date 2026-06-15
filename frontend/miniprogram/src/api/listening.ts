import { request } from '@/utils/request'

export interface ListeningBrief {
  id: string
  title: string
  type: string
  difficulty: number
  question_count: number
}

export interface ListeningQuestion {
  prompt: string
  options: string[]
  answer_index: number
  explanation: string
}

export interface ListeningDetail {
  id: string
  title: string
  type: string
  difficulty: number
  transcript: string
  questions: ListeningQuestion[]
}

export function getListeningExercises(): Promise<ListeningBrief[]> {
  return request<ListeningBrief[]>('/api/v1/listening/exercises', { method: 'GET' })
}

export function getListeningExercise(id: string): Promise<ListeningDetail> {
  return request<ListeningDetail>(`/api/v1/listening/exercises/${id}`, { method: 'GET' })
}

/** 提交精听答案：判分 + 错题归集（§6.4）*/
export function submitListening(id: string, answers: number[]): Promise<unknown> {
  return request(`/api/v1/listening/exercises/${id}/submit`, { method: 'POST', data: { answers } })
}

export interface ListeningWrong {
  id: string; exercise_id: string; exercise_title: string | null
  question_index: number; prompt: string; options: string[]
  correct_index: number; explanation: string | null; wrong_count: number; last_wrong_at: string | null
}
/** 听力错题库（会员专享）*/
export function getListeningWrong(): Promise<ListeningWrong[]> {
  return request<ListeningWrong[]>('/api/v1/listening/wrong', { method: 'GET' })
}

/** 听力句子跟读评测（会员专享）*/
export function shadowListening(reference_text: string, audio?: string, audio_format = 'mp3'): Promise<unknown> {
  return request('/api/v1/listening/shadow', { method: 'POST', data: { reference_text, audio, audio_format } })
}

export interface WeakSentence { id: string; sentence: string; best_score: number; attempts: number; last_at: string | null }
/** 跟读薄弱句库（最高分<60，优先复练；会员专享）*/
export function getWeakSentences(): Promise<WeakSentence[]> {
  return request<WeakSentence[]>('/api/v1/listening/weak-sentences', { method: 'GET' })
}

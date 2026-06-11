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

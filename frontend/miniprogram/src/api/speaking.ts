import { request } from '@/utils/request'

export interface SpeakScenario {
  key: string
  title: string
  emoji: string
  opening: string
  tag?: string       // preset | custom
  source?: string    // custom 来源：学期内容 / 词力通 / 错题
}

export interface SpeakScenarioList {
  custom: SpeakScenario[]
  preset: SpeakScenario[]
}

export interface SpeakTurn {
  role: 'user' | 'assistant'
  text: string
}

export interface SpeakOpening {
  scenario: { key: string; title: string; emoji: string }
  ai_text: string
  ai_audio_url: string
}

export interface SpeakReply {
  ai_text: string
  ai_audio_url: string
  correction: string
  translation: string
  mastered_wrong?: { kp: string; due_left: number } | null
  vocab_practiced?: { word: string; level: string }[]
}

export function getSpeakScenarios(): Promise<SpeakScenarioList> {
  return request<SpeakScenarioList>('/api/v1/speaking/scenarios', { method: 'GET' })
}

export function startSpeak(scenarioKey: string): Promise<SpeakOpening> {
  return request<SpeakOpening>('/api/v1/speaking/start', {
    method: 'POST', data: { scenario_key: scenarioKey },
  })
}

export function replySpeak(
  scenarioKey: string, userText: string, history: SpeakTurn[],
): Promise<SpeakReply> {
  return request<SpeakReply>('/api/v1/speaking/reply', {
    method: 'POST',
    data: { scenario_key: scenarioKey, user_text: userText, history },
  })
}

export interface SpeakSummary {
  overall: number
  fluency: number
  grammar: number
  vocabulary: number
  highlights: string[]
  improvements: string[]
  encouragement: string
  focus_source?: string     // 本次专项来源：词力通 / 错题薄弱点 / 学期内容
  focus_review?: string     // 专项掌握点评
  focus_used?: string[]     // 已用上的目标词
  focus_missed?: string[]   // 未用到的目标词
  checkin?: { checked_in_today: boolean; current_streak: number; longest_streak: number }
}

export interface SpeakStats {
  total_sessions: number
  week_sessions: number
  avg_score: number
  last_score: number
  speaking_streak: number
  last_practiced_at: string | null
}

export function getSpeakStats(): Promise<SpeakStats> {
  return request<SpeakStats>('/api/v1/speaking/stats', { method: 'GET' })
}

export function summarizeSpeak(
  scenarioKey: string, history: SpeakTurn[],
): Promise<SpeakSummary> {
  return request<SpeakSummary>('/api/v1/speaking/summary', {
    method: 'POST',
    data: { scenario_key: scenarioKey, history },
  })
}

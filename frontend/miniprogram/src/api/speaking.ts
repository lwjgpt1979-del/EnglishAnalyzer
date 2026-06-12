import { request } from '@/utils/request'

export interface SpeakScenario {
  key: string
  title: string
  emoji: string
  opening: string
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
}

export function getSpeakScenarios(): Promise<SpeakScenario[]> {
  return request<SpeakScenario[]>('/api/v1/speaking/scenarios', { method: 'GET' })
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

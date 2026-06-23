import { request, BASE_URL } from '@/utils/request'

export interface LSSegment { idx: number; type: string; text: string; color?: string; tint?: string }
export interface LSStructure { idx: number; parent: number | null }
export interface LSKeyWord { word: string; pos?: string; meaning?: string }
export interface LSGrammarPoint { name: string; explanation?: string }
export interface LSExplanation { idx: number; text: string }
export interface LSAnalysis {
  sentence_type?: string
  translation?: string
  summary?: string
  segments?: LSSegment[]
  structure?: LSStructure[]
  components?: Record<string, string>
  main_clause?: string
  key_words?: LSKeyWord[]
  grammar_points?: LSGrammarPoint[]
  explanations?: LSExplanation[]
  difficulty?: number
  complexity?: { word_count?: number; clause_count?: number; tree_depth?: number; mdd?: number; method?: string }
}
export interface LSItem { id: string; text: string; source_kind: string; syntax_points: string[]; favorited?: boolean }
export interface LSListOut { total: number; items: LSItem[] }
export interface LSNodeRef { node_id: string; name: string; node_kind: string | null }
export interface LSDetail {
  id: string; text: string; source_kind: string
  analysis: LSAnalysis | null
  audio_url?: string | null
  favorited?: boolean
  nodes: LSNodeRef[]
}

export function listLongSentences(limit = 20): Promise<LSListOut> {
  return request<LSListOut>('/api/v1/long-sentences', { method: 'GET', data: { limit } })
}

export function getLongSentence(id: string): Promise<LSDetail> {
  return request<LSDetail>(`/api/v1/long-sentences/${id}`, { method: 'GET' })
}

/** 听原句:TTS 流式音频直链(公开接口,可直接作为 audio src 播放)。 */
export function ttsSpeakUrl(text: string, stage = 'junior'): string {
  return `${BASE_URL}/api/v1/tts/speak?text=${encodeURIComponent(text)}&stage=${stage}`
}

/** 听原句:取/生成句子音频 COS 直链(首次合成→存 COS→回填库;再次直接返回库里链接)。 */
export function getLsAudioUrl(id: string): Promise<{ url: string }> {
  return request<{ url: string }>(`/api/v1/long-sentences/${id}/audio`, { method: 'POST' })
}

/** 收藏 / 取消收藏长难句,返回最终是否已收藏。 */
export function favoriteLs(id: string, on: boolean): Promise<{ favorited: boolean }> {
  return request<{ favorited: boolean }>(`/api/v1/long-sentences/${id}/favorite`, { method: on ? 'POST' : 'DELETE' })
}

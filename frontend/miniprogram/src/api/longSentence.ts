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

export type LSTier = 'intro' | 'build' | 'challenge'
export interface LSNextOut { item: (LSItem & { difficulty?: number }) | null; theta: number; target: number; weak_hit: boolean; tier: LSTier; review: boolean }
/** 自适应推荐下一句(按学生水平选;exclude=已学 id 逗号串)。 */
export function nextLongSentence(exclude: string[] = []): Promise<LSNextOut> {
  return request<LSNextOut>('/api/v1/long-sentences/next', { method: 'GET', data: { exclude: exclude.join(',') } })
}

/** 难度反馈,校准水平 θ。rating: easy|ok|hard。返回新 {theta,target}。 */
export function feedbackLongSentence(rating: 'easy' | 'ok' | 'hard', lsId?: string, isStudent = false): Promise<{ theta: number; target: number; tier: LSTier }> {
  return request<{ theta: number; target: number; tier: LSTier }>('/api/v1/long-sentences/feedback', { method: 'POST', data: { rating, ls_id: lsId, is_student: isStudent } })
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

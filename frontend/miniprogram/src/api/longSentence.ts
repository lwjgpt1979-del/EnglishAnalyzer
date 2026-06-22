import { request } from '@/utils/request'

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
  key_words?: LSKeyWord[]
  grammar_points?: LSGrammarPoint[]
  explanations?: LSExplanation[]
}
export interface LSItem { id: string; text: string; source_kind: string; syntax_points: string[] }
export interface LSListOut { total: number; items: LSItem[] }
export interface LSNodeRef { node_id: string; name: string; node_kind: string | null }
export interface LSDetail {
  id: string; text: string; source_kind: string
  analysis: LSAnalysis | null
  nodes: LSNodeRef[]
}

export function listLongSentences(limit = 20): Promise<LSListOut> {
  return request<LSListOut>('/api/v1/long-sentences', { method: 'GET', data: { limit } })
}

export function getLongSentence(id: string): Promise<LSDetail> {
  return request<LSDetail>(`/api/v1/long-sentences/${id}`, { method: 'GET' })
}

import { request } from '@/utils/request'
import type { EssayDetail, EssayList, EssayTemplates, EssayProgress } from '@/types/api'

export function createEssay(payload: { original_text: string; title?: string; essay_type?: string }): Promise<EssayDetail> {
  return request<EssayDetail>('/api/v1/essays', { method: 'POST', data: payload })
}

// ── 应试训练 E1 ──
export interface EssayPrompt {
  id: string; stage: string; genre: string; title: string; scenario: string
  required_points: string[]; person?: string | null; tense?: string | null
  word_min?: number | null; word_max?: number | null
}
export interface PromptAnalysis {
  title: string; genre: string; scenario: string; required_points: string[]
  person?: string | null; tense?: string | null; word_min?: number | null; word_max?: number | null
  // 提问式审题(四卡)干扰项 + 讲解
  audience?: string | null; genre_distractors?: string[]; point_distractors?: string[]; genre_explain?: string
}
export interface EssayDiagnosis {
  id: string; title?: string; genre?: string; overall_band?: string
  total: number; total_full: number
  scores: { dimension: string; score: number; full: number; band?: string }[]
  missing_points: { point: string; covered: boolean }[]
  upgrade_tips: { dimension: string; tip: string }[]
  issues: { original: string; suggestion: string; type: string; explanation: string }[]
}
export function getEssayPrompts(stage?: string, genre?: string): Promise<EssayPrompt[]> {
  // 小程序运行时无 URLSearchParams,手拼 query
  const parts: string[] = []
  if (stage) parts.push(`stage=${encodeURIComponent(stage)}`)
  if (genre) parts.push(`genre=${encodeURIComponent(genre)}`)
  const qs = parts.join('&')
  return request<EssayPrompt[]>(`/api/v1/essays/prompts${qs ? '?' + qs : ''}`, { method: 'GET' })
}
// 写作页支架:模版骨架 + 高分句 + 你学过的长难句
export interface WritingScaffold { template: string; high_sentences: string[]; my_sentences: { text: string; date?: string }[] }
export function getWritingScaffold(genre?: string): Promise<WritingScaffold> {
  return request<WritingScaffold>('/api/v1/essays/scaffold', { method: 'GET', data: { genre: genre || undefined } })
}
// 搭作文:多模版 × 分段 × 候选句
export interface ComposeSlot { key: string; label: string; hint?: string; sentences: string[] }
export interface ComposeTemplate { id: string; name: string; tag?: string; slots: ComposeSlot[] }
export function getComposeTemplates(genre?: string): Promise<{ templates: ComposeTemplate[] }> {
  return request('/api/v1/essays/compose-templates', { method: 'GET', data: { genre: genre || undefined } })
}
export function adaptSentences(genre: string | undefined, scenario: string, slots: { key: string; label: string }[]): Promise<{ by_slot: Record<string, { text: string; from?: string }[]> }> {
  return request('/api/v1/essays/adapt-sentences', { method: 'POST', data: { genre: genre || undefined, scenario, slots } })
}
// 逐句升级:平句→高分句,优先套用你学过的长难句
export interface SentenceUpgrade { original: string; upgraded: string; note: string; from_mine: boolean }
export function upgradeEssay(draftText: string, genre?: string): Promise<{ upgrades: SentenceUpgrade[] }> {
  return request('/api/v1/essays/upgrade', { method: 'POST', data: { draft_text: draftText, genre: genre || undefined } })
}
export function analyzeEssayPrompt(p: { prompt_id?: string; text?: string }): Promise<PromptAnalysis> {
  return request<PromptAnalysis>('/api/v1/essays/analyze-prompt', { method: 'POST', data: p })
}
export function diagnoseEssay(p: { draft_text: string; prompt_id?: string; prompt_text?: string; timed_seconds?: number }): Promise<EssayDiagnosis> {
  return request<EssayDiagnosis>('/api/v1/essays/diagnose', { method: 'POST', data: p })
}
export interface EssayErrorLog {
  by_type: { type: string; count: number }[]
  items: { type: string; original: string; suggestion: string; created_at: string }[]
}
export function getEssayErrorLog(): Promise<EssayErrorLog> {
  return request<EssayErrorLog>('/api/v1/essays/error-log', { method: 'GET' })
}
export function getEssays(): Promise<EssayList> {
  return request<EssayList>('/api/v1/essays', { method: 'GET' })
}
export function getEssay(id: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}`, { method: 'GET' })
}
export function repolishEssay(id: string, revisedText: string): Promise<EssayDetail> {
  return request<EssayDetail>(`/api/v1/essays/${id}/repolish`, { method: 'POST', data: { revised_text: revisedText } })
}
export function getEssayTemplates(essayType?: string): Promise<EssayTemplates> {
  const data: Record<string, string> = {}
  if (essayType) data.essay_type = essayType
  return request<EssayTemplates>('/api/v1/essays/templates', { method: 'GET', data })
}
export function getEssayProgress(): Promise<EssayProgress> {
  return request<EssayProgress>('/api/v1/essays/progress', { method: 'GET' })
}

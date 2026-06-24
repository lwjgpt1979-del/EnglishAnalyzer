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

// ── 理解检测(Phase1 双探针:过关才算学;θ 实测为主)──────────────
export interface ComprehensionProbe { key: string; type: string; prompt: string; options: string[] }
export interface ComprehensionProbeResult { key: string; correct: boolean; correct_answer: string; misconception?: string | null }
export interface ComprehensionResult { passed: boolean; probes: ComprehensionProbeResult[]; theta: number; target: number; tier: LSTier }

/** 取理解检测题面(双探针:点主干 + 释义/意义),不含答案。 */
export function getComprehension(id: string): Promise<{ probes: ComprehensionProbe[] }> {
  return request<{ probes: ComprehensionProbe[] }>(`/api/v1/long-sentences/${id}/comprehension`, { method: 'GET' })
}

/** 提交理解检测:{probe_key: 答案};可带自评 self_rating。返回是否过关 + 诊断 + 新 θ。 */
export function submitComprehension(id: string, answers: Record<string, string>, selfRating?: 'easy' | 'ok' | 'hard'): Promise<ComprehensionResult> {
  return request<ComprehensionResult>(`/api/v1/long-sentences/${id}/comprehension`, {
    method: 'POST', data: { answers, self_rating: selfRating },
  })
}

// ── 短翻译产出项(Phase3:维度 rubric 评分,检验「会输出」)──────────
export interface TranslateDim { key: string; label: string; score: number; max: number; note?: string | null }
export interface TranslateCheckResult { dimensions: TranslateDim[]; total: number; max: number; passed: boolean; feedback?: string | null; theta: number; target: number; tier: LSTier }

/** 提交短翻译,LLM 按维度(命题/逻辑/修饰/主干)评分。返回 rubric + 新 θ。 */
export function submitTranslateCheck(id: string, answer: string): Promise<TranslateCheckResult> {
  return request<TranslateCheckResult>(`/api/v1/long-sentences/${id}/translate-check`, { method: 'POST', data: { answer } })
}

// ── 迁移项(Phase3b:同结构新句,区分「记住题 vs 会技能」)──────────
export interface TransferItem { id: string; text: string; difficulty?: number | null }
export interface TransferOut { item: TransferItem | null; shared: string[]; probes: ComprehensionProbe[] }
export interface TransferResult { passed: boolean; verdict: 'transferred' | 'memorized'; shared: string[]; probes: ComprehensionProbeResult[]; theta: number; target: number; tier: LSTier }

/** 迁移挑战:取一句「同结构、新内容」的句子 + 其理解检测题。exclude=已学 id。 */
export function getTransfer(id: string, exclude: string[] = []): Promise<TransferOut> {
  return request<TransferOut>(`/api/v1/long-sentences/${id}/transfer`, { method: 'GET', data: { exclude: exclude.join(',') } })
}

/** 提交迁移句的理解检测:返回结论(transferred=真掌握 / memorized=疑似记住原题)。 */
export function submitTransfer(originId: string, transferId: string, answers: Record<string, string>): Promise<TransferResult> {
  return request<TransferResult>(`/api/v1/long-sentences/${originId}/transfer-submit`, { method: 'POST', data: { transfer_id: transferId, answers } })
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

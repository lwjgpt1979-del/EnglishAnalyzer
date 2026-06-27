import { request } from '@/utils/request'

// ── 类型 ───────────────────────────────────────────────────────────────
export interface GrammarProbe { key: string; kind: string; prompt: string; options: string[] }
export interface GrammarStatus { status: string; label: string; evidence: string[] }
export interface GrammarProbesOut {
  kp_id: string; kp_name: string
  probes: GrammarProbe[]
  produce: { key: string; prompt: string } | null
  has_transfer: boolean
  recognize: number; detect: number; produce_score: number; transfer_ok: boolean
  mastered: boolean; confirmed_mastered: boolean
  status: GrammarStatus
}
export interface GrammarProbeResult {
  correct: boolean; correct_answer: string; misconception?: string | null
  axis: string; recognize: number; detect: number; produce_score: number
  transfer_ok: boolean; mastered: boolean
}
export interface ProduceDim { key: string; label: string; score: number; max: number; note?: string | null }
export interface GrammarProduceResult {
  dimensions: ProduceDim[]; total: number; max: number; passed: boolean; graded?: boolean
  feedback?: string | null; recognize: number; detect: number; produce_score: number
  transfer_ok: boolean; mastered: boolean
}
export interface GrammarTransferResult {
  correct: boolean; correct_answer: string; verdict: 'transferred' | 'memorized'
  transfer_ok: boolean; mastered: boolean
}

// ── 单点四维 ───────────────────────────────────────────────────────────
export function getKpProbes(kpId: string): Promise<GrammarProbesOut> {
  return request<GrammarProbesOut>(`/api/v1/grammar/kp/${kpId}/probes`, { method: 'GET' })
}
export function submitKpProbe(kpId: string, key: string, answer: string): Promise<GrammarProbeResult> {
  return request<GrammarProbeResult>(`/api/v1/grammar/kp/${kpId}/probe`, { method: 'POST', data: { key, answer } })
}
export function submitKpProduce(kpId: string, sentence: string): Promise<GrammarProduceResult> {
  return request<GrammarProduceResult>(`/api/v1/grammar/kp/${kpId}/produce`, { method: 'POST', data: { sentence } })
}
export function getKpTransfer(kpId: string): Promise<{ probe: GrammarProbe | null }> {
  return request<{ probe: GrammarProbe | null }>(`/api/v1/grammar/kp/${kpId}/transfer`, { method: 'GET' })
}
export function submitKpTransfer(kpId: string, key: string, answer: string): Promise<GrammarTransferResult> {
  return request<GrammarTransferResult>(`/api/v1/grammar/kp/${kpId}/transfer-submit`, { method: 'POST', data: { key, answer } })
}
export function getKpRetention(kpId: string): Promise<{ probe: GrammarProbe | null; interval_days?: number }> {
  return request<{ probe: GrammarProbe | null; interval_days?: number }>(`/api/v1/grammar/kp/${kpId}/retention`, { method: 'GET' })
}
export function submitKpRetention(kpId: string, key: string, answer: string): Promise<{ correct: boolean; correct_answer: string; verdict: 'retained' | 'forgotten'; retain_count: number; confirmed_mastered: boolean; status: GrammarStatus }> {
  return request(`/api/v1/grammar/kp/${kpId}/retention-submit`, { method: 'POST', data: { key, answer } })
}
export function getKpStatus(kpId: string): Promise<GrammarStatus & { recognize: number; detect: number; produce_score: number; transfer_ok: boolean; confirmed_mastered: boolean }> {
  return request(`/api/v1/grammar/kp/${kpId}/status`, { method: 'GET' })
}

// ── 推进环 ─────────────────────────────────────────────────────────────
export interface PathNewItem { kp_id: string; name: string; index: number; confirmed_mastered: boolean; recognize: number; unlocked: number; score: number }
export interface PathMaintainItem { kp_id: string; kp_name: string; retain_count: number; due_at: string | null }
export interface DailyBatch {
  batch_size: number
  ratios: { new: number; maintain: number; apply: number }
  maintain: PathMaintainItem[]
  new: PathNewItem[]
  apply: { type: string; mastered_kp_count: number; suggest_count: number; hint: string; targets: string[] } | null
  stats: { pool: number; mastered: number; due: number; remaining_new: number }
}
export function getDailyPath(textbook?: string, grade?: string): Promise<DailyBatch> {
  const data: Record<string, string> = {}
  if (textbook) data.textbook = textbook
  if (grade) data.grade = grade
  return request<DailyBatch>('/api/v1/grammar/path/daily', { method: 'GET', data })
}

// ── 分级测验(CAT)──────────────────────────────────────────────────────
export interface PlacementItem { idx: number; kp_id: string; kp_name: string; item: { key: string; stem: string; options: string[] } }
export interface HeatCell { kp_id: string; name: string; prior: number; status: string; tested: boolean }
export interface PlacementState {
  session_id?: string; done: boolean
  item?: PlacementItem
  progress?: { asked: number; max: number; pool: number }
  heatmap?: HeatCell[]
  start_line?: { kp_id: string; name: string; index: number } | null
}
export function placementStart(body: { textbook?: string; grade?: string; kp_ids?: string[] }): Promise<PlacementState> {
  return request<PlacementState>('/api/v1/grammar/placement/start', { method: 'POST', data: body })
}
export function placementAnswer(sessionId: string, kpId: string, chosen: string): Promise<PlacementState> {
  return request<PlacementState>('/api/v1/grammar/placement/answer', { method: 'POST', data: { session_id: sessionId, kp_id: kpId, chosen } })
}

import { request } from '@/utils/request'
import type {
  VocabDailyTask,
  VocabAnswerResult,
  VocabWrongList,
  VocabCheckinResult,
  VocabStudentCalendar,
  VocabMakeUpResult,
} from '@/types/api'

export function getDailyTask(): Promise<VocabDailyTask> {
  return request<VocabDailyTask>('/api/v1/vocabulary/daily-task', { method: 'GET' })
}

export interface VocabPronSummary {
  count: number; avg: number | null
  accuracy: number | null; fluency: number | null; completion: number | null
  weak_words: string[]; trend: 'up' | 'flat' | 'down'; bars: number[]
}
export interface VocabOverview {
  mastered: number; review: number; learning: number; new_learned: number
  learned_total: number; wrong_total: number; due_total: number; remaining_new: number
  current_streak: number; longest_streak: number
  pron: VocabPronSummary | null
}
export function getVocabOverview(): Promise<VocabOverview> {
  return request<VocabOverview>('/api/v1/vocabulary/overview', { method: 'GET' })
}

export interface VocabSettings { words_per_group: number; reps_per_group: number; wrong_carry_threshold: number }
export function getVocabSettings(): Promise<VocabSettings> {
  return request<VocabSettings>('/api/v1/vocabulary/settings', { method: 'GET' })
}
export function setVocabSettings(s: VocabSettings): Promise<VocabSettings> {
  return request<VocabSettings>('/api/v1/vocabulary/settings', { method: 'PUT', data: s })
}

export interface AddWordResult { added: boolean; found: boolean; word?: string; already?: boolean; message?: string }
export function addVocabWord(word: string): Promise<AddWordResult> {
  return request<AddWordResult>('/api/v1/vocabulary/add-word', { method: 'POST', data: { word } })
}

export interface ShadowWordScore { word: string; score: number }
export interface ShadowScoreResult {
  overall: number
  level: string
  words: ShadowWordScore[]
  tip: string
}

/** 跟读发音评分（带录音 base64；空则后端走 dev-mock） */
export function shadowScore(
  referenceText: string, audio = '', audioFormat = 'mp3',
): Promise<ShadowScoreResult> {
  return request<ShadowScoreResult>('/api/v1/vocabulary/shadow-score', {
    method: 'POST',
    data: { reference_text: referenceText, audio, audio_format: audioFormat },
  })
}

export function submitVocabAnswer(
  wordId: string,
  correct: boolean,
  hesitant = false,
): Promise<VocabAnswerResult> {
  return request<VocabAnswerResult>('/api/v1/vocabulary/answer', {
    method: 'POST',
    data: { word_id: wordId, correct, hesitant },
  })
}

// R9 可输入性理解·探针(接收 + 产出)
export interface WordProbe { key: string; kind: string; prompt: string; options: string[] }
export interface WordProduceTask { key: string; prompt: string }
export interface WordProbesOut {
  context: { text: string; source: string } | null
  probes: WordProbe[]; produce: WordProduceTask | null
  recep: number; prod: number; mastered: boolean
}
export interface WordProbeResult { correct: boolean; correct_answer: string; misconception?: string | null; axis?: string; recep: number; prod: number; recep_mastered: boolean; prod_mastered: boolean; mastered: boolean }
export interface ProduceDim { key: string; label: string; score: number; max: number; note?: string | null }
export interface WordProduceResult { dimensions: ProduceDim[]; total: number; max: number; passed: boolean; graded?: boolean; feedback?: string | null; recep: number; prod: number; prod_mastered: boolean; mastered: boolean }

/** 取该词探针(语境句 + 接收 cloze/多义 + 产出 搭配/造句),不含答案。 */
export function getWordProbes(wordId: string): Promise<WordProbesOut> {
  return request<WordProbesOut>(`/api/v1/vocabulary/${wordId}/probes`, { method: 'GET' })
}

/** 提交一道客观探针(cloze/多义/搭配),返回判分 + 诊断 + 接收/产出掌握度。 */
export function submitWordProbe(wordId: string, key: string, answer: string): Promise<WordProbeResult> {
  return request<WordProbeResult>(`/api/v1/vocabulary/${wordId}/probe`, { method: 'POST', data: { key, answer } })
}

/** 提交造句(产出),LLM 维度 rubric 评分 → 产出掌握度。 */
export function submitWordProduce(wordId: string, sentence: string): Promise<WordProduceResult> {
  return request<WordProduceResult>(`/api/v1/vocabulary/${wordId}/produce`, { method: 'POST', data: { sentence } })
}

// R9.3 迁移项(同词新语境)
export interface WordTransferOut { context: { text: string; source: string } | null; probe: WordProbe | null }
export interface WordTransferResult { correct: boolean; verdict: 'transferred' | 'memorized'; correct_answer: string; misconception?: string | null; recep: number; prod: number; transfer_ok: boolean; mastered: boolean }

/** 取迁移题:同词新语境的语境填空(exclude=原句,避免雷同)。 */
export function getWordTransfer(wordId: string, exclude = ''): Promise<WordTransferOut> {
  return request<WordTransferOut>(`/api/v1/vocabulary/${wordId}/transfer`, { method: 'GET', data: { exclude } })
}

/** 提交迁移题:transferred(真懂)/ memorized(疑似记住原题)。 */
export function submitWordTransfer(wordId: string, answer: string): Promise<WordTransferResult> {
  return request<WordTransferResult>(`/api/v1/vocabulary/${wordId}/transfer-submit`, { method: 'POST', data: { answer } })
}

// R9.5 成组混合接收检测(防经验主义)
export interface GroupRecepItem { word_id: string; sentence: string }
export interface GroupRecepResult { word_id: string; word: string; correct: boolean; recep: number; mastered: boolean }
/** 取一组词的混合填空题面(N 句 + 共享词库,答案逐句不同)。 */
export function groupRecepProbes(wordIds: string[]): Promise<{ options: string[]; items: GroupRecepItem[] }> {
  return request<{ options: string[]; items: GroupRecepItem[] }>('/api/v1/vocabulary/group-recep/probes', { method: 'POST', data: { word_ids: wordIds } })
}
/** 提交成组检测:answers={word_id: 所选词}。 */
export function submitGroupRecep(answers: Record<string, string>): Promise<{ results: GroupRecepResult[] }> {
  return request<{ results: GroupRecepResult[] }>('/api/v1/vocabulary/group-recep/submit', { method: 'POST', data: { answers } })
}

export function getWrongWords(): Promise<VocabWrongList> {
  return request<VocabWrongList>('/api/v1/vocabulary/wrong-words', { method: 'GET' })
}

export function checkin(wrongCount = 0): Promise<VocabCheckinResult> {
  return request<VocabCheckinResult>('/api/v1/vocabulary/checkin', { method: 'POST', data: { wrong_count: wrongCount } })
}

export function getCheckinCalendar(year?: number, month?: number): Promise<VocabStudentCalendar> {
  const data: Record<string, number> = {}
  if (year) data.year = year
  if (month) data.month = month
  return request<VocabStudentCalendar>('/api/v1/vocabulary/checkin/calendar', { method: 'GET', data })
}

export function makeUpCheckin(date: string): Promise<VocabMakeUpResult> {
  return request<VocabMakeUpResult>('/api/v1/vocabulary/checkin/make-up', {
    method: 'POST', data: { date },
  })
}

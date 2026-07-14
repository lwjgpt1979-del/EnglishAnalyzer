import { request } from '@/utils/request'
import type { UnitOut, UnitDetailOut, KPContentOut, KpMasterySummaryItem, KpMasteryItem } from '@/types/api'

export interface CurriculumOptions {
  textbook_versions: string[]
  grades: string[]
  semesters: string[]
}

/** 教材版本/年级/学期可选值——后台单一真源(curriculum_service.preference_options)。 */
export function getCurriculumOptions(): Promise<CurriculumOptions> {
  return request<CurriculumOptions>('/api/v1/curriculum/options', { method: 'GET' })
}

// 个人语法树(教材进度驱动,分组可视):词法/句法 → 二级分类 → 已学/未学项 + 个人自建节点
export interface GrammarTreeItem { node_id: string; name: string; status: 'learned' | 'unlearned' }
export interface GrammarTreeCat { code: string; name: string; learned: number; unlearned: number; items: GrammarTreeItem[] }
export interface GrammarTreeRoot { code: string; name: string; learned: number; unlearned: number; cats: GrammarTreeCat[] }
export interface GrammarPersonalNode { personal_id: string; name: string; anchor: string | null; source: string }
export interface GrammarTree {
  has_progress: boolean
  totals: { learned: number; unlearned: number }
  roots: GrammarTreeRoot[]
  personal: GrammarPersonalNode[]
}
export function getGrammarTree(): Promise<GrammarTree> {
  return request<GrammarTree>('/api/v1/curriculum/grammar-tree', { method: 'GET' })
}

export function listUnits(
  textbook_version: string,
  grade: string,
  semester: string,
): Promise<UnitOut[]> {
  return request<UnitOut[]>('/api/v1/curriculum/units', {
    method: 'GET',
    data: { textbook_version, grade, semester },
  })
}

export function getUnitDetail(unitId: string): Promise<UnitDetailOut> {
  return request<UnitDetailOut>(`/api/v1/curriculum/units/${unitId}`, {
    method: 'GET',
  })
}

export function getKpContents(kpId: string): Promise<KPContentOut[]> {
  return request<KPContentOut[]>(
    `/api/v1/curriculum/knowledge-points/${kpId}/contents`,
    { method: 'GET' },
  )
}

// 取讲解;若为空则后端即时 AI 生成兜底(全学生共享、落库缓存,不二次付费)
export function ensureKpLecture(kpId: string): Promise<KPContentOut[]> {
  return request<KPContentOut[]>(
    `/api/v1/curriculum/knowledge-points/${kpId}/ensure-lecture`,
    { method: 'POST' },
  )
}

export function getKpMastery(kpId: string): Promise<KpMasteryItem | null> {
  return request<KpMasteryItem | null>(
    `/api/v1/curriculum/knowledge-points/${kpId}/mastery`,
    { method: 'GET' },
  )
}

export interface TextbookSentence {
  text: string
  difficulty: number | null
}

/** 本考点在教材单元原文中抽取的原始例句；给 unitId 则收敛到「本单元」 */
export function getTextbookSentences(kpId: string, unitId?: string): Promise<TextbookSentence[]> {
  const q = unitId ? `?unit_id=${unitId}` : ''
  return request<TextbookSentence[]>(
    `/api/v1/curriculum/knowledge-points/${kpId}/textbook-sentences${q}`,
    { method: 'GET' },
  )
}

export function getUnitMasterySummary(unitId: string): Promise<KpMasterySummaryItem[]> {
  return request<KpMasterySummaryItem[]>(
    `/api/v1/curriculum/units/${unitId}/mastery-summary`,
    { method: 'GET' },
  )
}

// 语法精讲 / 长难句精讲(作业按批次 / 课程按单元)
export interface IntensiveBatch { paper_id: string; title: string; date: string; count: number }
export interface IntensiveUnit { unit_id: string; grade: string; semester: string; unit_no: number; unit_title: string; count: number }
export interface GrammarPoint { node_id: string | null; name: string; code: string | null; personal?: boolean; sgn_id?: string }
export interface GrammarLectureSection { section_key: string; title: string; content_md: string }
// 个人语法(未入图谱)按语法名即时生成 AI 讲解(全局缓存,同名不二次付费)
export function namedGrammarLecture(name: string): Promise<{ sections: GrammarLectureSection[] }> {
  return request('/api/v1/curriculum/grammar-lecture', { method: 'POST', data: { name } })
}
export interface SentenceItem { text: string }

export function grHwBatches(): Promise<{ batches: IntensiveBatch[] }> {
  return request('/api/v1/curriculum/intensive/grammar/homework/batches', { method: 'GET' })
}
export function grHwPoints(paperId: string): Promise<{ points: GrammarPoint[] }> {
  return request('/api/v1/curriculum/intensive/grammar/homework/points', { method: 'GET', data: { paper_id: paperId } })
}
export function grCourseUnits(): Promise<{ version: string | null; units: IntensiveUnit[] }> {
  return request('/api/v1/curriculum/intensive/grammar/course/units', { method: 'GET' })
}
export function grCoursePoints(unitId: string): Promise<{ points: GrammarPoint[] }> {
  return request('/api/v1/curriculum/intensive/grammar/course/points', { method: 'GET', data: { unit_id: unitId } })
}
export function seHwBatches(): Promise<{ batches: IntensiveBatch[] }> {
  return request('/api/v1/curriculum/intensive/sentence/homework/batches', { method: 'GET' })
}
export function seHwSentences(paperId: string): Promise<{ sentences: SentenceItem[] }> {
  return request('/api/v1/curriculum/intensive/sentence/homework/sentences', { method: 'GET', data: { paper_id: paperId } })
}
// 阅读理解精讲(作业):按卷归组;每卷=短文+小题
export interface ReadingQuestion { no: string | null; type: string | null; stem: string | null; student_answer: string | null; correct_answer: string | null; explanation: string | null; is_wrong: boolean }
export interface ReadingBlock { block_label: string; passage: string; questions: ReadingQuestion[] }
export function rdHwBatches(): Promise<{ batches: IntensiveBatch[] }> {
  return request('/api/v1/curriculum/intensive/reading/homework/batches', { method: 'GET' })
}
export function rdHwPassages(paperId: string): Promise<{ blocks: ReadingBlock[] }> {
  return request('/api/v1/curriculum/intensive/reading/homework/passages', { method: 'GET', data: { paper_id: paperId } })
}
export function seCourseUnits(): Promise<{ version: string | null; units: IntensiveUnit[] }> {
  return request('/api/v1/curriculum/intensive/sentence/course/units', { method: 'GET' })
}
export function seCourseSentences(unitId: string): Promise<{ sentences: SentenceItem[] }> {
  return request('/api/v1/curriculum/intensive/sentence/course/sentences', { method: 'GET', data: { unit_id: unitId } })
}

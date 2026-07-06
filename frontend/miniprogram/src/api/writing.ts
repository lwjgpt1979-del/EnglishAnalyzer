import { request } from '@/utils/request'

export interface WritingPoint { id?: number; point: string }
export interface WritingStructureBlock { role?: string; guide: string; point_ids?: number[] }

/** 可练书面表达题(下发要点+结构脚手架,不下发范文) */
export interface WritingQuestion {
  id: string
  stem: string
  genre?: string
  main_tense?: string
  strategy?: string
  points_count?: number          // 审题小测:要点条数(前置门)
  points: WritingPoint[]
  structure: WritingStructureBlock[]
  full_score: number
}

export interface WGGradedPoint { id?: number; point: string; hit: boolean; comment?: string }
export interface WGError { span: string; type: string; fix: string }
export interface WGInline { sentence: string; comment: string }

/** 5 维评分结果 */
export interface WritingGradeResult {
  points: WGGradedPoint[]
  content_score: number
  content_full: number
  accuracy: { score: number; full: number; errors: WGError[] }
  richness: { score: number; full: number; used_targets: string[]; suggestions: string[] }
  organization: { score: number; full: number; comment: string }
  band: string
  total: number
  full: number
  inline_comments: WGInline[]
  feedback: string
  dim_passes?: Record<string, boolean>
  is_ai_graded?: boolean
  model_essay?: string           // 批改后才下发(S4 范文对照)
  point_map?: Record<string, string>
  target_expressions?: string[]
}

/** 列可练书面表达题(带要点+结构脚手架,不含范文) */
export function listWritingQuestions(limit = 10, nodeId?: string): Promise<WritingQuestion[]> {
  const data: Record<string, unknown> = { limit }
  if (nodeId) data.node_id = nodeId
  return request<WritingQuestion[]>('/api/v1/writing-practice/questions', { method: 'GET', data })
}

/** 提交作文批改(解析/范文服务端持有防抄):5 维分 + 整体档 + 逐句批注 + 升格 + 落 BKT */
export function gradeWritingByQuestion(payload: {
  question_id: string
  student_essay: string
  full_score?: number
}): Promise<WritingGradeResult> {
  return request<WritingGradeResult>('/api/v1/writing-practice/grade-question', {
    method: 'POST',
    data: payload,
  })
}

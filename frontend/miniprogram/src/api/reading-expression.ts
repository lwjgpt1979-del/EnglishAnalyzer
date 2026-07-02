import { request } from '@/utils/request'

export interface REGradePoint { point: string; hit: boolean; comment?: string }

export interface REGradeResult {
  points: REGradePoint[]
  content_score: number
  content_full: number
  language_comment: string
  language_deduction: number
  total: number
  full: number
  feedback: string
  is_correct?: boolean   // grade-question(按题练)返回;/grade(自测)无
}

export interface REQuestion {
  id: string
  stem: string
  passage?: string | null
  full_score: number
}

/** 列可练的阅读表达题(不含参考答案,防作弊);供「按题练」模式。 */
export function listReadingExpressionQuestions(limit = 10, nodeId?: string): Promise<REQuestion[]> {
  const data: Record<string, unknown> = { limit }
  if (nodeId) data.node_id = nodeId
  return request<REQuestion[]>('/api/v1/reading-expression/questions', { method: 'GET', data })
}

/** 按 question_id 批改(服务端持参考答案,防作弊)+ 落 KP 错题闭环。 */
export function gradeReadingExpressionByQuestion(payload: {
  question_id: string
  student_answer: string
  full_score?: number
}): Promise<REGradeResult> {
  return request<REGradeResult>('/api/v1/reading-expression/grade-question', {
    method: 'POST',
    data: payload,
  })
}

/** 阅读表达简答 AI 批改(P2a):逐要点命中 + 内容/语言得分 + 反馈。 */
export function gradeReadingExpression(payload: {
  question: string
  reference_answer: string
  student_answer: string
  passage?: string
  full_score?: number
}): Promise<REGradeResult> {
  return request<REGradeResult>('/api/v1/reading-expression/grade', {
    method: 'POST',
    data: payload,
  })
}

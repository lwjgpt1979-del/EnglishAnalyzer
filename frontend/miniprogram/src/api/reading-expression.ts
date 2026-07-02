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

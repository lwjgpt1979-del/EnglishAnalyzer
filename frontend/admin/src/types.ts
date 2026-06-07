// 后端统一响应包装
export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

// 仿真题（运营视图，含答案）
export interface AdminQuestionItem {
  id: string
  knowledge_point_id: string
  question_type: string
  stem: string
  options: string[] | null
  answer: string
  explanation: string | null
  difficulty: number
  dimension: string | null
  status: string
}
export interface AdminQuestionListOut {
  total: number
  items: AdminQuestionItem[]
}

// 知识点内容（运营视图）
export interface AdminContentItem {
  id: string
  knowledge_point_id: string
  dimension: string
  content_md: string
  audio_url: string | null
  status: string
  generated_by: string
}
export interface AdminContentListOut {
  total: number
  items: AdminContentItem[]
}

// 定价
export interface SemesterPricing {
  basic: number
  pro: number
  promax: number
}

export type ReviewStatus = 'draft' | 'reviewing' | 'published' | 'retired'

// 数据大盘概览
export interface AdminOverview {
  questions_by_status: Record<ReviewStatus, number>
  contents_by_status: Record<ReviewStatus, number>
  total_users: number
  paid_orders: number
}

// 课程单元（含内容完成度统计）
export interface AdminCurriculumUnit {
  unit_id: string
  textbook_version: string
  grade: string
  semester: string
  unit_no: number
  unit_title: string
  kp_count: number
  content_count: number
  content_rate: number   // 0-1
}

// src/types/api.ts
// 与后端 schemas 一一对应，字段名保持 snake_case

export interface BaseResponse<T> {
  code: number
  message: string
  data: T
}

// ── Auth ─────────────────────────────────────────────────────────────────────

/** 对应后端 TokenResponse — POST /api/v1/auth/wx-login 返回 */
export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
}

/** 对应后端 UserProfileOut — GET /api/v1/users/me 返回 */
export interface UserProfileOut {
  id: string
  role: string
  nickname: string | null
  avatar_url: string | null
  is_active: boolean
}

// ── Upload ───────────────────────────────────────────────────────────────────

export interface PresignData {
  presign_url: string
  file_url: string
  key: string
  expires_in: number
}

// ── WrongQuestion ────────────────────────────────────────────────────────────

export interface WrongQuestionCreate {
  source_image_url: string
  question_text?: string
  student_answer?: string
  correct_answer?: string
  question_type?: string
  difficulty?: number
  tags?: string[]
}

export interface WrongQuestionOut {
  id: string
  student_id: string
  source_image_url: string
  question_text: string | null
  student_answer: string | null
  correct_answer: string | null
  question_type: string | null
  difficulty: number | null
  tags: string[] | null
  is_mastered: boolean
  mastered_at: string | null
  created_at: string
  updated_at: string
}

export interface WrongQuestionListOut {
  items: WrongQuestionOut[]
  total: number
}

export interface AiAnalysisOut {
  id: string
  wrong_question_id: string
  llm_provider: string
  error_types: string[]
  knowledge_points: string[]
  diagnosis: string
  suggestions: string
  confidence_score: number | null
  tokens_used: number
  created_at: string
}

// ── Diagnosis ────────────────────────────────────────────────────────────────

export interface ErrorTypeCount {
  error_type: string
  count: number
}

export interface KnowledgePointCount {
  knowledge_point: string
  count: number
}

export interface DailyActivity {
  date: string
  count: number
}

export interface DiagnosisReport {
  total_questions: number
  total_analyzed: number
  mastered_count: number
  mastery_rate: number
  top_error_types: ErrorTypeCount[]
  top_weak_knowledge_points: KnowledgePointCount[]
  question_type_distribution: Record<string, number>
  difficulty_distribution: Record<string, number>
  recent_daily_activity: DailyActivity[]
  top_suggestions: string[]
}

// ── Membership ───────────────────────────────────────────────────────────────

export interface CurrentMembershipOut {
  tier: string          // free | basic | pro | promax
  started_at: string | null
  expires_at: string | null
  is_active: boolean
}

// ── Orders ───────────────────────────────────────────────────────────────────

export interface OrderCreate {
  tier: string          // basic | pro | promax
  duration_months: number  // 1 | 3 | 12
  order_type: string    // new | renew | upgrade
}

export interface OrderOut {
  id: string
  order_no: string
  tier: string
  duration_months: number
  amount_fen: number    // 分
  status: string        // pending | paid | refunded | partial_refunded
  wx_transaction_id: string | null
  paid_at: string | null
  created_at: string
}

export interface PayParamsOut {
  timeStamp: string
  nonceStr: string
  package: string       // prepay_id=wx...
  signType: string      // RSA
  paySign: string
}

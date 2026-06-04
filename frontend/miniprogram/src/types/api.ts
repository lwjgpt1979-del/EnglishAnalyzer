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
  profile_completed?: boolean
  birth_year?: number | null
  deactivation_scheduled_at?: string | null
  days_until_cancellation?: number | null
}

// ── Upload ───────────────────────────────────────────────────────────────────

export interface PresignData {
  presign_url: string
  file_url: string
  key: string
  expires_in: number
  is_mock?: boolean
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
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed' | null
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

// 按知识点维度的练习正确率（来自 sim_practice_records，M3 / D-094）
export interface KpDimensionItem {
  knowledge_point_id: string
  knowledge_point_name: string
  category: string | null
  attempts: number
  correct: number
  accuracy: number
}

// 按学期维度的练习正确率（M3 / D-094）
export interface SemesterDimensionItem {
  grade: string
  semester: string
  label: string
  attempts: number
  correct: number
  accuracy: number
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
  kp_dimension: KpDimensionItem[]
  semester_dimension: SemesterDimensionItem[]
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
  target_student_id?: string
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

/** OCR 任务状态 — GET /wrong-questions/{id}/ocr */
export interface OcrStatusOut {
  wrong_question_id: string
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed' | null
  printed_text: string | null
  handwritten_text: string | null
  error_message: string | null
  updated_at: string | null
}

/** 手动确认 OCR 文字 — PATCH /wrong-questions/{id}/text */
export interface ConfirmOcrTextRequest {
  question_text?: string | null
  student_answer?: string | null
  correct_answer?: string | null
  question_type?: string | null
}

// ── Teacher ──────────────────────────────────────────────────────────────────

export interface TeacherProfileOut {
  user_id: string
  subject: string | null
  cert_status: string
  max_students: number
  cert_doc_url?: string | null
}

export interface InviteCodeOut {
  code: string
  expires_at: string
}

export interface TeacherStudentOut {
  student_id: string
  bound_at: string | null
}

export interface TeacherCommentOut {
  id: string
  wrong_question_id: string
  teacher_id: string
  comment_text: string
  created_at: string
}

// ── Practice (AI 仿真题) ──────────────────────────────────────────────────────

export interface GenerateQuestionsRequest {
  knowledge_point?: string | null
  count?: number
  difficulty?: number
}

export interface PracticeQuestionOut {
  id: string
  knowledge_point_id: string
  knowledge_point_name: string
  question_type: string
  difficulty: number
  stem: string
  options: string[]
}

export interface SubmitAnswerRequest {
  question_id: string
  answer: string
  time_spent_sec?: number | null
}

export interface SubmitAnswerResult {
  record_id: string
  question_id: string
  is_correct: boolean
  correct_answer: string
  explanation: string
}

export interface PracticeRecordOut {
  id: string
  question_id: string
  is_correct: boolean
  student_answer: string
  practiced_at: string
  time_spent_sec: number | null
}

export interface PracticeHistoryOut {
  total: number
  items: PracticeRecordOut[]
}

export interface PracticeStatsOut {
  total_practiced: number
  total_correct: number
  correct_rate: number
  by_knowledge_point: Record<string, { practiced: number; correct: number }>
}

// ── Compliance ────────────────────────────────────────────────────────────────

export interface CompleteProfileResponse {
  profile_completed: boolean
  needs_guardian_verify: boolean
  age: number
}

export interface CancellationStatus {
  requested_at: string | null
  scheduled_at: string | null
  days_remaining: number | null
}

// ── Notifications ─────────────────────────────────────────────────────────────

export interface NotificationOut {
  id: string
  type: string
  channel: 'study' | 'membership' | 'system' | 'relative' | 'teacher'
  title: string
  content: string
  is_read: boolean
  read_at: string | null
  created_at: string
  expires_at: string | null
  meta: Record<string, any> | null
}

export interface NotificationListOut {
  items: NotificationOut[]
  total: number
  unread_count: number
}

// ── Classes ───────────────────────────────────────────────────────────────────

export interface ClassOut {
  id: string
  name: string
  student_count: number
  created_at: string
}

export interface ClassStudentOut {
  student_id: string
  joined_at: string
}

export interface ClassReport {
  class_id: string
  class_name: string
  student_count: number
  avg_mastery_rate: number
  total_questions: number
  top_error_types: { type: string; count: number }[]
  top_weak_knowledge_points: { kp: string; count: number }[]
  students_ranking: { student_id: string; total_questions: number; mastery_rate: number }[]
}

// ── Relative ──────────────────────────────────────────────────────────────────

export interface RelativeInviteCodeOut {
  code: string
  expires_at: string
}

export interface BoundStudent {
  student_id: string
  relationship: string
  bound_at: string
}

export interface QRCodeOut {
  code: string
  expires_at: string
  qrcode_base64: string
}

export interface SendInviteSmsOut {
  sent: boolean
  code: string
}

// ── V2 Semesters ──────────────────────────────────────────────────────────────

export type Semester = '上' | '下'

export interface SemesterIdentity {
  textbook_version: string
  grade: string
  semester: Semester
}

export interface PurchasedSemesterOut {
  id: string
  textbook_version: string
  grade: string
  semester: string
  tier: string
  started_at: string
  expires_at: string
}

// ─── V2 课程浏览（D-079 / M2）──

export interface UnitOut {
  id: string
  textbook_version: string
  grade: string
  semester: string
  unit_no: number
  unit_title: string
  locked: boolean
  kp_count: number
}

export interface KnowledgePointOut {
  id: string
  code: string
  name: string
  category: string
  description: string | null
}

export interface WordOut {
  id: string
  word: string
  phonetic: string | null
  definitions: Array<{ pos?: string; meaning: string }>
  difficulty: number
}

export interface UnitDetailOut extends UnitOut {
  knowledge_points: KnowledgePointOut[]
  words: WordOut[]
}

export interface KPContentOut {
  dimension: string
  content_md: string
  audio_url: string | null
}

// ─── V2 仿真题（D-079 / M3a）──

export type SimQuestionType =
  | '单选'
  | '填空'
  | '判断'
  | '完型'
  | '阅读'
  | '写作'
  | '连线'

export interface SimQuestionOut {
  id: string
  question_type: SimQuestionType
  stem: string
  options: string[] | null
  difficulty: number
}

export interface PracticeAttemptIn {
  question_id: string
  user_answer: string
}

export interface PracticeResultOut {
  correct: boolean
  correct_answer: string
  explanation: string
  wrong_question_id: string | null
}

// ─── 模拟考批量（D-079 / M3b）──

export interface ExamAttemptIn {
  items: PracticeAttemptIn[]
}

export interface ExamItemResult {
  question_id: string
  correct: boolean
  correct_answer: string
  user_answer: string
  explanation: string
  wrong_question_id: string | null
}

export interface ExamResultOut {
  total: number
  correct_count: number
  items: ExamItemResult[]
}

export interface KPAccuracyItem {
  knowledge_point_id: string
  knowledge_point_name: string
  attempts: number
  correct: number
  accuracy: number
}

export interface KPAccuracyOut {
  total_attempts: number
  overall_accuracy: number
  items: KPAccuracyItem[]
}

export interface ExamHistoryItem {
  id: string
  total: number
  correct_count: number
  accuracy: number
  created_at: string
}

export interface ExamHistoryOut {
  total_exams: number
  items: ExamHistoryItem[]
}

export interface ExamRankOut {
  in_class: boolean
  ranked: boolean
  class_name: string | null
  my_rank: number | null
  total_ranked: number | null
  percentile: number | null
  my_avg_accuracy: number | null
  class_avg_accuracy: number | null
}

// ─── V2 整卷上传 OCR 拆题（D-089 / M4）──

export type PaperOcrStatus = 'pending' | 'processing' | 'completed' | 'failed' | null

/** 拆出的单题 */
export interface UserPaperQuestionOut {
  id: string
  question_no: string | null
  question_type: string | null
  stem: string | null
  student_answer: string | null
  correct_answer: string | null
  explanation: string | null
  is_wrong: boolean
}

/** 试卷概要（列表用） */
export interface UserPaperOut {
  id: string
  title: string | null
  source_image_urls: string[]
  ocr_status: PaperOcrStatus
  question_count: number
  created_at: string
}

/** 试卷详情：概要 + 题目列表 */
export interface UserPaperDetailOut extends UserPaperOut {
  questions: UserPaperQuestionOut[]
}

export interface UserPaperListOut {
  items: UserPaperOut[]
  total: number
}

/** POST /user-papers 建卷返回 */
export interface UserPaperCreateResult {
  id: string
  title: string | null
  ocr_status: PaperOcrStatus
}

// ── 词力通（P1 / D-100）──────────────────────────────────────────────
export interface VocabWordCard {
  word_id: string
  word: string
  phonetic: string | null
  definitions: Array<{ pos?: string; meaning: string }> | Record<string, unknown>
  examples: unknown[] | Record<string, unknown> | null
  difficulty: number
  level: string
  is_new: boolean
  image_urls?: string[] | null
  en_description?: string | null
  word_audio_url?: string | null
  en_desc_audio_url?: string | null
}

export interface VocabDailyTask {
  new_words: VocabWordCard[]
  review_words: VocabWordCard[]
  new_count: number
  review_count: number
  new_limit: number
}

export interface VocabAnswerResult {
  word_id: string
  level: string
  repetitions: number
  interval_days: number
  next_review_at: string
}

// 错词本（D-103）
export interface VocabWrongItem {
  word_id: string
  word: string
  phonetic?: string | null
  definitions: Array<{ pos?: string; meaning: string }> | Record<string, unknown>
  wrong_count: number
  level: string
  image_urls?: string[] | null
  en_description?: string | null
  word_audio_url?: string | null
  en_desc_audio_url?: string | null
}
export interface VocabWrongList {
  total: number
  items: VocabWrongItem[]
}

// 打卡（D-104 / D-105 严格校验）
export interface VocabCheckinResult {
  completed: boolean
  checkin_date: string | null
  streak_days: number
  new_words_count: number
  review_done: boolean
  review_due: number
  new_learned_today: number
  new_target: number
}

// 亲人可见打卡日历（D-106）
export interface RelativeCheckinDay {
  date: string
  new_words_count: number
  streak_days: number
}
export interface RelativeCheckinCalendar {
  year: number
  month: number
  days: RelativeCheckinDay[]
  checked_count: number
  current_streak: number
  longest_streak: number
}

// 打卡热力图 + 徽章 + 补签（D-107）
export interface VocabCheckinBadge {
  level: string
  name: string
  threshold: number
  unlocked: boolean
}
export interface VocabStudentCalendar {
  year: number
  month: number
  days: { date: string; new_words_count: number; streak_days: number }[]
  checked_count: number
  current_streak: number
  longest_streak: number
  badges: VocabCheckinBadge[]
}
export interface VocabMakeUpResult {
  date: string
  current_streak: number
  longest_streak: number
}

// 作文精修（D-109 / D-110）
export interface EssayScoreItem { dimension: string; score: number; full: number }
export interface EssayIssueItem { original: string; suggestion: string; type: string; color: string; explanation: string }
export interface EssayRoundItem { round: number; total: number }
export interface EssayTemplates { essay_type: string | null; template: string; samples: string[] }
export interface EssayDetail {
  id: string
  original_text: string
  polished_text: string | null
  scores: EssayScoreItem[]
  total: number
  issues: EssayIssueItem[]
  title: string | null
  essay_type: string | null
  round_count: number
  status: string
  created_at: string
  rounds: EssayRoundItem[]
}
export interface EssayListItem {
  id: string; title: string | null; essay_type: string | null
  total: number; status: string; created_at: string
}
export interface EssayList { total: number; items: EssayListItem[] }
export interface EssayTrendItem { date: string; total: number }
export interface EssayDimensionAvg { dimension: string; avg: number }
export interface EssayProgress {
  total_essays: number
  avg_total: number
  trend: EssayTrendItem[]
  dimension_avg: EssayDimensionAvg[]
}

// 老师出卷（D-113）
export interface AssignmentQuestion { stem: string; type?: string | null; options?: string[] | null; answer?: string | null }
export interface AssignmentOut {
  id: string; class_id: string; title: string; questions: AssignmentQuestion[]
  due_at: string | null; status: string; published_at: string | null; created_at: string
}
export interface AssignmentListItem {
  id: string; class_id: string; title: string; status: string; due_at: string | null; submission_count: number
}
export interface SubmissionItem {
  id: string; student_id: string; answers: unknown; score: number | null; submitted_at: string
}
export interface TeacherAssignmentDetail { assignment: AssignmentOut; submissions: SubmissionItem[] }
export interface StudentAssignmentItem {
  id: string; title: string; status: string; due_at: string | null; submitted: boolean; score: number | null
}
export interface StudentAssignmentDetail {
  assignment: AssignmentOut; submitted: boolean; answers: unknown; score: number | null
}

export interface PerQuestionStat { index: number; stem: string; correct: number; total: number; rate: number }
export interface AssignmentStats {
  total_students: number; submitted_count: number; completion_rate: number
  graded_count: number; avg_score: number | null; max_score: number | null; min_score: number | null
  per_question: PerQuestionStat[]
}

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
  phone?: string | null
  preferred_grade?: string | null
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
  // KP-First 平台练习/模拟考错题的内置题面;source 区分数据源
  options: string[] | null
  explanation: string | null
  source: 'platform' | 'uploaded' | null
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

// 知识点掌握台账条目（来自 student_kp_mastery，M6c）
export interface MasteryLedgerItem {
  kp_key: string
  kp_id: string | null
  correct_count: number
  wrong_count: number
  total: number
  accuracy: number
  level: 'weak' | 'medium' | 'good'
  suggestion: string
  sources: string[]
  last_activity_at: string | null
  days_since_last: number | null
}

export interface RegressionAlert {
  kp_key: string
  latest_accuracy: number
  peak_accuracy: number
  drop: number
  severity: 'high' | 'mid' | 'low'
  latest_date: string
  peak_date: string
  latest_total: number
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
  mastery_ledger: MasteryLedgerItem[]
  regression_alerts: RegressionAlert[]
}

// ── 每日学习计划（M9 / 两来源重构）─────────────────────────────────────────────
export interface PlanTile {
  module: 'word' | 'grammar' | 'sentence' | 'reading'
  title: string
  count: number          // 今日待做（剩余未学）
  studied: number
  total: number
  route: string | null
}
export interface PlanSource {
  source: 'homework' | 'course'
  title: string
  subtitle: string
  available: boolean
  tiles: PlanTile[]
}
export interface PlanReview {
  count: number
  subtitle: string
  route: string
}
export interface TodayPlanOut {
  date: string
  sources: PlanSource[]
  review: PlanReview
  completed_count: number
  total_count: number
  checkin_done: boolean
  review_pending: number
}

// ── 学习激励中心（M10）────────────────────────────────────────────────────────
export interface BadgeItem {
  level: string
  name: string
  threshold: number
  unlocked: boolean
}
export interface AchievementItem {
  key: string
  name: string
  desc: string
  icon: string
  current: number
  target: number
  unlocked: boolean
  progress: number
}
export interface IncentiveStats {
  total_practice: number
  checkin_days: number
  mastered_kp: number
  wrong_mastered: number
  exam_count: number
  unlocked_achievements: number
  total_achievements: number
}
export interface IncentiveSummary {
  level: number
  xp: number
  xp_in_level: number
  xp_to_next: number
  current_streak: number
  longest_streak: number
  checked_in_today: boolean
  badges: BadgeItem[]
  achievements: AchievementItem[]
  stats: IncentiveStats
}

// ── Membership ───────────────────────────────────────────────────────────────

export interface CurrentMembershipOut {
  tier: string          // free | basic | pro | promax
  started_at: string | null
  expires_at: string | null
  is_active: boolean
}

// ── Orders ───────────────────────────────────────────────────────────────────

export interface SemesterItem {
  textbook_version: string
  grade: string
  semester: '上' | '下'
}

export interface OrderCreate {
  tier: string          // basic | pro | promax
  duration_months?: number  // 遗留按月：1 | 3 | 12
  quantity?: number     // 按份：每份6个月，x份=6x月
  addon_feature_key?: string  // 加量包：购买某功能加量次数
  order_type: string    // new | renew | upgrade
  minor_consent?: boolean
  target_student_id?: string
  semesters?: SemesterItem[]
  payment_confirm_log_id?: string  // 支付确认留存 ID（§4.6）
  is_promotional?: boolean         // 活动价订单
  coupon_grant_id?: string         // 使用的优惠券（SP-4）
}

export interface OrderOut {
  id: string
  order_no: string
  tier: string
  duration_months: number
  amount_fen: number    // 分（已扣优惠券）
  discount_fen?: number // 优惠券抵扣（分，SP-4）
  status: string        // pending | paid | refunded | partial_refunded
  refund_status: string // 退款状态码（§4.5.2），默认 NONE
  appeal_status: string // 申诉状态码（§4.5.2），默认 NONE
  wx_transaction_id: string | null
  paid_at: string | null
  created_at: string
}

/** 支付前合规确认（§4.6.3）*/
export interface PaymentConfirmCreate {
  plan_snapshot?: Record<string, unknown>
  checkbox_refund_policy: boolean
  checkbox_digital_service: boolean
  device_id?: string
  session_id?: string
}
export interface PaymentConfirmOut {
  log_id: string
}

/** 申诉（超7天有理由）*/
export interface AppealCreate {
  appeal_type: string   // SYSTEM_FAULT | DESC_MISMATCH | DUPLICATE_PURCHASE | MINOR_PURCHASE
  note?: string
  evidence_urls?: string[]
}

/** 退款 / 申诉处理结果 */
export interface RefundOut {
  id: string
  order_id: string
  amount_fen: number
  refund_type: string   // standard_7d | prorated | appeal
  status: string        // pending | approved | rejected | completed
  state_code: string | null
  appeal_type: string | null
  wx_refund_id: string | null
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
  nickname?: string | null
}

export interface MyTeacherOut {
  teacher_id: string
  nickname?: string | null
  subject?: string | null
  bound_at?: string | null
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
  nickname?: string | null
}

export interface ClassReport {
  class_id: string
  class_name: string
  student_count: number
  avg_mastery_rate: number
  total_questions: number
  top_error_types: { type: string; count: number }[]
  top_weak_knowledge_points: { kp: string; count: number }[]
  students_ranking: { student_id: string; total_questions: number; mastery_rate: number; nickname?: string | null }[]
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
  nickname?: string | null
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
  section_key: string   // concept | rule | examples | ...(随考点类型)
  title: string         // 环节中文标题
  content_md: string
  media_url: string | null
}

export interface KpMasteryItem {
  kp_name: string
  correct_count: number
  wrong_count: number
  total: number
  accuracy: number | null          // 原始正确率(兼容保留)
  mastery: number | null           // 加权掌握度 0–1(展示口径)
  mastery_events: number           // 事件数 C;< 10 证据不足
  // 掌握度四计数器(掌握度详情算式)
  fa_correct?: number              // 首答对 ×1
  fa_wrong?: number                // 首答错 ×-1.5
  corrected_count?: number         // 订正对 ×0.3
  redo_wrong_count?: number        // 订正错 ×-0.3
  last_activity_at: string | null
}

export interface KpMasterySummaryItem {
  kp_id: string
  kp_name: string
  kp_category: string | null
  correct_count: number
  wrong_count: number
  total: number
  accuracy: number | null          // 原始正确率(兼容保留)
  mastery: number | null           // 加权掌握度 0–1(展示口径)
  mastery_events: number           // 事件数 C;< 10 证据不足
  last_activity_at: string | null
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
  kp_name: string | null
  passage?: string | null   // 完型/阅读题组短文(逐空/逐问微题的上下文);无则 null（P1）
}

export interface AdaptiveSetOut {
  questions: SimQuestionOut[]
  weak_kp_names: string[]
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
  passage?: string | null       // 所属短文/语篇(完形/阅读;独立题为空)
  block_key?: string | null     // 同篇小问共享的分组键
  node_id?: string | null
  kp_name?: string | null
  kp_kind?: 'grammar' | 'vocab' | null   // 考语法 / 考词汇
}

/** 原卷大题/板块(还原题型结构) */
export interface UserPaperSectionOut {
  id: string
  label: string
  section_type: string | null
  is_suggested?: boolean        // AI 建议分类(原卷没识别到大题头);前端标「建议」、学生可改
  in_reading_intensive?: boolean  // 阅读理解:是否已手动加入作业精讲·阅读理解精讲
  questions: UserPaperQuestionOut[]
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

/** 试卷详情：概要 + 按原卷大题分组(sections) + 扁平题目列表(questions,兼容) */
export interface UserPaperDetailOut extends UserPaperOut {
  sections?: UserPaperSectionOut[]
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
  reused?: boolean        // 同图已解析过 → 复用,未重复解析
}

// ── 词力通（P1 / D-100）──────────────────────────────────────────────
export interface VocabWordCard {
  word_id: string
  word: string
  phonetic: string | null
  definitions: Array<{ pos?: string; meaning: string }> | Record<string, unknown>
  examples: Array<{ en: string; zh?: string; audio?: string }> | null
  phrases?: Array<{ en: string; zh?: string; audio?: string }> | null
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
  examples?: Array<{ en: string; zh?: string; audio?: string }> | null
  phrases?: Array<{ en: string; zh?: string; audio?: string }> | null
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
  id: string; student_id: string; answers: unknown; score: number | null; submitted_at: string; nickname?: string | null
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

export interface AssignmentSuggest { knowledge_point: string; questions: AssignmentQuestion[] }

export interface KPSearchItem {
  id: string
  name: string
  category: string
  description: string | null
}

// V2 M28：仿真题 & 班级试卷
export interface SimQuestionItem {
  id: string
  knowledge_point_id: string
  question_type: string
  stem: string
  options: string[] | null
  difficulty: number
  dimension: string | null
}
export interface SimQuestionListOut {
  items: SimQuestionItem[]
  total: number
}

export interface ClassPaperItem {
  paper_id: string
  class_id: string
  title: string
  textbook_version: string | null
  grade: string | null
  semester: string | null
  description: string | null
  question_count: number
  status: string
  created_at: string
}
export interface ClassPaperDetailOut extends ClassPaperItem {
  questions: SimQuestionItem[]
}
export interface ClassPaperCreate {
  title: string
  textbook_version?: string
  grade?: string
  semester?: string
  description?: string
  question_ids: string[]
}

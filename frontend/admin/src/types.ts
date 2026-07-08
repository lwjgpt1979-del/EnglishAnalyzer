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

// 知识点内容审核已退役(切 node_resource);AdminContent* 类型随之移除。

// 定价
export interface SemesterPricing {
  basic: number
  pro: number
  promax: number
  list_basic?: number
  list_pro?: number
  list_promax?: number
}

// 机构激活码定价（分 / 月）
export interface InstitutionCodePricing {
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
  pending_teachers: number
}

// 教师认证（管理员视图）
export interface AdminTeacherItem {
  teacher_id: string
  nickname: string | null
  phone: string | null
  subject: string | null
  cert_status: 'uncertified' | 'pending' | 'certified' | 'rejected'
  cert_doc_url: string | null
  max_students: number
  institution_id: string | null
  monthly_paper_quota: number | null
  created_at: string
}
export interface AdminTeacherListOut {
  total: number
  items: AdminTeacherItem[]
}

// 词力通单词媒体（图背单词 + 英文描述 + 双音频）
export interface AdminVocabMediaItem {
  word_id: string
  word: string
  image_urls: string[] | null
  en_description: string | null
  word_audio_url: string | null
  en_desc_audio_url: string | null
  media_status: 'draft' | 'published' | 'retired'
}
export interface AdminVocabMediaListOut {
  total: number
  items: AdminVocabMediaItem[]
}

// 课程单元（含内容完成度统计）
export interface AdminCurriculumUnit {
  unit_id: string
  textbook_version: string
  grade: string
  semester: string
  unit_no: number
  unit_title: string
  kp_count: number       // 单元考点数 = 各短文已关联考点去重汇总
  content_count: number  // 已关联考点的短文数
  passage_count: number  // 短文总数
  word_count: number     // 单元重点单词数
  content_rate: number   // 已关联短文 / 短文总数，0-1
  unit_pdf_url?: string | null   // 拆出的单元独立 PDF(COS)
  status?: string        // 发布闸门:draft/published(学生只见 published)
}

// V2 M28：真题试卷（内部管理，版权规避）
export interface AdminExamPaperItem {
  id: string
  title: string
  textbook_version: string
  grade: string
  semester: string
  region: string | null
  paper_url: string | null
  status: string
  sim_count: number
  created_at: string
}
export interface AdminExamPaperListOut {
  total: number
  items: AdminExamPaperItem[]
}
export interface ExamPaperCreate {
  title: string
  textbook_version: string
  grade: string
  semester: string
  region?: string
  paper_url?: string
}

// ── KP 候选审核（R0.4 KP-First）──────────────────────────────
export type KpCandidateStatus = 'pending' | 'approved' | 'merged' | 'rejected'

export interface KpCandidateItem {
  id: string
  raw_name: string
  name_norm: string
  suggested_axis?: string | null
  suggested_stage?: string | null
  occur_count: number
  source_type?: string | null
  context_sample?: Record<string, unknown> | null
  status: KpCandidateStatus
}

export interface KpCandidateListOut {
  total: number
  items: KpCandidateItem[]
}

export interface KpNodeItem {
  id: string
  axis: string
  node_kind?: string | null
  name: string
  code: string
  applicable_stages?: string[] | null
}

export interface KpNodeListOut {
  total: number
  items: KpNodeItem[]
}

// ── 单元↔知识图谱节点（KP-First R1）────────────────────────
export interface AdminUnitNodeItem {
  node_id: string
  name: string
  axis: string
  node_kind?: string | null
  source: string
}

export interface UnitExtractResult {
  matched: number
  candidate: number
  edges_created: number
}

// ── 通用词库（KP-First R5）──────────────────────────────────
export interface VocabListItem2 {
  id: string
  name: string
  exam_level?: string | null
  source_type?: string | null
  status: string
}

export interface VocabWordItem {
  word_id: string
  word: string
  rank?: number | null
  frequency?: number | null
  star: number
  verified: boolean
}

// 知识图谱总览(D1)
export interface KpNodeOverviewItem {
  id: string
  axis: string
  node_kind?: string | null
  name: string
  code: string
  status: string
  applicable_stages?: string[] | null
  source?: string | null
  lecture_filled: number
  lecture_total: number
  unit_refs: number
  question_refs: number
  alias_count: number
}
export interface KpNodeOverviewOut { total: number; items: KpNodeOverviewItem[] }

// 受控知识树(E1)
export interface NodeTreeItem {
  id: string
  name: string
  axis: string
  node_kind?: string | null
  status: string
  code: string
  applicable_stages?: string[] | null
  source?: string | null
  unit_refs?: number | null
  question_refs?: number | null
  children: NodeTreeItem[]
}

// 节点详情(D2)
// 考点讲解:按类型的教学环节 section(status: empty/draft/published)
export interface LectureSectionCell {
  section_key: string; title: string; order: number
  content_md?: string | null; media_url?: string | null
  status: string; source?: string | null; has_content: boolean
}
export interface NodeLecture {
  kp_type: string; kp_type_label: string
  total: number; filled: number
  sections: LectureSectionCell[]
}
export interface NodeUnitRef { unit_id: string; unit_title: string; textbook_version: string; grade: string; semester: string }
export interface NodeMastery { learners: number; avg?: number | null; mastered: number; mid: number; weak: number }
export interface KpNodeDetail {
  id: string
  axis: string
  node_kind?: string | null
  name: string
  code: string
  status: string
  applicable_stages?: string[] | null
  description?: string | null
  source: string
  lecture: NodeLecture
  aliases: { alias: string; source: string }[]
  units: NodeUnitRef[]
  question_real: number
  question_sim: number
  mastery: NodeMastery
}

// ── 长难句管理(KP-First L7)──────────────────────────────
export interface LSAdminItem {
  id: string
  text: string
  source_kind: string
  status: string
  syntax_points: string[]
  difficulty: number | null
  textbook_version: string | null
  stage: string | null
  grade: string | null
  semester: string | null
  exam_type: string | null
}

export interface LSExtractResult {
  created: number
  long_kept: number
  edges: number
  candidates: number
  skipped_done: number
}

export interface LSConfig {
  sources: string[]
  verify_types: string[]
  min_words: number
  required_pass: number
  textbook_difficulty_min: number | null
  textbook_top_n: number
}

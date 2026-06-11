import request, { unwrap } from './request'
import type {
  AdminQuestionListOut,
  AdminQuestionItem,
  AdminContentListOut,
  AdminContentItem,
  AdminOverview,
  SemesterPricing,
  ReviewStatus,
  AdminCurriculumUnit,
  AdminVocabMediaItem,
  AdminVocabMediaListOut,
  AdminTeacherItem,
  AdminTeacherListOut,
  AdminExamPaperItem,
  AdminExamPaperListOut,
  ExamPaperCreate,
} from '../types'

// ── 数据大盘 ────────────────────────────────────────────────
export function getOverview() {
  return unwrap<AdminOverview>(request.get('/admin/overview'))
}

// ── 仿真题审核 ──────────────────────────────────────────────
export function listQuestions(params: {
  status: ReviewStatus
  kp_id?: string
  skip?: number
  limit?: number
}) {
  return unwrap<AdminQuestionListOut>(
    request.get('/admin/questions', { params }),
  )
}

export function reviewQuestion(id: string, approve: boolean) {
  return unwrap<AdminQuestionItem>(
    request.post(`/admin/questions/${id}/review`, { approve }),
  )
}

// ── 知识点内容审核/编辑 ─────────────────────────────────────
export function listContents(params: {
  status: ReviewStatus
  kp_id?: string
  skip?: number
  limit?: number
}) {
  return unwrap<AdminContentListOut>(
    request.get('/admin/contents', { params }),
  )
}

export function reviewContent(id: string, approve: boolean) {
  return unwrap<AdminContentItem>(
    request.post(`/admin/contents/${id}/review`, { approve }),
  )
}

export function updateContent(id: string, body: { content_md?: string; audio_url?: string }) {
  return unwrap<AdminContentItem>(
    request.put(`/admin/contents/${id}`, body),
  )
}

// ── 定价 ────────────────────────────────────────────────────
export function getPricing() {
  return unwrap<SemesterPricing>(request.get('/admin/pricing'))
}

export function updatePricing(body: SemesterPricing) {
  return unwrap<SemesterPricing>(request.put('/admin/pricing', body))
}

export function getEssayTemplates() {
  return unwrap<Record<string, { template: string; samples: string[] }>>(request.get('/admin/essay-templates'))
}

export function updateEssayTemplates(payload: Record<string, { template: string; samples: string[] }>) {
  return unwrap<Record<string, { template: string; samples: string[] }>>(request.put('/admin/essay-templates', payload))
}

// ── 机构入驻审核（D-123）──
export interface AdminInstitution {
  id: string; name: string; contact_phone: string
  province_code: string; city_code: string; address: string
  status: string; source: string; created_at: string
}

export function createInstitution(data: {
  name: string; contact_phone: string; province_code: string; city_code: string; address: string
}): Promise<AdminInstitution> {
  return unwrap<AdminInstitution>(request.post('/admin/institutions', data))
}
export function listInstitutions(status?: string, source?: string): Promise<AdminInstitution[]> {
  const params = new URLSearchParams()
  if (status) params.set('status', status)
  if (source) params.set('source', source)
  const q = params.toString() ? `?${params.toString()}` : ''
  return unwrap<AdminInstitution[]>(request.get(`/admin/institutions${q}`))
}
export function approveInstitution(id: string, adminUsername: string): Promise<{ institution_id: string; admin_username: string; password: string }> {
  return unwrap(request.post(`/admin/institutions/${id}/approve`, { admin_username: adminUsername }))
}
export function rejectInstitution(id: string): Promise<AdminInstitution> {
  return unwrap<AdminInstitution>(request.post(`/admin/institutions/${id}/reject`))
}

// ── 教师认证管理 ──────────────────────────────────────────────────────────────
export function listTeachersForAdmin(params: {
  cert_status?: string
  skip?: number
  limit?: number
}): Promise<AdminTeacherListOut> {
  return unwrap<AdminTeacherListOut>(request.get('/admin/teachers', { params }))
}

export function reviewTeacherCert(
  teacherId: string,
  approve: boolean,
  reason?: string,
): Promise<AdminTeacherItem> {
  return unwrap<AdminTeacherItem>(
    request.post(`/admin/teachers/${teacherId}/review`, { approve, reason }),
  )
}

// ── 词力通媒体管理 ────────────────────────────────────────────────────────────
export function listVocabMedia(params: {
  media_status?: string
  skip?: number
  limit?: number
}): Promise<AdminVocabMediaListOut> {
  return unwrap<AdminVocabMediaListOut>(request.get('/admin/vocab', { params }))
}

export function generateVocabMedia(wordId: string): Promise<AdminVocabMediaItem> {
  return unwrap<AdminVocabMediaItem>(request.post(`/admin/vocab/${wordId}/generate-media`))
}

export function reviewVocabMedia(wordId: string, approve: boolean): Promise<AdminVocabMediaItem> {
  return unwrap<AdminVocabMediaItem>(request.post(`/admin/vocab/${wordId}/media/review`, { approve }))
}

export function updateVocabMedia(
  wordId: string,
  body: { en_description?: string; image_urls?: string[]; word_audio_url?: string; en_desc_audio_url?: string },
): Promise<AdminVocabMediaItem> {
  return unwrap<AdminVocabMediaItem>(request.put(`/admin/vocab/${wordId}/media`, body))
}

// ── 课程单元管理 ──────────────────────────────────────────────────────────────
export function listCurriculumUnits(): Promise<AdminCurriculumUnit[]> {
  return unwrap<AdminCurriculumUnit[]>(request.get('/admin/curriculum/units'))
}

export interface GenerateUnitResult {
  unit_id: string
  kp_count: number
  content_count: number
  content_rate: number
}

export function generateUnitContent(unitId: string): Promise<GenerateUnitResult> {
  return unwrap<GenerateUnitResult>(
    request.post(`/admin/curriculum/units/${unitId}/generate`)
  )
}

// ── M3 教材 PDF 上传解析 ──────────────────────────────────────────────────────

export interface UnitSegment {
  unit_no: number
  start_page: number
  end_page: number
  detected_title?: string | null
}

export interface PdfUploadOut {
  file_id: string
  filename: string
  total_pages: number
  auto_split_success: boolean
  auto_segments: UnitSegment[]
}

export interface PagePreview {
  page_no: number
  text_snippet: string
}

export interface UnitGenerateResult {
  unit_no: number
  unit_title: string
  kp_count: number
  word_count: number
  status: 'ok' | 'error'
  error?: string | null
}

export interface GenerateFromPdfOut {
  results: UnitGenerateResult[]
  success_count: number
  error_count: number
}

export function uploadCurriculumPdf(file: File): Promise<PdfUploadOut> {
  const form = new FormData()
  form.append('file', file)
  return unwrap<PdfUploadOut>(
    request.post('/admin/curriculum/pdf/upload', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 60000,
    }),
  )
}

export function getPdfPages(fileId: string): Promise<{ file_id: string; total_pages: number; pages: PagePreview[] }> {
  return unwrap(request.get(`/admin/curriculum/pdf/${fileId}/pages`))
}

export function generateFromPdf(
  fileId: string,
  body: { textbook_version: string; grade: string; semester: string; segments: UnitSegment[]; content_status?: string },
): Promise<GenerateFromPdfOut> {
  return unwrap<GenerateFromPdfOut>(
    request.post(`/admin/curriculum/pdf/${fileId}/generate`, { content_status: 'published', ...body }, { timeout: 300000 }),
  )
}

export interface GenerateSemesterResult {
  unit_no: number; unit_title: string; kp_count: number; word_count: number; status: string
}

export function generateSemester(body: {
  textbook_version: string; grade: string; semester: string
  unit_count?: number; content_status?: string; reset?: boolean
}): Promise<GenerateSemesterResult[]> {
  return unwrap<GenerateSemesterResult[]>(
    request.post('/admin/curriculum/generate-semester', { unit_count: 6, content_status: 'published', reset: true, ...body }, { timeout: 300000 }),
  )
}

// ── V2 M28：真题试卷管理 ────────────────────────────────────────────────────────
export function listExamPapers(params?: { skip?: number; limit?: number }): Promise<AdminExamPaperListOut> {
  return unwrap<AdminExamPaperListOut>(request.get('/admin/exam-papers', { params }))
}

export function createExamPaper(body: ExamPaperCreate): Promise<AdminExamPaperItem> {
  return unwrap<AdminExamPaperItem>(request.post('/admin/exam-papers', body))
}

export function generateSimQuestionsFromPaper(paperId: string): Promise<{ paper_id: string; sim_questions_created: number }> {
  return unwrap(request.post(`/admin/exam-papers/${paperId}/generate`))
}

// ── M11 主题中心 ────────────────────────────────────────────────────────────
export interface ThemeTokens {
  c_primary: string; c_primary_deep: string; c_primary_soft: string; c_primary_faint: string
  c_gold: string; c_accent: string; c_olive: string
  c_bg_page: string; c_bg_soft: string; c_border: string
  g_primary: string; g_hero: string; shadow_primary: string
}
export interface ThemePreset { key: string; name: string; desc: string; tokens: ThemeTokens }
export interface ThemeListOut { active_key: string; themes: ThemePreset[] }

export function listThemes(): Promise<ThemeListOut> {
  return unwrap<ThemeListOut>(request.get('/admin/themes'))
}
export function setActiveTheme(key: string): Promise<ThemePreset> {
  return unwrap<ThemePreset>(request.put('/admin/theme', { key }))
}

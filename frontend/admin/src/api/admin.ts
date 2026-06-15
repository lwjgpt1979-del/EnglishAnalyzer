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

export interface TtsSpeed { primary: number; junior: number; senior: number }
export function getTtsSpeed() {
  return unwrap<TtsSpeed>(request.get('/admin/tts-speed'))
}
export function updateTtsSpeed(body: TtsSpeed) {
  return unwrap<TtsSpeed>(request.put('/admin/tts-speed', body))
}

export interface TtsVoices { male: string[]; female: string[] }
export function getTtsVoices() {
  return unwrap<TtsVoices>(request.get('/admin/tts-voices'))
}
export function updateTtsVoices(body: TtsVoices) {
  return unwrap<TtsVoices>(request.put('/admin/tts-voices', body))
}
export function ttsPreview(params: { voice?: string; speed?: number }) {
  return unwrap<{ url: string }>(request.get('/admin/tts-preview', { params }))
}

// ── 口语场景配置 ──
export interface SpeakScenarioCfg { enabled: boolean; prompt: string }
export interface SpeakingConfig {
  special: { wrong: SpeakScenarioCfg; vocab: SpeakScenarioCfg }
  preset: Record<string, SpeakScenarioCfg>
  semester: { enabled: boolean; default_prompt: string; rules: Record<string, string> }
}
export interface SemScopeUnit {
  unit_id: string; textbook_version: string; grade: string
  semester: string; unit_no: number; unit_title: string
}
export function getSpeakingConfig() {
  return unwrap<SpeakingConfig>(request.get('/admin/speaking-config'))
}
export function updateSpeakingConfig(body: SpeakingConfig) {
  return unwrap<SpeakingConfig>(request.put('/admin/speaking-config', body))
}
export function getSpeakingSemesters() {
  return unwrap<SemScopeUnit[]>(request.get('/admin/speaking-config/semesters'))
}

// ── 词力通配图提示词配置 + 批量 ──
export interface VocabImageConfig {
  batch_size: number; images_per_word: number; use_ai_prompt: boolean; primary: string; styles: string[]
}
export interface VocabImageBatchStatus {
  running: boolean; total: number; done: number; ok: number; failed: number
}
export function getVocabImageConfig() {
  return unwrap<VocabImageConfig>(request.get('/admin/vocab-image-config'))
}
export function updateVocabImageConfig(body: VocabImageConfig) {
  return unwrap<VocabImageConfig>(request.put('/admin/vocab-image-config', body))
}
export function startVocabImageBatch() {
  return unwrap<{ started: boolean; total?: number; reason?: string }>(request.post('/admin/vocab-image/batch'))
}
export function getVocabImageBatchStatus() {
  return unwrap<VocabImageBatchStatus>(request.get('/admin/vocab-image/batch/status'))
}

export interface TtsCosUsage { available: boolean; object_count: number; total_bytes: number; total_mb: number }
export interface TtsPrewarmStatus { running: boolean; label: string; total: number; done: number; ok: number; failed: number }
export interface TtsPrewarmSemester { textbook_version: string; grade: string; semester: string; word_count: number }
export function getTtsStats() {
  return unwrap<{ cos: TtsCosUsage; prewarm: TtsPrewarmStatus }>(request.get('/admin/tts-stats'))
}
export function getPrewarmSemesters() {
  return unwrap<TtsPrewarmSemester[]>(request.get('/admin/tts-prewarm/semesters'))
}
export function startPrewarm(body: { textbook_version: string; grade: string; semester: string; scope: string; limit: number }) {
  return unwrap<{ started: boolean; total?: number; label?: string; reason?: string }>(request.post('/admin/tts-prewarm', body))
}
export function getPrewarmStatus() {
  return unwrap<TtsPrewarmStatus>(request.get('/admin/tts-prewarm/status'))
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

// ── 权益体系配置 ──
export interface FeatureRule { mode: string; limit: number | null; period: string | null }
export interface FeatureAddon { enabled: boolean; pack_size: number; price_fen: number }
export interface FeatureItem {
  key: string
  title: string
  module: string
  condition: string | null
  defaults: Record<string, FeatureRule>
  overrides: Record<string, FeatureRule>
  metered: boolean
  addon: FeatureAddon
}
export interface EntitlementsConfig { tiers: string[]; features: FeatureItem[]; top_tier: string }

export function getEntitlements(): Promise<EntitlementsConfig> {
  return unwrap<EntitlementsConfig>(request.get('/admin/entitlements'))
}
export function setEntitlementOverride(body: {
  feature_key: string; tier: string; mode: string; quota_limit?: number | null; quota_period?: string | null
}): Promise<EntitlementsConfig> {
  return unwrap<EntitlementsConfig>(request.put('/admin/entitlements', body))
}
export function clearEntitlementOverride(feature_key: string, tier: string): Promise<EntitlementsConfig> {
  return unwrap<EntitlementsConfig>(request.delete('/admin/entitlements', { params: { feature_key, tier } }))
}
export function setEntitlementAddon(body: {
  feature_key: string; enabled: boolean; pack_size: number; price_fen: number
}): Promise<EntitlementsConfig> {
  return unwrap<EntitlementsConfig>(request.put('/admin/entitlements/addon', body))
}

// ── 退款 / 申诉审核（P3）────────────────────────────────────
export interface AdminRefundItem {
  id: string
  order_id: string
  order_no: string
  kind: string            // refund | appeal
  refund_type: string
  appeal_type: string | null
  state_code: string | null
  status: string          // pending | approved | rejected | completed
  amount_fen: number
  order_amount_fen: number
  reason: string | null
  evidence_urls: string[]
  user_nickname: string | null
  user_phone: string | null
  order_tier: string
  paid_at: string | null
  created_at: string | null
}
export interface AdminRefundListOut { total: number; items: AdminRefundItem[] }

export function listRefunds(params: {
  kind?: string; status?: string; skip?: number; limit?: number
}): Promise<AdminRefundListOut> {
  return unwrap<AdminRefundListOut>(request.get('/admin/refunds', { params }))
}
export function reviewRefund(id: string, body: {
  approve: boolean; amount_fen?: number | null; reason?: string | null
}) {
  return unwrap<{ id: string; status: string; state_code: string; amount_fen: number }>(
    request.post(`/admin/refunds/${id}/review`, body),
  )
}
export function getOrderEvidence(orderId: string): Promise<Record<string, unknown>> {
  return unwrap<Record<string, unknown>>(request.get(`/admin/orders/${orderId}/evidence`))
}

// ── 收款主体（多主体/多渠道）────────────────────────────────
export interface PaymentAccountItem {
  id: string
  name: string
  subject_type: string     // individual | company | subsidiary
  provider: string         // wechat | alipay | apple_iap | ...
  config: Record<string, unknown>
  secret_alias: string | null
  branch_company_id: string | null
  is_default: boolean
  is_active: boolean
  credentials_ready: boolean
  required_secret_keys: string[]
  secrets_set: Record<string, boolean>
  created_at: string | null
}
export interface PaymentAccountCreate {
  name: string; subject_type: string; provider: string
  config?: Record<string, unknown>; secret_alias?: string | null
  branch_company_id?: string | null; is_active?: boolean
}

export function listPaymentAccounts(): Promise<PaymentAccountItem[]> {
  return unwrap<PaymentAccountItem[]>(request.get('/admin/payment-accounts'))
}
export function createPaymentAccount(body: PaymentAccountCreate): Promise<PaymentAccountItem> {
  return unwrap<PaymentAccountItem>(request.post('/admin/payment-accounts', body))
}
export function updatePaymentAccount(id: string, body: Partial<PaymentAccountCreate>): Promise<PaymentAccountItem> {
  return unwrap<PaymentAccountItem>(request.put(`/admin/payment-accounts/${id}`, body))
}
export function setDefaultPaymentAccount(id: string): Promise<PaymentAccountItem> {
  return unwrap<PaymentAccountItem>(request.post(`/admin/payment-accounts/${id}/set-default`))
}
export function togglePaymentAccount(id: string): Promise<PaymentAccountItem> {
  return unwrap<PaymentAccountItem>(request.post(`/admin/payment-accounts/${id}/toggle-active`))
}
/** 录入/更新密钥（加密存库，明文不回传）。值空=删除该密钥。 */
export function setPaymentSecrets(id: string, secrets: Record<string, string>): Promise<PaymentAccountItem> {
  return unwrap<PaymentAccountItem>(request.put(`/admin/payment-accounts/${id}/secrets`, secrets))
}

// ── 财务管理（§5.4）────────────────────────────────────────
export interface FinanceGroup {
  key: string | null; name: string
  gross_yuan: number; refund_yuan: number; net_yuan: number; orders: number; refunds: number
}
export interface FinanceSummary {
  period: { start: string; end: string }; group_by: string
  total: { gross_yuan: number; refund_yuan: number; net_yuan: number; orders: number; refunds: number }
  groups: FinanceGroup[]
}
export function getFinanceSummary(params: { month?: string; group_by?: string }): Promise<FinanceSummary> {
  return unwrap<FinanceSummary>(request.get('/admin/finance/summary', { params }))
}
export interface FinanceSettlement {
  id: string; branch_name: string; period_start: string; period_end: string
  gross_yuan: number; refund_yuan: number; net_yuan: number
  branch_payable_yuan: number; platform_share_yuan: number; status: string
}
export function getSettlements(branch_id?: string): Promise<FinanceSettlement[]> {
  return unwrap<FinanceSettlement[]>(request.get('/admin/finance/settlements', { params: { branch_id } }))
}
export function computeSettlement(body: { branch_id: string; start: string; end: string; persist?: boolean }) {
  return unwrap(request.post('/admin/finance/settlements/compute', body))
}
export async function exportFinance(month?: string): Promise<void> {
  const resp = await request.get('/admin/finance/export', { params: { month }, responseType: 'blob' })
  const url = URL.createObjectURL(resp.data as Blob)
  const a = document.createElement('a')
  a.href = url; a.download = `orders_${month || 'current'}.csv`; a.click()
  URL.revokeObjectURL(url)
}

// ── 用户管理：封禁/解封 ───────────────────────────────────────
export interface AdminUserItem {
  id: string
  nickname: string | null
  phone: string | null
  role: string
  is_active: boolean
  banned: boolean
  ban_reason: string | null
  banned_until: string | null
  ban_type: string | null   // permanent | temporary | null
  created_at: string | null
}
export interface AdminUserListOut { total: number; items: AdminUserItem[] }

export function listUsers(params: { q?: string; skip?: number; limit?: number }): Promise<AdminUserListOut> {
  return unwrap<AdminUserListOut>(request.get('/admin/users', { params }))
}
export function banUser(id: string, reason: string, days: number | null): Promise<AdminUserItem> {
  return unwrap<AdminUserItem>(request.post(`/admin/users/${id}/ban`, { reason, days }))
}
export function unbanUser(id: string): Promise<AdminUserItem> {
  return unwrap<AdminUserItem>(request.post(`/admin/users/${id}/unban`))
}

// ── 项目品牌（项目名）────────────────────────────────────────
export interface Branding { app_name: string; slogan: string }
export function getBranding(): Promise<Branding> {
  return unwrap<Branding>(request.get('/config/branding'))   // 公开，登录前也可读
}
export function setBranding(body: Branding): Promise<Branding> {
  return unwrap<Branding>(request.put('/admin/branding', body))
}

// ── 分公司管理（阶段③：地方子公司）────────────────────────────
export interface BranchCity { id: string; city_code: string; effective_from: string | null; effective_to: string | null }
export interface BranchCompanyItem {
  id: string
  name: string
  contact_phone: string | null
  commission_rate: number | null
  legal_name: string | null
  tax_number: string | null
  bank_name: string | null
  bank_account_set: boolean
  is_active: boolean
  cities: BranchCity[]
  payment_accounts: { id: string; name: string; provider: string }[]
  created_at: string | null
}
export function listBranches(): Promise<BranchCompanyItem[]> {
  return unwrap<BranchCompanyItem[]>(request.get('/admin/branch-companies'))
}
export function createBranch(body: Record<string, unknown>): Promise<{ id: string }> {
  return unwrap<{ id: string }>(request.post('/admin/branch-companies', body))
}
export function updateBranch(id: string, body: Record<string, unknown>) {
  return unwrap(request.put(`/admin/branch-companies/${id}`, body))
}
export function toggleBranch(id: string) {
  return unwrap(request.post(`/admin/branch-companies/${id}/toggle-active`))
}
export function addBranchCity(id: string, city_code: string, effective_from?: string) {
  return unwrap(request.post(`/admin/branch-companies/${id}/cities`, { city_code, effective_from }))
}
export function removeBranchCity(cityId: string) {
  return unwrap(request.delete(`/admin/branch-companies/cities/${cityId}`))
}

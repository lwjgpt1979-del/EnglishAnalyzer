import request, { unwrap } from './request'
import type {
  AdminQuestionListOut,
  AdminQuestionItem,
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
  KpCandidateStatus,
  KpCandidateItem,
  KpCandidateListOut,
  KpNodeItem,
  KpNodeListOut,
  AdminUnitNodeItem,
  UnitExtractResult,
  VocabListItem2,
  VocabWordItem,
  NodeResourceItem2,
  UnitContentOverview,
  VersionDiffOut,
  VersionItem,
  KpNodeOverviewOut,
  KpNodeDetail,
  NodeTreeItem,
  LSAdminItem,
  LSExtractResult,
  LSConfig,
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

// 知识点内容审核已退役:改由 node-resources(node_resource lecture)统一承接。

// ── KP 候选审核（R0.4 KP-First）──────────────────────────────
export function listKpCandidates(params: {
  status: KpCandidateStatus
  axis?: string
  skip?: number
  limit?: number
}) {
  return unwrap<KpCandidateListOut>(
    request.get('/admin/kp-candidates', { params }),
  )
}

export function listKpNodes(params: { axis?: string; stage?: string; q?: string; limit?: number }) {
  return unwrap<KpNodeListOut>(request.get('/admin/kp-nodes', { params }))
}

export function approveKpCandidate(
  id: string,
  body: { axis: string; stage?: string | null; node_kind?: string | null; parent_id?: string | null },
) {
  return unwrap<KpNodeItem>(request.post(`/admin/kp-candidates/${id}/approve`, body))
}

export function mergeKpCandidate(id: string, targetNodeId: string) {
  return unwrap<KpNodeItem>(
    request.post(`/admin/kp-candidates/${id}/merge`, { target_node_id: targetNodeId }),
  )
}

export function rejectKpCandidate(id: string, reason: string) {
  return unwrap<KpCandidateItem>(
    request.post(`/admin/kp-candidates/${id}/reject`, { reason }),
  )
}

// ── 定价 ────────────────────────────────────────────────────
export function getPricing() {
  return unwrap<SemesterPricing>(request.get('/admin/pricing'))
}

export interface LlmModelConfig { model: string; presets: string[]; base_url: string; dev_mock: boolean }
export function getLlmConfig() {
  return unwrap<LlmModelConfig>(request.get('/admin/llm-config'))
}
export function updateLlmConfig(model: string) {
  return unwrap<LlmModelConfig>(request.put('/admin/llm-config', { model }))
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

// 知识点 AI 提示词(按题型,多套选默认)
export interface KpPrompt { id?: string | null; name: string; text: string; question_type: string; is_default: boolean; focus_node_ids?: string[]; min_kp?: number; max_kp?: number }
export function getKpPrompts(): Promise<{ prompts: KpPrompt[] }> {
  return unwrap(request.get('/admin/kp-prompts'))
}
export function saveKpPrompts(prompts: KpPrompt[]): Promise<{ prompts: KpPrompt[] }> {
  return unwrap(request.put('/admin/kp-prompts', { prompts }))
}
export function suggestKpText(text: string, sourceType = '教材'): Promise<QuestionKpRef[]> {
  return unwrap(request.post('/admin/kp-suggest-text', { text, source_type: sourceType }))
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

// ── 单元↔知识图谱对齐（KP-First R1）──────────────────────────
export function reextractUnit(unitId: string): Promise<UnitExtractResult> {
  return unwrap<UnitExtractResult>(
    request.post(`/admin/curriculum/units/${unitId}/extract-kps`)
  )
}

export function listUnitNodes(unitId: string): Promise<{ total: number; items: AdminUnitNodeItem[] }> {
  return unwrap<{ total: number; items: AdminUnitNodeItem[] }>(
    request.get(`/admin/curriculum/units/${unitId}/nodes`)
  )
}

// ── 通用词库（KP-First R5）──────────────────────────────────
export function listVocabLists(params?: { status?: string }) {
  return unwrap<{ items: VocabListItem2[] }>(request.get('/admin/vocab-lists', { params }))
}

export function createVocabList(body: {
  name: string; exam_level?: string; source_type?: string; status?: string
}) {
  return unwrap<VocabListItem2>(request.post('/admin/vocab-lists', body))
}

export function listVocabItems(listId: string, params?: { skip?: number; limit?: number }) {
  return unwrap<{ total: number; items: VocabWordItem[] }>(
    request.get(`/admin/vocab-lists/${listId}/items`, { params }))
}

export function addVocabItems(listId: string, items: Array<{ word: string; rank?: number; star?: number }>) {
  return unwrap<{ total: number; items: VocabWordItem[] }>(
    request.post(`/admin/vocab-lists/${listId}/items`, { items }))
}

// ── 知识节点资源（KP-First R6）──────────────────────────────
export function listNodeResources(params: {
  status?: string; node_id?: string; resource_type?: string; unit_id?: string; skip?: number; limit?: number
}) {
  return unwrap<{ total: number; items: NodeResourceItem2[] }>(
    request.get('/admin/node-resources', { params }))
}

export function addNodeResource(body: {
  node_id: string; resource_type: string; dimension?: string; title?: string
  content_md?: string; media_url?: string; status?: string
}) {
  return unwrap<NodeResourceItem2>(request.post('/admin/node-resources', body))
}

export function updateNodeResource(id: string, body: {
  content_md?: string; media_url?: string; title?: string
}) {
  return unwrap<NodeResourceItem2>(request.put(`/admin/node-resources/${id}`, body))
}

export function reviewNodeResource(id: string, approve: boolean) {
  return unwrap<NodeResourceItem2>(request.post(`/admin/node-resources/${id}/review`, { approve }))
}

// 单元补全总览:每个对齐节点 × 六维讲解状态(缺失/草稿/已发布)
export function unitContentOverview(unitId: string): Promise<UnitContentOverview> {
  return unwrap<UnitContentOverview>(request.get(`/admin/curriculum/units/${unitId}/content-overview`))
}

// 一键发布整单元:所有对齐节点下 draft/reviewing 讲解 → published
export function publishUnit(unitId: string): Promise<{ published: number; already_published: number; missing_dims: number }> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/publish`))
}

// 知识图谱总览(D1)
export function listKnowledgeNodes(params: {
  axis?: string; stage?: string; status?: string; q?: string; skip?: number; limit?: number
}): Promise<KpNodeOverviewOut> {
  return unwrap<KpNodeOverviewOut>(request.get('/admin/knowledge-nodes', { params }))
}
// 受控知识树(E1)
export function getNodeTree(axis?: string, withCounts = false, stage?: string): Promise<{ items: NodeTreeItem[] }> {
  const params: Record<string, unknown> = {}
  if (axis) params.axis = axis
  if (withCounts) params.with_counts = true
  if (stage) params.stage = stage
  return unwrap(request.get('/admin/knowledge-nodes/tree', { params }))
}
export function createKnowledgeNode(body: {
  name: string; parent_id?: string | null; axis?: string; node_kind?: string | null
}): Promise<{ id: string; code: string; name: string }> {
  return unwrap(request.post('/admin/knowledge-nodes', body))
}
export function moveKnowledgeNode(id: string, parentId: string | null): Promise<{ id: string; parent_id: string | null }> {
  return unwrap(request.post(`/admin/knowledge-nodes/${id}/move`, { parent_id: parentId }))
}

// 节点详情 / 维护(D2)
export function getKnowledgeNode(id: string): Promise<KpNodeDetail> {
  return unwrap<KpNodeDetail>(request.get(`/admin/knowledge-nodes/${id}`))
}
// 知识点详情枢纽(F):详解正文 + 反向关联(教材/真题/仿真)+ 关系边
export interface NodeHubQuestion { id: string; question_no?: string | null; section?: string | null; stem?: string | null; status: string; paper_name?: string | null }
export interface NodeHub {
  id: string; name: string; code: string; status: string; node_kind?: string | null; description?: string | null
  lectures: { dimension?: string | null; status?: string | null; content_md?: string | null }[]
  units: { unit_id: string; unit_title?: string; textbook_version?: string; grade?: string; semester?: string }[]
  real_questions: NodeHubQuestion[]; sim_questions: NodeHubQuestion[]
  relations: { node_id: string; name: string; code?: string | null; relation: string }[]
}
export function getNodeHub(id: string): Promise<NodeHub> {
  return unwrap<NodeHub>(request.get(`/admin/knowledge-nodes/${id}/hub`))
}
export function updateKnowledgeNode(id: string, body: {
  name?: string; node_kind?: string | null; applicable_stages?: string[] | null; description?: string | null
}): Promise<KpNodeDetail> {
  return unwrap<KpNodeDetail>(request.patch(`/admin/knowledge-nodes/${id}`, body))
}
export function retireKnowledgeNode(id: string): Promise<{ id: string; status: string }> {
  return unwrap(request.post(`/admin/knowledge-nodes/${id}/retire`))
}
export function restoreKnowledgeNode(id: string): Promise<{ id: string; status: string }> {
  return unwrap(request.post(`/admin/knowledge-nodes/${id}/restore`))
}

// 内容版本对比 / 审核(C2)
export function versionDiff(versionId: string, against = 'current'): Promise<VersionDiffOut> {
  return unwrap<VersionDiffOut>(request.get(`/admin/node-resource-versions/${versionId}/diff`, { params: { against } }))
}
export function approveVersion(versionId: string): Promise<Record<string, string>> {
  return unwrap(request.post(`/admin/node-resource-versions/${versionId}/approve`))
}
export function rejectVersion(versionId: string): Promise<Record<string, string>> {
  return unwrap(request.post(`/admin/node-resource-versions/${versionId}/reject`))
}
// 版本历史 + 回滚(C3)
export function listResourceVersions(resourceId: string): Promise<{ resource_id: string; total: number; items: VersionItem[] }> {
  return unwrap(request.get(`/admin/node-resources/${resourceId}/versions`))
}
export function rollbackVersion(resourceId: string, versionId: string): Promise<Record<string, string>> {
  return unwrap(request.post(`/admin/node-resources/${resourceId}/rollback/${versionId}`))
}

// ── 长难句管理（KP-First L7）──────────────────────────────
export function extractLongSentences(params: { source?: string; limit?: number }) {
  return unwrap<LSExtractResult>(request.post('/admin/long-sentences/extract', null, { params }))
}

export function listLongSentences(params: {
  status?: string; node_id?: string; skip?: number; limit?: number
}) {
  return unwrap<{ total: number; items: LSAdminItem[] }>(
    request.get('/admin/long-sentences', { params }))
}

export function reviewLongSentence(id: string, approve: boolean) {
  return unwrap<LSAdminItem>(request.post(`/admin/long-sentences/${id}/review`, { approve }))
}

export function getLSConfig() {
  return unwrap<LSConfig>(request.get('/admin/long-sentences/config'))
}

export function setLSConfig(body: Partial<LSConfig>) {
  return unwrap<LSConfig>(request.put('/admin/long-sentences/config', body))
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
  page_offset?: number   // 印刷页码 = PDF 页序 − page_offset
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

// 异步生成任务(方案 A)
export interface GenJobCreated { job_id: string; total: number }
export interface GenJob {
  job_id: string
  source: string
  textbook_version: string
  grade: string
  semester: string
  status: 'running' | 'done' | 'failed'
  total: number
  done: number
  failed: number
  results: UnitGenerateResult[]
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
): Promise<GenJobCreated> {
  // 秒回 job_id;后台异步逐单元生成,前端轮询 getGenJob 看进度
  return unwrap<GenJobCreated>(
    request.post(`/admin/curriculum/pdf/${fileId}/generate`, { content_status: 'published', ...body }),
  )
}

export function getGenJob(jobId: string): Promise<GenJob> {
  return unwrap<GenJob>(request.get(`/admin/curriculum/pdf-jobs/${jobId}`))
}

export function listGenJobs(params: {
  status?: string; textbook_version?: string; grade?: string; semester?: string; limit?: number
}): Promise<GenJob[]> {
  return unwrap<GenJob[]>(request.get('/admin/curriculum/pdf-jobs', { params }))
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
  overdue: boolean        // 超 SLA(3天)未处理
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
/** 打开举证包打印版（带 Bearer 取 HTML → 新窗口，浏览器打印为 PDF）*/
export async function openEvidencePdf(orderId: string): Promise<void> {
  const resp = await request.get(`/admin/orders/${orderId}/evidence.html`, { responseType: 'text' })
  const w = window.open('', '_blank')
  if (w) { w.document.open(); w.document.write(resp.data as string); w.document.close() }
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

// ── 数据大盘深化（§5.5）──────────────────────────────────────
export interface DashboardData {
  users: { total: number; roles: Record<string, number>; new_today: number; new_7d: number; new_30d: number; regions_top: { city_code: string; count: number }[] }
  membership: { active_by_tier: Record<string, number>; paid_members: number; pay_conversion_pct: number }
  revenue: { gmv_today_yuan: number; gmv_month_yuan: number; refund_month_yuan: number; refund_rate_pct: number; arpu_month_yuan: number; payers_month: number }
  usage_today: Record<string, number>
  active: { dau: number; mau: number; trend_7d: { date: string; count: number }[] }
  feedback: { diagnosis: number; question: number; pending: number }
  content_quality: {
    review_rate: { total: number; mastered: number; rate_pct: number; by_review: number; by_manual: number; by_unknown: number }
    ocr_success: { wrong_questions: { total: number; completed: number; rate_pct: number }; uploaded_papers: { total: number; completed: number; rate_pct: number } }
    ocr_correction: { completed: number; corrected: number; rate_pct: number }
    practice_split: { free_entry: number; review_triggered: number; total: number; free_pct: number; review_pct: number }
  }
  growth: {
    channels: { total: number; items: { channel: string; label: string; count: number; pct: number }[] }
    renewal: { days: number; overall_rate_pct: number; total_expiring: number; total_renewed: number; by_tier: { tier: string; expiring: number; renewed: number; rate_pct: number }[] }
    funnel: { stages: { key: string; label: string; count: number; pct_of_registered: number; pct_of_prev: number }[] }
  }
  institution: { active: number; renewal: { institutions_purchased: number; institutions_repurchased: number; rate_pct: number } }
  generated_at: string
}
export function getDashboard(): Promise<DashboardData> {
  return unwrap<DashboardData>(request.get('/admin/dashboard'))
}

// ── 发票申请管理（§5.4）──────────────────────────────────────
export interface AdminInvoiceItem {
  id: string; order_id: string; order_no: string | null; payment_account: string | null
  title_type: string; title: string; tax_no: string | null; amount_yuan: number
  content: string | null; email: string | null; status: string
  invoice_no: string | null; invoice_url: string | null; note: string | null
  created_at: string | null; issued_at: string | null
}
export interface AdminInvoiceListOut { total: number; items: AdminInvoiceItem[] }
export function listInvoices(params: { status?: string; skip?: number; limit?: number }): Promise<AdminInvoiceListOut> {
  return unwrap<AdminInvoiceListOut>(request.get('/admin/invoices', { params }))
}
export function issueInvoice(id: string, invoice_no: string, invoice_url?: string) {
  return unwrap(request.post(`/admin/invoices/${id}/issue`, { invoice_no, invoice_url }))
}
export function rejectInvoice(id: string, note?: string) {
  return unwrap(request.post(`/admin/invoices/${id}/reject`, { note }))
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

// ── 内容质量反馈（§5.5）──
export interface ContentFeedbackItem {
  id: string; target_type: string; target_id: string | null; snippet: string | null
  reason: string | null; status: string; note: string | null
  created_at: string | null; handled_at: string | null
}
export interface ContentFeedbackListOut { total: number; items: ContentFeedbackItem[] }
export function listContentFeedback(params: { status?: string; target_type?: string; skip?: number; limit?: number }): Promise<ContentFeedbackListOut> {
  return unwrap<ContentFeedbackListOut>(request.get('/admin/content-feedback', { params }))
}
export function handleContentFeedback(id: string, action: 'handled' | 'dismissed', note?: string) {
  return unwrap(request.post(`/admin/content-feedback/${id}/handle`, { action, note }))
}

// ── 封禁申诉审核 ──
export interface BanAppealItem {
  id: string; user_id: string; reason: string; evidence_urls: string[]
  status: string; note: string | null; nickname: string | null; phone: string | null
  ban_reason: string | null; created_at: string | null; reviewed_at: string | null
}
export interface BanAppealListOut { total: number; items: BanAppealItem[] }
export function listBanAppeals(params: { status?: string; skip?: number; limit?: number }): Promise<BanAppealListOut> {
  return unwrap<BanAppealListOut>(request.get('/admin/ban-appeals', { params }))
}
export function reviewBanAppeal(id: string, approve: boolean, note?: string) {
  return unwrap(request.post(`/admin/ban-appeals/${id}/review`, { approve, note }))
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

// ══ 客服支持体系（§13）═══════════════════════════════════════════
export interface SupportTicketItem {
  id: string; user_id: string; category: string; subject: string
  status: string; last_reply_role: string | null; order_id: string | null
  last_content: string | null; created_at: string | null; updated_at: string | null
}
export interface SupportMessageItem { id: string; sender_role: string; content: string; created_at: string | null }
export function listTickets(params: { status?: string; category?: string; skip?: number; limit?: number }): Promise<{ total: number; items: SupportTicketItem[] }> {
  return unwrap(request.get('/admin/support/tickets', { params }))
}
export function getTicketThread(id: string): Promise<{ ticket: SupportTicketItem; messages: SupportMessageItem[] }> {
  return unwrap(request.get(`/admin/support/tickets/${id}`))
}
export function replyTicket(id: string, content: string) {
  return unwrap(request.post(`/admin/support/tickets/${id}/reply`, { content }))
}
export function closeTicket(id: string) {
  return unwrap(request.post(`/admin/support/tickets/${id}/close`))
}

export interface FaqItem {
  id: string; audience: string; category: string; question: string
  answer: string; sort_order: number; is_active: boolean; updated_at: string | null
}
export function listFaq(params: { audience?: string; skip?: number; limit?: number }): Promise<{ total: number; items: FaqItem[] }> {
  return unwrap(request.get('/admin/faq', { params }))
}
export function createFaq(body: Record<string, unknown>): Promise<{ id: string }> {
  return unwrap(request.post('/admin/faq', body))
}
export function updateFaq(id: string, body: Record<string, unknown>) {
  return unwrap(request.put(`/admin/faq/${id}`, body))
}
export function deleteFaq(id: string) {
  return unwrap(request.delete(`/admin/faq/${id}`))
}

export interface FeedbackItem {
  id: string; user_id: string; kind: string; content: string
  images: string[]; contact: string | null; status: string; note: string | null
  created_at: string | null; handled_at: string | null
}
export function listSuggestions(params: { status?: string; kind?: string; skip?: number; limit?: number }): Promise<{ total: number; items: FeedbackItem[] }> {
  return unwrap(request.get('/admin/feedback/suggestions', { params }))
}
export function handleSuggestion(id: string, action: string, note?: string) {
  return unwrap(request.post(`/admin/feedback/suggestions/${id}/handle`, { action, note }))
}

// ══ 优惠券 / 兑换码（SP-4）════════════════════════════════════════
export interface CouponItem {
  id: string; name: string; discount_type: string; discount_value: number
  min_amount_fen: number; max_discount_fen: number | null; scope: string
  redeem_code: string | null; redeem_quota: number | null; redeemed_count: number
  per_user_limit: number; valid_until: string | null; is_active: boolean
  granted: number; used: number; desc: string; created_at: string | null
}
export function listCoupons(params: { skip?: number; limit?: number }): Promise<{ total: number; items: CouponItem[] }> {
  return unwrap(request.get('/admin/coupons', { params }))
}
export function createCoupon(body: Record<string, unknown>): Promise<{ id: string; redeem_code: string | null }> {
  return unwrap(request.post('/admin/coupons', body))
}
export function setCouponActive(id: string, is_active: boolean) {
  return unwrap(request.post(`/admin/coupons/${id}/active`, { is_active }))
}
export function grantCoupon(id: string, user_ids: string[]): Promise<{ granted: number }> {
  return unwrap(request.post(`/admin/coupons/${id}/grant`, { user_ids }))
}

// ══ §5.6 敏感词库 ════════════════════════════════════════════════
export interface SensitiveWordItem {
  id: string; word: string; category: string; action: string; is_active: boolean; created_at: string | null
}
export function listSensitiveWords(params: { category?: string; q?: string; skip?: number; limit?: number }): Promise<{ total: number; items: SensitiveWordItem[] }> {
  return unwrap(request.get('/admin/sensitive-words', { params }))
}
export function addSensitiveWord(body: { word: string; category?: string; action?: string }): Promise<{ id: string }> {
  return unwrap(request.post('/admin/sensitive-words', body))
}
export function batchAddSensitiveWords(body: { words: string[]; category?: string; action?: string }): Promise<{ added: number }> {
  return unwrap(request.post('/admin/sensitive-words/batch', body))
}
export function updateSensitiveWord(id: string, body: Record<string, unknown>) {
  return unwrap(request.put(`/admin/sensitive-words/${id}`, body))
}
export function deleteSensitiveWord(id: string) {
  return unwrap(request.delete(`/admin/sensitive-words/${id}`))
}

// ══ §5.7 定价历史 ════════════════════════════════════════════════
export interface PriceHistoryItem { id: string; snapshot: Record<string, number>; changed_by: string | null; created_at: string | null }
export function getPricingHistory(limit = 50): Promise<PriceHistoryItem[]> {
  return unwrap(request.get('/admin/pricing/history', { params: { limit } }))
}

// ══ §5.8 老师认证增强 ════════════════════════════════════════════
export function claimTeacherCert(teacherId: string) {
  return unwrap(request.post(`/admin/teachers/${teacherId}/claim`))
}
export interface CertQuality {
  days: number; applied: number; reviewed: number; certified: number; pending: number
  pass_rate_pct: number; reject_reasons_top: { reason: string; count: number }[]
}
export function getCertQuality(days = 30): Promise<CertQuality> {
  return unwrap(request.get('/admin/teachers/cert-quality', { params: { days } }))
}

// ══ §5.7 限时活动价 campaign ══════════════════════════════════════
export interface CampaignItem {
  id: string; name: string
  price_basic: number | null; price_pro: number | null; price_promax: number | null
  starts_at: string | null; ends_at: string | null
  limit_type: string; total_quota: number | null; sold_count: number
  is_promotional: boolean; is_active: boolean; status: string; created_at: string | null
}
export function listCampaigns(params: { skip?: number; limit?: number }): Promise<{ total: number; items: CampaignItem[] }> {
  return unwrap(request.get('/admin/promo-campaigns', { params }))
}
export function createCampaign(body: Record<string, unknown>): Promise<{ id: string }> {
  return unwrap(request.post('/admin/promo-campaigns', body))
}
export function setCampaignActive(id: string, is_active: boolean) {
  return unwrap(request.post(`/admin/promo-campaigns/${id}/active`, { is_active }))
}

// ══ §5.6 公告管理 ════════════════════════════════════════════════
export interface AnnouncementItem {
  id: string; title: string; content: string; audience: string
  target_values: string[]; pinned: boolean; is_active: boolean
  starts_at: string | null; ends_at: string | null; created_at: string | null
}
export function listAnnouncements(params: { skip?: number; limit?: number }): Promise<{ total: number; items: AnnouncementItem[] }> {
  return unwrap(request.get('/admin/announcements', { params }))
}
export function createAnnouncement(body: Record<string, unknown>): Promise<{ id: string }> {
  return unwrap(request.post('/admin/announcements', body))
}
export function updateAnnouncement(id: string, body: Record<string, unknown>) {
  return unwrap(request.put(`/admin/announcements/${id}`, body))
}
export function deleteAnnouncement(id: string) {
  return unwrap(request.delete(`/admin/announcements/${id}`))
}

// ══ §5.6 老师月度限额 ════════════════════════════════════════════
export interface TeacherLimits {
  max_students: number; monthly_paper_quota: number; monthly_grading_quota: number
  warn_threshold_pct: number; reset_day: number
}
export function getTeacherLimits(): Promise<TeacherLimits> {
  return unwrap(request.get('/admin/teacher-limits'))
}
export function updateTeacherLimits(body: Partial<TeacherLimits>): Promise<TeacherLimits> {
  return unwrap(request.put('/admin/teacher-limits', body))
}
export function setTeacherLimitOverride(teacherId: string, body: Record<string, number | null>) {
  return unwrap(request.post(`/admin/teachers/${teacherId}/limits`, body))
}

// ══ §5.6 学习信息变更月度上限 ════════════════════════════════════
export function getInfoChangeLimit(): Promise<{ limit: number }> {
  return unwrap(request.get('/admin/info-change-limit'))
}
export function setInfoChangeLimit(limit: number): Promise<{ limit: number }> {
  return unwrap(request.put('/admin/info-change-limit', { limit }))
}

// ══ §9.1 机构套餐（配置驱动）════════════════════════════════════
export interface PackageTier { key: string; name: string; teacher_seats: number; paper_pool: number; grading_pool: number }
export interface PackageConfig { tiers: PackageTier[]; warn_threshold_pct: number; reset_day: number }
export function getInstitutionPackages(): Promise<PackageConfig> {
  return unwrap(request.get('/admin/institution-packages'))
}
export function updateInstitutionPackages(body: PackageConfig): Promise<PackageConfig> {
  return unwrap(request.put('/admin/institution-packages', body))
}
export function setInstitutionPackage(institutionId: string, body: Record<string, unknown>) {
  return unwrap(request.post(`/admin/institutions/${institutionId}/package`, body))
}
export interface PackageUsageBlock { used: number; limit: number; remaining: number; remaining_pct: number }
export interface PackageUsage {
  package_tier: string | null; package_name?: string; is_custom?: boolean
  warn_threshold_pct?: number; reset_day?: number
  teacher_seats?: PackageUsageBlock; paper?: PackageUsageBlock; grading?: PackageUsageBlock
}
export function getInstitutionPackageUsage(institutionId: string): Promise<PackageUsage> {
  return unwrap(request.get(`/admin/institutions/${institutionId}/package-usage`))
}

// ── 平台真题(KP-First TK1-3)──────────────────────────────
export interface PlatformQuestion {
  id: string
  type: string                 // real|sim
  parent_real_id?: string | null
  is_fallback: boolean
  question_type?: string | null
  stem?: string | null
  answer?: string | null
  difficulty?: number | null
  status: string
  block_id?: string | null      // 题组(短文)外键;同篇阅读/完形小问共享
  passage?: string | null       // 题组短文正文
}
export interface ParsedRealQuestion {
  question_no?: string | null
  question_type?: string | null
  stem?: string | null
  answer?: string | null
  explanation?: string | null
  passage?: string | null        // 题组短文(阅读/完形/信息还原);独立题为空
  block_key?: string | null      // 同短文小问共享;独立题为空
  section?: string | null        // 原卷大题名(听力选择/单项填空/完形填空…)
}

// ── 平台试卷(整卷聚合)──────────────────────────────────────
export interface PlatformPaper {
  id: string
  name: string
  textbook_version?: string | null
  stage?: string | null
  grade?: string | null
  semester?: string | null
  region_name?: string | null
  exam_type?: string | null
  status: string
  question_count: number
  published_count: number
  created_at?: string | null
}
export interface QuestionKpRef { node_id: string; name: string; code?: string | null }
export interface PaperQuestion {
  id: string
  question_no?: string | null
  section?: string | null
  question_type?: string | null
  stem?: string | null
  answer?: string | null
  difficulty?: number | null
  status: string
  block_id?: string | null
  passage?: string | null
  kps?: QuestionKpRef[]
}
export interface PaperDetail { paper: PlatformPaper; questions: PaperQuestion[] }

export function listPlatformPapers(params: {
  status?: string; textbook_version?: string; stage?: string; grade?: string
  exam_type?: string; region_code?: string; skip?: number; limit?: number
}): Promise<{ total: number; items: PlatformPaper[] }> {
  return unwrap(request.get('/admin/platform-papers', { params }))
}
export function getPlatformPaper(paperId: string): Promise<PaperDetail> {
  return unwrap(request.get(`/admin/platform-papers/${paperId}`))
}
export function publishPlatformPaper(paperId: string): Promise<PlatformPaper> {
  return unwrap(request.post(`/admin/platform-papers/${paperId}/publish`))
}
export function deletePlatformPapers(paperIds: string[]): Promise<{ deleted: number }> {
  return unwrap(request.post('/admin/platform-papers/delete', { paper_ids: paperIds }))
}
export function genSimBulk(questionIds: string[], count = 3): Promise<{ generated: number; per_question: number }> {
  return unwrap(request.post('/admin/platform-questions/gen-sim-bulk', { question_ids: questionIds, count }))
}
export function attachQuestionKp(questionId: string, nodeId: string): Promise<QuestionKpRef[]> {
  return unwrap(request.post(`/admin/platform-questions/${questionId}/kp`, { node_id: nodeId }))
}
export function detachQuestionKp(questionId: string, nodeId: string): Promise<QuestionKpRef[]> {
  return unwrap(request.delete(`/admin/platform-questions/${questionId}/kp/${nodeId}`))
}
export function attachSectionKp(paperId: string, section: string, nodeId: string): Promise<{ attached: number }> {
  return unwrap(request.post(`/admin/platform-papers/${paperId}/section-kp`, { section, node_id: nodeId }))
}
export function attachKpBulk(pairs: { question_id: string; node_id: string }[]): Promise<{ attached: number }> {
  return unwrap(request.post('/admin/platform-questions/kp-bulk', { pairs }))
}
export interface SuggestKpItem { question_id: string; suggestions: QuestionKpRef[] }
export function suggestPaperKp(paperId: string, opts?: { sections?: string[]; prompt_id?: string }): Promise<{ items: SuggestKpItem[] }> {
  return unwrap(request.post(`/admin/platform-papers/${paperId}/suggest-kp`, opts || {}))
}
export interface RealExtractJob {
  job_id: string
  source: string
  status: 'running' | 'done' | 'failed'
  error?: string | null
  parsed: ParsedRealQuestion[]
}

export function listPlatformQuestions(params: {
  type?: string; status?: string; node_id?: string; skip?: number; limit?: number
}): Promise<{ total: number; items: PlatformQuestion[] }> {
  return unwrap(request.get('/admin/platform-questions', { params }))
}

export function extractRealQuestions(opts: { file?: File; imageUrls?: string[] }): Promise<{ job_id: string }> {
  const form = new FormData()
  if (opts.file) form.append('file', opts.file)
  if (opts.imageUrls?.length) form.append('image_urls', JSON.stringify(opts.imageUrls))
  return unwrap(request.post('/admin/platform-questions/extract', form, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
  }))
}

export function getExtractJob(jobId: string): Promise<RealExtractJob> {
  return unwrap(request.get(`/admin/platform-questions/extract-jobs/${jobId}`))
}

// 真题图片直传:presign → PUT 到 COS → 拿 file_url 走 OCR
export interface AdminPresign { presign_url: string; file_url: string; key: string; expires_in: number; is_mock: boolean }
export function adminPresign(contentType: string): Promise<AdminPresign> {
  return unwrap(request.post('/admin/uploads/presign', { content_type: contentType }))
}
const _IMG_MIME: Record<string, string> = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp', gif: 'image/gif' }
/** 上传单张图片到 COS,返回可访问 file_url。dev(is_mock)跳过 PUT 直接用占位图。 */
export async function uploadImageViaPresign(file: File): Promise<string> {
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  const contentType = file.type || _IMG_MIME[ext] || 'image/jpeg'
  const ps = await adminPresign(contentType)
  if (!ps.is_mock) {
    const r = await fetch(ps.presign_url, { method: 'PUT', body: file, headers: { 'Content-Type': contentType } })
    if (r.status !== 200 && r.status !== 204) throw new Error(`COS 上传失败:HTTP ${r.status}`)
  }
  return ps.file_url
}

export function bulkImportRealQuestions(
  items: Array<{ stem: string; options?: unknown; answer?: string | null; question_type?: string | null
    explanation?: string | null; difficulty?: number | null; question_no?: string | null; kp_names?: string[]
    passage?: string | null; block_key?: string | null; section?: string | null }>,
  opts?: { status?: string; stage_hint?: string; meta?: Record<string, unknown>; paper_name?: string },
): Promise<{ imported: number; failed: number; paper_id?: string | null }> {
  return unwrap(request.post('/admin/platform-questions/bulk', { items, ...opts }))
}

export function genSimFromReal(realId: string, count = 3): Promise<{ generated: number; sim_ids: string[] }> {
  return unwrap(request.post(`/admin/platform-questions/${realId}/gen-sim`, null, { params: { count } }))
}

export function reviewPlatformQuestion(id: string, approve: boolean): Promise<PlatformQuestion> {
  return unwrap(request.post(`/admin/platform-questions/${id}/review`, { approve }))
}

// ── 行政区划地区(后端唯一源,懒加载)──────────────────────────
export interface RegionNode { code: string; name: string; parent_code: string | null; level: number; leaf: boolean }
export function listRegions(parent?: string): Promise<RegionNode[]> {
  return unwrap(request.get('/regions', { params: parent ? { parent } : {} }))
}
// 后台维护
export function adminListRegions(parent?: string): Promise<RegionNode[]> {
  return unwrap(request.get('/admin/regions', { params: parent ? { parent } : {} }))
}
export function createRegion(body: { code: string; name: string; parent_code?: string | null; level: number }): Promise<RegionNode> {
  return unwrap(request.post('/admin/regions', body))
}
export function updateRegion(code: string, name: string): Promise<RegionNode> {
  return unwrap(request.put(`/admin/regions/${code}`, { name }))
}
export function deleteRegion(code: string): Promise<{ deleted: string }> {
  return unwrap(request.delete(`/admin/regions/${code}`))
}

import request, { unwrap } from './request'
import type {
  AdminOverview,
  SemesterPricing,
  InstitutionCodePricing,
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

// R8 Phase6a-2 part2 已退役 listQuestions/reviewQuestion(读旧 /admin/questions=simulated_questions,
// 前端零调用)——仿真题审核走节点化 platform_question(listPlatformQuestions type='sim' + reviewPlatformBulk)。

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

export interface LlmModelConfig { model: string; presets: string[]; available?: string[]; base_url: string; dev_mock: boolean }
export function getLlmConfig() {
  return unwrap<LlmModelConfig>(request.get('/admin/llm-config'))
}
export function updateLlmConfig(model: string) {
  return unwrap<LlmModelConfig>(request.put('/admin/llm-config', { model }))
}

export interface LlmUsage {
  days: number
  total_calls: number
  total_prompt_tokens: number
  total_completion_tokens: number
  est_cost: number
  by_model: { model: string; calls: number; prompt_tokens: number; completion_tokens: number; cost: number }[]
  by_feature: { feature: string; calls: number; prompt_tokens: number; completion_tokens: number }[]
  by_day: { day: string; calls: number; prompt_tokens: number; completion_tokens: number }[]
}
export function getLlmUsage(days = 30) {
  return unwrap<LlmUsage>(request.get('/admin/llm-usage', { params: { days } }))
}

export interface LlmBalance {
  ok: boolean; reason?: string
  available?: boolean; currency?: string; total?: number; granted?: number; topped_up?: number
  low?: boolean; threshold?: number
}
export function getLlmBalance() {
  return unwrap<LlmBalance>(request.get('/admin/llm-balance'))
}

export interface ParaphraseBackfillResult { scanned: number; filled: number; stopped: boolean; spent_tokens: number }
export function backfillParaphrase(params: { limit?: number; only_missing?: boolean; max_tokens_budget?: number }) {
  return unwrap<ParaphraseBackfillResult>(request.post('/admin/long-sentences/paraphrase-backfill', null, { params }))
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
export interface KpPrompt { id?: string | null; name: string; text: string; question_type: string; is_default: boolean; focus_node_ids?: string[]; min_kp?: number; max_kp?: number; focus_ranges?: Record<string, [number, number]> }
export function getKpPrompts(scope?: string): Promise<{ prompts: KpPrompt[]; passage_include_skill: boolean }> {
  return unwrap(request.get('/admin/kp-prompts', { params: scope ? { scope } : {} }))
}
export function saveKpPrompts(prompts: KpPrompt[], scope?: string, passageIncludeSkill = false): Promise<{ prompts: KpPrompt[]; passage_include_skill: boolean }> {
  return unwrap(request.put('/admin/kp-prompts', { prompts, scope: scope || null, passage_include_skill: passageIncludeSkill }))
}
// 已定制(有独立提示词)的学期 scope 串列表
export function getKpPromptScopes(): Promise<string[]> {
  return unwrap(request.get('/admin/kp-prompts/scopes'))
}
// 删除某学期定制,恢复继承全局默认
export function deleteKpPromptScope(scope: string): Promise<{ deleted: boolean }> {
  return unwrap(request.delete('/admin/kp-prompts/scope', { params: { scope } }))
}
export function suggestKpText(text: string, sourceType = '教材·其他'): Promise<QuestionKpRef[]> {
  // AI 调用慢,放宽超时(默认 20s 不够)
  return unwrap(request.post('/admin/kp-suggest-text', { text, source_type: sourceType }, { timeout: 90000 }))
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
export function listInstitutions(params?: { status?: string; source?: string; skip?: number; limit?: number }):
  Promise<{ total: number; items: AdminInstitution[] }> {
  return unwrap(request.get('/admin/institutions', { params }))
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
  q?: string
  textbook?: string
  grade?: string
  semester?: string
  unit_id?: string
}): Promise<AdminVocabMediaListOut> {
  return unwrap<AdminVocabMediaListOut>(request.get('/admin/vocab', { params }))
}
export interface VocabTextbookOptions { textbook_versions: string[]; grades: string[]; semesters: string[] }
export function vocabTextbookOptions() {
  return unwrap<VocabTextbookOptions>(request.get('/admin/vocab/textbook-options'))
}
export interface VocabUnitOption { id: string; unit_no: number; unit_title: string }
export function vocabUnitOptions(params: { textbook?: string; grade?: string; semester?: string }) {
  return unwrap<VocabUnitOption[]>(request.get('/admin/vocab/unit-options', { params }))
}

export function generateVocabMedia(wordId: string): Promise<AdminVocabMediaItem> {
  // 生成媒体(LLM 描述+配图+双 TTS)较慢,放长超时避免默认 20s 超时
  return unwrap<AdminVocabMediaItem>(request.post(`/admin/vocab/${wordId}/generate-media`, undefined, { timeout: 120000 }))
}
// 批量彻底删除词条(连带清 课程/学习/发音日志 等引用,不可恢复)
export function deleteVocabWords(wordIds: string[]) {
  return unwrap<{ deleted: number }>(
    request.post('/admin/vocab/media/delete-batch', { word_ids: wordIds }))
}
// 生成动图 GIF(动作/过程词;静态词返回 animated=false)
export function generateVocabGif(wordId: string): Promise<AdminVocabMediaItem & { animated: boolean }> {
  // GIF = 1 图生 + 2 图生图 + 拼图 + 传 COS,较慢,放长超时(3 分钟)避免默认 20s 超时
  return unwrap<AdminVocabMediaItem & { animated: boolean }>(
    request.post(`/admin/vocab/${wordId}/generate-gif`, undefined, { timeout: 180000 }))
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
export interface CurriculumUnitsResp {
  total: number
  items: AdminCurriculumUnit[]
  options: { textbooks: string[]; grades: string[]; all_grades?: string[]; semesters: string[] }
}
export function listCurriculumUnits(params?: {
  textbook_version?: string; grade?: string; semester?: string; skip?: number; limit?: number
}): Promise<CurriculumUnitsResp> {
  return unwrap<CurriculumUnitsResp>(request.get('/admin/curriculum/units', { params }))
}

// 改单元基础字段(标题/教材/年级/学期/Unit 号;只传的才改,身份重复后端 409)
export function updateCurriculumUnit(unitId: string, body: {
  textbook_version?: string; grade?: string; semester?: string; unit_no?: number; unit_title?: string
}): Promise<AdminCurriculumUnit> {
  return unwrap<AdminCurriculumUnit>(request.patch(`/admin/curriculum/units/${unitId}`, body))
}

// 批量删除单元(连带知识图谱边 / 单词通词表 / 短文及考点边;返回删除数)
export function deleteCurriculumUnits(unitIds: string[]): Promise<{ deleted: number }> {
  return unwrap(request.post('/admin/curriculum/units/delete', { unit_ids: unitIds }))
}

// ── 教材主数据(版本/年级/学期 唯一真源 + 上下架)──────────────────────────────
// 上下架已从「课程单元页」移到独立的「教材版本维护」页(curriculum_catalog)。
export interface CatalogItem {
  id: string
  textbook_version: string
  grade: string
  semester: string
  status: 'draft' | 'published'
  sort_order?: number
}
export interface CatalogListResp { total: number; items: CatalogItem[] }
export interface CatalogOptions { textbook_versions: string[]; grades: string[]; semesters: string[] }

export function listCatalog(params?: {
  textbook_version?: string; grade?: string; semester?: string; skip?: number; limit?: number
}): Promise<CatalogListResp> {
  return unwrap<CatalogListResp>(request.get('/admin/curriculum/catalog', { params }))
}
export function getCatalogOptions(): Promise<CatalogOptions> {
  return unwrap<CatalogOptions>(request.get('/admin/curriculum/catalog/options'))
}
export function addCatalog(body: { textbook_version: string; grade: string; semester: string }): Promise<CatalogItem> {
  return unwrap<CatalogItem>(request.post('/admin/curriculum/catalog', body))
}
export function setCatalogStatus(catalogId: string, status: 'draft' | 'published'): Promise<{ updated: number }> {
  return unwrap(request.put(`/admin/curriculum/catalog/${catalogId}/status`, { status }))
}
export function deleteCatalog(catalogId: string): Promise<{ deleted: number }> {
  return unwrap(request.delete(`/admin/curriculum/catalog/${catalogId}`))
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
export interface PassageKp { node_id: string; name: string; code: string }
export interface UnitPassage { id: string; unit_id: string; kind: string; title: string | null; text: string; sort_order: number; kps: PassageKp[] }
export function getUnitPassages(unitId: string): Promise<{ total: number; items: UnitPassage[] }> {
  return unwrap(request.get(`/admin/curriculum/units/${unitId}/passages`))
}
// 从单元原文(PDF)AI 析出短文,整体覆盖旧短文;返回最新短文 + generated 条数
export function generateUnitPassages(unitId: string): Promise<{ total: number; items: UnitPassage[]; generated: number }> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/passages/generate`, {}, { timeout: 120000 }))
}
// 同源代理取单元 PDF 字节(authed);返回 Blob,前端转 blob: URL 内嵌预览(绕过跨域 iframe 不渲染)
export function fetchUnitPdfBlob(unitId: string): Promise<Blob> {
  return request.get(`/admin/curriculum/units/${unitId}/pdf`,
    { responseType: 'blob', timeout: 120000 }).then(r => r.data as Blob)
}

// ── 单元结构化解析(语法点+分级句 / 听力考点+句组 / 作文要求+正文)──
export interface UnitSentence { id: string; text: string; difficulty: number | null; syntax_points: string[] }
export interface UnitSectionItem { id: string; point_name: string | null; node_id: string | null; node_code: string | null; node_name?: string | null; sentences: UnitSentence[] }
export interface UnitStructured {
  grammar: UnitSectionItem[]
  listening: UnitSectionItem[]
  writing: { id: string; requirement: string | null; body_text: string | null } | null
  counts?: { grammar: number; listening: number; writing: number; sentences: number }
}
export function getUnitStructured(unitId: string): Promise<UnitStructured> {
  return unwrap(request.get(`/admin/curriculum/units/${unitId}/structured`))
}
export function generateUnitStructured(unitId: string): Promise<UnitStructured> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/structured/generate`, {}, { timeout: 180000 }))
}
// 第二步:语法点→词法/句法、听力考点→听力,一键关联(命中关联,未命中留待人工)
export function linkUnitStructured(unitId: string): Promise<UnitStructured & { link_counts?: { linked: number; unmatched: number; skipped: number } }> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/structured/link`, {}, { timeout: 120000 }))
}
// 人工挂靠:把某板块关联到图谱里已存在的节点
export function linkSectionNode(sectionId: string, nodeId: string): Promise<{ node_id: string; node_code: string; name: string }> {
  return unwrap(request.post(`/admin/curriculum-unit-sections/${sectionId}/link-node`, { node_id: nodeId }))
}
// 取消关联:清该板块的图谱节点(单元内无其它板块挂同节点时一并删聚合边)
export function unlinkSectionNode(sectionId: string): Promise<{ section_id: string; unlinked: boolean }> {
  return unwrap(request.post(`/admin/curriculum-unit-sections/${sectionId}/unlink-node`, {}))
}
// 目录没有→在所选父分类下新建图谱节点(手工标签)并挂靠
export function newNodeForSection(sectionId: string, parentId: string, name: string): Promise<{ node_id: string; node_code: string; name: string }> {
  return unwrap(request.post(`/admin/curriculum-unit-sections/${sectionId}/new-node`, { parent_id: parentId, name }))
}
// 单元考点 = 单元解析里语法点/听力已关联知识图谱的节点(去重)
export interface UnitLinkedNode { node_id: string; node_code: string; node_name: string; kinds: string[]; points: string[] }
export function getUnitLinkedNodes(unitId: string): Promise<{ items: UnitLinkedNode[] }> {
  return unwrap(request.get(`/admin/curriculum/units/${unitId}/linked-nodes`))
}

// ── 单元重点单词 ↔ 词力通 ──
export interface UnitWordItem {
  word_id?: string; word: string; phonetic?: string | null; meaning?: string | null
  pos?: string | null; type?: string; is_core?: boolean; sort_order?: number
}
export function getUnitWords(unitId: string): Promise<{ items: UnitWordItem[] }> {
  return unwrap(request.get(`/admin/curriculum/units/${unitId}/words`))
}
export function saveUnitWords(unitId: string, items: UnitWordItem[], isCore = true):
  Promise<{ items: UnitWordItem[]; counts: { linked: number; created: number; total: number } }> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/words`, { items, is_core: isCore }))
}
export function deleteUnitWord(unitId: string, wordId: string): Promise<{ ok: boolean }> {
  return unwrap(request.delete(`/admin/curriculum/units/${unitId}/words/${wordId}`))
}
export function ocrUnitWords(unitId: string, images: string[]): Promise<{ items: UnitWordItem[] }> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/words/ocr`, { images }, { timeout: 180000 }))
}
export function parseUnitWordsText(unitId: string, text: string): Promise<{ items: UnitWordItem[] }> {
  return unwrap(request.post(`/admin/curriculum/units/${unitId}/words/parse-text`, { text }, { timeout: 120000 }))
}

export function suggestPassageKp(passageId: string): Promise<{ items: PassageKp[] }> {
  return unwrap(request.post(`/admin/unit-passages/${passageId}/suggest-kp`, {}, { timeout: 90000 }))
}
export function attachPassageKp(passageId: string, nodeId: string): Promise<{ ok: boolean }> {
  return unwrap(request.post(`/admin/unit-passages/${passageId}/kp`, { node_id: nodeId }))
}
export function detachPassageKp(passageId: string, nodeId: string): Promise<{ ok: boolean }> {
  return unwrap(request.delete(`/admin/unit-passages/${passageId}/kp/${nodeId}`))
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

// 知识图谱总览(D1)
export function listKnowledgeNodes(params: {
  axis?: string; stage?: string; status?: string; q?: string
  linked?: 'unit' | 'question' | 'both'; roots?: string[]; skip?: number; limit?: number
}): Promise<KpNodeOverviewOut> {
  const p: Record<string, unknown> = { ...params }
  if (params.roots?.length) p.roots = params.roots.join(',')   // 多选根目录 → 逗号分隔
  else delete p.roots
  return unwrap<KpNodeOverviewOut>(request.get('/admin/knowledge-nodes', { params: p }))
}
// 根目录(顶层分类)选项——多选过滤下拉
export interface KnowledgeRoot { id: string; name: string; code: string; axis: string }
export function listKnowledgeRoots(): Promise<KnowledgeRoot[]> {
  return unwrap<KnowledgeRoot[]>(request.get('/admin/knowledge-nodes/roots'))
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

// 教材高频词统计
export interface WordStatRow { word: string; unit_count: number; gloss: string; star: number }
export interface WordStats { totals: { words: number; high_freq: number; max_units: number }; items: WordStatRow[]; options: { textbooks: string[]; grades: string[] } }
export function getTextbookWordStats(textbook?: string, grade?: string): Promise<WordStats> {
  const params: Record<string, string> = {}
  if (textbook) params.textbook = textbook
  if (grade) params.grade = grade
  return unwrap(request.get('/admin/textbook-word-stats', { params }))
}

// 考试类型统计
export interface ExamStatRow { id: string; name: string; code: string; 普通: number; 中考: number; 高考: number; 合计: number }
export interface ExamStatOptions { textbooks: string[]; stages: string[]; grades: string[]; regions: { code: string; name: string }[] }
export interface ExamStats { totals: { 普通: number; 中考: number; 高考: number; 合计: number }; items: ExamStatRow[]; options: ExamStatOptions }
export interface ExamStatFilter { grp?: string; textbook?: string; stage?: string; grade?: string; region_code?: string; exam_type?: string }
export function getKpExamStats(f: ExamStatFilter = {}): Promise<ExamStats> {
  const params: Record<string, string> = {}
  for (const [k, v] of Object.entries(f)) if (v) params[k] = v
  return unwrap(request.get('/admin/kp-exam-stats', { params }))
}

// 节点详情 / 维护(D2)
export function getKnowledgeNode(id: string): Promise<KpNodeDetail> {
  return unwrap<KpNodeDetail>(request.get(`/admin/knowledge-nodes/${id}`))
}

// ── 考点讲解(kp_lecture):按类型的教学环节 补全 / AI 生成 / 发布 ──────────────────
import type { NodeLecture } from '../types'
export function getNodeLecture(nodeId: string): Promise<NodeLecture> {
  return unwrap<NodeLecture>(request.get(`/admin/knowledge-nodes/${nodeId}/lecture`))
}
export function upsertLectureSection(nodeId: string, sectionKey: string,
  body: { content_md?: string; media_url?: string }): Promise<{ id: string; status: string; title: string }> {
  return unwrap(request.put(`/admin/knowledge-nodes/${nodeId}/lecture/${sectionKey}`, body))
}
export function generateLectureSection(nodeId: string, sectionKey: string): Promise<{ content_md: string; status: string }> {
  return unwrap(request.post(`/admin/knowledge-nodes/${nodeId}/lecture/${sectionKey}/generate`, {}, { timeout: 120000 }))
}
export function generateMissingLecture(nodeId: string): Promise<{ generated: number }> {
  return unwrap(request.post(`/admin/knowledge-nodes/${nodeId}/lecture/generate-missing`, {}, { timeout: 300000 }))
}
// 批量:勾选多个考点,并发 AI 生成各自缺失讲解环节
export function bulkGenerateLecture(nodeIds: string[]): Promise<{ nodes: number; sections_missing: number; generated: number; failed: number }> {
  return unwrap(request.post('/admin/knowledge-nodes/bulk-generate-lecture', { node_ids: nodeIds }, { timeout: 600000 }))
}
// 批量:把勾选/全部考点的讲解整体发布(默认)或下架(仅翻状态)
export function bulkPublishLecture(nodeIds: string[], status: 'draft' | 'published' = 'published'): Promise<{ nodes: number; updated: number }> {
  return unwrap(request.post('/admin/knowledge-nodes/bulk-publish-lecture', { node_ids: nodeIds, status }, { timeout: 120000 }))
}
export function setLectureSectionStatus(nodeId: string, sectionKey: string, status: 'draft' | 'published'): Promise<{ updated: number }> {
  return unwrap(request.put(`/admin/knowledge-nodes/${nodeId}/lecture/${sectionKey}/status`, { status }))
}
export function publishAllLecture(nodeId: string, status: 'draft' | 'published'): Promise<{ updated: number }> {
  return unwrap(request.put(`/admin/knowledge-nodes/${nodeId}/lecture/publish-all`, { status }))
}
export function deleteLectureSection(nodeId: string, sectionKey: string): Promise<{ deleted: number }> {
  return unwrap(request.delete(`/admin/knowledge-nodes/${nodeId}/lecture/${sectionKey}`))
}
// 知识点详情枢纽(F):详解正文 + 反向关联(教材/真题/仿真)+ 关系边
export interface NodeHubQuestion { id: string; question_no?: string | null; section?: string | null; stem?: string | null; status: string; paper_name?: string | null }
export interface NodeHub {
  id: string; name: string; code: string; status: string; node_kind?: string | null; description?: string | null
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
// 硬删除节点(连带挂边;有子节点会被后端拒绝)
export function deleteKnowledgeNode(id: string): Promise<{ deleted: string }> {
  return unwrap(request.delete(`/admin/knowledge-nodes/${id}`))
}
export interface NodeChild { id: string; name: string; code: string; status: string; source: string | null; child_count: number }
export function getNodeChildren(id: string): Promise<NodeChild[]> {
  return unwrap(request.get(`/admin/knowledge-nodes/${id}/children`))
}
export function restoreKnowledgeNode(id: string): Promise<{ id: string; status: string }> {
  return unwrap(request.post(`/admin/knowledge-nodes/${id}/restore`))
}

// ── 长难句管理（KP-First L7）──────────────────────────────
export interface LSExtractFilters {
  textbook_version?: string[]; stage?: string[]; grade?: string[]
  semester?: string[]; exam_type?: string[]; region?: string[]; unit_ids?: string[]
}
export function extractLongSentences(body: { source?: string; limit?: number; filters?: LSExtractFilters }) {
  return unwrap<LSExtractResult>(request.post('/admin/long-sentences/extract', body))
}
export interface LSTextbookUnit {
  unit_id: string; textbook_version: string; grade: string; semester: string
  unit_no: number; unit_title: string; stage: string
}
export function getLsTextbookUnits() {
  return unwrap<LSTextbookUnit[]>(request.get('/admin/long-sentences/textbook-units'))
}
export interface LSRealDimensions {
  textbook_version: string[]; stage: string[]; grade: string[]; semester: string[]
  exam_type: string[]; region: { code: string; name: string }[]
}
export function getLsRealDimensions() {
  return unwrap<LSRealDimensions>(request.get('/admin/long-sentences/real-dimensions'))
}
// 重新解析已有长难句(后台异步):刷新为新结构,可选顺带发布
export function reanalyzeLongSentences(params: { status?: string; limit?: number; publish?: boolean }) {
  return unwrap<{ job_id: string }>(request.post('/admin/long-sentences/reanalyze', null, { params }))
}
export interface LsReanalyzeJob { job_id: string; total: number; done: number; failed: number; status: string; error?: string }
export function getLsReanalyzeJob(jobId: string) {
  return unwrap<LsReanalyzeJob>(request.get(`/admin/long-sentences/reanalyze-jobs/${jobId}`))
}

// ── 上传长难句:文字 → LLM 语法点 → 关联知识图谱 ──
export interface UploadedLsItem {
  id: string; point: string; text: string; difficulty: number | null
  node_id: string | null; node_code: string | null; node_name: string | null
}
export function uploadParseLs(text: string, unitId?: string): Promise<{ items: UploadedLsItem[] }> {
  return unwrap(request.post('/admin/long-sentences/upload-parse', { text, unit_id: unitId }, { timeout: 120000 }))
}
export function listUploadedLs(limit = 50, unitId?: string): Promise<{ items: UploadedLsItem[] }> {
  return unwrap(request.get('/admin/long-sentences/uploaded', { params: { limit, unit_id: unitId } }))
}
export function linkUploadedLsNode(lsId: string, nodeId: string): Promise<{ node_id: string; node_code: string; name: string }> {
  return unwrap(request.post(`/admin/long-sentences/uploaded/${lsId}/link-node`, { node_id: nodeId }))
}
export function newUploadedLsNode(lsId: string, parentId: string, name: string): Promise<{ node_id: string; node_code: string; name: string }> {
  return unwrap(request.post(`/admin/long-sentences/uploaded/${lsId}/new-node`, { parent_id: parentId, name }))
}
export function deleteUploadedLs(lsId: string): Promise<{ ok: boolean }> {
  return unwrap(request.delete(`/admin/long-sentences/uploaded/${lsId}`))
}
export function autoLinkUnitLs(unitId: string):
  Promise<{ items: UploadedLsItem[]; counts: { linked: number; unmatched: number; skipped: number } }> {
  return unwrap(request.post('/admin/long-sentences/uploaded/auto-link', { unit_id: unitId }, { timeout: 60000 }))
}

export function listLongSentences(params: {
  status?: string; node_id?: string; skip?: number; limit?: number
  sort_by?: string; order?: string
  source_kind?: string; textbook_version?: string; stage?: string
  grade?: string; semester?: string; exam_type?: string
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
  is_scanned?: boolean   // 扫描件(无文字层)
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
  pdf?: boolean
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
  created_at?: string | null
  results: UnitGenerateResult[]
}

export interface PdfOcrStatus { status: string; done: number; total: number; error?: string; segments: UnitSegment[] }
export function startPdfOcr(fileId: string): Promise<{ status: string; done: number; total: number }> {
  return unwrap(request.post(`/admin/curriculum/pdf/${fileId}/ocr`))
}
export function getPdfOcrStatus(fileId: string): Promise<PdfOcrStatus> {
  return unwrap(request.get(`/admin/curriculum/pdf/${fileId}/ocr-status`))
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
export function retryGenJob(jobId: string): Promise<GenJob> {
  return unwrap<GenJob>(request.post(`/admin/curriculum/pdf-jobs/${jobId}/retry`))
}

export function listGenJobs(params: {
  status?: string; textbook_version?: string; grade?: string; semester?: string; skip?: number; limit?: number
}): Promise<{ total: number; items: GenJob[] }> {
  return unwrap(request.get('/admin/curriculum/pdf-jobs', { params }))
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

// R8 Phase5a 已退役 generateSimQuestionsFromPaper:后端 /exam-papers/{id}/generate 已删,
// 仿真生成统一到节点化 platform_question 流(genSimFromReal/genSimBulk/genSimForNode)。

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
// ── 敏感操作二次审批(maker-checker)──
export interface ApprovalItem {
  id: string; action_type: string; summary: string; amount_fen: number | null
  status: string; maker_id: string; maker_name: string | null; maker_note: string | null
  checker_id: string | null; checker_name: string | null; checker_note: string | null
  exec_error: string | null; created_at: string | null; decided_at: string | null
}
export interface ApprovalConfig { enabled: boolean; refund_amount_fen: number; coupon_grant_count: number }
export function listApprovals(params: { status?: string; skip?: number; limit?: number }): Promise<{ total: number; items: ApprovalItem[] }> {
  return unwrap(request.get('/admin/approvals', { params }))
}
export function decideApproval(id: string, body: { approve: boolean; note?: string | null }): Promise<{ id: string; status: string }> {
  return unwrap(request.post(`/admin/approvals/${id}/decide`, body))
}
export function getApprovalConfig(): Promise<ApprovalConfig> {
  return unwrap(request.get('/admin/approvals/config'))
}
export function updateApprovalConfig(body: Partial<ApprovalConfig>): Promise<ApprovalConfig> {
  return unwrap(request.put('/admin/approvals/config', body))
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

// ══ 机构激活码定价（分 / 月）════════════════════════════════════════
export function getInstitutionCodePricing() {
  return unwrap<InstitutionCodePricing>(request.get('/admin/institution-code-pricing'))
}
export function updateInstitutionCodePricing(body: InstitutionCodePricing) {
  return unwrap<InstitutionCodePricing>(request.put('/admin/institution-code-pricing', body))
}
export function getInstitutionCodePricingHistory(limit = 50): Promise<PriceHistoryItem[]> {
  return unwrap(request.get('/admin/institution-code-pricing/history', { params: { limit } }))
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
  options?: string[] | Record<string, string> | string | null
  answer?: string | null
  explanation?: string | null
  difficulty?: number | null
  status: string
  sim_version?: number | null   // 仿真题按题位累加的版本号
  kp_names?: string[]           // 关联考点名(继承母题)
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
  source_file_url?: string | null
  source_filename?: string | null
  parse_status?: string | null
  parse_error?: string | null
  convert_status?: string | null
  year?: number | null
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
  exam_type?: string; region_code?: string; year?: number; skip?: number; limit?: number
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
// 派生仿真(后台异步):秒回 job_id,再轮询 getSimGenJob 看进度
export function genSimBulk(questionIds: string[], count = 3): Promise<{ job_id: string; per_question: number }> {
  return unwrap(request.post('/admin/platform-questions/gen-sim-bulk', { question_ids: questionIds, count }))
}
export interface SimGenJob { job_id: string; total: number; done: number; generated: number; failed: number; status: string; error?: string }
export function getSimGenJob(jobId: string): Promise<SimGenJob> {
  return unwrap(request.get(`/admin/platform-questions/gen-sim-jobs/${jobId}`))
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
export interface KpProposal { name: string; parent_node_id?: string | null; parent_name?: string | null }
export interface SuggestKpItem { question_id: string; suggestions: QuestionKpRef[]; proposals?: KpProposal[] }
export function suggestPaperKp(paperId: string, opts?: { sections?: string[]; prompt_id?: string; skip_attached?: boolean }): Promise<{ items: SuggestKpItem[] }> {
  // 整卷匹配并行调多组大模型,放宽超时到 3 分钟(默认 20s 远不够)
  return unwrap(request.post(`/admin/platform-papers/${paperId}/suggest-kp`, opts || {}, { timeout: 180000 }))
}
export interface RealExtractJob {
  job_id: string
  source: string
  status: 'running' | 'done' | 'failed'
  error?: string | null
  parsed: ParsedRealQuestion[]
}

export function listPlatformQuestions(params: {
  type?: string; status?: string; node_id?: string; source_paper_id?: string; skip?: number; limit?: number
}): Promise<{ total: number; items: PlatformQuestion[] }> {
  return unwrap(request.get('/admin/platform-questions', { params }))
}
// 批量审核仿真题(整卷/选中):approve→published / reject→retired
export function reviewPlatformBulk(questionIds: string[], approve: boolean): Promise<{ updated: number; status: string }> {
  return unwrap(request.post('/admin/platform-questions/review-bulk', { question_ids: questionIds, approve }))
}
export interface SimPaper { paper_id: string; paper_name: string; sim_count: number }
// 仿真题按来源真题卷聚合(仿真题审核:先按卷列),分页
export function listSimPapers(params?: { status?: string; skip?: number; limit?: number }): Promise<{ total: number; items: SimPaper[] }> {
  return unwrap(request.get('/admin/sim-papers', { params }))
}

export function extractRealQuestions(opts: { file?: File; imageUrls?: string[] }): Promise<{ job_id: string }> {
  const form = new FormData()
  if (opts.file) form.append('file', opts.file)
  if (opts.imageUrls?.length) form.append('image_urls', JSON.stringify(opts.imageUrls))
  return unwrap(request.post('/admin/platform-questions/extract', form, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 60000,
  }))
}
// 批量上传真题:多份 word/pdf → COS + 建草稿占位试卷
export interface BatchUploadResult { filename: string; ok: boolean; paper_id?: string; file_url?: string | null; cos?: boolean; duplicate?: boolean; error?: string }
export function batchUploadPapers(files: File[], meta: Record<string, unknown>):
  Promise<{ results: BatchUploadResult[]; ok: number; total: number }> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  form.append('meta', JSON.stringify(meta))
  return unwrap(request.post('/admin/platform-questions/batch-upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000,
  }))
}
// 解析某份(批量上传的)试卷 → 拆题自动入库为草稿
export function parsePaper(paperId: string, mode?: 'llm'): Promise<{ imported: number; status: string; error?: string }> {
  return unwrap(request.post(`/admin/platform-papers/${paperId}/parse`, {},
    { params: mode ? { mode } : {}, timeout: 300000 }))
}
// 重试:.doc → PDF 转换
export function convertPaperDoc(paperId: string): Promise<{ convert_status: string; error?: string }> {
  return unwrap(request.post(`/admin/platform-papers/${paperId}/convert-doc`, {}, { timeout: 180000 }))
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

// ── 题目层科学解析(阅读+完形)——AI 建议 + 人工确认唯一写库 ──
export interface QuestionAnalysis {
  // 阅读:rc技能 + 定位句
  rc_code?: string
  evidence?: string
  answer_reason?: string
  // 完形双轴:载体槽(程序判) + 线索类型/线索句 + 线索轴考点
  slot?: string | null
  clue_type?: string
  clue?: string
  kp_codes?: string[]
  answer_letter?: string
  // 干扰项=原义/义项+干扰机制(完形与阅读同构);distractor_types 为历史枚举字段,仅兼容旧数据读取
  distractors?: Record<string, { meaning: string; why_wrong: string }>
  distractor_types?: Record<string, string>
  // 书面表达:体裁+要点(客观锚)+主时态+wr考点+范文+要点↔句映射+目标句型(取自范文)+失分点
  genre?: string
  sub_format?: string
  main_tense?: string
  points?: { id?: number; point: string }[]
  wr_codes?: string[]
  strategy?: string                                              // 一句话套路名(照着能写)
  structure?: { role?: string; guide: string; point_ids?: number[] }[]   // 逐段骨架+句式模板
  model_essay?: string
  point_map?: Record<string, string>
  target_expressions?: string[]
  pitfalls?: { type?: string; trap: string }[]
  // 填空词形类(动词填空/词汇运用/单词拼写):所给词→定形
  given?: string
  target_form?: string
  change_type?: string
  answer_word?: string       // 短文填空(开放填空)应填的词
  // 完成句子/翻译/句型转换(句法结构)
  target_structure?: string
  key_points?: string[]
  answer?: string
  validation_skipped?: string[]
  kind?: string
  confirmed_by?: string
  confirmed_at?: string
}
export interface AnalysisSuggestItem {
  question_id: string
  analysis: QuestionAnalysis | null
  errors: string[]
  existing?: QuestionAnalysis | null
  staged?: boolean       // true=来自暂存(未重跑 LLM)
}
export function suggestQuestionAnalysis(questionIds: string[], force = false): Promise<AnalysisSuggestItem[]> {
  return unwrap(request.post('/admin/question-analysis/suggest',
    { question_ids: questionIds, force }, { timeout: 180000 }))
}
export function confirmQuestionAnalysis(questionId: string, analysis: QuestionAnalysis, force = false): Promise<QuestionAnalysis> {
  return unwrap(request.put(`/admin/platform-questions/${questionId}/analysis`, { analysis, force }))
}
// 书面表达评分量表(满分/各维达标线)——运营可配置,读后台配置不写死
export interface WritingRubric {
  full_score: number
  accuracy_pass_ratio: number
  organization_pass_ratio: number
  richness_min_targets: number
}
export function getWritingRubric(): Promise<WritingRubric> {
  return unwrap(request.get('/admin/writing-rubric'))
}
export function updateWritingRubric(body: Partial<WritingRubric>): Promise<WritingRubric> {
  return unwrap(request.put('/admin/writing-rubric', body))
}
// 批量一键采纳(降人工):通过硬校验的写库、失败的返原因
export function confirmQuestionAnalysisBatch(
  items: { question_id: string; analysis: QuestionAnalysis }[],
): Promise<{ confirmed: string[]; failed: { question_id: string; error: string }[] }> {
  return unwrap(request.post('/admin/question-analysis/confirm-batch', { items }))
}

// P0:按考点「反向生成」仿真(dimension: verb_fill 动词填空 / vocab_form 词汇运用 / dictation / grammar)
export function genSimForNode(
  nodeId: string,
  opts?: { dimension?: string; count?: number; force?: boolean },
): Promise<{ generated: number; sim_ids: string[] }> {
  return unwrap(request.post(`/admin/kp-nodes/${nodeId}/gen-sim`, null, {
    params: { dimension: opts?.dimension || 'verb_fill', count: opts?.count ?? 3, force: opts?.force ?? false },
  }))
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

// ── 百度地图获客 ─────────────────────────────────────────────
export interface BaiduPoi {
  name: string; phone: string | null; address: string | null; business: string | null; city: string
  region_province?: string | null; region_city?: string | null; region_district?: string | null; region_town?: string | null
}
export interface BaiduFetchResult {
  fetched: number; with_phone: number; quota_stopped: boolean; daily_cap_stopped?: boolean; calls?: number; region: string
  preview: BaiduPoi[]; ingest?: { created: number; skipped: number; shared_phone?: number; no_phone: number; region_unresolved: number }
}
export interface MapUsageOne { used: number; quota: number; remaining: number }
export interface MapUsage { date: string; baidu: MapUsageOne; amap: MapUsageOne }
export function getMapUsage(): Promise<MapUsage> {
  return unwrap(request.get('/admin/sales/map/usage'))
}
export function setMapQuota(body: { baidu?: number; amap?: number }): Promise<{ daily_quota: { baidu: number; amap: number } }> {
  return unwrap(request.put('/admin/sales/map/quota', body))
}
// 手动模式:把已检索到的 POI 直接入库(不再调地图 API、不耗配额)
export function ingestMapItems(items: BaiduPoi[], source: string, sourceNote?: string): Promise<{ created: number; skipped: number; shared_phone?: number; no_phone: number; region_unresolved: number }> {
  return unwrap(request.post('/admin/sales/leads/ingest', { items, source, source_note: sourceNote, require_phone: true }))
}
export function getBaiduAk(): Promise<{ ak_set: boolean; ak_masked: string }> {
  return unwrap(request.get('/admin/sales/baidu/ak'))
}
export function setBaiduAk(ak: string): Promise<{ ak_masked: string }> {
  return unwrap(request.put('/admin/sales/baidu/ak', { ak }))
}
export function baiduFetch(body: { region_name?: string; districts?: string[]; keywords: string[]; pages: number; ingest: boolean }): Promise<BaiduFetchResult> {
  return unwrap(request.post('/admin/sales/baidu/fetch', body, { timeout: 120000 }))
}
// 高德地图获客(同结构;source=amap)
export function getAmapKey(): Promise<{ ak_set: boolean; ak_masked: string }> {
  return unwrap(request.get('/admin/sales/amap/ak'))
}
export function setAmapKey(ak: string): Promise<{ ak_masked: string }> {
  return unwrap(request.put('/admin/sales/amap/ak', { ak }))
}
export function amapFetch(body: { region_name?: string; districts?: string[]; keywords: string[]; types?: string[]; pages: number; ingest: boolean }): Promise<BaiduFetchResult> {
  return unwrap(request.post('/admin/sales/amap/fetch', body, { timeout: 120000 }))
}

// ── 地图获客·按区县自动采集(每日 cron 续采;目标省可配)────────────────────
export interface MapCrawlConfig { enabled: boolean; provinces: string[]; keywords: string[]; amap_types: string[]; pages: number }
export interface MapCrawlProgressOne { total: number; done: number; empty: number; error: number; pending: number; fetched: number; ingested: number }
export interface MapCrawlProgress { provinces: string[]; enabled: boolean; baidu: MapCrawlProgressOne; amap: MapCrawlProgressOne }
export function getMapCrawlConfig(): Promise<MapCrawlConfig> {
  return unwrap(request.get('/admin/sales/map/crawl-config'))
}
export function setMapCrawlConfig(patch: Partial<MapCrawlConfig>): Promise<MapCrawlConfig> {
  return unwrap(request.put('/admin/sales/map/crawl-config', patch))
}
export function getMapCrawlProgress(): Promise<MapCrawlProgress> {
  return unwrap(request.get('/admin/sales/map/crawl-progress'))
}
export function runMapCrawl(body: { source: string; max_districts?: number }): Promise<{ source: string; districts_done: number; fetched: number; ingested: number; stopped: string | null; remaining_pending: number }> {
  return unwrap(request.post('/admin/sales/map/crawl-run', body, { timeout: 600000 }))
}

// ── 地区↔英语教材版本 映射 ───────────────────────────────────────────────
export interface TextbookRow { region_code: string; region_name: string; level: number; versions: string[]; note: string | null; verified: boolean; updated_at: string | null }
export function listTextbookMap(params: { level?: number; skip?: number; limit?: number }): Promise<{ total: number; items: TextbookRow[] }> {
  return unwrap(request.get('/admin/textbook-map', { params }))
}
export function getTextbookVersions(): Promise<{ versions: string[] }> {
  return unwrap(request.get('/admin/textbook-map/versions'))
}
export function upsertTextbookMap(body: { region_code: string; versions: string[]; note?: string | null; verified?: boolean }): Promise<{ region_code: string }> {
  return unwrap(request.put('/admin/textbook-map', body))
}
export function deleteTextbookMap(regionCode: string): Promise<{ deleted: string }> {
  return unwrap(request.delete(`/admin/textbook-map/${regionCode}`))
}
export function seedTextbookMap(overwrite = false): Promise<{ provinces: number; written: number; skipped: number }> {
  return unwrap(request.post('/admin/textbook-map/seed', {}, { params: { overwrite } }))
}

// ── 平台级操作审计(admin 写操作自动留痕)─────────────────────────────────
export interface AuditLogRow {
  id: string; admin_id: string | null; admin_name: string | null
  method: string; path: string; module: string; status: number
  query: string | null; detail: Record<string, unknown> | null
  ip: string | null; duration_ms: number | null; created_at: string
}
export function listAuditLogs(params: {
  module?: string; method?: string; admin_id?: string; q?: string
  status_min?: number; date_from?: string; date_to?: string; skip?: number; limit?: number
}): Promise<{ total: number; items: AuditLogRow[] }> {
  return unwrap(request.get('/admin/audit-logs', { params }))
}
export function getAuditAdmins(): Promise<{ admin_id: string; name: string }[]> {
  return unwrap(request.get('/admin/audit-logs/admins'))
}

// ── 管理员账号 + 模块权限(RBAC)──────────────────────────────────────────
export interface AdminMe { id: string; username: string | null; nickname: string | null; modules: string[] | null }
export interface AdminAccountRow { id: string; username: string; nickname: string | null; modules: string[] | null; is_active: boolean; created_at: string | null }
export function adminMe(): Promise<AdminMe> {
  return unwrap(request.get('/admin/me'))
}
export function listAdminAccounts(params: { skip?: number; limit?: number }): Promise<{ total: number; items: AdminAccountRow[] }> {
  return unwrap(request.get('/admin/admins', { params }))
}
export function createAdminAccount(body: { username: string; password: string; nickname?: string; modules?: string[] | null }): Promise<AdminAccountRow> {
  return unwrap(request.post('/admin/admins', body))
}
export function updateAdminAccount(id: string, body: { nickname?: string; modules?: string[]; all_modules?: boolean; is_active?: boolean }): Promise<AdminAccountRow> {
  return unwrap(request.patch(`/admin/admins/${id}`, body))
}
export function resetAdminPassword(id: string, password: string): Promise<{ id: string }> {
  return unwrap(request.post(`/admin/admins/${id}/reset-password`, { password }))
}

// ── 定时任务健康看板 ─────────────────────────────────────────────────────────
export interface TaskRunItem {
  task: string; label: string; cadence_hours: number | null
  last_status: string; last_run_at: string | null
  last_result: Record<string, unknown> | null; last_error: string | null
  duration_ms: number | null; last_success_at: string | null; stale: boolean
}
export interface TaskRunRow {
  id: string; task: string; label: string; status: string
  result: Record<string, unknown> | null; error: string | null
  started_at: string; finished_at: string | null; duration_ms: number | null
}
export function getTaskRunsOverview(): Promise<{ summary: { ok: number; stale: number; failing: number; total: number }; items: TaskRunItem[] }> {
  return unwrap(request.get('/admin/task-runs/overview'))
}
export function listTaskRuns(params: { task?: string; status?: string; skip?: number; limit?: number }): Promise<{ total: number; items: TaskRunRow[] }> {
  return unwrap(request.get('/admin/task-runs', { params }))
}

// ── R10 语法掌握判定校准(用真实作答反查「已掌握」判得准不准)────────────
export interface GrammarCalibWorstNode {
  node_id: string; name: string; answers: number
  accuracy: number | null; false_mastery_rate: number | null
  paper_hits: number; confirmed: boolean; days_since_mastered: number | null
}
export interface GrammarCalibration {
  source: string; note: string
  mastered_points: number; confirmed_points: number
  post_mastery: { answers: number; correct: number; accuracy: number | null; false_mastery_rate: number | null }
  pre_or_unmastered: { answers: number; accuracy: number | null; hint: string }
  paper_wrong_after_mastery: { hits: number; affected_points: number }
  worst_nodes: GrammarCalibWorstNode[]
}
export function getGrammarCalibration(studentId?: string): Promise<GrammarCalibration> {
  return unwrap(request.get('/admin/grammar/calibration', { params: studentId ? { student_id: studentId } : {} }))
}

// 词库缺词审核
export interface VocabReviewItem { id: string; word: string; source: string; occur_count: number; status: string; created_at: string | null }
export function listVocabReviews(params: { status?: string; skip?: number; limit?: number }) {
  return unwrap<{ total: number; items: VocabReviewItem[] }>(request.get('/admin/vocab-reviews', { params }))
}
export function approveVocabReview(id: string, body: { phonetic?: string; definitions?: any[] } = {}) {
  return unwrap<{ approved: boolean }>(request.post(`/admin/vocab-reviews/${id}/approve`, body))
}
// 批量入库(自动生成词力通全要素:文本/探针/媒体,后台跑)
export function approveVocabBatch(reviewIds: string[]) {
  return unwrap<{ approved: number; generating: number }>(
    request.post('/admin/vocab-reviews/approve-batch', { review_ids: reviewIds }))
}
export interface VocabGenStatus { running: boolean; total: number; done: number; ok: number; failed: number }
export function vocabGenStatus() {
  return unwrap<VocabGenStatus>(request.get('/admin/vocab-reviews/gen-status'))
}
export function rejectVocabReview(id: string) {
  return unwrap<{ rejected: boolean }>(request.post(`/admin/vocab-reviews/${id}/reject`))
}

// 第三方付费 API 资源总览
export interface ThirdPartyItem {
  category: string; name: string; provider: string; api: string; purpose: string
  configured: boolean; mode: 'real' | 'mock'; billing: string; console: string; usage: string | null
}
export interface ThirdPartyStatus {
  categories: { category: string; items: ThirdPartyItem[] }[]
  total: number; configured: number; mock: number
}
export function getThirdPartyStatus() {
  return unwrap<ThirdPartyStatus>(request.get('/admin/third-party/status'))
}

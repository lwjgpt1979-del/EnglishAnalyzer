<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Warning, Document, Notebook } from '@element-plus/icons-vue'
import {
  listPlatformPapers, getPlatformPaper, publishPlatformPaper, deletePlatformPapers, genSimBulk, getSimGenJob,
  attachQuestionKp, detachQuestionKp, attachSectionKp, attachKpBulk, suggestPaperKp, getNodeTree, getKpPrompts,
  createKnowledgeNode, genSimFromReal, suggestQuestionAnalysis, confirmQuestionAnalysis,
  confirmQuestionAnalysisBatch, getWritingRubric, updateWritingRubric,
  type QuestionAnalysis, type AnalysisSuggestItem, type WritingRubric,
  type QuestionKpRef, type KpPrompt, type KpProposal,
  extractRealQuestions, getExtractJob, bulkImportRealQuestions, batchUploadPapers, parsePaper, convertPaperDoc,
  listRegions, uploadImageViaPresign,
  type PlatformPaper, type PaperQuestion, type BatchUploadResult,
} from '../api/admin'
import type { NodeTreeItem } from '../types'

// ── 试卷列表(一卷一条)+ 筛选 ──
const statusFilter = ref('')
const filTextbook = ref('')
const filStage = ref('')
const filGrade = ref('')
const filExam = ref('')
const filYear = ref<number | ''>('')
const filRegionPath = ref<string[]>([])
const YEAR_OPTS = Array.from({ length: (new Date().getFullYear() + 1) - 2005 }, (_, i) => new Date().getFullYear() + 1 - i)
const papers = ref<PlatformPaper[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const statusOpts = ['', 'draft', 'published']

const selectedPapers = ref<PlatformPaper[]>([])
function onSelectionChange(rows: PlatformPaper[]) { selectedPapers.value = rows }
async function onDeleteSelected() {
  const ids = selectedPapers.value.map(p => p.id)
  if (!ids.length) { ElMessage.warning('请先勾选要删除的试卷'); return }
  const qsum = selectedPapers.value.reduce((s, p) => s + (p.question_count || 0), 0)
  await ElMessageBox.confirm(
    `确认删除选中的 ${ids.length} 份试卷(连带 ${qsum} 道题及其仿真/短文/知识点关联)?此操作不可恢复。`,
    '批量删除试卷', { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger' })
  try {
    const r = await deletePlatformPapers(ids)
    ElMessage.success(`已删除 ${r.deleted} 份试卷`)
    selectedPapers.value = []
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}

function onStageFilterChange() { filGrade.value = ''; reload() }
// 筛选/查询变更 → 回到第 1 页再查
function reload() { page.value = 1; load() }
function resetFilters() {
  statusFilter.value = ''; filTextbook.value = ''; filStage.value = ''
  filGrade.value = ''; filExam.value = ''; filRegionPath.value = []; filYear.value = ''
  reload()
}

async function load() {
  loading.value = true
  try {
    const region = filRegionPath.value
    const data = await listPlatformPapers({
      status: statusFilter.value || undefined,
      textbook_version: filTextbook.value || undefined,
      stage: filStage.value || undefined,
      grade: filGrade.value || undefined,
      exam_type: filExam.value || undefined,
      region_code: region.length ? region[region.length - 1] : undefined,  // 选到的最细级(省/市)
      year: filYear.value || undefined,
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    papers.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// ── 试卷详情弹框(整卷题 + 勾选发布/仿真)──
const paperDlg = ref(false)
const paperLoading = ref(false)
const curPaper = ref<PlatformPaper | null>(null)
const paperQuestions = ref<PaperQuestion[]>([])
const checkedIds = ref<string[]>([])

// 整卷题按「大题」分节,阅读/完形等同短文小问折叠为题组
const paperSections = computed(() => {
  const secs: { name: string; groups: { key: string | null; passage?: string | null; rows: PaperQuestion[] }[] }[] = []
  for (const q of paperQuestions.value) {
    const secName = q.section || '其他'
    let sec = secs[secs.length - 1]
    if (!sec || sec.name !== secName) { sec = { name: secName, groups: [] }; secs.push(sec) }
    const key = q.block_id || null
    const last = sec.groups[sec.groups.length - 1]
    if (last && last.key === key && key) last.rows.push(q)
    else sec.groups.push({ key, passage: q.passage, rows: [q] })
  }
  return secs
})

// 未挂知识点的题数(母题靠 KP 派生仿真,提醒别漏)
const unmappedCount = computed(() => paperQuestions.value.filter(q => !(q.kps && q.kps.length)).length)

async function openPaper(p: PlatformPaper) {
  paperDlg.value = true; paperLoading.value = true; curPaper.value = p
  paperQuestions.value = []; checkedIds.value = []; kpSuggest.value = {}; kpProposals.value = {}
  try {
    const d = await getPlatformPaper(p.id)
    curPaper.value = d.paper
    paperQuestions.value = d.questions
  } catch (e: any) { ElMessage.error(e?.message || '加载试卷失败') }
  finally { paperLoading.value = false }
}

// 重新解析:清掉旧题、按原卷重新拆题入库(幂等)。mode='llm' → 强制走 AI 整卷解析(排版复杂时用)
const reparsing = ref(false)
async function onReparse(mode?: 'llm') {
  if (!curPaper.value) return
  const llm = mode === 'llm'
  try {
    await ElMessageBox.confirm(
      llm ? '将清空本卷现有题目,用 AI 整卷解析拆题(适合个性化排版/规则漏题;较慢,消耗少量 AI 额度)。是否继续?'
          : '将清空本卷现有题目,按原卷文件重新解析拆题(草稿)。是否继续?',
      llm ? 'AI 解析' : '重新解析', { type: 'warning', confirmButtonText: llm ? 'AI 解析' : '重新解析' })
  } catch { return }
  reparsing.value = true
  paperLoading.value = true
  try {
    const r = await parsePaper(curPaper.value.id, llm ? 'llm' : undefined)
    if (r.status === 'parsed') ElMessage.success(`已${llm ? 'AI ' : '重新'}解析:${r.imported} 题`)
    else ElMessage.error(r.error || '解析失败')
    const d = await getPlatformPaper(curPaper.value.id)   // 刷新弹框
    curPaper.value = d.paper
    paperQuestions.value = d.questions
    await load()                                          // 刷新列表题数
  } catch (e: any) { ElMessage.error(e?.message || '重新解析失败') }
  finally { reparsing.value = false; paperLoading.value = false }
}

// ── 知识点选择器(受控知识分类树,单树)──
const kpPickerDlg = ref(false)
const kpTree = ref<NodeTreeItem[]>([])
const kpFilter = ref('')
const kpTreeRef = ref()
const kpTarget = ref<PaperQuestion | null>(null)       // 单题挂载目标
const kpTargetSection = ref<string | null>(null)       // 按大题挂载目标(整段)
const kpTreeProps = { label: 'name', children: 'children' }

async function loadKpTree() {
  if (kpTree.value.length) return
  try { kpTree.value = (await getNodeTree('knowledge')).items }
  catch (e: any) { ElMessage.error(e?.message || '加载知识点树失败') }
}
async function openKpPicker(q: PaperQuestion) {
  kpTarget.value = q; kpTargetSection.value = null
  kpFilter.value = ''; kpPickerDlg.value = true
  await loadKpTree()
}
async function openSectionKpPicker(section: string) {
  kpTarget.value = null; kpTargetSection.value = section
  kpFilter.value = ''; kpPickerDlg.value = true
  await loadKpTree()
}
function filterKpNode(val: string, data: NodeTreeItem) {
  return !val || data.name.includes(val)
}
async function onPickKp(node: NodeTreeItem) {
  try {
    if (kpTargetSection.value && curPaper.value) {           // 按大题整段挂
      const r = await attachSectionKp(curPaper.value.id, kpTargetSection.value, node.id)
      const d = await getPlatformPaper(curPaper.value.id)    // 刷新整卷 KP
      paperQuestions.value = d.questions
      ElMessage.success(`「${kpTargetSection.value}」${r.attached} 题已挂「${node.name}」`)
    } else if (kpTarget.value) {                             // 单题挂
      if (kpTarget.value.kps?.some(k => k.node_id === node.id)) { ElMessage.info('已挂该知识点'); return }
      kpTarget.value.kps = await attachQuestionKp(kpTarget.value.id, node.id)
      ElMessage.success(`已挂「${node.name}」`)
    }
    kpPickerDlg.value = false
  } catch (e: any) { ElMessage.error(e?.message || '挂载失败') }
}
async function onRemoveKp(q: PaperQuestion, nodeId: string) {
  try { q.kps = await detachQuestionKp(q.id, nodeId) }
  catch (e: any) { ElMessage.error(e?.message || '解挂失败') }
}

// ── AI 建议考点 ── 建议不自动挂,点 ✓ 采纳
const suggesting = ref(false)
const kpSuggest = ref<Record<string, QuestionKpRef[]>>({})
const kpProposals = ref<Record<string, KpProposal[]>>({})   // 缺口:AI 建议新建的考点(待人工确认)
// 把 suggest 返回合并进 kpSuggest/kpProposals(过滤已挂);merge=true 仅并入(整段),false 整体替换(整卷)
function mergeSuggestions(items: { question_id: string; suggestions: QuestionKpRef[]; proposals?: KpProposal[] }[], merge: boolean) {
  const map: Record<string, QuestionKpRef[]> = merge ? { ...kpSuggest.value } : {}
  const pmap: Record<string, KpProposal[]> = merge ? { ...kpProposals.value } : {}
  let n = 0
  for (const it of items) {
    const q = paperQuestions.value.find(x => x.id === it.question_id)
    const have = new Set((q?.kps || []).map(k => k.node_id))
    const fresh = (it.suggestions || []).filter(s => !have.has(s.node_id))
    if (fresh.length) { map[it.question_id] = fresh; n++ }
    if (it.proposals?.length) { pmap[it.question_id] = it.proposals; n++ }
  }
  kpSuggest.value = map
  kpProposals.value = pmap
  return n
}
async function onSuggestKp() {
  if (!curPaper.value) return
  suggesting.value = true
  try {
    // 整卷:跳过已挂考点的题,只补未挂的(避免重复匹配);单题型「一键挂」不传此项,可重跑
    const r = await suggestPaperKp(curPaper.value.id, { skip_attached: true })
    const n = mergeSuggestions(r.items, false)
    ElMessage.success(n ? `整卷匹配:AI 为 ${n} 道未挂考点的题给出建议,点 ✓ 采纳` : '未挂考点的题都已建议(或无新建议)')
  } catch (e: any) { ElMessage.error(e?.message || '整卷匹配失败') }
  finally { suggesting.value = false }
}

// ── P0:从本题(真题母题)派生同考点仿真 ──
// 走 generate_sim_from_real:继承母题 KP + 题型(经 _fine_type,动词填空/词汇运用如实继承),
// 落 draft 待审。符合「有源铁律」——有母题就派生,不造 fallback。
const genBusy = ref<string | null>(null)       // 正在派生的题 id
const simDeriveCount = 3
async function onDeriveSim(q: PaperQuestion) {
  genBusy.value = q.id
  try {
    const r = await genSimFromReal(q.id, simDeriveCount)
    ElMessage.success(`已从本题派生 ${r.generated} 道同考点仿真(草稿,可到仿真审核发布)`)
  } catch (e: any) { ElMessage.error(e?.message || '派生仿真失败') }
  finally { genBusy.value = null }
}

// ── 题目层科学解析(阅读+完形)——AI 建议预填,人工逐题确认才写库 ──
const CLUE_TYPES = ['句内固定搭配', '句内语法约束', '跨句逻辑关系', '跨句词汇复现', '全篇情感基调', '指代与人物追踪', '情景交际惯用']
const SLOT_TYPES = ['副词槽', '连词槽', '介词槽', '代词槽', '交际用语槽', '动词形式槽', '动词短语槽', '实义动词槽', '名词槽', '形容词槽', '数词槽']
const anaDlg = ref(false)
const anaBusy = ref(false)
const anaSaving = ref(false)
const anaTarget = ref<PaperQuestion | null>(null)
const anaErrors = ref<string[]>([])
const anaConfirmed = ref(false)   // 已有人工确认过的解析
const anaIgnore = ref(false)      // 人工判定校验误报 → 忽略校验强制写库
const anaIsCloze = computed(() => anaTarget.value?.question_type === '完型')
const anaIsWriting = computed(() => anaTarget.value?.question_type === '写作')
// 语法单选:单选且非阅读理解单选、非听力单选(词法/句法)
const anaIsGrammar = computed(() => anaTarget.value?.question_type === '单选'
  && !/阅读|听力/.test(anaTarget.value?.section || ''))
// 填空词形类:填空 + 词形段(词汇/词语/动词/单词/所给/适当形式/词形),排除短文/完成句子/翻译/句型转换
const anaIsWordFill = computed(() => anaTarget.value?.question_type === '填空'
  && /词汇|词语|动词|单词|所给|适当形式|词形/.test(anaTarget.value?.section || '')
  && !/短文|完成句子|翻译|句型转换|缺词/.test(anaTarget.value?.section || ''))
// 短文填空(开放填空):填空 + 短文/缺词段
const anaIsPassageFill = computed(() => anaTarget.value?.question_type === '填空'
  && /短文|缺词/.test(anaTarget.value?.section || ''))
const WRITING_GENRES = ['记叙文', '议论文', '说明文', '应用文']
const WRITING_TENSES = ['一般现在时', '一般过去时', '一般将来时', '现在完成时', '现在进行时', '过去进行时', '混合时态']
type DistractorNote = { meaning: string; why_wrong: string }
// 写作表单:要点/目标句型/失分点用「一行一条」文本框,保存时序列化成结构
type WritingForm = { genre: string; sub_format: string; main_tense: string;
  points: string; wr_codes: string; strategy: string; structure: string;
  model_essay: string; target_expressions: string; pitfalls: string }
const _emptyW = (): WritingForm => ({ genre: '', sub_format: '', main_tense: '',
  points: '', wr_codes: '', strategy: '', structure: '',
  model_essay: '', target_expressions: '', pitfalls: '' })
const _emptyDss = (): Record<string, DistractorNote> => ({
  A: { meaning: '', why_wrong: '' }, B: { meaning: '', why_wrong: '' },
  C: { meaning: '', why_wrong: '' }, D: { meaning: '', why_wrong: '' },
})
// 填空词形类表单:所给词/目标形式/词形变化类型
type WordFillForm = { given: string; target_form: string; change_type: string }
const _emptyWf = (): WordFillForm => ({ given: '', target_form: '', change_type: '' })
const anaForm = ref<{ rc_code: string; evidence: string; answer_reason: string;
  slot: string; clue_type: string; clue: string; kp_codes: string; answer_word: string;
  dss: Record<string, DistractorNote>; w: WritingForm; wf: WordFillForm }>({
  rc_code: '', evidence: '', answer_reason: '',
  slot: '', clue_type: '', clue: '', kp_codes: '', answer_word: '',
  dss: _emptyDss(), w: _emptyW(), wf: _emptyWf(),
})
function _resetAnaForm() {
  anaForm.value = { rc_code: '', evidence: '', answer_reason: '',
    slot: '', clue_type: '', clue: '', kp_codes: '', answer_word: '',
    dss: _emptyDss(), w: _emptyW(), wf: _emptyWf() }
}
function _fillAnaForm(src: QuestionAnalysis | null | undefined) {
  if (!src) { _resetAnaForm(); return }
  const dss = _emptyDss()
  for (const [k, v] of Object.entries(src.distractors || {}))
    dss[k] = { meaning: v?.meaning || '', why_wrong: v?.why_wrong || '' }
  const w = _emptyW()
  w.genre = src.genre || ''; w.sub_format = src.sub_format || ''; w.main_tense = src.main_tense || ''
  w.points = (src.points || []).map(p => p.point).join('\n')
  w.wr_codes = (src.wr_codes || []).join(',')
  w.strategy = src.strategy || ''
  w.structure = (src.structure || []).map(b => (b.role ? `${b.role}: ${b.guide}` : b.guide)).join('\n')
  w.model_essay = src.model_essay || ''
  w.target_expressions = (src.target_expressions || []).join('\n')
  w.pitfalls = (src.pitfalls || []).map(p => (p.type ? `${p.type}: ${p.trap}` : p.trap)).join('\n')
  const wf = _emptyWf()
  wf.given = src.given || ''; wf.target_form = src.target_form || ''; wf.change_type = src.change_type || ''
  anaForm.value = {
    rc_code: src.rc_code || '', evidence: src.evidence || '',
    answer_reason: src.answer_reason || '',
    slot: src.slot || '', clue_type: src.clue_type || '', clue: src.clue || '',
    kp_codes: (src.kp_codes || []).join(','), answer_word: src.answer_word || '',
    dss, w, wf,
  }
}
async function openAnalysis(q: PaperQuestion) {
  anaTarget.value = q
  anaDlg.value = true
  anaBusy.value = true
  anaErrors.value = []
  anaConfirmed.value = false
  anaIgnore.value = false
  _resetAnaForm()
  try {
    const [item] = await suggestQuestionAnalysis([q.id])
    anaConfirmed.value = !!item?.existing?.confirmed_at
    anaErrors.value = item?.existing ? [] : (item?.errors || [])
    _fillAnaForm(item?.existing || item?.analysis)   // 已确认过的优先展示
  } catch (e: any) { ElMessage.error(e?.message || 'AI 解析建议失败') }
  finally { anaBusy.value = false }
}
// 「AI 重新解析」:忽略暂存强制重跑 LLM(误报/漏项时重试),用新建议回填表单
async function reanalyzeAnalysis() {
  if (!anaTarget.value || anaBusy.value) return
  anaBusy.value = true
  anaErrors.value = []
  try {
    const [item] = await suggestQuestionAnalysis([anaTarget.value.id], true)
    anaErrors.value = item?.errors || []
    anaIgnore.value = false
    _fillAnaForm(item?.analysis)
  } catch (e: any) { ElMessage.error(e?.message || 'AI 重新解析失败') }
  finally { anaBusy.value = false }
}
// 「查看」:直接用批量已算好的建议秒开详情弹窗(不重跑 LLM),可就地确认写库
function viewAnaBatchItem(it: AnalysisSuggestItem) {
  const q = anaBatchQmap.value[it.question_id]
  if (!q) return
  anaTarget.value = q
  anaErrors.value = it.errors || []
  anaConfirmed.value = false
  anaBusy.value = false
  anaIgnore.value = false
  _fillAnaForm(it.analysis)
  anaDlg.value = true            // 批量弹窗保留在底层,详情叠加于上
}
async function saveAnalysis() {
  if (!anaTarget.value) return
  anaSaving.value = true
  try {
    const dss: Record<string, DistractorNote> = {}
    for (const [k, v] of Object.entries(anaForm.value.dss))
      if (v.meaning.trim() || v.why_wrong.trim())
        dss[k] = { meaning: v.meaning.trim(), why_wrong: v.why_wrong.trim() }
    const lines = (s: string) => s.split('\n').map(x => x.trim()).filter(Boolean)
    const csv = (s: string) => s.split(/[,，\s]+/).map(x => x.trim()).filter(Boolean)
    let payload: QuestionAnalysis
    if (anaIsWriting.value) {
      const w = anaForm.value.w
      payload = {
        genre: w.genre, sub_format: w.sub_format.trim() || undefined,
        main_tense: w.main_tense || undefined,
        points: lines(w.points).map((point, i) => ({ id: i + 1, point })),
        wr_codes: csv(w.wr_codes),
        strategy: w.strategy.trim() || undefined,
        structure: lines(w.structure).map(l => {
          const m = l.match(/^(.+?)[:：]\s*(.+)$/)
          return m ? { role: m[1].trim(), guide: m[2].trim() } : { guide: l }
        }),
        model_essay: w.model_essay.trim(),
        target_expressions: lines(w.target_expressions),
        pitfalls: lines(w.pitfalls).map(l => {
          const m = l.match(/^(.+?)[:：]\s*(.+)$/)
          return m ? { type: m[1].trim(), trap: m[2].trim() } : { trap: l }
        }),
      }
    } else if (anaIsCloze.value) {
      payload = { slot: anaForm.value.slot.trim() || null, clue_type: anaForm.value.clue_type,
        clue: anaForm.value.clue.trim(), kp_codes: csv(anaForm.value.kp_codes), distractors: dss }
    } else if (anaIsWordFill.value) {
      // 填空词形类:given/target_form/change_type + kp_codes + 定形依据(有 change_type → 后端分发 word_fill)
      const wf = anaForm.value.wf
      payload = { given: wf.given.trim(), target_form: wf.target_form.trim(),
        change_type: wf.change_type.trim(), kp_codes: csv(anaForm.value.kp_codes),
        answer_reason: anaForm.value.answer_reason.trim() }
    } else if (anaIsPassageFill.value) {
      // 短文填空:clue_type + clue + answer_word + kp_codes(有 clue_type 但无 distractors → 后端分发 passage_fill)
      payload = { clue_type: anaForm.value.clue_type, clue: anaForm.value.clue.trim(),
        answer_word: anaForm.value.answer_word.trim(), kp_codes: csv(anaForm.value.kp_codes) }
    } else if (anaIsGrammar.value) {
      // 语法单选:kp_codes(cf/jf)+ 答案依据 + 干扰机制(无 rc_code/clue_type → 后端分发到 grammar_mc)
      payload = { kp_codes: csv(anaForm.value.kp_codes),
        answer_reason: anaForm.value.answer_reason.trim(), distractors: dss }
    } else {
      payload = { rc_code: anaForm.value.rc_code.trim(), evidence: anaForm.value.evidence.trim(),
        answer_reason: anaForm.value.answer_reason.trim(), distractors: dss }
    }
    await confirmQuestionAnalysis(anaTarget.value.id, payload, anaIgnore.value)
    ElMessage.success(anaIgnore.value ? '已人工忽略校验强制写库(已记审计)' : '解析已确认写库(已通过原文子串校验)')
    // 若从批量「查看」进来:确认后从待办列表移除该行,保持列表与库一致
    anaBatchItems.value = anaBatchItems.value.filter(it => it.question_id !== anaTarget.value!.id)
    anaDlg.value = false
  } catch (e: any) { ElMessage.error(e?.message || '确认失败(未通过校验?)') }
  finally { anaSaving.value = false }
}

// ── 批量解析(降人工:整段 AI 建议 → 一键采纳校验通过项,只逐个驳回异常)──
const anaBatchDlg = ref(false)
const anaBatchBusy = ref(false)
const anaBatchSaving = ref(false)
const anaBatchSection = ref('')
const anaBatchItems = ref<AnalysisSuggestItem[]>([])
const anaBatchQmap = ref<Record<string, PaperQuestion>>({})
const anaBatchPassCount = computed(() => anaBatchItems.value.filter(it => it.analysis && !it.errors.length).length)
function analyzableSection(sec: { name: string }): boolean {
  return /完形|完型|阅读|书面|写作|单项|选择填空|词汇|词语|动词|单词|适当形式|词形|短文填空|缺词/.test(sec.name)
}
// 单题是否可做题目层解析:类型即完型/阅读/写作;语法单选(单选·非阅读/听力段);
// 填空词形类(填空·词形段);或阅读理解题机械形式常为「单选/填空」但段名表明是阅读/完形。
function isAnalyzableQuestion(q: { question_type: string }, sectionName: string): boolean {
  const sec = sectionName || ''
  if (q.question_type === '完型' || q.question_type === '阅读' || q.question_type === '写作') return true
  if (q.question_type === '单选' && !/阅读|听力/.test(sec)) return true   // 语法单选
  if (q.question_type === '填空' && /词汇|词语|动词|单词|所给|适当形式|词形/.test(sec)
    && !/短文|完成句子|翻译|句型转换|缺词/.test(sec)) return true          // 填空词形类
  if (q.question_type === '填空' && /短文|缺词/.test(sec)) return true      // 短文填空(开放填空)
  return /完形|完型|阅读/.test(sec) && (q.question_type === '单选' || q.question_type === '填空')
}
function anaSummary(it: AnalysisSuggestItem): string {
  const a = it.analysis
  if (!a) return '(无建议)'
  if (a.clue_type) return `${a.slot || '—'} · ${a.clue_type} · ${(a.kp_codes || []).join(',')}`
  return `${a.rc_code || '—'} · ${(a.evidence || '').slice(0, 24)}`
}
const anaBatchStaged = computed(() => anaBatchItems.value.some(it => it.staged))
async function _runAnaBatch(force: boolean) {
  anaBatchBusy.value = true
  try {
    anaBatchItems.value = await suggestQuestionAnalysis(
      Object.keys(anaBatchQmap.value), force)
  } catch (e: any) { ElMessage.error(e?.message || 'AI 批量解析失败') }
  finally { anaBatchBusy.value = false }
}
async function openAnaBatch(sec: { name: string; groups: any[] }) {
  // 防重入:上一次解析还在途(未 commit 暂存)时再点,只重开弹窗看进度,绝不再发第二个全段请求
  // (否则秒读缓存尚未落库 → 又全量重跑,正是卡顿的根因)
  if (anaBatchBusy.value) { anaBatchDlg.value = true; return }
  const qs: PaperQuestion[] = sec.groups.flatMap(g => g.rows)
    .filter((q: PaperQuestion) => isAnalyzableQuestion(q, sec.name))
  if (!qs.length) { ElMessage.info('本大题无完形/阅读题'); return }
  anaBatchSection.value = sec.name
  anaBatchQmap.value = Object.fromEntries(qs.map(q => [q.id, q]))
  anaBatchItems.value = []
  anaBatchDlg.value = true
  await _runAnaBatch(false)     // 优先读暂存(秒开);只对没解析过的跑 LLM
}
async function reparseAnaBatch() {
  try {
    await ElMessageBox.confirm('忽略已暂存的建议,对本段全部题重新解析(会重新消耗 LLM)。继续?',
      '重新解析全段', { type: 'warning' })
  } catch { return }
  await _runAnaBatch(true)
}
async function adoptAnaBatch() {
  const pass = anaBatchItems.value.filter(it => it.analysis && !it.errors.length)
  if (!pass.length) { ElMessage.warning('无校验通过的建议可采纳'); return }
  anaBatchSaving.value = true
  try {
    const r = await confirmQuestionAnalysisBatch(
      pass.map(it => ({ question_id: it.question_id, analysis: it.analysis as QuestionAnalysis })))
    ElMessage.success(`已采纳 ${r.confirmed.length} 道${r.failed.length ? `,失败 ${r.failed.length}` : ''}`)
    // 采纳后从列表移除已写库项;剩报错项留给人工逐个改
    const done = new Set(r.confirmed)
    anaBatchItems.value = anaBatchItems.value.filter(it => !done.has(it.question_id))
  } catch (e: any) { ElMessage.error(e?.message || '批量采纳失败') }
  finally { anaBatchSaving.value = false }
}
function editAnaBatchItem(it: AnalysisSuggestItem) {
  const q = anaBatchQmap.value[it.question_id]
  if (q) { anaBatchDlg.value = false; openAnalysis(q) }   // 复用单题弹窗人工改
}

// ── 书面表达评分量表(运营可配置:满分/各维达标线)──
const rubricDlg = ref(false)
const rubricSaving = ref(false)
const rubric = ref<WritingRubric>({ full_score: 20, accuracy_pass_ratio: 0.7, organization_pass_ratio: 0.6, richness_min_targets: 1 })
async function openRubric() {
  rubricDlg.value = true
  try { rubric.value = await getWritingRubric() } catch (e: any) { ElMessage.error(e?.message || '读取量表失败') }
}
async function saveRubric() {
  rubricSaving.value = true
  try {
    rubric.value = await updateWritingRubric(rubric.value)
    ElMessage.success('写作评分量表已保存(全局生效)')
    rubricDlg.value = false
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { rubricSaving.value = false }
}

// ── 一键挂某大题:选该题型提示词 → AI 对该段每题建议 ──
const secSuggestDlg = ref(false)
const secSuggestName = ref('')
const secSuggestType = ref('')
const secPrompts = ref<KpPrompt[]>([])
const secPromptId = ref('')
const secSuggesting = ref(false)
let allPrompts: KpPrompt[] = []
async function openSectionSuggest(section: string) {
  if (!curPaper.value) return
  const q = paperQuestions.value.find(x => x.section === section)
  secSuggestName.value = section
  secSuggestType.value = section.includes('听力') ? '听力' : (q?.question_type || '单选')
  if (!allPrompts.length) {
    try { allPrompts = (await getKpPrompts()).prompts } catch { allPrompts = [] }
  }
  secPrompts.value = allPrompts.filter(p => p.question_type === secSuggestType.value)
  secPromptId.value = (secPrompts.value.find(p => p.is_default) || secPrompts.value[0])?.id || ''
  secSuggestDlg.value = true
}
async function runSectionSuggest() {
  if (!curPaper.value) return
  secSuggesting.value = true
  try {
    const r = await suggestPaperKp(curPaper.value.id, {
      sections: [secSuggestName.value], prompt_id: secPromptId.value || undefined })
    const n = mergeSuggestions(r.items, true)
    ElMessage.success(n ? `「${secSuggestName.value}」AI 为 ${n} 题给出建议,点 ✓ 采纳` : '该大题 AI 未给出新建议')
    secSuggestDlg.value = false
  } catch (e: any) { ElMessage.error(e?.message || 'AI 建议失败') }
  finally { secSuggesting.value = false }
}
async function acceptSuggest(q: PaperQuestion, s: QuestionKpRef) {
  try {
    q.kps = await attachQuestionKp(q.id, s.node_id)
    kpSuggest.value[q.id] = (kpSuggest.value[q.id] || []).filter(x => x.node_id !== s.node_id)
  } catch (e: any) { ElMessage.error(e?.message || '采纳失败') }
}
// 待确认建议总条数
const suggestTotal = computed(() =>
  Object.values(kpSuggest.value).reduce((n, arr) => n + (arr?.length || 0), 0))
async function acceptAllSuggest() {
  const pairs: { question_id: string; node_id: string }[] = []
  for (const [qid, arr] of Object.entries(kpSuggest.value)) {
    for (const s of (arr || [])) pairs.push({ question_id: qid, node_id: s.node_id })
  }
  if (!pairs.length) { ElMessage.warning('暂无可采纳的 AI 建议'); return }
  acceptingAll.value = true
  try {
    const r = await attachKpBulk(pairs)
    if (curPaper.value) {        // 刷新整卷 KP(已入库)
      const d = await getPlatformPaper(curPaper.value.id)
      paperQuestions.value = d.questions
    }
    kpSuggest.value = {}
    ElMessage.success(`已采纳并保存 ${r.attached} 条知识点关联`)
  } catch (e: any) { ElMessage.error(e?.message || '采纳失败') }
  finally { acceptingAll.value = false }
}
const acceptingAll = ref(false)
function dismissSuggest(q: PaperQuestion, s: QuestionKpRef) {
  kpSuggest.value[q.id] = (kpSuggest.value[q.id] || []).filter(x => x.node_id !== s.node_id)
}
// 缺口建议:✓ 确认 = 在归属分类下新建该考点 + 挂到本题;✕ = 忽略
async function acceptProposal(q: PaperQuestion, p: KpProposal) {
  if (!p.parent_node_id) { openProposalPicker(q, p); return }   // 未定分类 → 人工选归属分类
  await createKpUnderAndAttach(q, p, p.parent_node_id)
}
async function createKpUnderAndAttach(q: PaperQuestion, p: KpProposal, parentId: string) {
  try {
    const node = await createKnowledgeNode({ name: p.name, parent_id: parentId })
    q.kps = await attachQuestionKp(q.id, node.id)
    kpProposals.value[q.id] = (kpProposals.value[q.id] || []).filter(x => x !== p)
    ElMessage.success(`已新建考点「${p.name}」并挂到本题`)
  } catch (e: any) { ElMessage.error(e?.message || '新建并挂载失败') }
}
function dismissProposal(q: PaperQuestion, p: KpProposal) {
  kpProposals.value[q.id] = (kpProposals.value[q.id] || []).filter(x => x !== p)
}

// 未定分类的缺口建议:弹分类树,人工选归属分类后再新建+挂载
const propPickerDlg = ref(false)
const propTarget = ref<{ q: PaperQuestion; p: KpProposal } | null>(null)
const propFilter = ref('')
const propTreeRef = ref<any>(null)
function openProposalPicker(q: PaperQuestion, p: KpProposal) {
  propTarget.value = { q, p }; propFilter.value = ''; propPickerDlg.value = true
}
async function onPickProposalParent(node: any) {
  if (!propTarget.value) return
  const { q, p } = propTarget.value
  await createKpUnderAndAttach(q, p, node.id)
  propPickerDlg.value = false; propTarget.value = null
}
watch(propFilter, v => propTreeRef.value?.filter(v))

watch(kpFilter, v => kpTreeRef.value?.filter(v))

async function onPublishPaper() {
  if (!curPaper.value) return
  await ElMessageBox.confirm(
    `发布「${curPaper.value.name}」共 ${curPaper.value.question_count} 题为母题?发布后这些真题成为对应知识点的「母题」,可勾选题派生仿真供学生练习。`,
    '发布成为母题', { type: 'warning' })
  const p = await publishPlatformPaper(curPaper.value.id)
  curPaper.value = p
  for (const q of paperQuestions.value) q.status = 'published'
  ElMessage.success(`已发布 ${p.published_count} 题为母题,可勾选题派生仿真`)
  await load()
}

async function onGenSimChecked() {
  if (!checkedIds.value.length) { ElMessage.warning('请先勾选要派生仿真的题'); return }
  await runGenSim(checkedIds.value, `勾选的 ${checkedIds.value.length} 道题`)
  checkedIds.value = []
}
// 题型级勾选:勾整个题型 = 把该 section 全部题加入 checkedIds(可多选题型后统一派生仿真)
function sectionQuestionIds(sec: { groups: { rows: { id: string }[] }[] }): string[] {
  return sec.groups.flatMap(g => g.rows).map(q => q.id)
}
function secAllChecked(sec: any): boolean {
  const ids = sectionQuestionIds(sec)
  return ids.length > 0 && ids.every(id => checkedIds.value.includes(id))
}
function secSomeChecked(sec: any): boolean {
  const ids = sectionQuestionIds(sec)
  const n = ids.filter(id => checkedIds.value.includes(id)).length
  return n > 0 && n < ids.length
}
function onToggleSec(sec: any, checked: boolean) {
  const ids = sectionQuestionIds(sec)
  if (checked) checkedIds.value = [...new Set([...checkedIds.value, ...ids])]
  else checkedIds.value = checkedIds.value.filter(id => !ids.includes(id))
}
const simGen = ref<{ running: boolean; done: number; total: number; generated: number }>({ running: false, done: 0, total: 0, generated: 0 })
async function runGenSim(ids: string[], label: string) {
  const { value } = await ElMessageBox.prompt(`为${label}各派生几套仿真?(后台生成,可继续操作)`, '派生仿真', {
    inputValue: '2', inputPattern: /^[1-9]\d*$/, inputErrorMessage: '请输入正整数',
  })
  const { job_id } = await genSimBulk(ids, Number(value))
  simGen.value = { running: true, done: 0, total: 0, generated: 0 }
  ElMessage.info('已在后台派生仿真,生成中…(可继续操作,完成后去「仿真题审核」查看)')
  // 轮询进度
  const poll = async () => {
    try {
      const j = await getSimGenJob(job_id)
      simGen.value = { running: j.status === 'pending' || j.status === 'running', done: j.done, total: j.total, generated: j.generated }
      if (j.status === 'done') {
        ElMessage.success(`派生完成:共生成 ${j.generated} 道仿真${j.failed ? `(${j.failed} 个题位失败)` : ''},去「仿真题审核」查看`)
        return
      }
      if (j.status === 'error') { ElMessage.error('派生失败:' + (j.error || '未知错误')); return }
      setTimeout(poll, 2000)
    } catch { simGen.value.running = false }  // 任务丢失(后端重启)→ 停止轮询
  }
  setTimeout(poll, 1500)
}

// ── 上传抽题向导 ──
const VERSIONS = ['译林版', '人教版', '外研版', '北师大版']
const STAGES = ['小', '初', '高']          // 学段(对接 stage_hint:小/初/高)
const STAGE_LABEL: Record<string, string> = { 小: '小学', 初: '初中', 高: '高中' }
const GRADES: Record<string, string[]> = {
  小: ['三年级', '四年级', '五年级', '六年级'],
  初: ['七年级', '八年级', '九年级'],
  高: ['高一', '高二', '高三'],
}
const dlg = ref(false)
const step = ref(0)                 // 0=选源, 1=抽题中, 2=校对
// 批次元信息:教材+学段 必选;年级/学期/地区 选填
const EXAM_TYPES = [{ label: '普通(无)', value: '' }, { label: '中考', value: '中考' }, { label: '高考', value: '高考' }]
// platform_question.question_type 为 varchar,除 ai_question_type_enum 的 7 种外,
// 另收「动词填空 / 词汇运用」独立题型(P0):真题切题按大题名归位,勿再降级成单选。
const QUESTION_TYPES = ['单选', '填空', '完型', '阅读', '写作', '判断', '连线', '动词填空', '词汇运用']
const metaTextbook = ref('译林版')
const metaStage = ref('初')
const metaGrade = ref('')
const metaSemester = ref('')
const metaExamType = ref('')
// 地区:后端 region 表懒加载级联(省→市→区县→乡镇),code 与学生 user.city_code 同源
const regionPath = ref<string[]>([])
const regionLabels = ref<string[]>([])
const regionCascader = ref()
const regionProps = {
  lazy: true,
  async lazyLoad(node: any, resolve: (n: any[]) => void) {
    try {
      const rows = await listRegions(node.value || undefined)
      // 地区最细到市:root(level0)→省(可下钻),省(level1)→市(置 leaf,不再下钻区县)
      const capCity = node.level >= 1
      resolve(rows.map(r => ({ value: r.code, label: r.name, leaf: capCity || r.leaf })))
    } catch { resolve([]) }
  },
}
function onRegionChange() {
  const nodes = regionCascader.value?.getCheckedNodes?.()
  regionLabels.value = nodes?.[0]?.pathLabels || []
}
const pickedFile = ref<File | null>(null)       // PDF / Word(.docx)
const pickedImages = ref<File[]>([])             // 直传图片(走 OCR)
const uploadingImg = ref(false)
const imageUrlsText = ref('')
const extracting = ref(false)
const importing = ref(false)
let pollTimer: ReturnType<typeof setTimeout> | null = null

const metaPaperName = ref('')        // 试卷名(选填,缺省后端按地区/教材/年级自动合成)
interface EditRow {
  question_no?: string | null; question_type: string; stem: string
  answer: string; explanation: string; difficulty: number | null; kp_names: string
  block_key?: string | null; section?: string | null
}
const editRows = ref<EditRow[]>([])
const passages = ref<Record<string, string>>({})    // block_key → 短文正文(组内共享，可编辑)

// 校对分组:按大题(section)分节,节内同短文小问折叠为题组,独立题各占一行组
const editGroups = computed(() => {
  const out: { key: string | null; section: string | null; rows: EditRow[] }[] = []
  for (const row of editRows.value) {
    const key = row.block_key || null
    const ident = key || `sec:${row.section || ''}`     // 无短文时按大题归并
    const last = out[out.length - 1]
    const lastIdent = last ? (last.key || `sec:${last.section || ''}`) : null
    if (last && lastIdent === ident) last.rows.push(row)
    else out.push({ key, section: row.section || null, rows: [row] })
  }
  return out
})
function delRow(row: EditRow) {
  const i = editRows.value.indexOf(row)
  if (i >= 0) editRows.value.splice(i, 1)
}

function stopPoll() { if (pollTimer) { clearTimeout(pollTimer); pollTimer = null } }

function openDlg() {
  stopPoll()
  step.value = 0; pickedFile.value = null; pickedImages.value = []; uploadingImg.value = false; imageUrlsText.value = ''
  metaGrade.value = ''; metaSemester.value = ''; metaExamType.value = ''; metaPaperName.value = ''
  regionPath.value = []; regionLabels.value = []
  extracting.value = false; importing.value = false; editRows.value = []
  dlg.value = true
}

function batchMeta(): Record<string, unknown> {
  const m: Record<string, unknown> = { textbook_version: metaTextbook.value, stage: metaStage.value }
  if (metaGrade.value) m.grade = metaGrade.value
  if (metaSemester.value) m.semester = metaSemester.value
  if (metaExamType.value) m.exam_type = metaExamType.value
  const path = regionPath.value
  if (path.length) {        // code 与学生 user.city_code 同源 → 中考可按地区匹配
    m.province_code = path[0]
    if (path[1]) m.city_code = path[1]      // 市(4位)
    m.region_code = path[path.length - 1]   // 选到的最细级(可到区县/乡镇)
    if (regionLabels.value.length) m.region_name = regionLabels.value.join('')
  }
  return m
}

// ── 批量上传真题(文件 → COS + 建草稿占位试卷,题目延后解析)──
const batchDlg = ref(false)
const batchFiles = ref<File[]>([])
const batchUploading = ref(false)
const batchResults = ref<BatchUploadResult[]>([])
const batchAutofilled = ref(false)
function openBatchDlg() {
  regionPath.value = []; regionLabels.value = []
  batchFiles.value = []; batchResults.value = []
  batchAutofilled.value = false
  batchDlg.value = true
}
function onBatchFiles(_f: any, fileList: any[]) {
  batchFiles.value = (fileList || []).map(x => x.raw as File).filter(Boolean)
  // 用第一个文件名自动命中 教材/学段/年级/上下册/考试/地区(只填一次,不覆盖后续手改)
  if (!batchAutofilled.value && batchFiles.value.length) {
    const fn = (batchFiles.value[0].name || '').replace(/\.(pdf|docx?)$/i, '').trim()
    if (fn) { autoFillMetaFromName(fn); batchAutofilled.value = true }
  }
}
async function submitBatch() {
  if (!batchFiles.value.length) { ElMessage.warning('请先选择文件'); return }
  batchUploading.value = true
  batchResults.value = []
  try {
    const r = await batchUploadPapers(batchFiles.value, batchMeta())
    batchResults.value = r.results
    const dup = r.results.filter(x => x.duplicate).length
    ElMessage.success(`上传完成:${r.ok} / ${r.total} 份成功` +
      (dup ? `,${dup} 份试卷名重复已跳过` : '') + '(已建草稿,可到列表「批量解析原题目」)')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '批量上传失败') }
  finally { batchUploading.value = false }
}

// ── 批量解析原题目(选中的批量上传卷 → OCR/LLM 拆题入库,并发)──
async function runPool<T>(items: T[], worker: (it: T) => Promise<void>, concurrency: number) {
  let i = 0
  const next = async (): Promise<void> => { while (i < items.length) { await worker(items[i++]) } }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, next))
}
const parsing = ref(false)
const parseProg = ref({ done: 0, total: 0, failed: 0 })
const parseLabel = (s?: string | null) =>
  (({ parsing: '解析中', parsed: '已解析', failed: '解析失败' } as Record<string, string>)[s || ''] || '未解析')
// .doc → pdf 转换状态
const fileType = (fn?: string | null) => (fn && fn.includes('.') ? fn.split('.').pop()!.toUpperCase() : '')
const convertLabel = (s?: string | null) =>
  (({ pending: '待转换', converting: '转换中', converted: '已转PDF', failed: '转换失败' } as Record<string, string>)[s || ''] || '')
const convertingIds = ref<Record<string, boolean>>({})
async function onRetryConvert(p: PlatformPaper) {
  convertingIds.value[p.id] = true
  p.convert_status = 'converting'
  try {
    const r = await convertPaperDoc(p.id)
    p.convert_status = r.convert_status
    if (r.convert_status === 'converted') ElMessage.success(`${p.name}:已转 PDF,可「批量解析原题目」`)
    else ElMessage.error(`${p.name}:转换失败(需服务器安装 LibreOffice)`)
  } catch (e: any) { p.convert_status = 'failed'; ElMessage.error(e?.message || '转换失败') }
  finally { convertingIds.value[p.id] = false; await load() }
}
async function onBatchParse() {
  // 与「重新解析」一致:选中的都重跑(已解析的也会清旧题重解析,不再跳过)
  const targets = selectedPapers.value.filter(p => p.source_filename)
  if (!targets.length) { ElMessage.warning('请勾选批量上传的试卷(有原卷文件)'); return }
  const reParsed = targets.filter(p => p.parse_status === 'parsed').length
  try {
    await ElMessageBox.confirm(
      `解析选中的 ${targets.length} 份试卷(读原始文件 OCR/LLM 拆题,自动入库为草稿题),并发执行。` +
      (reParsed ? `其中 ${reParsed} 份已解析过,将清空旧题重新解析。` : '') + '是否继续?',
      '批量解析原题目', { type: 'warning', confirmButtonText: '开始解析' })
  } catch { return }
  parsing.value = true
  parseProg.value = { done: 0, total: targets.length, failed: 0 }
  await runPool(targets, async (p) => {
    p.parse_status = 'parsing'
    try {
      const r = await parsePaper(p.id)
      p.parse_status = r.status
      if (r.status !== 'parsed') { parseProg.value.failed++; ElMessage.error(`${p.name}:${r.error || '解析失败'}`) }
    } catch (e: any) { p.parse_status = 'failed'; parseProg.value.failed++; ElMessage.error(`${p.name}:${e?.message || ''}`) }
    finally { parseProg.value.done++ }
  }, 4)
  parsing.value = false
  const ok = parseProg.value.total - parseProg.value.failed
  ElMessage.success(`解析完成:${ok} 成功${parseProg.value.failed ? `、${parseProg.value.failed} 失败` : ''}`)
  await load()
}

function onFileChange(f: any) {
  pickedFile.value = f.raw as File
  // 试卷名缺省取上传文件名(去扩展名);已手填则不覆盖
  const fn = (f.raw?.name || '').replace(/\.(pdf|docx?)$/i, '').trim()
  if (fn && !metaPaperName.value.trim()) metaPaperName.value = fn
  if (fn) autoFillMetaFromName(fn)        // 文件名里出现的教材/学段/年级/上下册/考试/地区 → 自动选
}

// 从试卷名识别上方各下拉并自动选中(文件名为准)
function autoFillMetaFromName(name: string) {
  const v = VERSIONS.find(x => name.includes(x))
  if (v) metaTextbook.value = v
  let gradeHit = false
  for (const [stage, grades] of Object.entries(GRADES)) {
    const g = grades.find(x => name.includes(x))
    if (g) { metaStage.value = stage; metaGrade.value = g; gradeHit = true; break }
  }
  if (!gradeHit) {           // 无年级时按"小学/初中/高中"判学段
    if (name.includes('初中')) metaStage.value = '初'
    else if (name.includes('小学')) metaStage.value = '小'
    else if (name.includes('高中')) metaStage.value = '高'
  }
  if (/下学期|下册/.test(name)) metaSemester.value = '下'
  else if (/上学期|上册/.test(name)) metaSemester.value = '上'
  if (name.includes('中考')) { metaExamType.value = '中考'; if (!gradeHit) metaStage.value = '初' }
  else if (name.includes('高考')) { metaExamType.value = '高考'; if (!gradeHit) metaStage.value = '高' }
  autoPickRegionFromName(name)
}

// 地区:从试卷名匹配 省→市(懒加载两级),自动选中
async function autoPickRegionFromName(name: string) {
  if (regionPath.value.length) return     // 已选则不覆盖
  const bare = (s: string) => s.replace(/(省|市|自治区|特别行政区|壮族|回族|维吾尔|自治州|地区)/g, '')
  try {
    const provs = await listRegions()
    const prov = provs.find((p: any) => name.includes(p.name) || (bare(p.name).length >= 2 && name.includes(bare(p.name))))
    if (!prov) return
    const cities = await listRegions(prov.code)
    const city = cities.find((c: any) => name.includes(c.name) || (bare(c.name).length >= 2 && name.includes(bare(c.name))))
    regionPath.value = city ? [prov.code, city.code] : [prov.code]
    regionLabels.value = city ? [prov.name, city.name] : [prov.name]
  } catch { /* 地区识别失败不影响其它 */ }
}
function onImagesChange(_f: any, list: any[]) { pickedImages.value = list.map(x => x.raw).filter(Boolean) }

async function startExtract() {
  if (!metaTextbook.value || !metaStage.value) { ElMessage.warning('请先选教材版本和学段'); return }
  const typedUrls = imageUrlsText.value.split('\n').map(s => s.trim()).filter(Boolean)
  if (!pickedFile.value && !pickedImages.value.length && !typedUrls.length) {
    ElMessage.warning('请选 PDF/Word 文件,或上传/粘贴图片'); return
  }
  extracting.value = true; step.value = 1
  try {
    let urls = typedUrls
    if (pickedImages.value.length) {        // 图片先直传 COS 拿 file_url
      uploadingImg.value = true
      const uploaded = await Promise.all(pickedImages.value.map(f => uploadImageViaPresign(f)))
      urls = [...uploaded, ...typedUrls]
      uploadingImg.value = false
    }
    // file(PDF/Word)优先;无 file 时走图片/URL 的 OCR
    const { job_id } = await extractRealQuestions({ file: pickedFile.value || undefined, imageUrls: urls })
    pollExtract(job_id)
  } catch (e: any) { extracting.value = false; uploadingImg.value = false; ElMessage.error(e?.message || '抽题失败') }
}

async function pollExtract(jobId: string) {
  try {
    const job = await getExtractJob(jobId)
    if (job.status === 'running') { pollTimer = setTimeout(() => pollExtract(jobId), 2500); return }
    extracting.value = false
    if (job.status === 'failed') { ElMessage.error(`抽题失败:${job.error || ''}`); step.value = 0; return }
    const pmap: Record<string, string> = {}
    editRows.value = job.parsed.map(p => {
      if (p.block_key && p.passage && !(p.block_key in pmap)) pmap[p.block_key] = p.passage
      return {
        question_no: p.question_no, question_type: p.question_type || '单选',
        stem: p.stem || '', answer: p.answer || '', explanation: p.explanation || '',
        difficulty: null, kp_names: '', block_key: p.block_key || null, section: p.section || null,
      }
    })
    passages.value = pmap
    step.value = 2
    if (!editRows.value.length) ElMessage.warning('未抽到题,请检查文件或改用图片上传')
  } catch (e: any) { extracting.value = false; ElMessage.error(e?.message || '查询失败') }
}

async function doImport() {
  const items = editRows.value.filter(r => r.stem.trim()).map(r => ({
    stem: r.stem.trim(), answer: r.answer || null, question_type: r.question_type || null,
    explanation: r.explanation || null, difficulty: r.difficulty, question_no: r.question_no,
    kp_names: r.kp_names.split(/[,，]/).map(s => s.trim()).filter(Boolean),
    block_key: r.block_key || null, section: r.section || null,
    passage: r.block_key ? (passages.value[r.block_key] || null) : null,
  }))
  if (!items.length) { ElMessage.warning('没有可导入的题'); return }
  importing.value = true
  try {
    // 整卷先入草稿;回列表后点试卷「发布」整卷上架
    const r = await bulkImportRealQuestions(items, {
      status: 'draft', stage_hint: metaStage.value, meta: batchMeta(), paper_name: metaPaperName.value || undefined,
    })
    ElMessage.success(`已导入试卷:${r.imported} 题${r.failed ? `,失败 ${r.failed}` : ''}。回列表点「发布」上架`)
    dlg.value = false
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '导入失败') }
  finally { importing.value = false }
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <el-select v-model="filTextbook" placeholder="教材" clearable style="width:108px" @change="reload">
        <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
      </el-select>
      <el-select v-model="filStage" placeholder="学段" clearable style="width:88px" @change="onStageFilterChange">
        <el-option v-for="s in STAGES" :key="s" :label="STAGE_LABEL[s]" :value="s" />
      </el-select>
      <el-select v-model="filGrade" placeholder="年级" clearable :disabled="!filStage" style="width:98px" @change="reload">
        <el-option v-for="g in (GRADES[filStage] || [])" :key="g" :label="g" :value="g" />
      </el-select>
      <el-cascader v-model="filRegionPath" :props="regionProps" clearable placeholder="地区" style="width:160px" @change="reload" />
      <el-select v-model="filExam" placeholder="考试" clearable style="width:96px" @change="reload">
        <el-option v-for="e in EXAM_TYPES.filter(x => x.value)" :key="e.value" :label="e.label" :value="e.value" />
      </el-select>
      <el-select v-model="filYear" placeholder="年份" clearable filterable style="width:96px" @change="reload">
        <el-option v-for="y in YEAR_OPTS" :key="y" :label="y + '年'" :value="y" />
      </el-select>
      <el-select v-model="statusFilter" placeholder="状态" clearable style="width:96px" @change="reload">
        <el-option v-for="s in statusOpts.filter(Boolean)" :key="s" :label="s === 'published' ? '已发布' : '草稿'" :value="s" />
      </el-select>
      <el-button @click="resetFilters">重置</el-button>
      <el-button type="primary" @click="openDlg">+ 上传真题</el-button>
      <el-button type="success" plain @click="openBatchDlg"><el-icon style="margin-right:4px"><UploadFilled /></el-icon>批量上传真题</el-button>
      <el-button type="warning" plain :disabled="!selectedPapers.length || parsing" :loading="parsing" @click="onBatchParse">
        {{ parsing ? `解析中 ${parseProg.done}/${parseProg.total}` : '批量解析原题目' }}
      </el-button>
      <el-button type="danger" plain :disabled="!selectedPapers.length" @click="onDeleteSelected">删除选中{{ selectedPapers.length ? ` (${selectedPapers.length})` : '' }}</el-button>
      <span class="hint">一份上传 = 一份试卷;点「查看/发布」弹整卷题。共 {{ total }} 份</span>
    </div>

    <el-table v-loading="loading" :data="papers" border style="width:100%" row-key="id" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="44" />
      <el-table-column label="试卷" min-width="240">
        <template #default="{ row }">
          <div style="font-weight:600">
            <el-tag v-if="row.year" size="small" type="primary" effect="plain" style="margin-right:6px">{{ row.year }}</el-tag>
            {{ row.name }}
            <el-link v-if="row.source_file_url" :href="row.source_file_url" target="_blank" type="primary" :underline="false" style="font-size:12px;margin-left:6px">原卷 ↗</el-link>
          </div>
          <div style="font-size:12px;color:#909399">
            {{ [row.year ? row.year + '年' : '', row.textbook_version, row.grade, row.semester ? row.semester + '册' : '', row.region_name, row.exam_type].filter(Boolean).join(' · ') }}
          </div>
        </template>
      </el-table-column>
      <el-table-column label="文件" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="fileType(row.source_filename)" size="small" effect="plain"
            :type="fileType(row.source_filename) === 'PDF' ? 'success' : fileType(row.source_filename) === 'DOC' ? 'warning' : 'primary'">
            {{ fileType(row.source_filename) }}
          </el-tag>
          <span v-else style="color:#c0c4cc">—</span>
        </template>
      </el-table-column>
      <el-table-column label="题数" width="80" align="center"><template #default="{ row }">{{ row.question_count }}</template></el-table-column>
      <el-table-column label="已发布" width="90" align="center">
        <template #default="{ row }">{{ row.published_count }}/{{ row.question_count }}</template>
      </el-table-column>
      <el-table-column label="状态" width="150" align="center">
        <template #default="{ row }">
          <el-tag :type="row.status === 'published' ? 'success' : 'info'" size="small">{{ row.status === 'published' ? '已发布' : '草稿' }}</el-tag>
          <!-- .doc→pdf 转换状态(未转好时优先显示,可重试)-->
          <template v-if="row.convert_status && row.convert_status !== 'converted'">
            <el-tag size="small" style="margin-top:2px"
              :type="row.convert_status === 'failed' ? 'danger' : 'warning'" effect="plain">
              {{ convertLabel(row.convert_status) }}
            </el-tag>
            <el-button v-if="row.convert_status !== 'converting'" size="small" link type="primary"
              :loading="convertingIds[row.id]" style="margin-top:2px" @click="onRetryConvert(row)">重试转PDF</el-button>
          </template>
          <!-- 解析状态 -->
          <template v-else-if="row.source_filename">
            <el-tooltip v-if="row.parse_status === 'failed' && row.parse_error"
              :content="row.parse_error" placement="top" effect="dark">
              <el-tag size="small" style="margin-top:2px" type="danger" effect="plain">解析失败 ⓘ</el-tag>
            </el-tooltip>
            <el-tag v-else size="small" style="margin-top:2px"
              :type="row.parse_status === 'parsed' ? 'success' : row.parse_status === 'parsing' ? 'warning' : 'info'"
              effect="plain">{{ parseLabel(row.parse_status) }}</el-tag>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openPaper(row)">查看 / 发布</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <!-- 试卷详情:整卷题(按大题分节、阅读题组折叠)+ 整卷发布 + 勾选派生仿真 -->
    <el-dialog v-model="paperDlg" :title="curPaper ? curPaper.name : '试卷详情'" width="960px" :close-on-click-modal="false">
      <div v-loading="paperLoading">
        <div style="display:flex;align-items:center;margin-bottom:10px;gap:12px">
          <el-tag :type="curPaper?.status === 'published' ? 'success' : 'info'" size="small">{{ curPaper?.status === 'published' ? '已发布' : '草稿' }}</el-tag>
          <span style="color:#606266">共 {{ curPaper?.question_count }} 题,已发布 {{ curPaper?.published_count }}</span>
          <span style="color:#909399;font-size:12px">已勾选 {{ checkedIds.length }} 题</span>
          <el-tag v-if="unmappedCount" type="warning" size="small"><el-icon style="vertical-align:-2px;margin-right:4px"><Warning /></el-icon>{{ unmappedCount }} 题未挂知识点</el-tag>
          <div style="flex:1"></div>
          <el-button v-if="curPaper?.source_filename" :loading="reparsing" @click="onReparse()"
            title="清空本卷题目,按原卷文件重新拆题(草稿)">重新解析</el-button>
          <el-button v-if="curPaper?.source_filename" :loading="reparsing" @click="onReparse('llm')"
            title="排版复杂/规则漏题时用:清空后走 AI 整卷解析(较慢,消耗少量 AI 额度)">AI 解析</el-button>
          <el-button :loading="suggesting" @click="onSuggestKp"
            title="整卷按每个大题/题型分别调用其匹配提示词,候选考点按本卷学段(高⊇初⊇小)过滤">AI 整卷匹配知识点</el-button>
          <el-button v-if="suggestTotal" type="warning" :loading="acceptingAll" @click="acceptAllSuggest">采纳全部建议 ({{ suggestTotal }})</el-button>
          <el-button type="success" :disabled="curPaper?.status === 'published'" @click="onPublishPaper">发布成为母题</el-button>
          <el-button type="primary" :disabled="!checkedIds.length" @click="onGenSimChecked">勾选题派生仿真</el-button>
          <el-button text type="info" @click="openRubric" title="书面表达 AI 评分的满分与各维达标线(运营可配置,读后台配置)">写作评分量表</el-button>
          <span v-if="simGen.running" style="font-size:12px;color:#409eff">后台派生中 {{ simGen.done }}/{{ simGen.total || '…' }} 题位，已生成 {{ simGen.generated }} 道</span>
        </div>
        <div style="max-height:520px;overflow:auto">
          <!-- font-size:14px 复位:el-checkbox-group 默认 font-size:0 会让组内纯文本不可见 -->
          <el-checkbox-group v-model="checkedIds" style="font-size:14px;line-height:1.5">
            <div v-for="(sec, si) in paperSections" :key="si" style="margin-bottom:14px">
              <div style="font-size:14px;font-weight:600;color:#303133;margin-bottom:6px;border-left:3px solid #409eff;padding-left:8px;display:flex;align-items:center;gap:8px">
                <span>{{ sec.name }}</span>
                <el-button size="small" text type="primary" style="height:22px;padding:0 6px" @click="openSectionSuggest(sec.name)">一键挂知识点(AI)</el-button>
                <el-button v-if="analyzableSection(sec)" size="small" text type="warning" style="height:22px;padding:0 6px"
                  :loading="anaBatchBusy" :disabled="anaBatchBusy"
                  title="整段 AI 解析(完形双轴/阅读题目层)→ 一键采纳校验通过项,只逐个驳回异常"
                  @click="openAnaBatch(sec)">{{ anaBatchBusy ? '解析中…' : '批量解析全段' }}</el-button>
                <el-button size="small" text style="height:22px;padding:0 6px;color:#909399" @click="openSectionKpPicker(sec.name)">手动挂</el-button>
                <el-button size="small" :type="secAllChecked(sec) ? 'primary' : 'default'" plain
                  style="height:22px;padding:0 8px;margin-left:6px"
                  title="选中整个题型(可多选题型累加),再点上方「勾选题派生仿真」"
                  @click="onToggleSec(sec, !secAllChecked(sec))">
                  {{ secAllChecked(sec) ? '☑' : (secSomeChecked(sec) ? '◪' : '☐') }} 全选本题型
                </el-button>
              </div>
              <div v-for="(g, gi) in sec.groups" :key="gi" :style="g.key ? 'border:1px solid #ebeef5;border-radius:6px;padding:8px;margin-bottom:8px;background:#fafcff' : ''">
                <div v-if="g.key" style="font-size:12px;color:#606266;margin-bottom:6px;white-space:pre-wrap;max-height:84px;overflow:auto"><el-icon style="vertical-align:-2px;margin-right:4px"><Document /></el-icon>{{ g.passage }}</div>
                <div v-for="q in g.rows" :key="q.id" style="display:flex;align-items:flex-start;gap:8px;padding:5px 0;border-bottom:1px dashed #f0f0f0;font-size:13px">
                  <el-checkbox :value="q.id" style="margin-top:2px" />
                  <span style="color:#909399;width:30px;flex-shrink:0">{{ q.question_no }}</span>
                  <div style="flex:1;min-width:0">
                    <div style="white-space:pre-wrap">{{ q.stem }}</div>
                    <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px;align-items:center">
                      <el-tag v-for="k in q.kps" :key="k.node_id" size="small" closable @close="onRemoveKp(q, k.node_id)">{{ k.name }}</el-tag>
                      <el-tag v-if="(!q.kps || !q.kps.length) && !(kpSuggest[q.id] && kpSuggest[q.id].length) && !(kpProposals[q.id] && kpProposals[q.id].length)" size="small" type="warning" effect="plain">未挂知识点</el-tag>
                      <el-tag v-for="s in (kpSuggest[q.id] || [])" :key="'s' + s.node_id" size="small" type="primary" effect="plain" style="border-style:dashed">
                        AI建议:{{ s.name }}
                        <span style="cursor:pointer;color:#67c23a;font-weight:700;margin-left:3px" @click="acceptSuggest(q, s)">✓</span>
                        <span style="cursor:pointer;color:#c0c4cc;margin-left:2px" @click="dismissSuggest(q, s)">✕</span>
                      </el-tag>
                      <el-tag v-for="(p, pi) in (kpProposals[q.id] || [])" :key="'p' + pi" size="small" type="danger" effect="plain" style="border-style:dashed"
                        :title="p.parent_node_id ? ('目录无对应考点 → 新建并归到「' + (p.parent_name || '?') + '」,点 ✓ 确认') : '未定分类:点 ✓ 人工选归属分类后再新建'">
                        新建:{{ p.name }}<span style="color:#909399"> → {{ p.parent_name || '未定分类(点✓选)' }}</span>
                        <span style="cursor:pointer;color:#67c23a;font-weight:700;margin-left:3px" @click="acceptProposal(q, p)">✓</span>
                        <span style="cursor:pointer;color:#c0c4cc;margin-left:2px" @click="dismissProposal(q, p)">✕</span>
                      </el-tag>
                      <el-button size="small" text type="primary" style="height:22px;padding:0 6px" @click="openKpPicker(q)">+ 知识点</el-button>
                      <el-button v-if="q.kps && q.kps.length" size="small" text type="success" style="height:22px;padding:0 6px"
                        :loading="genBusy === q.id"
                        :title="`从本题派生 ${simDeriveCount} 道同考点仿真(继承本题「${q.question_type}」题型与考点,落草稿待审)`"
                        @click="onDeriveSim(q)">↻ 派生仿真</el-button>
                      <el-button v-if="isAnalyzableQuestion(q, sec.name)" size="small" text type="warning" style="height:22px;padding:0 6px"
                        title="AI 生成题目层解析(阅读:rc技能+定位句;完形:载体槽+线索类型),人工确认后才写库;线索句程序校验防幻觉"
                        @click="openAnalysis(q)">解析</el-button>
                    </div>
                  </div>
                  <el-tag size="small" :type="q.status === 'published' ? 'success' : 'info'" style="flex-shrink:0">{{ q.status === 'published' ? '已发布' : '草稿' }}</el-tag>
                </div>
              </div>
            </div>
          </el-checkbox-group>
        </div>
      </div>
    </el-dialog>

    <!-- 题目层科学解析(阅读试点):AI 建议预填 → 人工改/确认 → 唯一写库入口 -->
    <el-dialog v-model="anaDlg" title="题目层解析(人工确认后写库)" width="620px" append-to-body>
      <div v-if="anaBusy" style="text-align:center;color:#909399;padding:24px">AI 生成解析建议中…</div>
      <template v-else>
        <div style="font-size:12px;color:#909399;margin-bottom:10px;white-space:pre-wrap">{{ anaTarget?.stem }}</div>
        <el-alert v-if="anaConfirmed" type="success" :closable="false" style="margin-bottom:10px"
          title="本题已有人工确认的解析(下方为已存内容,可修改后重新确认)" />
        <el-alert v-if="anaErrors.length" type="warning" :closable="false" style="margin-bottom:10px"
          :title="'AI 建议未通过程序校验,请人工修正:' + anaErrors.join(';')" />
        <el-form label-width="92px" size="small">
          <!-- 书面表达:体裁+要点(客观锚)+主时态+wr考点+范文+目标句型(取自范文)+失分点 -->
          <template v-if="anaIsWriting">
            <el-form-item label="体裁">
              <div style="display:flex;gap:8px;width:100%">
                <el-select v-model="anaForm.w.genre" placeholder="体裁" style="width:130px">
                  <el-option v-for="g in WRITING_GENRES" :key="g" :label="g" :value="g" />
                </el-select>
                <el-input v-model="anaForm.w.sub_format" placeholder="具体文体(如 演讲稿/书信/通知,可空)" style="flex:1" />
              </div>
            </el-form-item>
            <el-form-item label="主时态">
              <el-select v-model="anaForm.w.main_tense" clearable placeholder="主时态(如 一般现在时)" style="width:100%">
                <el-option v-for="t in WRITING_TENSES" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item label="要点">
              <el-input v-model="anaForm.w.points" type="textarea" :rows="3"
                placeholder="一行一条要点(客观锚:漏要点是第一失分源);范文须覆盖全部要点" />
            </el-form-item>
            <el-form-item label="写作考点">
              <el-input v-model="anaForm.w.wr_codes" placeholder="wr-* 编码,逗号分隔(如 wr-1-2,wr-4-1)" />
            </el-form-item>
            <el-form-item label="套路名">
              <el-input v-model="anaForm.w.strategy"
                placeholder="一句话好记公式(如 三段式演讲稿:问候引题→分点论述→升华号召);仿真同体裁复用" />
            </el-form-item>
            <el-form-item label="结构套路">
              <el-input v-model="anaForm.w.structure" type="textarea" :rows="4"
                placeholder="逐段一行「角色: 该段写什么+现成开头语/连接词/句式」,学生照着套(如 开头: 问候引题 Good morning! I'd like to talk about…)" />
            </el-form-item>
            <el-form-item label="范文">
              <el-input v-model="anaForm.w.model_essay" type="textarea" :rows="5"
                placeholder="覆盖全部要点、词数达标的范文(目标句型须逐字出自此范文)" />
            </el-form-item>
            <el-form-item label="目标句型">
              <el-input v-model="anaForm.w.target_expressions" type="textarea" :rows="2"
                placeholder="一行一条,升格靶;必须逐字取自上面范文(保存时程序校验子串,防幻觉)" />
            </el-form-item>
            <el-form-item label="失分点">
              <el-input v-model="anaForm.w.pitfalls" type="textarea" :rows="2"
                placeholder="一行一条,格式「类型: 陷阱」(如 时态: 演讲稿易误用过去时)" />
            </el-form-item>
          </template>
          <!-- 完形双轴:载体槽(程序判,区分度=0 的形式轴)+ 线索类型(真构念)+ 线索句 + 线索轴考点 -->
          <template v-else-if="anaIsCloze">
            <el-form-item label="载体槽">
              <el-select v-model="anaForm.slot" clearable filterable style="width:100%"
                placeholder="程序按选项词性判定(如 副词槽/动词短语槽);拿不准可留空">
                <el-option v-for="s in SLOT_TYPES" :key="s" :label="s" :value="s" />
              </el-select>
            </el-form-item>
            <el-form-item label="线索类型">
              <el-select v-model="anaForm.clue_type" placeholder="真构念:决定学情归因与仿真变式" style="width:100%">
                <el-option v-for="t in CLUE_TYPES" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item label="线索句">
              <el-input v-model="anaForm.clue" type="textarea" :rows="2"
                placeholder="决定答案的原文句(保存时程序校验子串,防幻觉)" />
            </el-form-item>
            <el-form-item label="考点编码">
              <el-input v-model="anaForm.kp_codes" placeholder="线索轴为主,逗号分隔(如 rc-6-1)" />
            </el-form-item>
          </template>
          <!-- 填空词形类(动词填空/词汇运用/单词拼写):给词→定形,开放填空无干扰项 -->
          <template v-else-if="anaIsWordFill">
            <el-form-item label="所给词">
              <el-input v-model="anaForm.wf.given" placeholder="括号里给的原词(如 divide)" />
            </el-form-item>
            <el-form-item label="目标形式">
              <el-input v-model="anaForm.wf.target_form" placeholder="应填的正确形式(如 was dividing)" />
            </el-form-item>
            <el-form-item label="词形变化类型">
              <el-input v-model="anaForm.wf.change_type" placeholder="如 过去进行时/被动语态/名词复数/形容词比较级/动词→名词派生" />
            </el-form-item>
            <el-form-item label="考点编码">
              <el-input v-model="anaForm.kp_codes" placeholder="词法 cf- / 句法 jf-,逗号分隔" />
            </el-form-item>
            <el-form-item label="定形依据">
              <el-input v-model="anaForm.answer_reason" type="textarea" :rows="2"
                placeholder="据什么线索定这个形式(时间状语/主句时态/主谓一致/语义)" />
            </el-form-item>
          </template>
          <!-- 短文填空(开放填空):线索类型+线索句(短文子串)+应填词+考点。无载体槽/无干扰项 -->
          <template v-else-if="anaIsPassageFill">
            <el-form-item label="线索类型">
              <el-select v-model="anaForm.clue_type" placeholder="决定答案的语境线索类型" style="width:100%">
                <el-option v-for="t in CLUE_TYPES" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
            <el-form-item label="线索句">
              <el-input v-model="anaForm.clue" type="textarea" :rows="2"
                placeholder="决定答案的短文句(保存时程序校验子串,防幻觉)" />
            </el-form-item>
            <el-form-item label="应填词">
              <el-input v-model="anaForm.answer_word" placeholder="本空应填的词" />
            </el-form-item>
            <el-form-item label="考点编码">
              <el-input v-model="anaForm.kp_codes" placeholder="cf-/jf-/rc-,逗号分隔(线索轴为主)" />
            </el-form-item>
          </template>
          <!-- 语法单选(词法/句法):cf-/jf- 考点 + 答案规则依据(无原文子串,单选自足)-->
          <template v-else-if="anaIsGrammar">
            <el-form-item label="考点编码">
              <el-input v-model="anaForm.kp_codes" placeholder="词法 cf- / 句法 jf-,逗号分隔(如 jf-1-1)" />
            </el-form-item>
            <el-form-item label="答案依据">
              <el-input v-model="anaForm.answer_reason" type="textarea" :rows="2"
                placeholder="正确项命中哪条语法/搭配规则(1-2 句)" />
            </el-form-item>
          </template>
          <template v-else>
            <el-form-item label="rc 技能编码">
              <el-input v-model="anaForm.rc_code" placeholder="如 rc-1-1(细节直查)" />
            </el-form-item>
            <el-form-item label="定位句">
              <el-input v-model="anaForm.evidence" type="textarea" :rows="2"
                placeholder="必须逐字摘自原文(保存时程序校验子串,防幻觉)" />
            </el-form-item>
            <el-form-item label="答案归因">
              <el-input v-model="anaForm.answer_reason" type="textarea" :rows="2"
                placeholder="由定位句到正确项的推理(1-2 句)" />
            </el-form-item>
          </template>
          <!-- 干扰项=原义/义项+干扰机制。正确项留空;写作/填空词形类/短文填空(开放填空)无此项 -->
          <el-form-item v-if="!anaIsWriting && !anaIsWordFill && !anaIsPassageFill" label="干扰项">
            <div style="display:flex;flex-direction:column;gap:6px;width:100%">
              <div v-for="k in ['A','B','C','D']" :key="k" style="display:flex;align-items:center;gap:8px">
                <span style="width:18px;color:#606266">{{ k }}</span>
                <el-input v-model="anaForm.dss[k].meaning"
                  :placeholder="anaIsGrammar ? '选项形态/义(正确项留空)' : anaIsCloze ? '原义(正确项留空)' : '选项义项/主张(正确项留空)'" style="width:180px" />
                <el-input v-model="anaForm.dss[k].why_wrong"
                  :placeholder="anaIsGrammar ? '违规机制:违反哪条语法/搭配' : anaIsCloze ? '干扰机制:与哪条语境线索冲突' : '干扰机制:与哪处定位句/原文冲突(可点明张冠李戴等)'" style="flex:1" />
              </div>
            </div>
          </el-form-item>
        </el-form>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <el-button text type="primary" :loading="anaBusy" @click="reanalyzeAnalysis">↻ AI 重新解析</el-button>
          <div style="display:flex;align-items:center;gap:10px">
            <el-checkbox v-if="anaErrors.length" v-model="anaIgnore"
              title="人工判定程序校验为误报(如定位句实为原文但子串比对过严),忽略后强制写库并记审计">忽略校验</el-checkbox>
            <el-button @click="anaDlg = false">取消</el-button>
            <el-button type="primary" :loading="anaSaving" :disabled="anaErrors.length > 0 && !anaIgnore"
              @click="saveAnalysis">{{ anaIgnore ? '忽略校验强制写库' : '人工确认并写库' }}</el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 批量解析:整段 AI 建议 → 一键采纳校验通过项;报错项逐个「改」走单题弹窗 -->
    <el-dialog v-model="anaBatchDlg" :title="`批量解析:${anaBatchSection}`" width="720px" append-to-body>
      <div v-if="anaBatchBusy" style="text-align:center;color:#909399;padding:24px">AI 批量解析中…(整段并发,已暂存的秒读)</div>
      <template v-else>
        <div style="font-size:12px;color:#606266;margin-bottom:8px">
          共 {{ anaBatchItems.length }} 题;<b style="color:#67c23a">{{ anaBatchPassCount }}</b> 道通过硬校验(线索句子串/枚举/图谱编码)可直接采纳,其余需人工修。
          <el-tag v-if="anaBatchStaged" size="small" type="info" effect="plain" style="margin-left:6px">已暂存·再开不重跑</el-tag>
        </div>
        <div style="max-height:52vh;overflow:auto">
          <div v-for="it in anaBatchItems" :key="it.question_id"
            style="display:flex;align-items:flex-start;gap:8px;padding:6px 0;border-bottom:1px dashed #f0f0f0;font-size:12px">
            <el-tag size="small" :type="it.analysis && !it.errors.length ? 'success' : 'warning'" style="flex-shrink:0">
              {{ it.analysis && !it.errors.length ? '通过' : '需改' }}
            </el-tag>
            <span style="width:30px;color:#909399;flex-shrink:0">{{ (anaBatchQmap[it.question_id] || {}).question_no }}</span>
            <div style="flex:1;min-width:0">
              <div style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#303133">{{ anaSummary(it) }}</div>
              <div v-if="it.errors.length" style="color:#e6a23c">{{ it.errors.join(';') }}</div>
            </div>
            <el-button size="small" text type="primary" style="height:20px;padding:0 6px;flex-shrink:0"
              :disabled="!it.analysis" @click="viewAnaBatchItem(it)">查看</el-button>
            <el-button size="small" text type="primary" style="height:20px;padding:0 6px;flex-shrink:0" @click="editAnaBatchItem(it)">改</el-button>
          </div>
        </div>
        <div style="display:flex;align-items:center;margin-top:12px">
          <span style="font-size:12px;color:#a0a4ab">解析结果已暂存,「一键采纳/人工确认」才正式写库</span>
          <div style="margin-left:auto">
            <el-button @click="reparseAnaBatch">重新解析</el-button>
            <el-button @click="anaBatchDlg = false">关闭</el-button>
            <el-button type="primary" :loading="anaBatchSaving" :disabled="!anaBatchPassCount" @click="adoptAnaBatch">
              一键采纳 {{ anaBatchPassCount }} 道通过项
            </el-button>
          </div>
        </div>
      </template>
    </el-dialog>

    <!-- 受控知识点树选择器:给某题/某大题挂知识点(只能挑已建节点) -->
    <el-dialog v-model="kpPickerDlg" title="挂知识点(受控树)" width="460px" append-to-body>
      <div style="font-size:12px;color:#909399;margin-bottom:8px">
        {{ kpTargetSection ? `为「${kpTargetSection}」整段挑知识点(挂到该大题所有小问)` : `为「${kpTarget?.question_no}」题挑知识点` }},点击节点即挂上
      </div>
      <el-input v-model="kpFilter" placeholder="搜索知识点名" clearable style="margin-bottom:8px" />
      <el-tree ref="kpTreeRef" :data="kpTree" :props="kpTreeProps" node-key="id"
        :filter-node-method="filterKpNode" :expand-on-click-node="false"
        style="max-height:420px;overflow:auto">
        <template #default="{ data }">
          <span @click="onPickKp(data)" style="cursor:pointer">{{ data.name }}</span>
        </template>
      </el-tree>
    </el-dialog>

    <!-- 缺口建议·未定分类:人工选归属分类,在其下新建该考点并挂到本题 -->
    <el-dialog v-model="propPickerDlg" title="选归属分类(新建考点)" width="460px" append-to-body>
      <div style="font-size:12px;color:#909399;margin-bottom:8px">
        将新建考点「<b>{{ propTarget?.p.name }}</b>」并归到所选分类下,挂到「{{ propTarget?.q.question_no }}」题。点击下方某个分类即归到其下。
      </div>
      <el-input v-model="propFilter" placeholder="搜索分类名" clearable style="margin-bottom:8px" />
      <el-tree ref="propTreeRef" :data="kpTree" :props="kpTreeProps" node-key="id"
        :filter-node-method="filterKpNode" :expand-on-click-node="false"
        style="max-height:420px;overflow:auto">
        <template #default="{ data }">
          <span @click="onPickProposalParent(data)" style="cursor:pointer">{{ data.name }}</span>
        </template>
      </el-tree>
    </el-dialog>

    <!-- 书面表达评分量表(运营可配置,全局生效)-->
    <el-dialog v-model="rubricDlg" title="书面表达评分量表(运营可配置)" width="480px" append-to-body>
      <div style="font-size:12px;color:#909399;margin-bottom:14px">AI 5 维批改的满分与各维达标线,全局生效(学生端满分、掌握判定均读此配置)。</div>
      <el-form label-width="150px" size="small">
        <el-form-item label="满分">
          <el-input-number v-model="rubric.full_score" :min="1" :max="100" />
          <span style="margin-left:8px;color:#909399;font-size:12px">中考 20 / 高考可设 25</span>
        </el-form-item>
        <el-form-item label="语言准确达标线">
          <el-input-number v-model="rubric.accuracy_pass_ratio" :min="0" :max="1" :step="0.05" :precision="2" />
          <span style="margin-left:8px;color:#909399;font-size:12px">得分/满分 ≥ 此比例算达标</span>
        </el-form-item>
        <el-form-item label="结构连贯达标线">
          <el-input-number v-model="rubric.organization_pass_ratio" :min="0" :max="1" :step="0.05" :precision="2" />
        </el-form-item>
        <el-form-item label="丰富度达标(目标句型数)">
          <el-input-number v-model="rubric.richness_min_targets" :min="0" :max="10" />
          <span style="margin-left:8px;color:#909399;font-size:12px">至少命中几个目标句型算达标</span>
        </el-form-item>
      </el-form>
      <div style="text-align:right">
        <el-button @click="rubricDlg = false">取消</el-button>
        <el-button type="primary" :loading="rubricSaving" @click="saveRubric">保存</el-button>
      </div>
    </el-dialog>

    <!-- 大题级 AI 建议:选该题型提示词 → AI 对整段每题建议考点 -->
    <el-dialog v-model="secSuggestDlg" title="一键挂知识点(AI 建议)" width="560px" append-to-body>
      <div style="font-size:13px;color:#606266;margin-bottom:10px">
        大题「{{ secSuggestName }}」(题型:{{ secSuggestType }})—— 选一套提示词,AI 为该段每题建议考点(不自动挂,逐题 ✓ 采纳)。
      </div>
      <el-empty v-if="!secPrompts.length" description="该题型暂无提示词,请先到「知识点 AI 提示词」配置" :image-size="44" />
      <el-radio-group v-else v-model="secPromptId" style="display:block">
        <div v-for="p in secPrompts" :key="p.id || p.name" style="border:1px solid #ebeef5;border-radius:6px;padding:8px 10px;margin-bottom:8px">
          <el-radio :value="p.id">
            {{ p.name }}<span v-if="p.is_default" style="color:#67c23a;font-size:12px;margin-left:6px">默认</span>
          </el-radio>
          <div style="font-size:12px;color:#909399;white-space:pre-wrap;margin-top:4px">{{ p.text }}</div>
        </div>
      </el-radio-group>
      <template #footer>
        <el-button @click="secSuggestDlg = false">取消</el-button>
        <el-button type="primary" :loading="secSuggesting" :disabled="!secPrompts.length" @click="runSectionSuggest">开始 AI 建议</el-button>
      </template>
    </el-dialog>

    <!-- 批量上传真题:文件 → COS + 建草稿占位试卷(题目延后解析)-->
    <el-dialog v-model="batchDlg" title="批量上传真题(文件 → COS,建草稿占位)" width="820px" :close-on-click-modal="false">
      <el-form :inline="true" label-width="72px" style="margin-bottom:10px">
        <el-form-item label="教材版本" required>
          <el-select v-model="metaTextbook" style="width:140px">
            <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="学段" required>
          <el-select v-model="metaStage" style="width:100px" @change="metaGrade = ''">
            <el-option v-for="s in STAGES" :key="s" :label="STAGE_LABEL[s]" :value="s" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="metaGrade" clearable placeholder="选填" style="width:120px">
            <el-option v-for="g in GRADES[metaStage]" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="上下册">
          <el-select v-model="metaSemester" clearable placeholder="选填" style="width:100px">
            <el-option label="上册" value="上" /><el-option label="下册" value="下" />
          </el-select>
        </el-form-item>
        <el-form-item label="考试类型">
          <el-select v-model="metaExamType" style="width:120px">
            <el-option v-for="e in EXAM_TYPES" :key="e.value" :label="e.label" :value="e.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区">
          <el-cascader ref="regionCascader" v-model="regionPath" :props="regionProps"
            clearable placeholder="选填:省→市" style="width:220px" @change="onRegionChange" />
        </el-form-item>
      </el-form>
      <el-alert type="info" :closable="false" style="margin-bottom:12px"
        title="上面的元信息应用于本次所有文件;试卷名默认取文件名。文件只传 COS + 建草稿占位试卷(0 题),题目之后再解析。支持 pdf / doc / docx,可多选。" />
      <el-upload drag :auto-upload="false" multiple :on-change="onBatchFiles" :on-remove="onBatchFiles"
        accept=".pdf,.doc,.docx">
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">拖入或点击选择 <b>多份真题文件</b>(pdf / word)</div>
      </el-upload>
      <el-table v-if="batchResults.length" :data="batchResults" border size="small" style="margin-top:12px" max-height="260">
        <el-table-column prop="filename" label="文件" min-width="220" show-overflow-tooltip />
        <el-table-column label="结果" width="200">
          <template #default="{ row }">
            <el-tag v-if="row.ok" size="small" type="success">已建草稿{{ row.cos ? ' · 已传COS' : ' · COS未配' }}</el-tag>
            <el-tag v-else-if="row.duplicate" size="small" type="warning" effect="plain">试卷名已存在 · 已跳过</el-tag>
            <span v-else style="color:#F56C6C;font-size:12px">{{ row.error }}</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="batchDlg = false">关闭</el-button>
        <el-button type="primary" :loading="batchUploading" :disabled="!batchFiles.length" @click="submitBatch">
          上传{{ batchFiles.length ? `（${batchFiles.length} 份）` : '' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="dlg" title="上传真题 → 抽题 → 校对导入" width="900px" @close="stopPoll" :close-on-click-modal="false">
      <!-- 选源 -->
      <div v-if="step === 0">
        <el-form :inline="true" label-width="72px" style="margin-bottom:10px">
          <el-form-item label="教材版本" required>
            <el-select v-model="metaTextbook" style="width:140px">
              <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>
          <el-form-item label="学段" required>
            <el-select v-model="metaStage" style="width:100px" @change="metaGrade = ''">
              <el-option v-for="s in STAGES" :key="s" :label="STAGE_LABEL[s]" :value="s" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-select v-model="metaGrade" clearable placeholder="选填" style="width:120px">
              <el-option v-for="g in GRADES[metaStage]" :key="g" :label="g" :value="g" />
            </el-select>
          </el-form-item>
          <el-form-item label="上下册">
            <el-select v-model="metaSemester" clearable placeholder="选填" style="width:100px">
              <el-option label="上册" value="上" /><el-option label="下册" value="下" />
            </el-select>
          </el-form-item>
          <el-form-item label="考试类型">
            <el-select v-model="metaExamType" style="width:120px">
              <el-option v-for="e in EXAM_TYPES" :key="e.value" :label="e.label" :value="e.value" />
            </el-select>
          </el-form-item>
          <el-form-item label="地区">
            <el-cascader ref="regionCascader" v-model="regionPath" :props="regionProps"
              clearable placeholder="选填:省→市(最细到市)" style="width:240px" @change="onRegionChange" />
          </el-form-item>
          <el-form-item label="试卷名">
            <el-input v-model="metaPaperName" clearable placeholder="选填:缺省按地区/教材/年级自动命名" style="width:300px" />
          </el-form-item>
        </el-form>
        <el-alert type="info" :closable="false" style="margin-bottom:12px"
          title="教材+学段必选(挂知识节点/匹配);年级/上下册/地区选填存档。文本版 PDF / Word(.docx)直接取字;扫描版/拍照请上传图片走 OCR。文件优先,有文件时忽略图片。" />
        <el-upload drag :auto-upload="false" :limit="1" :on-change="onFileChange" accept=".pdf,.docx">
          <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
          <div class="el-upload__text">拖入或点击选择 <b>真题 PDF / Word(.docx)</b>(文本版)</div>
        </el-upload>
        <div style="margin:16px 0 6px;color:#909399;font-size:13px">或:上传真题图片(扫描/拍照,走 OCR,可多张)</div>
        <el-upload :auto-upload="false" list-type="picture-card" multiple
          :on-change="onImagesChange" :on-remove="onImagesChange" accept="image/*">
          <el-icon><UploadFilled /></el-icon>
        </el-upload>
        <div style="margin:10px 0 6px;color:#c0c4cc;font-size:12px">高级:也可直接粘贴图片 URL(每行一个)</div>
        <el-input v-model="imageUrlsText" type="textarea" :rows="2" placeholder="https://.../p1.jpg&#10;https://.../p2.jpg" />
        <div style="text-align:right;margin-top:16px">
          <el-button type="primary" :loading="uploadingImg" @click="startExtract">
            {{ uploadingImg ? '图片上传中…' : '开始抽题' }}
          </el-button>
        </div>
      </div>

      <!-- 抽题中 -->
      <div v-else-if="step === 1" class="gen-loading">
        <div style="font-size:15px;font-weight:600">AI 抽题中…</div>
        <div style="font-size:13px;color:#909399;margin-top:6px">整卷拆题约 30–90 秒,可关窗口稍后重开</div>
        <el-progress :percentage="100" :indeterminate="true" :duration="2" style="width:320px;margin-top:16px" />
      </div>

      <!-- 校对 -->
      <div v-else-if="step === 2">
        <div style="margin-bottom:8px;color:#606266">抽出 {{ editRows.length }} 题,核对/编辑后导入(可填 KP 名挂知识节点);阅读/完形等「短文+小问」按题组呈现,短文存一份</div>
        <div style="max-height:460px;overflow:auto">
          <div v-for="(g, gi) in editGroups" :key="gi" :style="g.key ? 'border:1px solid #ebeef5;border-radius:6px;padding:8px;margin-bottom:10px;background:#fafcff' : 'margin-bottom:10px'">
            <div v-if="g.section" style="font-size:12px;color:#67c23a;font-weight:600;margin-bottom:4px">【{{ g.section }}】</div>
            <div v-if="g.key" style="margin-bottom:6px">
              <span style="font-size:12px;color:#409eff;font-weight:600"><el-icon style="vertical-align:-2px;margin-right:4px"><Notebook /></el-icon>短文题组 · {{ g.rows.length }} 小问共享</span>
              <el-input v-model="passages[g.key]" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="短文/材料正文(本组小问共用)" style="margin-top:4px" />
            </div>
            <el-table :data="g.rows" border size="small">
              <el-table-column label="#" width="48" align="center"><template #default="{ row }">{{ row.question_no }}</template></el-table-column>
              <el-table-column :label="g.key ? '小问题干' : '题干'" min-width="240">
                <template #default="{ row }"><el-input v-model="row.stem" type="textarea" :rows="2" /></template>
              </el-table-column>
              <el-table-column label="答案" width="90"><template #default="{ row }"><el-input v-model="row.answer" /></template></el-table-column>
              <el-table-column label="题型" width="96"><template #default="{ row }">
                <el-select v-model="row.question_type" size="small">
                  <el-option v-for="t in QUESTION_TYPES" :key="t" :label="t" :value="t" />
                </el-select>
              </template></el-table-column>
              <el-table-column label="难度" width="80"><template #default="{ row }"><el-input-number v-model="row.difficulty" :min="1" :max="5" size="small" controls-position="right" /></template></el-table-column>
              <el-table-column label="知识点(逗号分隔)" width="160"><template #default="{ row }"><el-input v-model="row.kp_names" placeholder="如:定语从句" /></template></el-table-column>
              <el-table-column label="" width="50" align="center">
                <template #default="{ row }"><el-button size="small" type="danger" link @click="delRow(row)">删</el-button></template>
              </el-table-column>
            </el-table>
          </div>
        </div>
        <div style="text-align:right;margin-top:16px">
          <el-button @click="step = 0">上一步</el-button>
          <el-button type="primary" :loading="importing" @click="doImport">导入 {{ editRows.length }} 题</el-button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.gen-loading { display: flex; flex-direction: column; align-items: center; padding: 40px 0; }
</style>

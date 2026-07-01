<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Warning, Document, Notebook } from '@element-plus/icons-vue'
import {
  listPlatformPapers, getPlatformPaper, publishPlatformPaper, deletePlatformPapers, genSimBulk, getSimGenJob,
  attachQuestionKp, detachQuestionKp, attachSectionKp, attachKpBulk, suggestPaperKp, getNodeTree, getKpPrompts,
  createKnowledgeNode,
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

function onStageFilterChange() { filGrade.value = ''; load() }
function resetFilters() {
  statusFilter.value = ''; filTextbook.value = ''; filStage.value = ''
  filGrade.value = ''; filExam.value = ''; filRegionPath.value = []; filYear.value = ''
  load()
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
      limit: 50,
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

// 重新解析:清掉旧题、按原卷重新拆题入库(幂等)
const reparsing = ref(false)
async function onReparse() {
  if (!curPaper.value) return
  try {
    await ElMessageBox.confirm('将清空本卷现有题目,按原卷文件重新解析拆题(草稿)。是否继续?',
      '重新解析', { type: 'warning', confirmButtonText: '重新解析' })
  } catch { return }
  reparsing.value = true
  paperLoading.value = true
  try {
    const r = await parsePaper(curPaper.value.id)
    if (r.status === 'parsed') ElMessage.success(`已重新解析:${r.imported} 题`)
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
const QUESTION_TYPES = ['单选', '填空', '完型', '阅读', '写作', '判断', '连线']  // 与 ai_question_type_enum 对齐
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
      <el-select v-model="filTextbook" placeholder="教材" clearable style="width:108px" @change="load">
        <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
      </el-select>
      <el-select v-model="filStage" placeholder="学段" clearable style="width:88px" @change="onStageFilterChange">
        <el-option v-for="s in STAGES" :key="s" :label="STAGE_LABEL[s]" :value="s" />
      </el-select>
      <el-select v-model="filGrade" placeholder="年级" clearable :disabled="!filStage" style="width:98px" @change="load">
        <el-option v-for="g in (GRADES[filStage] || [])" :key="g" :label="g" :value="g" />
      </el-select>
      <el-cascader v-model="filRegionPath" :props="regionProps" clearable placeholder="地区" style="width:160px" @change="load" />
      <el-select v-model="filExam" placeholder="考试" clearable style="width:96px" @change="load">
        <el-option v-for="e in EXAM_TYPES.filter(x => x.value)" :key="e.value" :label="e.label" :value="e.value" />
      </el-select>
      <el-select v-model="filYear" placeholder="年份" clearable filterable style="width:96px" @change="load">
        <el-option v-for="y in YEAR_OPTS" :key="y" :label="y + '年'" :value="y" />
      </el-select>
      <el-select v-model="statusFilter" placeholder="状态" clearable style="width:96px" @change="load">
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

    <!-- 试卷详情:整卷题(按大题分节、阅读题组折叠)+ 整卷发布 + 勾选派生仿真 -->
    <el-dialog v-model="paperDlg" :title="curPaper ? curPaper.name : '试卷详情'" width="960px" :close-on-click-modal="false">
      <div v-loading="paperLoading">
        <div style="display:flex;align-items:center;margin-bottom:10px;gap:12px">
          <el-tag :type="curPaper?.status === 'published' ? 'success' : 'info'" size="small">{{ curPaper?.status === 'published' ? '已发布' : '草稿' }}</el-tag>
          <span style="color:#606266">共 {{ curPaper?.question_count }} 题,已发布 {{ curPaper?.published_count }}</span>
          <span style="color:#909399;font-size:12px">已勾选 {{ checkedIds.length }} 题</span>
          <el-tag v-if="unmappedCount" type="warning" size="small"><el-icon style="vertical-align:-2px;margin-right:4px"><Warning /></el-icon>{{ unmappedCount }} 题未挂知识点</el-tag>
          <div style="flex:1"></div>
          <el-button v-if="curPaper?.source_filename" :loading="reparsing" @click="onReparse"
            title="清空本卷题目,按原卷文件重新拆题(草稿)">重新解析</el-button>
          <el-button :loading="suggesting" @click="onSuggestKp"
            title="整卷按每个大题/题型分别调用其匹配提示词,候选考点按本卷学段(高⊇初⊇小)过滤">AI 整卷匹配知识点</el-button>
          <el-button v-if="suggestTotal" type="warning" :loading="acceptingAll" @click="acceptAllSuggest">采纳全部建议 ({{ suggestTotal }})</el-button>
          <el-button type="success" :disabled="curPaper?.status === 'published'" @click="onPublishPaper">发布成为母题</el-button>
          <el-button type="primary" :disabled="!checkedIds.length" @click="onGenSimChecked">勾选题派生仿真</el-button>
          <span v-if="simGen.running" style="font-size:12px;color:#409eff">后台派生中 {{ simGen.done }}/{{ simGen.total || '…' }} 题位，已生成 {{ simGen.generated }} 道</span>
        </div>
        <div style="max-height:520px;overflow:auto">
          <!-- font-size:14px 复位:el-checkbox-group 默认 font-size:0 会让组内纯文本不可见 -->
          <el-checkbox-group v-model="checkedIds" style="font-size:14px;line-height:1.5">
            <div v-for="(sec, si) in paperSections" :key="si" style="margin-bottom:14px">
              <div style="font-size:14px;font-weight:600;color:#303133;margin-bottom:6px;border-left:3px solid #409eff;padding-left:8px;display:flex;align-items:center;gap:8px">
                <span>{{ sec.name }}</span>
                <el-button size="small" text type="primary" style="height:22px;padding:0 6px" @click="openSectionSuggest(sec.name)">一键挂知识点(AI)</el-button>
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

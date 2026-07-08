<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Document, Notebook, Search, Cpu, CircleCheck, CircleClose, Delete, Plus, Collection } from '@element-plus/icons-vue'
import {
  listCurriculumUnits, deleteCurriculumUnits,
  uploadCurriculumPdf, generateFromPdf, getGenJob, listGenJobs,
  startPdfOcr, getPdfOcrStatus, retryGenJob,
  fetchUnitPdfBlob, getUnitStructured, generateUnitStructured, linkUnitStructured,
  linkSectionNode, unlinkSectionNode, newNodeForSection, getNodeTree, getUnitLinkedNodes,
  getUnitWords, saveUnitWords, deleteUnitWord, ocrUnitWords, parseUnitWordsText,
  uploadParseLs, listUploadedLs, linkUploadedLsNode, newUploadedLsNode, deleteUploadedLs, autoLinkUnitLs,
  type UnitLinkedNode, type UploadedLsItem,
  type UnitSegment, type GenJob, type UnitStructured, type UnitWordItem,
} from '../api/admin'
import type { AdminCurriculumUnit, NodeTreeItem } from '../types'

const router = useRouter()
function goUploadLs() { router.push({ path: '/long-sentences', query: { upload: '1' } }) }

// ── 单元列表 ──────────────────────────────────────────────────────────────────
const rows = ref<AdminCurriculumUnit[]>([])
const loading = ref(false)

const filterTextbook = ref('')
const filterGrade    = ref('')
const filterSemester = ref('')

// 服务端分页 + 服务端筛选;下拉可选值由后端 options 全量去重给出(排序在后端做好)。
const total    = ref(0)
const page     = ref(1)
const pageSize = 50
const options  = ref<{ textbooks: string[]; grades: string[]; all_grades?: string[]; semesters: string[] }>({ textbooks: [], grades: [], all_grades: [], semesters: [] })
const textbookOptions = computed(() => options.value.textbooks)
const gradeOptions    = computed(() => options.value.grades)
const semesterOptions = computed(() => options.value.semesters)

async function load() {
  loading.value = true
  try {
    const r = await listCurriculumUnits({
      textbook_version: filterTextbook.value || undefined,
      grade:            filterGrade.value    || undefined,
      semester:         filterSemester.value || undefined,
      skip: (page.value - 1) * pageSize, limit: pageSize,
    })
    rows.value = r.items
    total.value = r.total
    options.value = r.options
    // 删到本页空了(如末页删光)→ 退到最后一页重取,避免停在空页
    if (!rows.value.length && page.value > 1 && total.value > 0) {
      page.value = Math.ceil(total.value / pageSize)
      return await load()
    }
  }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
// 筛选变更:回到第一页再查
function reload() { page.value = 1; load() }

// 上下架已移到独立「教材版本维护」页(curriculum_catalog);本页只管内容整理,不再发布/下架。

// ── 选择删除 ──────────────────────────────────────────────────────────────────
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selected = ref<AdminCurriculumUnit[]>([])
const deleting = ref(false)
function onSelectionChange(rows: AdminCurriculumUnit[]) { selected.value = rows }

function unitLabel(r: AdminCurriculumUnit) {
  return `${r.textbook_version} ${r.grade} ${r.semester}学期 U${r.unit_no}`
}

// 并发池:对 items 跑 worker,最多 concurrency 个同时进行
async function runPool<T>(items: T[], worker: (it: T) => Promise<void>, concurrency: number) {
  let i = 0
  const next = async (): Promise<void> => {
    while (i < items.length) {
      const it = items[i++]
      await worker(it)
    }
  }
  await Promise.all(Array.from({ length: Math.min(concurrency, items.length) }, next))
}

// 批量 LLM 解析选中单元(并发)
const batchParsing = ref(false)
const batchProg = ref({ done: 0, total: 0, failed: 0 })
async function batchParseSelected() {
  const units = selected.value.slice()
  if (!units.length) { ElMessage.warning('请先勾选要解析的单元'); return }
  try {
    await ElMessageBox.confirm(
      `将对选中的 ${units.length} 个单元逐个用 LLM 解析单元(各自覆盖已有的单元解析),并发执行。是否继续?`,
      '批量 LLM 解析', { type: 'warning', confirmButtonText: '开始解析', cancelButtonText: '取消' })
  } catch { return }
  batchParsing.value = true
  batchProg.value = { done: 0, total: units.length, failed: 0 }
  await runPool(units, async (u) => {
    try { await generateUnitStructured(u.unit_id) }
    catch (e: any) { batchProg.value.failed++; ElMessage.error(`${unitLabel(u)} 解析失败:${e?.message || ''}`) }
    finally { batchProg.value.done++ }
  }, 4)
  batchParsing.value = false
  const ok = batchProg.value.total - batchProg.value.failed
  ElMessage.success(`批量解析完成:${ok} 成功${batchProg.value.failed ? `、${batchProg.value.failed} 失败` : ''}`)
  await load()
}

async function deleteUnits(targets: AdminCurriculumUnit[]) {
  if (!targets.length) return
  const names = targets.slice(0, 8).map(unitLabel).join('、')
  const more = targets.length > 8 ? ` 等 ${targets.length} 个单元` : ''
  try {
    await ElMessageBox.confirm(
      `将删除 ${names}${more}，并连带删除：该单元与<b>知识图谱</b>的关联(单元考点边)、与<b>单词通</b>的关联(单元词表)、以及单元短文及其考点边。<br/><br/>` +
      `<span style="color:#909399">注：共享的知识节点、词汇主表本身不会被删除；该单元生成的练习题会解除单元关联后保留。此操作不可恢复。</span>`,
      `确认删除 ${targets.length} 个单元？`,
      { type: 'warning', confirmButtonText: '删除', confirmButtonClass: 'el-button--danger', cancelButtonText: '取消', dangerouslyUseHTMLString: true },
    )
  } catch { return }   // 用户取消
  deleting.value = true
  try {
    const { deleted } = await deleteCurriculumUnits(targets.map(r => r.unit_id))
    ElMessage.success(`已删除 ${deleted} 个单元及其关联`)
    tableRef.value?.clearSelection()
    selected.value = []
    await load()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  } finally {
    deleting.value = false
  }
}


const nodesDlg = ref(false)
const nodesLoading = ref(false)
// 单元考点 = 单元解析里语法点/听力考点已关联到知识图谱的节点(去重)
const unitKps = ref<UnitLinkedNode[]>([])
const nodesUnitTitle = ref('')
const nodesUnitId = ref('')


async function onViewNodes(row: AdminCurriculumUnit) {
  nodesUnitTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  nodesUnitId.value = row.unit_id
  nodesDlg.value = true
  nodesLoading.value = true
  unitKps.value = []
  try {
    unitKps.value = (await getUnitLinkedNodes(row.unit_id)).items
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    nodesLoading.value = false
  }
}

// ── 单元重点单词 ↔ 词力通 ──
const wordsDlg = ref(false)
const wordsUnit = ref<AdminCurriculumUnit | null>(null)
const wordsTitle = ref('')
const wordsLoading = ref(false)
const linkedWords = ref<UnitWordItem[]>([])        // 已挂在单元的词
const pendingWords = ref<UnitWordItem[]>([])       // OCR/手动待保存的词
const wordSaving = ref(false)
const ocrImages = ref<string[]>([])               // base64 dataURL 列表
const ocrBusy = ref(false)
const pasteText = ref('')                          // 粘贴的单词表文本
const parseBusy = ref(false)

function mergePending(items: UnitWordItem[]): number {
  const have = new Set([...linkedWords.value, ...pendingWords.value].map(w => w.word.toLowerCase()))
  const fresh = items.filter(w => !have.has((w.word || '').toLowerCase()))
  pendingWords.value.push(...fresh)
  return fresh.length
}
async function runParseText() {
  if (!wordsUnit.value || !pasteText.value.trim()) { ElMessage.warning('请先粘贴文本'); return }
  parseBusy.value = true
  try {
    const r = await parseUnitWordsText(wordsUnit.value.unit_id, pasteText.value)
    const n = mergePending(r.items)
    ElMessage.success(`解析到 ${r.items.length} 个,新增 ${n} 个到待保存(已去重)`)
    if (n) pasteText.value = ''
  } catch (e: any) { ElMessage.error(e?.message || '解析失败') }
  finally { parseBusy.value = false }
}

async function onViewWords(row: AdminCurriculumUnit) {
  wordsUnit.value = row
  wordsTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  wordsDlg.value = true
  wordsLoading.value = true
  linkedWords.value = []
  pendingWords.value = []
  ocrImages.value = []
  pasteText.value = ''
  try { linkedWords.value = (await getUnitWords(row.unit_id)).items }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { wordsLoading.value = false }
}
// el-upload 选图 → 读成 base64 存入 ocrImages(不自动上传)
function onPickImage(file: any) {
  const raw = file.raw || file
  if (!raw || !raw.type?.startsWith('image/')) { ElMessage.warning('请选择图片'); return }
  const reader = new FileReader()
  reader.onload = () => { ocrImages.value.push(String(reader.result)) }
  reader.readAsDataURL(raw)
}
function removeOcrImage(i: number) { ocrImages.value.splice(i, 1) }
async function runOcr() {
  if (!wordsUnit.value || !ocrImages.value.length) { ElMessage.warning('请先添加图片'); return }
  ocrBusy.value = true
  try {
    const r = await ocrUnitWords(wordsUnit.value.unit_id, ocrImages.value)
    const n = mergePending(r.items)
    ElMessage.success(`识别到 ${r.items.length} 个,新增 ${n} 个到待保存(已去重)`)
  } catch (e: any) { ElMessage.error(e?.message || 'OCR 失败') }
  finally { ocrBusy.value = false }
}
function addPendingRow() { pendingWords.value.push({ word: '', phonetic: '', meaning: '', type: 'word' }) }
function removePendingRow(i: number) { pendingWords.value.splice(i, 1) }
async function savePendingWords() {
  if (!wordsUnit.value) return
  const items = pendingWords.value.filter(w => (w.word || '').trim())
  if (!items.length) { ElMessage.warning('没有可保存的词'); return }
  wordSaving.value = true
  try {
    const r = await saveUnitWords(wordsUnit.value.unit_id, items, true)
    linkedWords.value = r.items
    pendingWords.value = []
    ocrImages.value = []
    wordsUnit.value.word_count = r.items.length
    ElMessage.success(`已保存:挂靠 ${r.counts.linked} 个、词力通新建 ${r.counts.created} 个`)
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { wordSaving.value = false }
}
async function removeLinkedWord(w: UnitWordItem) {
  if (!wordsUnit.value || !w.word_id) return
  try {
    await ElMessageBox.confirm(`从本单元移除「${w.word}」?(词力通词条保留)`, '移除', { type: 'warning' })
  } catch { return }
  try {
    await deleteUnitWord(wordsUnit.value.unit_id, w.word_id)
    linkedWords.value = linkedWords.value.filter(x => x.word_id !== w.word_id)
    wordsUnit.value.word_count = linkedWords.value.length
    ElMessage.success('已移除')
  } catch (e: any) { ElMessage.error(e?.message || '移除失败') }
}

// ── 单元长难句(粘贴文字 → LLM 语法点 → 关联知识图谱)──
const lsDlg = ref(false)
const lsUnit = ref<AdminCurriculumUnit | null>(null)
const lsTitle = ref('')
const lsLoading = ref(false)
const lsText = ref('')
const lsParsing = ref(false)
const lsItems = ref<UploadedLsItem[]>([])

async function onViewLs(row: AdminCurriculumUnit) {
  lsUnit.value = row
  lsTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  lsDlg.value = true
  lsLoading.value = true
  lsText.value = ''
  lsItems.value = []
  try { lsItems.value = (await listUploadedLs(100, row.unit_id)).items }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { lsLoading.value = false }
}
async function runLsParse() {
  if (!lsUnit.value || !lsText.value.trim()) { ElMessage.warning('请先粘贴文字'); return }
  lsParsing.value = true
  try {
    const r = await uploadParseLs(lsText.value, lsUnit.value.unit_id)
    lsItems.value = [...r.items, ...lsItems.value]
    ElMessage.success(`解析到 ${r.items.length} 个语法点,可逐个关联知识图谱`)
    if (r.items.length) lsText.value = ''
  } catch (e: any) { ElMessage.error(e?.message || 'LLM 解析失败') }
  finally { lsParsing.value = false }
}
const lsAutoLinking = ref(false)
async function onAutoLinkLs() {
  if (!lsUnit.value) return
  lsAutoLinking.value = true
  try {
    const r = await autoLinkUnitLs(lsUnit.value.unit_id)
    lsItems.value = r.items
    ElMessage.success(`分词打分关联完成:命中 ${r.counts.linked} 个、未命中 ${r.counts.unmatched} 个(已挂的跳过 ${r.counts.skipped})`)
  } catch (e: any) { ElMessage.error(e?.message || '关联失败') }
  finally { lsAutoLinking.value = false }
}
async function onLinkLs(it: UploadedLsItem) {
  const nid = pickNode.value[it.id]
  if (!nid) { ElMessage.warning('请先在目录里选一个节点'); return }
  try {
    const r = await linkUploadedLsNode(it.id, nid)
    it.node_code = r.node_code; it.node_name = r.name; it.node_id = r.node_id
    pickNode.value[it.id] = ''; relinkOpen.value[it.id] = false
    ElMessage.success(`已挂靠到「${r.name}」(${r.node_code})`)
  } catch (e: any) { ElMessage.error(e?.message || '挂靠失败') }
}
async function onNewNodeLs(it: UploadedLsItem) {
  const parent = pickNode.value[it.id]
  if (!parent) { ElMessage.warning('请先选一个父分类(在其下新建)'); return }
  try {
    const { value } = await ElMessageBox.prompt(
      '在所选父分类下新建知识图谱节点(手工标签),节点名:', '新建节点',
      { inputValue: it.point || '', confirmButtonText: '新建并挂靠', cancelButtonText: '取消' })
    const r = await newUploadedLsNode(it.id, parent, (value || '').trim())
    it.node_code = r.node_code; it.node_name = r.name; it.node_id = r.node_id
    pickNode.value[it.id] = ''; relinkOpen.value[it.id] = false
    reloadKgTree()   // 树多了新节点,立即重拉
    ElMessage.success(`已新建并挂靠「${r.name}」(${r.node_code})`)
  } catch { /* 取消 */ }
}
function onRelinkLs(it: UploadedLsItem) {
  pickNode.value[it.id] = it.node_id || ''
  relinkOpen.value[it.id] = true
}
async function removeLs(it: UploadedLsItem) {
  try { await ElMessageBox.confirm(`删除该长难句「${it.point}」?`, '删除', { type: 'warning' }) }
  catch { return }
  try {
    await deleteUploadedLs(it.id)
    lsItems.value = lsItems.value.filter(x => x.id !== it.id)
    ElMessage.success('已删除')
  } catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}

// ── 单元短文(听力/阅读/写作)──
const passDlg = ref(false)
const passLoading = ref(false)
const passTitle = ref('')
const passUnit = ref<AdminCurriculumUnit | null>(null)   // 当前单元(取 unit_id / unit_pdf_url)
const passGenerating = ref(false)
// 跨域 PDF 在 iframe 里 Chrome 不渲染(新标签却能开)。改走「后端同源代理→取 blob→blob: URL」内嵌。
const pdfSrc = ref('')
const pdfLoading = ref(false)
let pdfObjUrl = ''
function revokePdf() { if (pdfObjUrl) { URL.revokeObjectURL(pdfObjUrl); pdfObjUrl = '' } }
async function loadUnitPdf() {
  if (!passUnit.value?.unit_pdf_url) return
  pdfLoading.value = true
  try {
    const blob = await fetchUnitPdfBlob(passUnit.value.unit_id)
    revokePdf()
    pdfObjUrl = URL.createObjectURL(blob)
    pdfSrc.value = pdfObjUrl
  } catch (e: any) {
    ElMessage.error(e?.message || 'PDF 加载失败,可点「新标签打开」查看')
  } finally {
    pdfLoading.value = false
  }
}
// 结构化解析结果(语法点+分级句 / 听力考点+句组 / 作文要求+正文)
const structured = ref<UnitStructured>({ grammar: [], listening: [], writing: null })
const hasStructured = computed(() => !!(structured.value.grammar.length
  || structured.value.listening.length || structured.value.writing))
function openUnitPdf(row: AdminCurriculumUnit) {
  if (row.unit_pdf_url) window.open(row.unit_pdf_url, '_blank')
}
async function onViewPassages(row: AdminCurriculumUnit) {
  passTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  passUnit.value = row
  pdfSrc.value = ''                 // 等 @opened 再设,避免动画期 iframe 白屏
  passDlg.value = true
  passLoading.value = true
  structured.value = { grammar: [], listening: [], writing: null }
  pickNode.value = {}
  // 知识图谱树改为懒加载:第一次点开「挂靠」下拉时才拉(见 onKgDropdown),不在开弹框时拖慢
  try { structured.value = await getUnitStructured(row.unit_id) }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { passLoading.value = false }
}

async function onRegenerate() {
  if (!passUnit.value) return
  if (hasStructured.value) {
    try {
      await ElMessageBox.confirm(
        '将用单元原文(PDF)重新 LLM 解析,覆盖当前的「语法点 / 听力 / 作文」结构。是否继续？',
        '重新生成', { type: 'warning', confirmButtonText: '重新生成', cancelButtonText: '取消' })
    } catch { return }
  }
  passGenerating.value = true
  try {
    const r = await generateUnitStructured(passUnit.value.unit_id)
    structured.value = r
    const c = r.counts
    if (c && (c.grammar + c.listening + c.writing) > 0)
      ElMessage.success(`已解析:语法 ${c.grammar} 点 / 听力 ${c.listening} 点 / 作文 ${c.writing} · 共 ${c.sentences} 句`)
    else ElMessage.info('未解析出结构(可能原文为空或为 dev 模式)')
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    passGenerating.value = false
  }
}

// 第二步:关联知识图谱(语法点→词法/句法、听力考点→听力)
const passLinking = ref(false)
async function onLinkKg() {
  if (!passUnit.value || !hasStructured.value) return
  passLinking.value = true
  try {
    const r = await linkUnitStructured(passUnit.value.unit_id)
    structured.value = r
    const c = r.link_counts
    if (c) ElMessage.success(`已关联 ${c.linked} 个;${c.candidate} 个目录暂无→已落候选(去「候选审核」通过后再关联)`)
  } catch (e: any) {
    ElMessage.error(e?.message || '关联失败')
  } finally {
    passLinking.value = false
  }
}

// 人工挂靠/新建节点:知识图谱树(取 cf/jf 给语法、lt 给听力)
const kgTree = ref<NodeTreeItem[]>([])
const kgLoading = ref(false)
const pickNode = ref<Record<string, string>>({})   // section_id → 选中的目录节点 id
async function reloadKgTree() {
  kgLoading.value = true
  try { kgTree.value = (await getNodeTree('knowledge')).items }
  catch (e: any) { ElMessage.error(e?.message || '加载知识图谱失败') }
  finally { kgLoading.value = false }
}
async function ensureKgTree() {
  if (kgTree.value.length || kgLoading.value) return
  await reloadKgTree()
}
// 挂靠下拉展开时才懒加载知识图谱树(只首次拉,之后命中 component 缓存)
function onKgDropdown(visible: boolean) { if (visible) ensureKgTree() }
function subtreeByCodes(prefixes: string[]): NodeTreeItem[] {
  return kgTree.value.filter(n => prefixes.some(p => (n.code || '').startsWith(p)))
}
// 把目录子树拍平成可搜索的扁平列表(避免 el-tree-select 多实例共享 :data 的 No-data 坑)
interface FlatNode { value: string; name: string; code: string; depth: number }
function flatten(nodes: NodeTreeItem[], depth = 0, out: FlatNode[] = []): FlatNode[] {
  for (const n of nodes || []) {
    out.push({ value: n.id, name: n.name, code: n.code || '', depth })
    if (n.children?.length) flatten(n.children, depth + 1, out)
  }
  return out
}
// 语法点→词法/句法子树(扁平);听力→听力子树(扁平)
const grammarFlat = computed(() => flatten(subtreeByCodes(['cf', 'jf'])))
const listenFlat = computed(() => flatten(subtreeByCodes(['lt'])))

const relinkOpen = ref<Record<string, boolean>>({})   // section_id → 是否处于「改挂」编辑态
async function onManualLink(kind: string, sec: { id: string; node_code: string | null; node_name?: string | null }) {
  const nid = pickNode.value[sec.id]
  if (!nid) { ElMessage.warning('请先在目录里选一个节点'); return }
  try {
    const r = await linkSectionNode(sec.id, nid)
    sec.node_code = r.node_code   // 就地覆盖标签
    sec.node_name = r.name
    pickNode.value[sec.id] = ''
    relinkOpen.value[sec.id] = false
    ElMessage.success(`已挂靠到「${r.name}」(${r.node_code})`)
  } catch (e: any) { ElMessage.error(e?.message || '挂靠失败') }
}
async function onNewNode(kind: string, sec: { id: string; point_name: string | null; node_code: string | null; node_name?: string | null }) {
  const parent = pickNode.value[sec.id]
  if (!parent) { ElMessage.warning('请先选一个父分类(在其下新建)'); return }
  try {
    const { value } = await ElMessageBox.prompt(
      '在所选父分类下新建知识图谱节点(手工标签),节点名:', '新建节点',
      { inputValue: sec.point_name || '', confirmButtonText: '新建并挂靠', cancelButtonText: '取消' })
    const r = await newNodeForSection(sec.id, parent, (value || '').trim())
    sec.node_code = r.node_code
    sec.node_name = r.name
    pickNode.value[sec.id] = ''
    relinkOpen.value[sec.id] = false
    reloadKgTree()   // 树多了新节点,立即重拉(否则同弹框内其它下拉会变空→No data)
    ElMessage.success(`已新建并挂靠「${r.name}」(${r.node_code})`)
  } catch { /* 取消 */ }
}
// 改挂:保留原关联标签,展开选择器并预选中原节点;重选后「挂靠」覆盖
function onRelink(sec: { id: string; node_id: string | null }) {
  pickNode.value[sec.id] = sec.node_id || ''
  relinkOpen.value[sec.id] = true
}
function cancelRelink(sec: { id: string }) {
  relinkOpen.value[sec.id] = false
  pickNode.value[sec.id] = ''
}

// 取消关联:清该板块的图谱节点(就地清标签);单元内无其它板块挂同节点时后端一并删聚合边
async function onUnlink(sec: { id: string; node_id: string | null; node_code: string | null; node_name?: string | null }) {
  try {
    await ElMessageBox.confirm('取消该考点与知识图谱节点的关联?学生端单元考点会相应减少(可再重新挂靠)。',
      '取消关联', { type: 'warning' })
  } catch { return }
  try {
    await unlinkSectionNode(sec.id)
    sec.node_id = null; sec.node_code = null; sec.node_name = null
    relinkOpen.value[sec.id] = false
    pickNode.value[sec.id] = ''
    ElMessage.success('已取消关联')
  } catch (e: any) { ElMessage.error(e?.message || '取消关联失败') }
}

// 句子难度色(0–100)
function diffColor(d: number | null): string {
  if (d == null) return '#c0c4cc'
  if (d >= 60) return '#F56C6C'
  if (d >= 35) return '#E6A23C'
  return '#67C23A'
}

// ── PDF 上传 Dialog ──────────────────────────────────────────────────────────

const VERSIONS     = ['译林版', '人教版', '外研版', '北师大版']
// 规范年级主数据:优先用后端下发的 all_grades(单一真源);兜底为规范全量。禁止再用「七年级」旧格式。
const _CANON_GRADES = ['小学1年级', '小学2年级', '小学3年级', '小学4年级', '小学5年级', '小学6年级',
  '初中7年级', '初中8年级', '初中9年级', '高中1年级', '高中2年级', '高中3年级']
const GRADES       = computed(() => (options.value.all_grades?.length ? options.value.all_grades : _CANON_GRADES))
const SEMS         = ['上', '下']

const pdfDialogVisible = ref(false)
const pdfStep          = ref(0)          // 0=信息, 1=上传, 2=分单元, 3=生成中/结果

// step 0
const pdfTextbook = ref('译林版')
const pdfGrade    = ref('七年级')
const pdfSemester = ref('上')

// step 1
const pdfFile          = ref<File | null>(null)
const pdfUploading     = ref(false)
const pdfFileId        = ref('')
const pdfTotalPages    = ref(0)
const pdfAutoSuccess   = ref(false)
const pdfPageOffset    = ref(0)        // 印刷页码 = PDF 页序 − offset
const pdfUploadErr     = ref('')
// 扫描件 OCR
const pdfScanned       = ref(false)
const ocrRunning       = ref(false)
const ocrDone          = ref(0)
const ocrTotal         = ref(0)
let ocrTimer: ReturnType<typeof setTimeout> | null = null
function stopOcrPoll() { if (ocrTimer) { clearTimeout(ocrTimer); ocrTimer = null } }
async function startOcr() {
  if (!pdfFileId.value) return
  ocrRunning.value = true; ocrDone.value = 0; ocrTotal.value = pdfTotalPages.value
  try { await startPdfOcr(pdfFileId.value) } catch (e: any) { ElMessage.error(e?.message || 'OCR 启动失败'); ocrRunning.value = false; return }
  const poll = async () => {
    try {
      const st = await getPdfOcrStatus(pdfFileId.value)
      ocrDone.value = st.done; ocrTotal.value = st.total || pdfTotalPages.value
      if (st.status === 'done') {
        ocrRunning.value = false; pdfScanned.value = false
        pdfAutoSuccess.value = st.segments.length > 0
        segments.value = st.segments.map(s => ({ ...s }))
        ElMessage.success(`OCR 完成,识别到 ${st.segments.length} 个单元`)
        return
      }
      if (st.status === 'error') { ocrRunning.value = false; ElMessage.error('OCR 失败:' + (st.error || '')); return }
      ocrTimer = setTimeout(poll, 2500)
    } catch { ocrTimer = setTimeout(poll, 3000) }
  }
  ocrTimer = setTimeout(poll, 2000)
}

function printedPage(pdfNo: number): string {
  return pdfPageOffset.value > 0 ? `印刷 P${pdfNo - pdfPageOffset.value}` : ''
}

// step 2
const segments     = ref<UnitSegment[]>([])
const segErr       = ref('')

// step 3:异步任务进度(方案 A)
const pdfGenerating = ref(false)
const pdfJob        = ref<GenJob | null>(null)
let pdfPollTimer: ReturnType<typeof setTimeout> | null = null

function stopPoll() { if (pdfPollTimer) { clearTimeout(pdfPollTimer); pdfPollTimer = null } }

async function pollJob(jobId: string) {
  try {
    pdfJob.value = await getGenJob(jobId)
    if (pdfJob.value.status === 'running') {
      pdfPollTimer = setTimeout(() => pollJob(jobId), 2500)   // 每 2.5s 轮询
    } else {
      pdfGenerating.value = false
      if (pdfJob.value.done > 0) { ElMessage.success(`拆分完成:${pdfJob.value.done} 个单元已挂 PDF`); await load() }
      if (pdfJob.value.failed > 0) ElMessage.warning(`${pdfJob.value.failed} 个单元失败,可点「重试失败单元」`)
    }
  } catch (e: any) {
    pdfGenerating.value = false
    ElMessage.error(e?.message || '查询进度失败')
  }
}
async function retryFailedUnits() {
  if (!pdfJob.value) return
  try {
    pdfGenerating.value = true
    const j = await retryGenJob(pdfJob.value.job_id)
    pdfJob.value = j
    pollJob(j.job_id)
    ElMessage.info('已重试失败单元')
  } catch (e: any) { pdfGenerating.value = false; ElMessage.error(e?.message || '重试失败') }
}

async function openPdfDialog() {
  stopPoll(); stopOcrPoll()
  pdfStep.value       = 0
  pdfFile.value       = null
  pdfFileId.value     = ''
  pdfTotalPages.value = 0
  pdfAutoSuccess.value= false
  pdfScanned.value    = false
  ocrRunning.value    = false
  pdfPageOffset.value = 0
  pdfUploadErr.value  = ''
  segments.value      = []
  segErr.value        = ''
  pdfJob.value        = null
  pdfGenerating.value = false
  pdfDialogVisible.value = true
  // 重开时:有在跑的任务 → 挂回进度;否则最近有失败的任务 → 显示结果供「重试失败单元」
  try {
    const running = await listGenJobs({ status: 'running', limit: 1 })
    if (running.length) {
      pdfStep.value = 3
      pdfGenerating.value = true
      pollJob(running[0].job_id)
      return
    }
    const failed = await listGenJobs({ status: 'failed', limit: 1 })
    if (failed.length) {
      pdfStep.value = 3
      pdfGenerating.value = false
      pdfJob.value = await getGenJob(failed[0].job_id)
    }
  } catch { /* 忽略 */ }
}

function onFileChange(uploadFile: any) {
  pdfFile.value = uploadFile.raw as File
  pdfUploadErr.value = ''
}

async function doUpload() {
  if (!pdfFile.value) { ElMessage.warning('请先选择 PDF 文件'); return }
  pdfUploading.value = true
  pdfUploadErr.value = ''
  try {
    const out = await uploadCurriculumPdf(pdfFile.value)
    pdfFileId.value     = out.file_id
    pdfTotalPages.value = out.total_pages
    pdfScanned.value    = !!out.is_scanned
    if (out.is_scanned) {       // 扫描件:无文字层 → 提示走 OCR(后台逐页识别)
      pdfStep.value = 2
      return
    }
    pdfAutoSuccess.value= out.auto_split_success
    pdfPageOffset.value = out.page_offset ?? 0
    segments.value      = out.auto_split_success
      ? out.auto_segments.map(s => ({ ...s }))
      : []
    pdfStep.value = 2
  } catch (e: any) {
    pdfUploadErr.value = e?.message || '上传失败'
  } finally {
    pdfUploading.value = false
  }
}

function addSegment() {
  const last    = segments.value[segments.value.length - 1]
  const nextNo  = segments.value.length + 1
  const start   = last ? last.end_page + 1 : 1
  segments.value.push({ unit_no: nextNo, start_page: start, end_page: Math.min(start + 19, pdfTotalPages.value || 999), detected_title: null })
}

function removeSegment(i: number) { segments.value.splice(i, 1) }

async function startPdfGenerate() {
  segErr.value = ''
  if (!segments.value.length) { segErr.value = '请至少添加一个单元'; return }
  for (const s of segments.value) {
    if (s.end_page < s.start_page) { segErr.value = `Unit ${s.unit_no} 结束页不能小于起始页`; return }
  }
  pdfStep.value    = 3
  pdfGenerating.value = true
  pdfJob.value     = null
  try {
    const created = await generateFromPdf(pdfFileId.value, {
      textbook_version: pdfTextbook.value,
      grade: pdfGrade.value,
      semester: pdfSemester.value,
      segments: segments.value,
    })
    // 秒回 job_id → 轮询进度(可关窗口,后台继续)
    pollJob(created.job_id)
  } catch (e: any) {
    pdfGenerating.value = false
    ElMessage.error(e?.message || '生成失败')
  }
}

// ── 一键生成学期 Dialog ───────────────────────────────────────────────────────


onMounted(load)
</script>

<template>
  <div>
    <!-- 工具栏 -->
    <div class="toolbar">
      <el-select v-model="filterTextbook" placeholder="教材版本" clearable style="width:140px" @change="reload">
        <el-option v-for="t in textbookOptions" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="filterGrade" placeholder="年级" clearable style="width:140px" @change="reload">
        <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="filterSemester" placeholder="学期" clearable style="width:100px" @change="reload">
        <el-option v-for="s in semesterOptions" :key="s" :label="s+'学期'" :value="s" />
      </el-select>
      <el-button @click="load" :loading="loading"><el-icon style="margin-right:4px"><Refresh /></el-icon>刷新</el-button>
      <span class="stat-txt">
        共 {{ total }} 个单元 ·
        本页已挂考点 {{ rows.filter(r => r.kp_count > 0).length }} 个
      </span>
      <div style="flex:1" />
      <el-button
        type="success" plain
        :disabled="!selected.length || batchParsing" :loading="batchParsing"
        @click="batchParseSelected"
      ><el-icon style="margin-right:4px"><Cpu /></el-icon>{{ batchParsing ? `解析中 ${batchProg.done}/${batchProg.total}` : `批量解析${selected.length ? `（${selected.length}）` : ''}` }}</el-button>
      <el-button
        type="danger" plain
        :disabled="!selected.length" :loading="deleting"
        @click="deleteUnits(selected)"
      ><el-icon style="margin-right:4px"><Delete /></el-icon>删除选中{{ selected.length ? `（${selected.length}）` : '' }}</el-button>
      <el-button @click="goUploadLs"><el-icon style="margin-right:4px"><Document /></el-icon>上传长难句</el-button>
      <el-button type="primary" @click="openPdfDialog"><el-icon style="margin-right:4px"><Document /></el-icon>上传教材 PDF</el-button>
    </div>

    <!-- 单元表格 -->
    <el-table ref="tableRef" v-loading="loading" :data="rows" border style="width:100%"
              row-key="unit_id" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="44" />
      <el-table-column prop="textbook_version" label="教材"   width="90" />
      <el-table-column prop="grade"            label="年级"   width="110" />
      <el-table-column prop="semester"         label="学期"   width="70">
        <template #default="{ row }">{{ row.semester }}学期</template>
      </el-table-column>
      <el-table-column prop="unit_no"    label="Unit"  width="60" align="center" />
      <el-table-column prop="unit_title" label="单元标题" min-width="160" show-overflow-tooltip />
      <el-table-column prop="kp_count"   label="单元考点"  width="80" align="center" />
      <el-table-column label="重点单词" width="100" align="center">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="onViewWords(row)">
            <el-icon style="margin-right:3px"><Collection /></el-icon>{{ row.word_count ? `${row.word_count} 词` : '挂单词' }}
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="380" fixed="right">
        <template #default="{ row }">
          <div class="act-row">
            <el-button size="small" type="primary" @click="onViewPassages(row)"><el-icon style="margin-right:4px"><Document /></el-icon>短文</el-button>
            <el-button v-if="row.unit_pdf_url" size="small" @click="openUnitPdf(row)"><el-icon style="margin-right:4px"><Notebook /></el-icon>原版PDF</el-button>
            <el-button size="small" @click="onViewNodes(row)">单元考点 {{ row.kp_count || 0 }}</el-button>
            <el-button size="small" @click="onViewLs(row)">长难句</el-button>
            <el-button size="small" type="danger" plain :loading="deleting" @click="deleteUnits([row])"><el-icon><Delete /></el-icon></el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="total > pageSize" style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <!-- ── 单元知识图谱节点 Dialog ── -->
    <AppDialog v-model="nodesDlg" :title="`单元考点 · ${nodesUnitTitle}`" width="640px">
      <div class="hint" style="margin-bottom:10px">单元考点 = 单元解析里语法点/听力考点已关联到知识图谱的节点(去重)。要增删请到「短文」弹框里挂靠/改挂。</div>
      <el-table v-loading="nodesLoading" :data="unitKps" border style="width:100%">
        <el-table-column label="知识图谱考点" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">{{ row.node_name }} <span class="muted">{{ row.node_code }}</span></template>
        </el-table-column>
        <el-table-column label="板块" width="100">
          <template #default="{ row }">{{ row.kinds.join(' / ') }}</template>
        </el-table-column>
        <el-table-column label="来源(解析点)" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">{{ row.points.join('、') }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!nodesLoading && !unitKps.length" description="该单元暂无已关联的考点,去「短文」弹框里把语法点/听力考点关联到知识图谱" :image-size="50" />
      <template #footer>
        <el-button @click="nodesDlg = false">关闭</el-button>
      </template>
    </AppDialog>

    <!-- ── 单元长难句(粘贴文字 → LLM 语法点 → 关联知识图谱)Dialog ── -->
    <AppDialog v-model="lsDlg" :title="`单元长难句 · ${lsTitle}`" width="940px" top="6vh">
      <div v-loading="lsLoading">
        <div class="words-ocr">
          <div class="pane-head"><span>① 粘贴长难句文字 → LLM 抽语法点</span></div>
          <el-input v-model="lsText" type="textarea" :rows="4" resize="vertical"
            placeholder="把含长难句的英文文字粘到这里(可整段),点解析自动抽出语法点 + 例句" />
          <el-button type="primary" :loading="lsParsing" :disabled="!lsText.trim()" style="margin-top:8px" @click="runLsParse">
            <el-icon style="margin-right:4px"><Cpu /></el-icon>LLM 解析语法点
          </el-button>
          <span class="muted" style="margin-left:8px">解析结果进下方列表,逐个「挂靠」到知识图谱</span>
        </div>

        <div class="pane-head" style="margin-top:14px">
          <span>② 本单元长难句({{ lsItems.length }})· 关联知识图谱</span>
          <el-button size="small" type="success" plain :loading="lsAutoLinking" :disabled="!lsItems.length"
            @click="onAutoLinkLs">
            <el-icon style="margin-right:4px"><Cpu /></el-icon>一键关联知识图谱
          </el-button>
        </div>
        <div v-for="it in lsItems" :key="it.id" class="sec-point">
          <div class="point-name">
            {{ it.point }}
            <el-tag v-if="it.difficulty != null" size="small" :style="{ background: diffColor(it.difficulty), color: '#fff', border: 'none' }">{{ it.difficulty }}</el-tag>
            <el-tag v-if="it.node_code" size="small" type="success" effect="plain" style="margin-left:6px">
              已关联 {{ it.node_name || it.node_code }} <span class="muted">{{ it.node_code }}</span>
            </el-tag>
            <el-button v-if="it.node_code && !relinkOpen[it.id]" size="small" link type="primary" style="margin-left:2px" @click="onRelinkLs(it)">改挂</el-button>
            <el-button size="small" link type="danger" style="margin-left:auto" @click="removeLs(it)"><el-icon><Delete /></el-icon></el-button>
          </div>
          <div class="sent-row"><span class="sent-text">{{ it.text }}</span></div>
          <div v-if="!it.node_code || relinkOpen[it.id]" class="link-row">
            <el-select v-model="pickNode[it.id]" filterable clearable :loading="kgLoading" size="small"
              @visible-change="onKgDropdown" style="width:280px" placeholder="选词法/句法目录节点(可输入名称/编码搜索)">
              <el-option v-for="o in grammarFlat" :key="o.value" :value="o.value" :label="`${o.name} ${o.code}`">
                <span :style="{ paddingLeft: o.depth * 12 + 'px' }">{{ o.name }} <span class="muted">{{ o.code }}</span></span>
              </el-option>
            </el-select>
            <el-button size="small" @click="onLinkLs(it)">{{ relinkOpen[it.id] ? '覆盖挂靠' : '挂靠' }}</el-button>
            <el-button size="small" type="primary" plain @click="onNewNodeLs(it)">目录没有→新建</el-button>
            <el-button v-if="relinkOpen[it.id]" size="small" link @click="cancelRelink(it)">取消</el-button>
          </div>
        </div>
        <el-empty v-if="!lsLoading && !lsItems.length" description="本单元暂无长难句,粘贴文字后点「LLM 解析语法点」" :image-size="50" />
      </div>
      <template #footer><el-button @click="lsDlg = false">关闭</el-button></template>
    </AppDialog>

    <!-- ── 单元重点单词(挂词力通)Dialog ── -->
    <AppDialog v-model="wordsDlg" :title="`单元重点单词 · ${wordsTitle}`" width="900px" top="6vh">
      <div v-loading="wordsLoading">
        <!-- 多图 OCR -->
        <div class="words-ocr">
          <div class="pane-head"><span>① 多图 OCR(单词表/词组页)</span></div>
          <div class="ocr-imgs">
            <div v-for="(img, i) in ocrImages" :key="i" class="ocr-thumb">
              <img :src="img" />
              <el-icon class="rm" @click="removeOcrImage(i)"><CircleClose /></el-icon>
            </div>
            <el-upload action="#" :auto-upload="false" :show-file-list="false" accept="image/*"
              multiple :on-change="onPickImage">
              <div class="ocr-add"><el-icon><Plus /></el-icon><span>加图片</span></div>
            </el-upload>
          </div>
          <el-button type="primary" :loading="ocrBusy" :disabled="!ocrImages.length" @click="runOcr">
            <el-icon style="margin-right:4px"><Cpu /></el-icon>识别这些图片
          </el-button>
          <span class="muted" style="margin-left:8px">识别结果进下方「待保存」,可编辑核对后再保存</span>
        </div>

        <!-- 文本粘贴 → LLM 解析 -->
        <div class="words-ocr" style="margin-top:12px">
          <div class="pane-head"><span>①′ 粘贴文本 → LLM 解析(单词表/词组)</span></div>
          <el-input v-model="pasteText" type="textarea" :rows="4" resize="vertical"
            placeholder="把单词表/词组文本粘到这里(可含音标、词性、中文释义,排版乱也行),点解析自动抽出所有单词与词组" />
          <el-button type="primary" :loading="parseBusy" :disabled="!pasteText.trim()" style="margin-top:8px" @click="runParseText">
            <el-icon style="margin-right:4px"><Cpu /></el-icon>解析文本
          </el-button>
          <span class="muted" style="margin-left:8px">解析结果同样进「待保存」核对后入库</span>
        </div>

        <!-- 待保存(OCR/手动)-->
        <div class="pane-head" style="margin-top:14px">
          <span>② 待保存({{ pendingWords.length }})</span>
          <el-button size="small" link type="primary" @click="addPendingRow"><el-icon><Plus /></el-icon>手动加一行</el-button>
        </div>
        <el-table v-if="pendingWords.length" :data="pendingWords" border size="small" max-height="260">
          <el-table-column label="单词/词组" min-width="160">
            <template #default="{ row }"><el-input v-model="row.word" size="small" placeholder="word / phrase" /></template>
          </el-table-column>
          <el-table-column label="音标" width="150">
            <template #default="{ row }"><el-input v-model="row.phonetic" size="small" /></template>
          </el-table-column>
          <el-table-column label="释义" min-width="200">
            <template #default="{ row }"><el-input v-model="row.meaning" size="small" placeholder="词性+中文" /></template>
          </el-table-column>
          <el-table-column label="类型" width="92">
            <template #default="{ row }">
              <el-select v-model="row.type" size="small">
                <el-option label="单词" value="word" /><el-option label="词组" value="phrase" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column width="44">
            <template #default="{ $index }"><el-button size="small" link type="danger" @click="removePendingRow($index)"><el-icon><Delete /></el-icon></el-button></template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="OCR 识别或「手动加一行」添加待保存的词" :image-size="46" />

        <!-- 已挂在单元 -->
        <div class="pane-head" style="margin-top:14px"><span>③ 已挂在本单元({{ linkedWords.length }})· 词力通词库</span></div>
        <el-table v-if="linkedWords.length" :data="linkedWords" border size="small" max-height="240">
          <el-table-column prop="word" label="单词/词组" min-width="150" />
          <el-table-column prop="phonetic" label="音标" width="150" />
          <el-table-column prop="meaning" label="释义" min-width="200" show-overflow-tooltip />
          <el-table-column label="类型" width="70">
            <template #default="{ row }"><el-tag size="small" :type="row.type === 'phrase' ? 'warning' : 'info'" effect="plain">{{ row.type === 'phrase' ? '词组' : '单词' }}</el-tag></template>
          </el-table-column>
          <el-table-column width="56">
            <template #default="{ row }"><el-button size="small" link type="danger" @click="removeLinkedWord(row)"><el-icon><Delete /></el-icon></el-button></template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="本单元暂无重点单词" :image-size="46" />
      </div>
      <template #footer>
        <el-button @click="wordsDlg = false">关闭</el-button>
        <el-button type="primary" :loading="wordSaving" :disabled="!pendingWords.length" @click="savePendingWords">
          保存待挂词{{ pendingWords.length ? `（${pendingWords.length}）` : '' }}
        </el-button>
      </template>
    </AppDialog>

    <!-- ── 单元短文(听力/阅读/写作)Dialog ── -->
    <AppDialog v-model="passDlg" :title="`单元短文 · ${passTitle}`" width="1120px" top="5vh"
               @closed="revokePdf(); pdfSrc = ''">
      <div class="pass-wrap">
        <!-- 左:单元 PDF 预览(同源 blob,对照原文;按需点击加载,避免开弹框就整份下载拖慢) -->
        <div class="pass-pdf" v-loading="pdfLoading" element-loading-text="加载 PDF…">
          <div class="pane-head">
            <span>单元 PDF</span>
            <el-link v-if="passUnit?.unit_pdf_url" type="primary" :href="passUnit.unit_pdf_url"
              target="_blank" :underline="false" style="font-size:13px">新标签打开 ↗</el-link>
          </div>
          <iframe v-if="passUnit?.unit_pdf_url && pdfSrc" :src="pdfSrc" class="pdf-frame" />
          <div v-else-if="passUnit?.unit_pdf_url" class="pdf-load-hint">
            <el-button type="primary" plain :loading="pdfLoading" @click="loadUnitPdf">
              <el-icon style="margin-right:4px"><Document /></el-icon>加载 PDF 预览
            </el-button>
            <div class="muted" style="margin-top:8px">PDF 较大、按需加载;也可点右上「新标签打开」</div>
          </div>
          <el-empty v-else description="该单元暂无 PDF（请先在批量上传里拆出该单元 PDF）" :image-size="60" />
        </div>

        <!-- 右:结构化解析(语法点+分级句 / 听力考点+句组 / 作文要求+正文)-->
        <div class="pass-list" v-loading="passLoading">
          <div class="pane-head">
            <span>单元解析<span class="muted" v-if="hasStructured">（语法 {{ structured.grammar.length }} · 听力 {{ structured.listening.length }} · 作文 {{ structured.writing ? 1 : 0 }}）</span></span>
            <div style="display:flex;gap:8px;align-items:center">
              <el-button v-if="hasStructured" size="small" type="success" plain
                :loading="passLinking" @click="onLinkKg">
                <el-icon style="margin-right:4px"><Cpu /></el-icon>关联知识图谱
              </el-button>
              <el-button size="small" type="primary" :loading="passGenerating"
                :disabled="!passUnit?.unit_pdf_url && !hasStructured" @click="onRegenerate">
                <el-icon style="margin-right:4px"><Cpu /></el-icon>{{ hasStructured ? '重新生成' : 'LLM 解析单元' }}
              </el-button>
            </div>
          </div>

          <el-empty v-if="!passLoading && !hasStructured" :image-size="60"
            description="该单元暂无解析结果,点右上「LLM 解析单元」从 PDF 原文解析" />
          <template v-else>
            <!-- 语法部分 -->
            <div v-if="structured.grammar.length" class="sec-group">
              <div class="sec-head sec-grammar">语法部分<span class="muted">（{{ structured.grammar.length }} 个语法点）</span></div>
              <div v-for="g in structured.grammar" :key="g.id" class="sec-point">
                <div class="point-name">
                  {{ g.point_name }}
                  <el-tag v-if="g.node_code" size="small" type="success" effect="plain" style="margin-left:6px">
                    已关联 {{ g.node_name || g.node_code }} <span class="muted">{{ g.node_code }}</span>
                  </el-tag>
                  <el-button v-if="g.node_code && !relinkOpen[g.id]" size="small" link type="primary" style="margin-left:2px" @click="onRelink(g)">改挂</el-button>
                  <el-button v-if="g.node_code && !relinkOpen[g.id]" size="small" link type="danger" style="margin-left:2px" @click="onUnlink(g)">取消关联</el-button>
                  <span class="muted" style="margin-left:6px">{{ g.sentences.length }} 句</span>
                </div>
                <div v-if="!g.node_code || relinkOpen[g.id]" class="link-row">
                  <el-select v-model="pickNode[g.id]" filterable clearable :loading="kgLoading" size="small"
                    @visible-change="onKgDropdown"
                    style="width:280px" placeholder="选词法/句法目录节点(可输入名称/编码搜索)">
                    <el-option v-for="o in grammarFlat" :key="o.value" :value="o.value" :label="`${o.name} ${o.code}`">
                      <span :style="{ paddingLeft: o.depth * 12 + 'px' }">{{ o.name }} <span class="muted">{{ o.code }}</span></span>
                    </el-option>
                  </el-select>
                  <el-button size="small" @click="onManualLink('grammar', g)">{{ relinkOpen[g.id] ? '覆盖挂靠' : '挂靠' }}</el-button>
                  <el-button size="small" type="primary" plain @click="onNewNode('grammar', g)">目录没有→新建</el-button>
                  <el-button v-if="relinkOpen[g.id]" size="small" link @click="cancelRelink(g)">取消</el-button>
                </div>
                <div v-for="s in g.sentences" :key="s.id" class="sent-row">
                  <span class="diff-badge" :style="{ background: diffColor(s.difficulty) }">{{ s.difficulty ?? '—' }}</span>
                  <span class="sent-text">{{ s.text }}</span>
                </div>
              </div>
            </div>
            <!-- 听力部分 -->
            <div v-if="structured.listening.length" class="sec-group">
              <div class="sec-head sec-listen">听力部分<span class="muted">（{{ structured.listening.length }} 个听力考点）</span></div>
              <div v-for="g in structured.listening" :key="g.id" class="sec-point">
                <div class="point-name">
                  {{ g.point_name }}
                  <el-tag v-if="g.node_code" size="small" type="success" effect="plain" style="margin-left:6px">
                    已关联 {{ g.node_name || g.node_code }} <span class="muted">{{ g.node_code }}</span>
                  </el-tag>
                  <el-button v-if="g.node_code && !relinkOpen[g.id]" size="small" link type="primary" style="margin-left:2px" @click="onRelink(g)">改挂</el-button>
                  <el-button v-if="g.node_code && !relinkOpen[g.id]" size="small" link type="danger" style="margin-left:2px" @click="onUnlink(g)">取消关联</el-button>
                  <span class="muted" style="margin-left:6px">{{ g.sentences.length }} 句</span>
                </div>
                <div v-if="!g.node_code || relinkOpen[g.id]" class="link-row">
                  <el-select v-model="pickNode[g.id]" filterable clearable :loading="kgLoading" size="small"
                    @visible-change="onKgDropdown"
                    style="width:280px" placeholder="选听力(lt)目录节点(可输入名称/编码搜索)">
                    <el-option v-for="o in listenFlat" :key="o.value" :value="o.value" :label="`${o.name} ${o.code}`">
                      <span :style="{ paddingLeft: o.depth * 12 + 'px' }">{{ o.name }} <span class="muted">{{ o.code }}</span></span>
                    </el-option>
                  </el-select>
                  <el-button size="small" @click="onManualLink('listening', g)">{{ relinkOpen[g.id] ? '覆盖挂靠' : '挂靠' }}</el-button>
                  <el-button size="small" type="primary" plain @click="onNewNode('listening', g)">目录没有→新建</el-button>
                  <el-button v-if="relinkOpen[g.id]" size="small" link @click="cancelRelink(g)">取消</el-button>
                </div>
                <div v-for="s in g.sentences" :key="s.id" class="sent-row">
                  <span class="diff-badge" :style="{ background: diffColor(s.difficulty) }">{{ s.difficulty ?? '—' }}</span>
                  <span class="sent-text">{{ s.text }}</span>
                </div>
              </div>
            </div>
            <!-- 作文部分 -->
            <div v-if="structured.writing" class="sec-group">
              <div class="sec-head sec-write">作文部分</div>
              <div class="sec-point">
                <div v-if="structured.writing.requirement" class="point-name">作文要求</div>
                <pre v-if="structured.writing.requirement" class="pass-text">{{ structured.writing.requirement }}</pre>
                <div class="point-name" style="margin-top:8px">正文(书本原文)</div>
                <pre class="pass-text">{{ structured.writing.body_text }}</pre>
              </div>
            </div>
          </template>
        </div>
      </div>
      <template #footer><el-button @click="passDlg = false">关闭</el-button></template>
    </AppDialog>

    <!-- ── PDF 上传 Dialog ── -->
    <AppDialog
      v-model="pdfDialogVisible"
      title="上传教材 PDF · 拆分单元(挂 PDF)"
      width="680px"
      @close="stopPoll"
      :close-on-click-modal="false"
    >
      <el-steps :active="pdfStep" finish-status="success" style="margin-bottom:28px">
        <el-step title="教材信息" />
        <el-step title="上传文件" />
        <el-step title="单元划分" />
        <el-step title="拆分挂PDF" />
      </el-steps>

      <!-- Step 0：教材信息 -->
      <div v-if="pdfStep === 0">
        <el-form label-width="90px">
          <el-form-item label="教材版本">
            <el-select v-model="pdfTextbook" style="width:200px">
              <el-option v-for="v in VERSIONS" :key="v" :label="v" :value="v" />
            </el-select>
          </el-form-item>
          <el-form-item label="年级">
            <el-select v-model="pdfGrade" style="width:200px">
              <el-option v-for="g in GRADES" :key="g" :label="g" :value="g" />
            </el-select>
          </el-form-item>
          <el-form-item label="学期">
            <el-select v-model="pdfSemester" style="width:200px">
              <el-option v-for="s in SEMS" :key="s" :label="s+'学期'" :value="s" />
            </el-select>
          </el-form-item>
        </el-form>
        <div style="text-align:right;margin-top:16px">
          <el-button type="primary" @click="pdfStep = 1">下一步</el-button>
        </div>
      </div>

      <!-- Step 1：上传文件 -->
      <div v-if="pdfStep === 1">
        <div class="meta-tag">{{ pdfTextbook }} · {{ pdfGrade }} · {{ pdfSemester }}学期</div>
        <el-upload
          drag
          :auto-upload="false"
          :limit="1"
          accept=".pdf"
          :on-change="onFileChange"
          :show-file-list="true"
          style="margin-bottom:16px"
        >
          <el-icon style="font-size:40px;color:#c0c4cc"><UploadFilled /></el-icon>
          <div style="margin-top:8px;font-size:14px;color:#606266">将 PDF 拖到此处，或<em style="color:#409eff">点击选择</em></div>
          <div style="font-size:12px;color:#909399;margin-top:4px">仅支持 .pdf 格式，上限 300MB</div>
        </el-upload>
        <el-alert v-if="pdfUploadErr" :title="pdfUploadErr" type="error" style="margin-bottom:12px" :closable="false" />
        <div style="text-align:right;display:flex;justify-content:space-between">
          <el-button @click="pdfStep = 0">上一步</el-button>
          <el-button type="primary" :loading="pdfUploading" :disabled="!pdfFile" @click="doUpload">
            上传并识别单元
          </el-button>
        </div>
      </div>

      <!-- Step 2：单元划分 -->
      <div v-if="pdfStep === 2">
        <div class="meta-tag">{{ pdfTextbook }} · {{ pdfGrade }} · {{ pdfSemester }}学期 · 共 {{ pdfTotalPages }} 页</div>

        <!-- 扫描件:无文字层,走 OCR -->
        <template v-if="pdfScanned">
          <el-alert type="warning" :closable="false" show-icon style="margin-bottom:12px"
            title="这是扫描件 PDF(无文字层)"
            description="无法直接抽取文字。可用 OCR 逐页识别(豆包视觉),约每页 1-2 秒、整本几分钟;完成后照常识别单元、生成内容。" />
          <div v-if="!ocrRunning" style="margin-bottom:12px">
            <el-button type="primary" @click="startOcr"><el-icon style="margin-right:4px"><Search /></el-icon>开始 OCR 识别({{ pdfTotalPages }} 页)</el-button>
            <span class="muted" style="margin-left:10px">或返回上一步改用文字版 PDF</span>
          </div>
          <div v-else style="margin-bottom:12px">
            <el-progress :percentage="ocrTotal ? Math.round(ocrDone / ocrTotal * 100) : 0" :stroke-width="14" />
            <div class="muted" style="margin-top:6px">OCR 识别中… {{ ocrDone }}/{{ ocrTotal }} 页(请勿关闭弹窗)</div>
          </div>
        </template>

        <template v-else>
        <el-alert
          v-if="pdfAutoSuccess"
          :title="`自动识别到 ${segments.length} 个单元，可直接生成。也可手动调整下方分界。`"
          type="success" :closable="false" style="margin-bottom:12px"
        />
        <el-alert
          v-else
          title="未能自动识别单元分界，请手动填写各单元起止页码。"
          type="warning" :closable="false" style="margin-bottom:12px"
        />
        <div v-if="pdfPageOffset > 0" class="offset-tip">
          下方为 PDF 页序;本书 PDF 比印刷页码多 {{ pdfPageOffset }} 页 → 印刷页码 = PDF 页序 − {{ pdfPageOffset }}(各页已标「印刷 P」)
        </div>

        <!-- 分段列表 -->
        <el-table :data="segments" border size="small" style="margin-bottom:12px">
          <el-table-column label="单元" width="80" align="center">
            <template #default="{ row }">Unit {{ row.unit_no }}</template>
          </el-table-column>
          <el-table-column label="起始页(PDF)" width="120" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.start_page" :min="1" :max="pdfTotalPages" size="small" controls-position="right" />
              <div v-if="pdfPageOffset > 0" class="printed-hint">{{ printedPage(row.start_page) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="结束页(PDF)" width="120" align="center">
            <template #default="{ row }">
              <el-input-number v-model="row.end_page" :min="row.start_page" :max="pdfTotalPages" size="small" controls-position="right" />
              <div v-if="pdfPageOffset > 0" class="printed-hint">{{ printedPage(row.end_page) }}</div>
            </template>
          </el-table-column>
          <el-table-column label="识别标题" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">
              <span style="color:#909399;font-size:12px">{{ row.detected_title || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="" width="60" align="center">
            <template #default="{ $index }">
              <el-button link type="danger" size="small" @click="removeSegment($index)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-button link type="primary" @click="addSegment" style="margin-bottom:12px">+ 添加单元</el-button>

        <el-alert v-if="segErr" :title="segErr" type="error" :closable="false" style="margin-bottom:12px" />
        </template>

        <div style="display:flex;justify-content:space-between">
          <el-button :disabled="ocrRunning" @click="pdfStep = 1">上一步</el-button>
          <el-button type="primary" :disabled="!segments.length || ocrRunning" @click="startPdfGenerate">
            开始拆分（{{ segments.length }} 个单元）
          </el-button>
        </div>
      </div>

      <!-- Step 3：生成中 / 结果 -->
      <div v-if="pdfStep === 3">
        <div v-if="pdfGenerating" class="gen-loading">
          <div style="font-size:15px;font-weight:600">拆分单元 PDF 中…</div>
          <div style="font-size:13px;color:#909399;margin-top:6px">
            已完成 {{ pdfJob?.done ?? 0 }} / {{ pdfJob?.total ?? segments.length }} 个单元<span v-if="pdfJob?.failed">（失败 {{ pdfJob.failed }}）</span>
            ——可关闭窗口,后台继续,重开本弹窗会自动恢复进度
          </div>
          <el-progress
            :percentage="pdfJob && pdfJob.total ? Math.round((pdfJob.done + pdfJob.failed) / pdfJob.total * 100) : 0"
            style="width:320px;margin-top:16px" />
          <div style="text-align:right;margin-top:16px;width:100%">
            <el-button @click="pdfDialogVisible = false">关闭(后台继续)</el-button>
          </div>
        </div>

        <div v-else-if="pdfJob">
          <div class="result-summary">
            <el-tag type="success" size="large"><el-icon style="vertical-align:-2px;margin-right:4px"><CircleCheck /></el-icon>成功 {{ pdfJob.done }} 个单元</el-tag>
            <el-tag v-if="pdfJob.failed" type="danger" size="large" style="margin-left:8px">
              <el-icon style="vertical-align:-2px;margin-right:4px"><CircleClose /></el-icon>失败 {{ pdfJob.failed }} 个单元
            </el-tag>
          </div>
          <el-table :data="pdfJob.results" border size="small" style="margin-top:16px">
            <el-table-column label="状态" width="60" align="center">
              <template #default="{ row }">
                <el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small">
                  <el-icon><CircleCheck v-if="row.status === 'ok'" /><CircleClose v-else /></el-icon>
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="单元" width="70" align="center">
              <template #default="{ row }">Unit {{ row.unit_no }}</template>
            </el-table-column>
            <el-table-column prop="unit_title" label="标题" min-width="140" show-overflow-tooltip />
            <el-table-column label="PDF" width="90" align="center">
              <template #default="{ row }">
                <span v-if="row.status === 'ok'" :style="{ color: row.pdf ? '#67C23A' : '#E6A23C' }">
                  {{ row.pdf ? '已挂' : '无 PDF' }}
                </span>
                <span v-else style="color:#F56C6C;font-size:12px">{{ row.error }}</span>
              </template>
            </el-table-column>
          </el-table>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-top:16px">
            <el-button v-if="pdfJob.failed" type="warning" @click="retryFailedUnits">
              <el-icon style="margin-right:4px"><Refresh /></el-icon>重试失败的 {{ pdfJob.failed }} 个单元
            </el-button>
            <span v-else></span>
            <el-button @click="pdfDialogVisible = false">关闭</el-button>
          </div>
        </div>
      </div>
    </AppDialog>
  </div>
</template>

<style scoped>
.toolbar {
  display: flex; gap: 12px; align-items: center;
  flex-wrap: wrap; margin-bottom: 16px;
}
.stat-txt { color: #909399; font-size: 13px; }
.meta-tag {
  display: inline-block; background: #f0f9ff; color: #0369a1;
  font-size: 13px; padding: 4px 10px; border-radius: 4px; margin-bottom: 16px;
}
.gen-loading {
  display: flex; flex-direction: column; align-items: center;
  padding: 40px 0; gap: 8px;
}
.spinning { font-size: 36px; animation: spin 1s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
.result-summary { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; }
.offset-tip { color: #b45309; background: #fffbeb; font-size: 12px;
  padding: 6px 10px; border-radius: 4px; margin-bottom: 10px; }
.printed-hint { color: #2563eb; font-size: 11px; margin-top: 2px; }
/* 单元短文弹窗:左 PDF / 右短文,等高对照 */
.pass-wrap { display: flex; gap: 16px; height: 76vh; }
.pass-pdf { flex: 1; min-width: 0; display: flex; flex-direction: column;
  border: 1px solid #ebeef5; border-radius: 8px; overflow: hidden; }
.sec-group { margin-bottom: 16px; }
.sec-head { font-weight: 700; font-size: 15px; color: #303133; padding: 6px 0 6px 10px;
  border-left: 4px solid #409eff; margin-bottom: 8px; }
.sec-head .muted { font-weight: 400; }
.sec-grammar { border-left-color: #409eff; }
.sec-listen { border-left-color: #67c23a; }
.sec-write { border-left-color: #e6a23c; }
.sec-point { margin: 0 0 12px 6px; padding: 8px 10px; background: #fafcff;
  border: 1px solid #eef2f8; border-radius: 6px; }
.point-name { font-weight: 600; font-size: 13px; color: #303133; margin-bottom: 6px; }
.link-row { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; flex-wrap: wrap; }
.sent-row { display: flex; align-items: flex-start; gap: 8px; padding: 3px 0; }
.diff-badge { flex-shrink: 0; min-width: 26px; text-align: center; color: #fff;
  font-size: 11px; line-height: 18px; border-radius: 9px; padding: 0 6px; margin-top: 1px; }
.sent-text { font-size: 13px; line-height: 1.6; color: #303133; word-break: break-word; }
.pass-list { flex: 1; min-width: 0; display: flex; flex-direction: column;
  border: 1px solid #ebeef5; border-radius: 8px; padding: 0 12px 12px; overflow: auto; }
.pane-head { position: sticky; top: 0; z-index: 1; background: #fff;
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600; font-size: 14px; color: #303133;
  padding: 10px 0; border-bottom: 1px solid #f0f2f5; margin-bottom: 10px; }
.pass-pdf .pane-head { padding: 10px 12px; margin-bottom: 0; }
.pane-head .muted { color: #909399; font-weight: 400; font-size: 12px; }
.pdf-frame { flex: 1; width: 100%; border: 0; }
.pdf-load-hint { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; }
.pass-group { margin-bottom: 14px; }
.pass-kind { font-weight: 600; font-size: 14px; color: #303133; margin-bottom: 6px;
  border-left: 3px solid #409eff; padding-left: 8px; }
.pass-kind .muted { color: #909399; font-weight: 400; font-size: 12px; }
.pass-item { margin-bottom: 8px; }
.pass-title { font-size: 13px; color: #606266; font-weight: 600; margin-bottom: 2px; }
.pass-text { white-space: pre-wrap; word-break: break-word; font-size: 13px; line-height: 1.6;
  color: #303133; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px;
  padding: 8px 10px; margin: 0; max-height: 280px; overflow: auto; }
.pass-kp { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; margin-top: 5px; }
.kp-label { font-size: 12px; color: #909399; }
.act-row { display: flex; align-items: center; flex-wrap: wrap; gap: 4px; }
.unit-sug { display: flex; align-items: center; flex-wrap: wrap; gap: 2px; margin-bottom: 10px;
  padding: 6px 8px; background: #f4f8ff; border-radius: 6px; }
.words-ocr { padding: 10px 12px; background: #f7f9fc; border: 1px solid #ebeef5; border-radius: 8px; }
.ocr-imgs { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0 10px; }
.ocr-thumb { position: relative; width: 72px; height: 72px; border-radius: 6px; overflow: hidden;
  border: 1px solid #dcdfe6; }
.ocr-thumb img { width: 100%; height: 100%; object-fit: cover; }
.ocr-thumb .rm { position: absolute; top: 2px; right: 2px; color: #f56c6c; background: #fff;
  border-radius: 50%; cursor: pointer; font-size: 16px; }
.ocr-add { width: 72px; height: 72px; border: 1px dashed #c0c4cc; border-radius: 6px;
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  color: #909399; font-size: 12px; cursor: pointer; gap: 2px; }
.ocr-add:hover { border-color: var(--c-primary, #3d8bf5); color: var(--c-primary, #3d8bf5); }
</style>

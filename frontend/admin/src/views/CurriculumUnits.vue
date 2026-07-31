<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Document, Notebook, Search, Cpu, CircleCheck, CircleClose, Delete, Plus, Collection, EditPen } from '@element-plus/icons-vue'
import {
  listCurriculumUnits, deleteCurriculumUnits, updateCurriculumUnit,
  uploadCurriculumPdf, generateFromPdf, getGenJob, listGenJobs,
  startPdfOcr, getPdfOcrStatus, retryGenJob,
  fetchUnitPdfBlob, getUnitStructured, generateUnitStructured, linkUnitStructured,
  linkUnitStructuredBySource, clearUnitGrammar, getUnitCourseText, saveUnitCourseText,
  linkSectionNode, unlinkSectionNode, newNodeForSection, getNodeTree, getUnitLinkedNodes,
  getUnitWords, saveUnitWords, deleteUnitWord, ocrUnitWords, parseUnitWordsText,
  listUnitUnderstandLs, generateUnitUnderstandLs, updateUnitUnderstandLs, deleteUnitUnderstandLs,
  type UnitLinkedNode, type UnitUnderstandLsItem,
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


// ── 单元基础信息编辑 ──────────────────────────────────────────────────────────
const editDlg = ref(false)
const editSaving = ref(false)
const editRow = ref<AdminCurriculumUnit | null>(null)
const editForm = ref({ textbook_version: '', grade: '', semester: '上', unit_no: 1, unit_title: '' })

function openEdit(row: AdminCurriculumUnit) {
  editRow.value = row
  editForm.value = {
    textbook_version: row.textbook_version,
    grade: row.grade,
    semester: row.semester,
    unit_no: row.unit_no,
    unit_title: row.unit_title || '',
  }
  editDlg.value = true
}

async function saveEdit() {
  const row = editRow.value
  if (!row) return
  const f = editForm.value
  if (!f.textbook_version.trim() || !f.grade.trim() || !f.semester) {
    ElMessage.warning('教材版本 / 年级 / 学期不能为空'); return
  }
  if (!f.unit_no || f.unit_no < 1) { ElMessage.warning('Unit 号需为正整数'); return }
  // 只提交有变化的字段
  const patch: Record<string, any> = {}
  if (f.textbook_version.trim() !== row.textbook_version) patch.textbook_version = f.textbook_version.trim()
  if (f.grade.trim() !== row.grade) patch.grade = f.grade.trim()
  if (f.semester !== row.semester) patch.semester = f.semester
  if (f.unit_no !== row.unit_no) patch.unit_no = f.unit_no
  if ((f.unit_title || '').trim() !== (row.unit_title || '')) patch.unit_title = (f.unit_title || '').trim()
  if (!Object.keys(patch).length) { editDlg.value = false; return }   // 无改动
  editSaving.value = true
  try {
    const updated = await updateCurriculumUnit(row.unit_id, patch)
    // 原地更新该行(避免整表重载丢失滚动/选择)
    Object.assign(row, {
      textbook_version: updated.textbook_version, grade: updated.grade,
      semester: updated.semester, unit_no: updated.unit_no, unit_title: updated.unit_title,
    })
    editDlg.value = false
    ElMessage.success('已保存')
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  } finally {
    editSaving.value = false
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

// 已挂词批量移除(多选;逐条删,词力通词条保留)
const linkedTableRef = ref<{ clearSelection: () => void } | null>(null)
const linkedSel = ref<UnitWordItem[]>([])
const linkedRemoving = ref(false)
function onLinkedSelChange(rows: UnitWordItem[]) { linkedSel.value = rows }

async function batchRemoveLinked() {
  const ws = linkedSel.value.filter(w => w.word_id)
  if (!ws.length || !wordsUnit.value) return
  try {
    await ElMessageBox.confirm(
      `从本单元批量移除选中的 ${ws.length} 个词?(词力通词条本身保留,仅解除与本单元的关联)`,
      '批量移除', { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' })
  } catch { return }
  linkedRemoving.value = true
  const uid = wordsUnit.value.unit_id
  const failed = new Set<string>()
  await runPool(ws, async (w) => {
    try { await deleteUnitWord(uid, w.word_id as string) }
    catch { failed.add(w.word_id as string) }
  }, 4)
  linkedWords.value = linkedWords.value.filter(x => !(x.word_id && ws.some(w => w.word_id === x.word_id) && !failed.has(x.word_id)))
  wordsUnit.value.word_count = linkedWords.value.length
  linkedTableRef.value?.clearSelection()
  linkedSel.value = []
  linkedRemoving.value = false
  const ok = ws.length - failed.size
  if (failed.size) ElMessage.warning(`已移除 ${ok} 个,${failed.size} 个失败`)
  else ElMessage.success(`已移除 ${ok} 个`)
}

// ── 单元长难句·理解向(S1: 原文抽尽 / 无则合成;不挂图谱)──
const lsDlg = ref(false)
const lsUnit = ref<AdminCurriculumUnit | null>(null)
const lsTitle = ref('')
const lsLoading = ref(false)
const lsGenerating = ref(false)
const lsItems = ref<UnitUnderstandLsItem[]>([])
const lsMeta = ref({ extract_count: 0, synth_count: 0, grade: '', cached: false })
const lsEditId = ref<string | null>(null)
const lsEditForm = ref({ text: '', translation: '', why: '' })
const lsSavingEdit = ref(false)

const lsExtractCount = computed(() => lsItems.value.filter(x => x.src === 'extract').length)
const lsSynthCount = computed(() => lsItems.value.filter(x => x.src === 'synth').length)

async function loadUnderstandLs(unitId: string) {
  const r = await listUnitUnderstandLs(unitId)
  lsItems.value = r.items || []
  lsMeta.value = {
    extract_count: r.extract_count || 0,
    synth_count: r.synth_count || 0,
    grade: r.grade || lsUnit.value?.grade || '',
    cached: !!r.cached,
  }
}

async function onViewLs(row: AdminCurriculumUnit) {
  lsUnit.value = row
  lsTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  lsDlg.value = true
  lsLoading.value = true
  lsItems.value = []
  lsEditId.value = null
  try { await loadUnderstandLs(row.unit_id) }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { lsLoading.value = false }
}

/** 从图1「粘贴原文」或图2「重新跑」触发:须已保存原文 */
async function runUnderstandLs(opts?: { force?: boolean; openDlg?: boolean }) {
  /** 短文弹框打开时优先当前粘贴单元,否则用长难句弹框单元 */
  const unit = (passDlg.value && passUnit.value) ? passUnit.value : (lsUnit.value || passUnit.value)
  if (!unit) return
  if (passDlg.value && passUnit.value?.unit_id === unit.unit_id
    && (!courseTextSaved.value || !courseText.value.trim() || courseTextDirty.value)) {
    ElMessage.warning('请先在「粘贴原文」保存课文')
    passLeftTab.value = 'text'
    return
  }
  if (opts?.openDlg !== false) {
    lsUnit.value = unit
    lsTitle.value = `${unit.textbook_version} ${unit.grade} ${unit.semester} U${unit.unit_no}`
    lsDlg.value = true
  }
  lsGenerating.value = true
  try {
    const r = await generateUnitUnderstandLs(unit.unit_id, !!opts?.force)
    lsItems.value = r.items || []
    lsMeta.value = {
      extract_count: r.extract_count || 0,
      synth_count: r.synth_count || 0,
      grade: r.grade || unit.grade || '',
      cached: !!r.cached,
    }
    const tip = r.cached
      ? `命中缓存 · 共 ${r.total} 句`
      : (r.synth_count && !r.extract_count
        ? `原文未检出 · 已合成 ${r.synth_count} 句`
        : `已从原文找出 ${r.extract_count} 句长难句`)
    ElMessage.success(tip)
  } catch (e: any) { ElMessage.error(e?.message || '找出/合成失败') }
  finally { lsGenerating.value = false }
}

function startEditLs(it: UnitUnderstandLsItem) {
  lsEditId.value = it.id
  lsEditForm.value = {
    text: it.text || '',
    translation: it.translation || '',
    why: it.why || '',
  }
}
function cancelEditLs() { lsEditId.value = null }
async function saveEditLs(it: UnitUnderstandLsItem) {
  if (!lsUnit.value) return
  lsSavingEdit.value = true
  try {
    const r = await updateUnitUnderstandLs(lsUnit.value.unit_id, it.id, { ...lsEditForm.value })
    Object.assign(it, r)
    lsEditId.value = null
    ElMessage.success('已保存')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { lsSavingEdit.value = false }
}
async function removeUnderstandLs(it: UnitUnderstandLsItem) {
  if (!lsUnit.value) return
  try {
    await ElMessageBox.confirm(`删除该长难句？\n${it.text.slice(0, 80)}`, '删除', { type: 'warning' })
  } catch { return }
  try {
    await deleteUnitUnderstandLs(lsUnit.value.unit_id, it.id)
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
const passLeftTab = ref<'pdf' | 'text'>('pdf')
const courseText = ref('')
const courseTextSaved = ref(false)
const courseTextDirty = ref(false)
const courseSaving = ref(false)
const linkSource = ref<'pdf' | 'paste' | 'merge'>('pdf')
const passLinking = ref(false)
const linkSteps = ref<string[]>([])

const LINK_SOURCE_TIPS: Record<string, string> = {
  pdf: '无结构化结果 → 先从 PDF 文本层抽取语法/听力/作文，再挂图谱；已有结果则直接挂未挂点。',
  paste: '须已「保存原文」。按粘贴文本抽取（md5 暂存）→ 合并进单元解析 → 挂未挂点。未保存会提示先保存。',
  merge: '两边都抽（或缺哪边补哪边），按考点名去重合并后再挂。适合 PDF 缺页、粘贴补全。',
}
const LINK_SOURCE_BRIEF: Record<string, string> = {
  pdf: 'PDF 抽（若需）→ 挂未挂点',
  paste: '校验已保存 → 粘贴抽 → 合并 → 挂',
  merge: '补齐 PDF+粘贴 → 去重合并 → 挂',
}
const unlinkedCount = computed(() =>
  structured.value.grammar.filter(g => !g.node_code).length
  + structured.value.listening.filter(g => !g.node_code).length)
const linkedCount = computed(() =>
  structured.value.grammar.filter(g => !!g.node_code).length
  + structured.value.listening.filter(g => !!g.node_code).length)
/** 语法细目总数(方案 D 双层展示) */
const grammarFacetTotal = computed(() =>
  structured.value.grammar.reduce((n, g) => n + (g.facets?.length || 0), 0))
function extractSourceLabel(src?: string | null) {
  if (src === 'paste') return '粘贴'
  if (src === 'pdf') return 'PDF'
  return ''
}

async function onViewPassages(row: AdminCurriculumUnit) {
  passTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  passUnit.value = row
  pdfSrc.value = ''
  passLeftTab.value = 'pdf'
  linkSource.value = 'pdf'
  courseText.value = ''
  courseTextSaved.value = false
  courseTextDirty.value = false
  linkSteps.value = []
  passDlg.value = true
  passLoading.value = true
  structured.value = { grammar: [], listening: [], writing: null }
  pickNode.value = {}
  try {
    const [st, ct] = await Promise.all([
      getUnitStructured(row.unit_id),
      getUnitCourseText(row.unit_id).catch(() => ({ course_text: '', saved: false })),
    ])
    structured.value = st
    courseText.value = ct.course_text || ''
    courseTextSaved.value = !!ct.saved
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { passLoading.value = false }
}

async function saveCourseText() {
  if (!passUnit.value) return
  courseSaving.value = true
  try {
    const r = await saveUnitCourseText(passUnit.value.unit_id, courseText.value)
    courseText.value = r.course_text || ''
    courseTextSaved.value = r.saved
    courseTextDirty.value = false
    ElMessage.success(r.saved ? '原文已保存' : '已清空保存的原文')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { courseSaving.value = false }
}
function clearCourseText() {
  courseText.value = ''
  courseTextDirty.value = true
}

/** 按来源选项:缺结构则抽,再关联知识图谱(方案 A) */
async function onLinkKg() {
  if (!passUnit.value) return
  if (linkSource.value === 'paste' || linkSource.value === 'merge') {
    if (!courseTextSaved.value || !courseText.value.trim()) {
      ElMessage.warning('请先在「粘贴原文」保存课文后再用该来源关联')
      passLeftTab.value = 'text'
      return
    }
  }
  if (linkSource.value === 'pdf' && !passUnit.value.unit_pdf_url && !hasStructured.value) {
    ElMessage.warning('该单元暂无 PDF,请改用「粘贴原文」或先拆出单元 PDF')
    return
  }
  passLinking.value = true
  linkSteps.value = []
  try {
    const r = await linkUnitStructuredBySource(passUnit.value.unit_id, linkSource.value)
    structured.value = r
    linkSteps.value = r.steps || []
    const c = r.link_counts
    if (c) ElMessage.success(
      `关联完成 · 新挂 ${c.linked ?? 0}`
      + (c.unmatched ? ` · 未命中 ${c.unmatched}` : '')
      + (c.candidate ? ` · 候选 ${c.candidate}` : ''))
    else ElMessage.success('关联流程已完成')
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
async function onManualLink(_kind: string, sec: { id: string; node_code: string | null; node_name?: string | null }) {
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
async function onNewNode(_kind: string, sec: { id: string; point_name: string | null; node_code: string | null; node_name?: string | null }) {
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

const clearingGrammar = ref(false)
/** 清除本单元全部语法点(含句子)及其图谱关联;听力/作文保留 */
async function onClearGrammar() {
  if (!passUnit.value) return
  try {
    await ElMessageBox.confirm(
      '清除本单元全部语法解析点？已挂图谱关联会一并解除(可再重新抽取/关联)。',
      '清除全部语法', { type: 'warning' })
  } catch { return }
  clearingGrammar.value = true
  try {
    const r = await clearUnitGrammar(passUnit.value.unit_id)
    const d = r.clear_counts?.deleted ?? 0
    structured.value = await getUnitStructured(passUnit.value.unit_id)
    ElMessage.success(`已清除 ${d} 个语法点`)
  } catch (e: any) {
    ElMessage.error(e?.message || '清除失败')
  } finally { clearingGrammar.value = false }
}

// 句子难度色(0–100)
function diffColor(d: number | null): string {
  if (d == null) return '#c0c4cc'
  if (d >= 60) return '#F56C6C'
  if (d >= 35) return '#E6A23C'
  return '#67C23A'
}

/** 易/中/难档位标签色 */
function tierTagType(tier?: number | null): 'success' | 'warning' | 'danger' | 'info' {
  if (tier === 1) return 'success'
  if (tier === 3) return 'danger'
  if (tier === 2) return 'warning'
  return 'info'
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
    if (running.items.length) {
      pdfStep.value = 3
      pdfGenerating.value = true
      pollJob(running.items[0].job_id)
      return
    }
    const failed = await listGenJobs({ status: 'failed', limit: 1 })
    if (failed.items.length) {
      pdfStep.value = 3
      pdfGenerating.value = false
      pdfJob.value = await getGenJob(failed.items[0].job_id)
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
    <!-- 工具栏:左=筛选/统计,右=操作(批量操作随勾选出现) -->
    <div class="toolbar">
      <div class="tb-left">
        <el-select v-model="filterTextbook" placeholder="教材版本" clearable style="width:150px" @change="reload">
          <el-option v-for="t in textbookOptions" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="filterGrade" placeholder="年级" clearable style="width:130px" @change="reload">
          <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
        </el-select>
        <el-select v-model="filterSemester" placeholder="学期" clearable style="width:110px" @change="reload">
          <el-option v-for="s in semesterOptions" :key="s" :label="s+'学期'" :value="s" />
        </el-select>
        <el-button @click="load" :loading="loading" :icon="Refresh" circle title="刷新" />
        <span class="stat-txt">
          共 <b>{{ total }}</b> 单元 · 本页 <b>{{ rows.filter(r => r.kp_count > 0).length }}</b>/{{ rows.length }} 已挂考点
        </span>
      </div>
      <div class="tb-right">
        <transition name="fade">
          <div v-if="selected.length" class="tb-batch">
            <span class="sel-badge">已选 {{ selected.length }}</span>
            <el-button type="success" plain size="default" :loading="batchParsing" @click="batchParseSelected">
              <el-icon style="margin-right:4px"><Cpu /></el-icon>{{ batchParsing ? `解析中 ${batchProg.done}/${batchProg.total}` : '批量解析' }}
            </el-button>
            <el-button type="danger" plain size="default" :loading="deleting" @click="deleteUnits(selected)">
              <el-icon style="margin-right:4px"><Delete /></el-icon>删除
            </el-button>
            <el-divider direction="vertical" />
          </div>
        </transition>
        <el-button @click="goUploadLs"><el-icon style="margin-right:4px"><Document /></el-icon>上传长难句</el-button>
        <el-button type="primary" @click="openPdfDialog"><el-icon style="margin-right:4px"><UploadFilled /></el-icon>上传教材 PDF</el-button>
      </div>
    </div>

    <!-- 单元表格:合并「教材/年级/学期/Unit」为单元身份列;考点/单词为可点标签 -->
    <el-table ref="tableRef" v-loading="loading" :data="rows" border style="width:100%"
              row-key="unit_id" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="44" />
      <el-table-column label="单元" min-width="280">
        <template #default="{ row }">
          <div class="unit-cell">
            <div class="unit-title">
              <span class="u-no">U{{ row.unit_no }}</span>
              <span :class="{ 'u-empty': !row.unit_title }">{{ row.unit_title || '未命名单元' }}</span>
            </div>
            <div class="unit-meta">{{ row.textbook_version }} · {{ row.grade }} · {{ row.semester }}学期</div>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="单元考点" width="118" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.kp_count" type="success" effect="light" round class="cell-tag" @click="onViewNodes(row)">
            {{ row.kp_count }} 考点
          </el-tag>
          <el-button v-else link type="info" size="small" @click="onViewNodes(row)">未挂靠</el-button>
        </template>
      </el-table-column>
      <el-table-column label="重点单词" width="118" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.word_count" type="primary" effect="light" round class="cell-tag" @click="onViewWords(row)">
            {{ row.word_count }} 词
          </el-tag>
          <el-button v-else link type="primary" size="small" @click="onViewWords(row)">
            <el-icon style="margin-right:3px"><Collection /></el-icon>挂单词
          </el-button>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="270" fixed="right">
        <template #default="{ row }">
          <div class="act-row">
            <el-button size="small" type="primary" @click="onViewPassages(row)"><el-icon style="margin-right:4px"><Document /></el-icon>短文</el-button>
            <el-button size="small" @click="onViewLs(row)">长难句</el-button>
            <el-button size="small" :icon="EditPen" title="编辑基础信息(标题/教材/年级/学期/Unit)" @click="openEdit(row)" />
            <el-button v-if="row.unit_pdf_url" size="small" :icon="Notebook" title="原版 PDF" @click="openUnitPdf(row)" />
            <el-button size="small" type="danger" plain :icon="Delete" title="删除单元" :loading="deleting" @click="deleteUnits([row])" />
          </div>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="total > pageSize" style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <!-- ── 单元基础信息编辑 Dialog ── -->
    <AppDialog v-model="editDlg" title="编辑单元基础信息" width="520px">
      <el-form label-width="88px" @submit.prevent>
        <el-form-item label="单元标题">
          <el-input v-model="editForm.unit_title" placeholder="如 This is me!(留空显示为「未命名单元」)" clearable maxlength="120" show-word-limit />
        </el-form-item>
        <el-form-item label="教材版本">
          <el-select v-model="editForm.textbook_version" filterable allow-create default-first-option style="width:100%" placeholder="选择或输入教材版本">
            <el-option v-for="t in textbookOptions" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="editForm.grade" filterable allow-create default-first-option style="width:100%" placeholder="选择或输入年级">
            <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="学期">
          <el-select v-model="editForm.semester" style="width:100%">
            <el-option label="上学期" value="上" />
            <el-option label="下学期" value="下" />
          </el-select>
        </el-form-item>
        <el-form-item label="Unit 号">
          <el-input-number v-model="editForm.unit_no" :min="1" :max="99" />
        </el-form-item>
        <div class="hint">改「教材 / 年级 / 学期 / Unit 号」= 改单元身份;与已有单元重复会被拒绝。不影响该单元已挂的短文 / 考点 / 单词。</div>
      </el-form>
      <template #footer>
        <el-button @click="editDlg = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
      </template>
    </AppDialog>

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

    <!-- ── 单元长难句·理解向(接收/呈现;不挂图谱)Dialog ── -->
    <AppDialog v-model="lsDlg" :title="`单元长难句 · ${lsTitle}`" width="860px" top="6vh">
      <div v-loading="lsLoading || lsGenerating" :element-loading-text="lsGenerating ? '正在找出/合成…' : '加载中…'">
        <div class="uls-head">
          <div>
            <div class="uls-title">本单元长难句 · 理解练习用</div>
            <div class="muted" style="font-size:12px;margin-top:2px">
              贴本单元语法 · 易→难梯度 · 练「看懂结构」· 不关联知识图谱
            </div>
          </div>
          <el-button size="small" :loading="lsGenerating" @click="runUnderstandLs({ force: true, openDlg: false })">
            <el-icon style="margin-right:4px"><Refresh /></el-icon>重新跑
          </el-button>
        </div>
        <div class="uls-stats">
          <span class="uls-chip">共 {{ lsItems.length }} 句</span>
          <span class="uls-chip ex">原文抽取 {{ lsExtractCount }}</span>
          <span class="uls-chip syn">AI 合成 {{ lsSynthCount }}</span>
          <span class="uls-chip" v-if="lsMeta.grade || lsUnit?.grade">年级锚点：{{ lsMeta.grade || lsUnit?.grade }}</span>
          <span class="uls-chip" v-if="lsMeta.cached">缓存命中</span>
        </div>

        <div v-for="(it, idx) in lsItems" :key="it.id" class="uls-card">
          <div class="uls-meta">
            <span class="uls-no">{{ idx + 1 }}</span>
            <el-tag size="small" :type="it.src === 'synth' ? 'warning' : 'primary'" effect="plain">
              {{ it.src === 'synth' ? 'AI 合成' : '原文抽取' }}
            </el-tag>
            <el-tag v-if="it.tier_label || it.tier" size="small" :type="tierTagType(it.tier)" effect="dark">
              {{ it.tier_label || ({ 1: '易', 2: '中', 3: '难' }[it.tier!] || '中') }}
            </el-tag>
            <el-tag v-if="it.grammar_point" size="small" type="info" effect="plain">
              {{ it.grammar_point }}
            </el-tag>
            <el-tag v-if="it.difficulty != null" size="small"
              :style="{ background: diffColor(it.difficulty), color: '#fff', border: 'none' }">
              {{ it.difficulty }}
            </el-tag>
            <el-button size="small" link type="danger" style="margin-left:auto" @click="removeUnderstandLs(it)">
              <el-icon><Delete /></el-icon>
            </el-button>
          </div>
          <template v-if="lsEditId === it.id">
            <el-input v-model="lsEditForm.text" type="textarea" :rows="2" style="margin-bottom:6px" />
            <el-input v-model="lsEditForm.translation" placeholder="中文译文" style="margin-bottom:6px" />
            <el-input v-model="lsEditForm.why" placeholder="为何算长难句" style="margin-bottom:6px" />
            <div style="display:flex;gap:8px">
              <el-button size="small" type="primary" :loading="lsSavingEdit" @click="saveEditLs(it)">保存</el-button>
              <el-button size="small" @click="cancelEditLs">取消</el-button>
            </div>
          </template>
          <template v-else>
            <div class="uls-en">{{ it.text }}</div>
            <div class="uls-zh" v-if="it.translation">{{ it.translation }}</div>
            <div class="uls-why" v-if="it.why">为何算长难句：{{ it.why }}</div>
            <div class="uls-acts">
              <el-button size="small" link type="primary" @click="startEditLs(it)">编辑</el-button>
            </div>
          </template>
        </div>
        <el-empty v-if="!lsLoading && !lsGenerating && !lsItems.length"
          description="尚无长难句。请在「单元短文 → 粘贴原文」保存后点「找出/合成长难句」"
          :image-size="50" />
      </div>
      <template #footer>
        <el-button @click="lsDlg = false">关闭</el-button>
      </template>
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
        <div class="pane-head" style="margin-top:14px">
          <span>③ 已挂在本单元({{ linkedWords.length }})· 词力通词库</span>
          <el-button v-if="linkedSel.length" size="small" type="danger" plain :loading="linkedRemoving" @click="batchRemoveLinked">
            <el-icon style="margin-right:3px"><Delete /></el-icon>批量移除（{{ linkedSel.length }}）
          </el-button>
        </div>
        <el-table ref="linkedTableRef" v-if="linkedWords.length" :data="linkedWords" border size="small" max-height="240"
                  row-key="word_id" @selection-change="onLinkedSelChange">
          <el-table-column type="selection" width="40" />
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
        <!-- 左: PDF / 粘贴原文 Tab -->
        <div class="pass-pdf" v-loading="pdfLoading" element-loading-text="加载 PDF…">
          <div class="pane-head">
            <div class="src-tabs">
              <button type="button" class="src-tab" :class="{ on: passLeftTab === 'pdf' }" @click="passLeftTab = 'pdf'">单元 PDF</button>
              <button type="button" class="src-tab" :class="{ on: passLeftTab === 'text' }" @click="passLeftTab = 'text'">粘贴原文</button>
            </div>
            <el-link v-if="passLeftTab === 'pdf' && passUnit?.unit_pdf_url" type="primary" :href="passUnit.unit_pdf_url"
              target="_blank" :underline="false" style="font-size:13px;margin-left:auto">新标签打开 ↗</el-link>
          </div>
          <template v-if="passLeftTab === 'pdf'">
            <iframe v-if="passUnit?.unit_pdf_url && pdfSrc" :src="pdfSrc" class="pdf-frame" />
            <div v-else-if="passUnit?.unit_pdf_url" class="pdf-load-hint">
              <el-button type="primary" plain :loading="pdfLoading" @click="loadUnitPdf">
                <el-icon style="margin-right:4px"><Document /></el-icon>加载 PDF 预览
              </el-button>
              <div class="muted" style="margin-top:8px">PDF 较大、按需加载;也可点右上「新标签打开」</div>
            </div>
            <el-empty v-else description="该单元暂无 PDF（请先在批量上传里拆出该单元 PDF）" :image-size="60" />
          </template>
          <div v-else class="course-text-pane">
            <div class="muted" style="margin-bottom:8px;font-size:12px">粘贴教辅/课文；须先「保存原文」。保存后可「找出/合成长难句」，或选「左侧粘贴原文」跑关联图谱。</div>
            <el-input v-model="courseText" type="textarea" :rows="16" placeholder="粘贴本单元课文 / 教辅原文…"
              @input="courseTextDirty = true" />
            <div style="display:flex;gap:8px;align-items:center;margin-top:10px;flex-wrap:wrap">
              <el-button type="primary" :loading="courseSaving" @click="saveCourseText">保存原文</el-button>
              <el-button @click="clearCourseText">清空</el-button>
              <el-button type="warning" plain :loading="lsGenerating"
                :disabled="!courseTextSaved || !courseText.trim() || courseTextDirty"
                @click="runUnderstandLs({ force: false })">
                <el-icon style="margin-right:4px"><Search /></el-icon>找出/合成长难句
              </el-button>
              <span class="muted" style="font-size:12px">
                {{ courseTextSaved && !courseTextDirty ? '已保存 · 可作关联源' : (courseTextDirty ? '未保存的修改' : '未保存') }}
              </span>
            </div>
          </div>
        </div>

        <!-- 右:结构化解析(语法点+分级句 / 听力考点+句组 / 作文要求+正文)-->
        <div class="pass-list" v-loading="passLoading">
          <div class="pane-head">
            <span>单元解析<span class="muted" v-if="hasStructured">（语法 {{ structured.grammar.length }} · 听力 {{ structured.listening.length }} · 作文 {{ structured.writing ? 1 : 0 }}）</span></span>
            <div style="display:flex;gap:8px;align-items:center;margin-left:auto;flex-wrap:wrap">
              <span class="stat-pill warn" v-if="hasStructured">未挂 {{ unlinkedCount }}</span>
              <span class="stat-pill ok" v-if="hasStructured">已挂 {{ linkedCount }}</span>
              <el-button size="small" type="success" :loading="passLinking" @click="onLinkKg">
                <el-icon style="margin-right:4px"><Cpu /></el-icon>关联知识图谱
              </el-button>
            </div>
          </div>

          <div class="link-source-bar">
            <div class="lsb-title">
              关联内容来源
              <el-tooltip content="点「关联知识图谱」时按所选来源：缺结构则先抽取，再一键挂未挂点。悬停各选项旁问号看细则。" placement="top">
                <span class="tip-q">?</span>
              </el-tooltip>
            </div>
            <div class="lsb-opts">
              <label class="lsb-opt" :class="{ on: linkSource === 'pdf' }">
                <input type="radio" v-model="linkSource" value="pdf" />
                单元 PDF
                <el-tooltip :content="LINK_SOURCE_TIPS.pdf" placement="top"><span class="tip-q">?</span></el-tooltip>
              </label>
              <label class="lsb-opt" :class="{ on: linkSource === 'paste' }">
                <input type="radio" v-model="linkSource" value="paste" />
                左侧粘贴原文
                <el-tooltip :content="LINK_SOURCE_TIPS.paste" placement="top"><span class="tip-q">?</span></el-tooltip>
              </label>
              <label class="lsb-opt" :class="{ on: linkSource === 'merge' }">
                <input type="radio" v-model="linkSource" value="merge" />
                PDF + 粘贴合并
                <el-tooltip :content="LINK_SOURCE_TIPS.merge" placement="top"><span class="tip-q">?</span></el-tooltip>
              </label>
            </div>
            <div class="lsb-brief">
              <b>将执行：</b>{{ LINK_SOURCE_BRIEF[linkSource] }}
              <el-tooltip :content="LINK_SOURCE_TIPS[linkSource]" placement="top"><span class="tip-q">?</span></el-tooltip>
            </div>
          </div>
          <div v-if="linkSteps.length" class="link-steps muted">
            <div v-for="(s, i) in linkSteps" :key="i">{{ i + 1 }}. {{ s }}</div>
          </div>

          <el-empty v-if="!passLoading && !hasStructured" :image-size="60"
            description="暂无解析结果。选好来源后点「关联知识图谱」即可抽取并挂靠" />
          <template v-else>
            <!-- 语法部分 -->
            <div v-if="structured.grammar.length" class="sec-group">
              <div class="sec-head sec-grammar">
                <span>语法部分<span class="muted">（{{ structured.grammar.length }} 个挂靠点<span v-if="grammarFacetTotal"> · {{ grammarFacetTotal }} 细目</span>）</span></span>
                <el-button size="small" type="danger" plain :icon="Delete" :loading="clearingGrammar" @click="onClearGrammar">清除全部语法</el-button>
              </div>
              <div v-for="g in structured.grammar" :key="g.id" class="sec-point">
                <div class="point-name">
                  {{ g.point_name }}
                  <el-tag v-if="extractSourceLabel(g.extract_source)" size="small" effect="plain" style="margin-left:6px">{{ extractSourceLabel(g.extract_source) }}</el-tag>
                  <el-tag v-if="g.node_code" size="small" type="success" effect="plain" style="margin-left:6px">
                    已关联 {{ g.node_name || g.node_code }} <span class="muted">{{ g.node_code }}</span>
                  </el-tag>
                  <el-tag v-if="g.facets?.length" size="small" effect="plain" type="info" style="margin-left:6px">{{ g.facets.length }} 细目</el-tag>
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
                <!-- 方案 D:细目折叠展示;无细目时回退扁平句子(旧数据) -->
                <template v-if="g.facets?.length">
                  <div v-for="(fc, fi) in g.facets" :key="`${g.id}-f-${fi}`" class="facet-block">
                    <div class="facet-h">细目 · {{ fc.name }}<span class="muted">（{{ fc.sentences.length }} 句）</span></div>
                    <div v-for="(s, si) in fc.sentences" :key="s.id || `${g.id}-f-${fi}-${si}`" class="sent-row">
                      <span class="diff-badge" :style="{ background: diffColor(s.difficulty) }">{{ s.difficulty ?? '—' }}</span>
                      <span class="sent-text">{{ s.text }}</span>
                    </div>
                  </div>
                </template>
                <template v-else>
                  <div v-for="s in g.sentences" :key="s.id" class="sent-row">
                    <span class="diff-badge" :style="{ background: diffColor(s.difficulty) }">{{ s.difficulty ?? '—' }}</span>
                    <span class="sent-text">{{ s.text }}</span>
                  </div>
                </template>
              </div>
            </div>
            <!-- 听力部分 -->
            <div v-if="structured.listening.length" class="sec-group">
              <div class="sec-head sec-listen">听力部分<span class="muted">（{{ structured.listening.length }} 个听力考点）</span></div>
              <div v-for="g in structured.listening" :key="g.id" class="sec-point">
                <div class="point-name">
                  {{ g.point_name }}
                  <el-tag v-if="extractSourceLabel(g.extract_source)" size="small" effect="plain" style="margin-left:6px">{{ extractSourceLabel(g.extract_source) }}</el-tag>
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
  display: flex; gap: 12px; align-items: center; justify-content: space-between;
  flex-wrap: wrap; margin-bottom: 16px;
}
.tb-left, .tb-right, .tb-batch { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.tb-right { justify-content: flex-end; }
.stat-txt { color: #909399; font-size: 13px; white-space: nowrap; }
.stat-txt b { color: #303133; font-weight: 600; }
.sel-badge {
  font-size: 13px; color: var(--c-primary, #3d8bf5); font-weight: 600;
  background: #eef5ff; padding: 3px 10px; border-radius: 12px;
}
.fade-enter-active, .fade-leave-active { transition: opacity .18s ease; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

/* 单元身份单元格:标题 + 元信息两行 */
.unit-cell { line-height: 1.4; }
.unit-title { font-size: 14px; color: #303133; font-weight: 500; display: flex; align-items: center; gap: 6px; }
.u-no {
  flex-shrink: 0; font-size: 12px; font-weight: 600; color: var(--c-primary, #3d8bf5);
  background: #eef5ff; border-radius: 4px; padding: 1px 7px; line-height: 18px;
}
.u-empty { color: #c0c4cc; font-weight: 400; font-style: italic; }
.unit-meta { font-size: 12px; color: #909399; margin-top: 3px; }
/* 考点/单词可点标签 */
.cell-tag { cursor: pointer; transition: transform .1s ease; }
.cell-tag:hover { transform: translateY(-1px); }
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

.src-tabs { display: inline-flex; border: 1px solid #e8edf3; border-radius: 8px; overflow: hidden; }
.src-tab { border: 0; background: #fff; padding: 5px 12px; font-size: 12px; cursor: pointer; color: #64748b; border-right: 1px solid #e8edf3; }
.src-tab:last-child { border-right: 0; }
.src-tab.on { background: #e8f2ff; color: #3d8bf5; font-weight: 600; }
.course-text-pane { flex: 1; padding: 12px; overflow: auto; background: #f8fafc; }
.link-source-bar { margin: 0 0 10px; padding: 8px 10px; border: 1px solid #e8edf3; border-radius: 8px; background: #fafcff; }
.lsb-title { font-size: 12px; color: #64748b; font-weight: 600; margin-bottom: 6px; display: flex; align-items: center; gap: 6px; }
.lsb-opts { display: flex; flex-wrap: wrap; gap: 6px; }
.lsb-opt { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; padding: 5px 10px; border: 1px solid #e8edf3; border-radius: 999px; background: #fff; cursor: pointer; user-select: none; }
.lsb-opt.on { border-color: #bfdbfe; background: #e8f2ff; color: #3d8bf5; font-weight: 600; }
.lsb-opt input { margin: 0; accent-color: #3d8bf5; }
.lsb-brief { margin-top: 6px; font-size: 12px; color: #64748b; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.lsb-brief b { color: #475569; }
.tip-q { display: inline-flex; width: 15px; height: 15px; border-radius: 50%; border: 1px solid #94a3b8; color: #64748b; font-size: 10px; font-weight: 700; align-items: center; justify-content: center; cursor: help; background: #fff; line-height: 1; }
.stat-pill { font-size: 12px; padding: 2px 8px; border-radius: 999px; background: #f1f5f9; color: #64748b; }
.stat-pill.warn { background: #fff7e8; color: #9a6700; }
.stat-pill.ok { background: #e9f6f1; color: #1f7a61; }
.link-steps { font-size: 12px; padding: 6px 10px; margin-bottom: 8px; background: #f8fafc; border-radius: 6px; border: 1px solid #eef2f7; }
.pass-wrap { display: flex; gap: 16px; height: 76vh; }
.pass-pdf { flex: 1; min-width: 0; display: flex; flex-direction: column;
  border: 1px solid #ebeef5; border-radius: 8px; overflow: hidden; }
.sec-group { margin-bottom: 16px; }
.sec-head { font-weight: 700; font-size: 15px; color: #303133; padding: 6px 0 6px 10px;
  border-left: 4px solid #409eff; margin-bottom: 8px;
  display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.sec-head .muted { font-weight: 400; }
.sec-grammar { border-left-color: #409eff; }
.sec-listen { border-left-color: #67c23a; }
.sec-write { border-left-color: #e6a23c; }
.sec-point { margin: 0 0 12px 6px; padding: 8px 10px; background: #fafcff;
  border: 1px solid #eef2f8; border-radius: 6px; }
.point-name { font-weight: 600; font-size: 13px; color: #303133; margin-bottom: 6px; }
.link-row { display: flex; align-items: center; gap: 8px; margin: 0 0 8px; flex-wrap: wrap; }
.facet-block {
  margin: 8px 0 0; padding: 8px 10px; border-radius: 6px;
  background: #f8fafc; border: 1px solid #e8edf3;
}
.facet-h { font-size: 12px; font-weight: 600; color: #475569; margin-bottom: 4px; }
.facet-h .muted { font-weight: 400; color: #94a3b8; }
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
.uls-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.uls-title { font-size: 14px; font-weight: 700; color: #1e293b; }
.uls-stats { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 12px; }
.uls-chip { font-size: 11px; padding: 4px 10px; border-radius: 999px; background: #f1f5f9; color: #475569; font-weight: 600; }
.uls-chip.ex { background: #e8f2ff; color: #3d8bf5; }
.uls-chip.syn { background: #fff3d6; color: #9a6700; }
.uls-card { border: 1px solid #e8edf3; border-radius: 10px; padding: 12px; margin-bottom: 8px; background: #fff; }
.uls-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.uls-no { width: 22px; height: 22px; border-radius: 6px; background: #e8f2ff; color: #3d8bf5;
  font-size: 11px; font-weight: 800; display: inline-flex; align-items: center; justify-content: center; }
.uls-en { font-size: 14px; font-weight: 600; color: #1e293b; line-height: 1.45; }
.uls-zh { font-size: 12px; color: #64748b; margin-top: 4px; }
.uls-why { font-size: 11px; color: #64748b; margin-top: 6px; background: #f8fafc; border-radius: 6px; padding: 6px 8px; }
.uls-acts { margin-top: 4px; }
</style>

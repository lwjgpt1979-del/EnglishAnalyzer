<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { UploadFilled, Refresh, Document, Notebook, Search, Cpu, CircleCheck, CircleClose, Delete } from '@element-plus/icons-vue'
import {
  listCurriculumUnits, deleteCurriculumUnits,
  uploadCurriculumPdf, generateFromPdf, getGenJob, listGenJobs,
  startPdfOcr, getPdfOcrStatus, retryGenJob,
  fetchUnitPdfBlob, getUnitStructured, generateUnitStructured, linkUnitStructured,
  linkSectionNode, newNodeForSection, getNodeTree, getUnitPassages,
  type UnitSegment, type GenJob, type UnitStructured,
} from '../api/admin'
import type { AdminCurriculumUnit, NodeTreeItem } from '../types'
import KpPromptEditor from '../components/KpPromptEditor.vue'

// ── 单元列表 ──────────────────────────────────────────────────────────────────
const rows = ref<AdminCurriculumUnit[]>([])
const loading = ref(false)

const filterTextbook = ref('')
const filterGrade    = ref('')
const filterSemester = ref('')

const textbookOptions = computed(() => [...new Set(rows.value.map(r => r.textbook_version))])
const gradeOptions    = computed(() => [...new Set(rows.value.map(r => r.grade))])
const semesterOptions = computed(() => [...new Set(rows.value.map(r => r.semester))])

const filteredRows = computed(() => rows.value.filter(r => {
  if (filterTextbook.value && r.textbook_version !== filterTextbook.value) return false
  if (filterGrade.value    && r.grade            !== filterGrade.value)    return false
  if (filterSemester.value && r.semester         !== filterSemester.value) return false
  return true
}))

async function load() {
  loading.value = true
  try { rows.value = await listCurriculumUnits() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// ── 选择删除 ──────────────────────────────────────────────────────────────────
const tableRef = ref<{ clearSelection: () => void } | null>(null)
const selected = ref<AdminCurriculumUnit[]>([])
const deleting = ref(false)
function onSelectionChange(rows: AdminCurriculumUnit[]) { selected.value = rows }

function unitLabel(r: AdminCurriculumUnit) {
  return `${r.textbook_version} ${r.grade} ${r.semester}学期 U${r.unit_no}`
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

// 本学期考点提示词配置弹窗(预填当前筛选的 教材/年级/学期;无筛选给默认)
const kpDlg = ref(false)
const kpInit = ref({ textbook: '译林版', grade: '七年级', semester: '上' })
function openKpDialog() {
  kpInit.value = {
    textbook: filterTextbook.value || rows.value[0]?.textbook_version || '译林版',
    grade: filterGrade.value || rows.value[0]?.grade || '七年级',
    semester: filterSemester.value || rows.value[0]?.semester || '上',
  }
  kpDlg.value = true
}

const nodesDlg = ref(false)
const nodesLoading = ref(false)
// 单元考点 = 各短文已关联考点的并集(从短文级 unit_passage_kp 汇总;单一来源)
const unitKps = ref<{ node_id: string; name: string; kinds: string[] }[]>([])
const nodesUnitTitle = ref('')
const nodesUnitId = ref('')


async function onViewNodes(row: AdminCurriculumUnit) {
  nodesUnitTitle.value = `${row.textbook_version} ${row.grade} ${row.semester} U${row.unit_no}`
  nodesUnitId.value = row.unit_id
  nodesDlg.value = true
  nodesLoading.value = true
  unitKps.value = []
  try {
    const passages = (await getUnitPassages(row.unit_id)).items
    const map = new Map<string, { node_id: string; name: string; kinds: string[] }>()
    for (const p of passages) {
      for (const k of (p.kps || [])) {
        const e = map.get(k.node_id) || { node_id: k.node_id, name: k.name, kinds: [] }
        if (!e.kinds.includes(p.kind)) e.kinds.push(p.kind)
        map.set(k.node_id, e)
      }
    }
    unitKps.value = [...map.values()]
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    nodesLoading.value = false
  }
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
  ensureKgTree()   // 先并行拉知识图谱树(~700 节点,给足时间,免得点开下拉时还没到→No data)
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
async function ensureKgTree() {
  if (kgTree.value.length) return
  kgLoading.value = true
  try { kgTree.value = (await getNodeTree('knowledge')).items }
  catch (e: any) { ElMessage.error(e?.message || '加载知识图谱失败') }
  finally { kgLoading.value = false }
}
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
    kgTree.value = []   // 树有新节点,清缓存下次重拉
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

// 句子难度色(0–100)
function diffColor(d: number | null): string {
  if (d == null) return '#c0c4cc'
  if (d >= 60) return '#F56C6C'
  if (d >= 35) return '#E6A23C'
  return '#67C23A'
}

function rateColor(rate: number) {
  if (rate >= 1) return '#67C23A'
  if (rate > 0)  return '#E6A23C'
  return '#F56C6C'
}

// ── PDF 上传 Dialog ──────────────────────────────────────────────────────────

const VERSIONS     = ['译林版', '人教版', '外研版', '北师大版']
const GRADES       = ['小学5年级', '小学6年级', '七年级', '八年级', '九年级']
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
      <el-select v-model="filterTextbook" placeholder="教材版本" clearable style="width:140px">
        <el-option v-for="t in textbookOptions" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="filterGrade" placeholder="年级" clearable style="width:140px">
        <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="filterSemester" placeholder="学期" clearable style="width:100px">
        <el-option v-for="s in semesterOptions" :key="s" :label="s+'学期'" :value="s" />
      </el-select>
      <el-button @click="load" :loading="loading"><el-icon style="margin-right:4px"><Refresh /></el-icon>刷新</el-button>
      <span class="stat-txt">
        共 {{ filteredRows.length }} 个单元 ·
        已完成 {{ filteredRows.filter(r => r.content_rate >= 1).length }} 个
      </span>
      <div style="flex:1" />
      <el-button @click="openKpDialog"><el-icon style="margin-right:4px"><Cpu /></el-icon>本学期考点提示词</el-button>
      <el-button
        type="danger" plain
        :disabled="!selected.length" :loading="deleting"
        @click="deleteUnits(selected)"
      ><el-icon style="margin-right:4px"><Delete /></el-icon>删除选中{{ selected.length ? `（${selected.length}）` : '' }}</el-button>
      <el-button type="primary" @click="openPdfDialog"><el-icon style="margin-right:4px"><Document /></el-icon>上传教材 PDF</el-button>
    </div>

    <!-- ── 本学期考点提示词配置 Dialog（按学期定制知识脑图匹配提示词)── -->
    <el-dialog v-model="kpDlg" title="考点提示词配置（按学期定制)" width="1100px" top="4vh"
               :destroy-on-close="true">
      <KpPromptEditor v-if="kpDlg" :init-scope-on="true"
        :init-textbook="kpInit.textbook" :init-grade="kpInit.grade" :init-semester="kpInit.semester" />
      <template #footer><el-button @click="kpDlg = false">关闭</el-button></template>
    </el-dialog>

    <!-- 单元表格 -->
    <el-table ref="tableRef" v-loading="loading" :data="filteredRows" border style="width:100%"
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
      <el-table-column label="短文挂考点" width="210">
        <template #default="{ row }">
          <div v-if="row.passage_count" style="display:flex;align-items:center;gap:8px">
            <el-progress :percentage="Math.round(row.content_rate * 100)" :color="rateColor(row.content_rate)" :stroke-width="8" style="flex:1" />
            <span style="font-size:12px;white-space:nowrap;color:#606266">{{ row.content_count }}/{{ row.passage_count }} 短文</span>
          </div>
          <span v-else style="font-size:12px;color:#c0c4cc">无短文</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="340" fixed="right">
        <template #default="{ row }">
          <div class="act-row">
            <el-button size="small" type="primary" @click="onViewPassages(row)"><el-icon style="margin-right:4px"><Document /></el-icon>短文</el-button>
            <el-button v-if="row.unit_pdf_url" size="small" @click="openUnitPdf(row)"><el-icon style="margin-right:4px"><Notebook /></el-icon>原版PDF</el-button>
            <el-button size="small" @click="onViewNodes(row)">单元考点</el-button>
            <el-button size="small" type="danger" plain :loading="deleting" @click="deleteUnits([row])"><el-icon><Delete /></el-icon></el-button>
          </div>
        </template>
      </el-table-column>
    </el-table>

    <!-- ── 单元知识图谱节点 Dialog ── -->
    <el-dialog v-model="nodesDlg" :title="`单元考点 · ${nodesUnitTitle}`" width="560px">
      <div class="hint" style="margin-bottom:10px">单元考点 = 各短文已关联考点的汇总。要增删请到「短文」里给对应短文关联考点。</div>
      <el-table v-loading="nodesLoading" :data="unitKps" border style="width:100%">
        <el-table-column prop="name" label="考点" min-width="200" show-overflow-tooltip />
        <el-table-column label="来自短文" width="180">
          <template #default="{ row }">{{ row.kinds.join(' / ') }}</template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!nodesLoading && !unitKps.length" description="该单元暂无考点,去「短文」给短文关联考点" :image-size="50" />
      <template #footer>
        <el-button @click="nodesDlg = false">关闭</el-button>
      </template>
    </el-dialog>

    <!-- ── 单元短文(听力/阅读/写作)Dialog ── -->
    <el-dialog v-model="passDlg" :title="`单元短文 · ${passTitle}`" width="1120px" top="5vh"
               @opened="loadUnitPdf" @closed="revokePdf(); pdfSrc = ''">
      <div class="pass-wrap">
        <!-- 左:单元 PDF 预览(同源 blob,对照原文) -->
        <div class="pass-pdf" v-loading="pdfLoading" element-loading-text="加载 PDF…">
          <div class="pane-head">
            <span>单元 PDF</span>
            <el-link v-if="passUnit?.unit_pdf_url" type="primary" :href="passUnit.unit_pdf_url"
              target="_blank" :underline="false" style="font-size:13px">新标签打开 ↗</el-link>
          </div>
          <iframe v-if="passUnit?.unit_pdf_url" :src="pdfSrc" class="pdf-frame" />
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
                  <span class="muted" style="margin-left:6px">{{ g.sentences.length }} 句</span>
                </div>
                <div v-if="!g.node_code || relinkOpen[g.id]" class="link-row">
                  <el-select v-model="pickNode[g.id]" filterable clearable :loading="kgLoading" size="small"
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
                  <span class="muted" style="margin-left:6px">{{ g.sentences.length }} 句</span>
                </div>
                <div v-if="!g.node_code || relinkOpen[g.id]" class="link-row">
                  <el-select v-model="pickNode[g.id]" filterable clearable :loading="kgLoading" size="small"
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
    </el-dialog>

    <!-- ── PDF 上传 Dialog ── -->
    <el-dialog
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
          <div style="font-size:12px;color:#909399;margin-top:4px">仅支持 .pdf 格式，上限 100MB</div>
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
    </el-dialog>
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
</style>

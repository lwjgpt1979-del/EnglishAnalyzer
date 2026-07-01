<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  extractLongSentences, reanalyzeLongSentences, getLsReanalyzeJob, listLongSentences, reviewLongSentence,
  getLSConfig, setLSConfig, getLsTextbookUnits, getLsRealDimensions, backfillParaphrase,
  uploadParseLs, listUploadedLs, linkUploadedLsNode, newUploadedLsNode, deleteUploadedLs,
  getNodeTree,
  type LSTextbookUnit, type LSRealDimensions, type ParaphraseBackfillResult, type UploadedLsItem,
} from '../api/admin'
import type { LSAdminItem, LSConfig, NodeTreeItem } from '../types'
import { Refresh, Loading, Upload, Plus, Delete } from '@element-plus/icons-vue'

// ── 抽取触发 ──
const sourceOptions = [
  { label: '按配置(sources)', value: 'config' },
  { label: '全部(真题+教材)', value: 'all' },
  { label: '① 平台真题', value: 'platform_real' },
  { label: '② 教材单元短文', value: 'textbook' },
]
const extractSource = ref('config')
const extractLimit = ref(200)
const extracting = ref(false)

// 选项数据 + 已选维度
const tbUnits = ref<LSTextbookUnit[]>([])
const realDims = ref<LSRealDimensions>({ textbook_version: [], stage: [], grade: [], semester: [], exam_type: [], region: [] })
const uniq = (a: (string | undefined | null)[]) => [...new Set(a.filter(Boolean) as string[])]
// 教材已选
const tbVer = ref<string[]>([]); const tbGrade = ref<string[]>([]); const tbSem = ref<string[]>([]); const tbUnitIds = ref<string[]>([])
// 真题已选
const rqVer = ref<string[]>([]); const rqStage = ref<string[]>([]); const rqGrade = ref<string[]>([])
const rqSem = ref<string[]>([]); const rqExam = ref<string[]>([]); const rqRegion = ref<string[]>([])

// 教材级联:版本→年级→册→单元(下游随上游收窄)
const tbVerOpts = computed(() => uniq(tbUnits.value.map(u => u.textbook_version)))
const tbGradeOpts = computed(() => uniq(tbUnits.value.filter(u => !tbVer.value.length || tbVer.value.includes(u.textbook_version)).map(u => u.grade)))
const tbSemOpts = computed(() => uniq(tbUnits.value.filter(u => (!tbVer.value.length || tbVer.value.includes(u.textbook_version)) && (!tbGrade.value.length || tbGrade.value.includes(u.grade))).map(u => u.semester)))
const tbUnitOpts = computed(() => tbUnits.value.filter(u =>
  (!tbVer.value.length || tbVer.value.includes(u.textbook_version))
  && (!tbGrade.value.length || tbGrade.value.includes(u.grade))
  && (!tbSem.value.length || tbSem.value.includes(u.semester))))

async function loadExtractOptions() {
  try { tbUnits.value = await getLsTextbookUnits() } catch { /* ignore */ }
  try { realDims.value = await getLsRealDimensions() } catch { /* ignore */ }
}

function buildFilters() {
  if (extractSource.value === 'textbook') {
    return { textbook_version: tbVer.value, grade: tbGrade.value, semester: tbSem.value, unit_ids: tbUnitIds.value }
  }
  if (extractSource.value === 'platform_real') {
    return { textbook_version: rqVer.value, stage: rqStage.value, grade: rqGrade.value, semester: rqSem.value, exam_type: rqExam.value, region: rqRegion.value }
  }
  return undefined
}

async function onExtract() {
  extracting.value = true
  try {
    const r = await extractLongSentences({ source: extractSource.value, limit: extractLimit.value, filters: buildFilters() })
    ElMessage.success(`抽取完成:新建 ${r.created} / 长句 ${r.long_kept} / 挂边 ${r.edges} / `
      + `候选 ${r.candidates} / 跳过 ${r.skipped_done}`)
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '抽取失败') }
  finally { extracting.value = false }
}

// ── 释义回填(带 token 预算熔断)──
const bfLimit = ref(50)
const bfBudget = ref(200000)
const bfOnlyMissing = ref(true)
const bfRunning = ref(false)
const bfResult = ref<ParaphraseBackfillResult | null>(null)
// 给操作人员"钱感":token→元 粗略换算(快档混合单价≈¥3/百万token,仅估算)
const TOK_PRICE_PER_M = 3
const yuan = (tok: number) => (tok / 1_000_000 * TOK_PRICE_PER_M)
const bfBudgetYuan = computed(() => yuan(bfBudget.value))
async function onBackfill() {
  bfRunning.value = true; bfResult.value = null
  try {
    bfResult.value = await backfillParaphrase({
      limit: bfLimit.value, only_missing: bfOnlyMissing.value, max_tokens_budget: bfBudget.value })
    if (bfResult.value.stopped) ElMessage.warning('已达预算上限,回填中途停止')
    else ElMessage.success(`回填完成:补全 ${bfResult.value.filled} 句`)
  } catch (e: any) { ElMessage.error(e?.message || '回填失败') }
  finally { bfRunning.value = false }
}

// ── 重新解析(刷新为新结构:分段/结构/成分/词汇/语法点,供小程序展示)──
const reanalyzing = ref(false)
const reJob = ref<{ done: number; total: number } | null>(null)
async function onReanalyze(publish: boolean) {
  try {
    await ElMessageBox.confirm(
      `重新解析「${status.value}」状态的长难句,刷新为新结构${publish ? ',并发布' : ''}?(后台跑,可继续操作)`,
      '重新解析', { type: 'warning' })
  } catch { return }
  reanalyzing.value = true; reJob.value = { done: 0, total: 0 }
  try {
    const { job_id } = await reanalyzeLongSentences({ status: status.value, limit: 500, publish })
    const poll = async () => {
      try {
        const j = await getLsReanalyzeJob(job_id)
        reJob.value = { done: j.done, total: j.total }
        if (j.status === 'done') {
          ElMessage.success(`重新解析完成:${j.done} 条${j.failed ? `(${j.failed} 失败)` : ''}`)
          reanalyzing.value = false; reJob.value = null; await load(); return
        }
        if (j.status === 'error') { ElMessage.error('重新解析失败:' + (j.error || '')); reanalyzing.value = false; return }
        setTimeout(poll, 2000)
      } catch { reanalyzing.value = false }
    }
    setTimeout(poll, 1500)
  } catch (e: any) { ElMessage.error(e?.message || '启动失败'); reanalyzing.value = false }
}

// ── 审核队列 ──
const status = ref('draft')
const nodeId = ref('')
const rows = ref<LSAdminItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const sortBy = ref('created_at')   // created_at | difficulty
const order = ref('asc')           // asc | desc
const statusOptions = ['draft', 'published', 'retired']
const stLabel = (s: string) => (({ draft: '草稿', published: '已发布', retired: '已下架' } as Record<string, string>)[s] || s)

// 筛选维度
const fSource = ref('')      // platform_real | textbook
const fStage = ref('')       // 小|初|高
const fSemester = ref('')    // 上|下
const fExam = ref('')        // 普通|中考|高考
const fGrade = ref('')       // 年级(文本)
const fTextbook = ref('')    // 教材版(文本)
const srcLabel = (s: string) => (({ platform_real: '真题', textbook: '教材', uploaded: '上传' } as Record<string, string>)[s] || s)

function resetFilters() {
  fSource.value = ''; fStage.value = ''; fSemester.value = ''; fExam.value = ''
  fGrade.value = ''; fTextbook.value = ''; nodeId.value = ''
  reload()
}

async function load() {
  loading.value = true
  try {
    const data = await listLongSentences({
      status: status.value || undefined,
      node_id: nodeId.value.trim() || undefined,
      source_kind: fSource.value || undefined,
      stage: fStage.value || undefined,
      semester: fSemester.value || undefined,
      exam_type: fExam.value || undefined,
      grade: fGrade.value.trim() || undefined,
      textbook_version: fTextbook.value.trim() || undefined,
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
      sort_by: sortBy.value,
      order: order.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
// 筛选/查询变更 → 回到第 1 页再查
function reload() { page.value = 1; load() }

// el-table 列表头排序:难度 升/降;取消则回到按时间升序
function onSortChange({ prop, order: ord }: { prop: string; order: string | null }) {
  if (!ord) { sortBy.value = 'created_at'; order.value = 'asc' }
  else { sortBy.value = prop; order.value = ord === 'ascending' ? 'asc' : 'desc' }
  load()
}

async function onReview(row: LSAdminItem, approve: boolean) {
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '退回下架'}该长难句？`, '确认', { type: 'warning' })
  await reviewLongSentence(row.id, approve)
  ElMessage.success(approve ? '已发布' : '已退回')
  await load()
}

// ── 配置 ──
const cfg = ref<LSConfig>({ sources: [], verify_types: [], min_words: 20, required_pass: 3, textbook_difficulty_min: null, textbook_top_n: 3 })
const allSources = ['platform_real', 'textbook']
const allVerifyTypes = ['cloze', 'struct_type', 'main_clause', 'translate',
  'span_label', 'reorder', 'rewrite', 'read_aloud']
const savingCfg = ref(false)

async function loadCfg() {
  try { cfg.value = await getLSConfig() } catch (e: any) { ElMessage.error(e?.message || '配置加载失败') }
}

async function saveCfg() {
  savingCfg.value = true
  try {
    cfg.value = await setLSConfig({
      sources: cfg.value.sources,
      verify_types: cfg.value.verify_types,
      min_words: cfg.value.min_words,
      required_pass: cfg.value.required_pass,
      textbook_difficulty_min: cfg.value.textbook_difficulty_min,
      textbook_top_n: cfg.value.textbook_top_n,
    })
    ElMessage.success('配置已保存')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { savingCfg.value = false }
}

// ── 上传长难句:文字 → LLM 语法点 → 关联知识图谱 ──
const uploadDlg = ref(false)
const uploadText = ref('')
const parsing = ref(false)
const uploadItems = ref<UploadedLsItem[]>([])

// 知识图谱树(词法 cf / 句法 jf 子树),懒加载 + 扁平可搜索
const kgTree = ref<NodeTreeItem[]>([])
const kgLoading = ref(false)
const pickNode = ref<Record<string, string>>({})      // ls_id → 选中节点
const relinkOpen = ref<Record<string, boolean>>({})
async function ensureKgTree() {
  if (kgTree.value.length || kgLoading.value) return
  kgLoading.value = true
  try { kgTree.value = (await getNodeTree('knowledge')).items }
  catch (e: any) { ElMessage.error(e?.message || '加载知识图谱失败') }
  finally { kgLoading.value = false }
}
function onKgDropdown(v: boolean) { if (v) ensureKgTree() }
interface FlatNode { value: string; name: string; code: string; depth: number }
function flatten(nodes: NodeTreeItem[], depth = 0, out: FlatNode[] = []): FlatNode[] {
  for (const n of nodes || []) {
    out.push({ value: n.id, name: n.name, code: n.code || '', depth })
    if (n.children?.length) flatten(n.children, depth + 1, out)
  }
  return out
}
const grammarFlat = computed(() => flatten(kgTree.value.filter(n => ['cf', 'jf'].some(p => (n.code || '').startsWith(p)))))

function openUploadDlg() {
  uploadDlg.value = true
  uploadText.value = ''
  uploadItems.value = []
  pickNode.value = {}
  relinkOpen.value = {}
  listUploadedLs().then(r => { uploadItems.value = r.items }).catch(() => {})
}
async function runParse() {
  if (!uploadText.value.trim()) { ElMessage.warning('请输入文字'); return }
  parsing.value = true
  try {
    const r = await uploadParseLs(uploadText.value)
    uploadItems.value = [...r.items, ...uploadItems.value]
    if (!r.items.length) ElMessage.info('未解析出语法点(可能文字过短或 dev 模式)')
    else { ElMessage.success(`解析出 ${r.items.length} 个语法点`); uploadText.value = '' }
  } catch (e: any) { ElMessage.error(e?.message || '解析失败') }
  finally { parsing.value = false }
}
async function onLsLink(it: UploadedLsItem) {
  const nid = pickNode.value[it.id]
  if (!nid) { ElMessage.warning('请先选一个节点'); return }
  try {
    const r = await linkUploadedLsNode(it.id, nid)
    it.node_code = r.node_code; it.node_name = r.name; it.node_id = r.node_id
    pickNode.value[it.id] = ''; relinkOpen.value[it.id] = false
    ElMessage.success(`已挂靠到「${r.name}」(${r.node_code})`)
  } catch (e: any) { ElMessage.error(e?.message || '挂靠失败') }
}
async function onLsNewNode(it: UploadedLsItem) {
  const parent = pickNode.value[it.id]
  if (!parent) { ElMessage.warning('请先选一个父分类(在其下新建)'); return }
  try {
    const { value } = await ElMessageBox.prompt('在所选父分类下新建知识图谱节点,节点名:', '新建节点',
      { inputValue: it.point || '', confirmButtonText: '新建并挂靠', cancelButtonText: '取消' })
    const r = await newUploadedLsNode(it.id, parent, (value || '').trim())
    it.node_code = r.node_code; it.node_name = r.name; it.node_id = r.node_id
    pickNode.value[it.id] = ''; relinkOpen.value[it.id] = false
    kgTree.value = []   // 新节点 → 下次重拉
    ElMessage.success(`已新建并挂靠「${r.name}」(${r.node_code})`)
  } catch { /* 取消 */ }
}
function onLsRelink(it: UploadedLsItem) { pickNode.value[it.id] = it.node_id || ''; relinkOpen.value[it.id] = true }
function cancelLsRelink(it: UploadedLsItem) { relinkOpen.value[it.id] = false; pickNode.value[it.id] = '' }
async function onLsDelete(it: UploadedLsItem) {
  try { await ElMessageBox.confirm(`删除这条长难句「${it.text.slice(0, 30)}…」?`, '删除', { type: 'warning' }) }
  catch { return }
  try {
    await deleteUploadedLs(it.id)
    uploadItems.value = uploadItems.value.filter(x => x.id !== it.id)
    ElMessage.success('已删除')
  } catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}
function lsDiffColor(d: number | null): string {
  if (d == null) return '#c0c4cc'
  if (d >= 60) return '#F56C6C'
  if (d >= 35) return '#E6A23C'
  return '#67C23A'
}

const route = useRoute()
onMounted(() => {
  load(); loadCfg(); loadExtractOptions()
  if (route.query.upload) openUploadDlg()   // 从课程页「上传长难句」跳转过来自动开弹框
})
</script>

<template>
  <div>
    <div style="display:flex;justify-content:flex-end;margin-bottom:10px">
      <el-button type="primary" @click="openUploadDlg"><el-icon style="margin-right:4px"><Upload /></el-icon>上传长难句</el-button>
    </div>

    <!-- 抽取触发 -->
    <el-card shadow="never" class="sec">
      <template #header><b>抽取触发</b>(平台库,幂等;来源:平台真题 / 教材单元短文。学生上传的长难句在上传作业时自动抽取、存独立表)</template>
      <div class="toolbar" style="flex-wrap:wrap; gap:8px 0;">
        <span>来源：</span>
        <el-select v-model="extractSource" style="width: 160px">
          <el-option v-for="s in sourceOptions" :key="s.value" :label="s.label" :value="s.value" />
        </el-select>
        <span style="margin-left: 16px">limit：</span>
        <el-input-number v-model="extractLimit" :min="1" :max="2000" style="width: 120px" />
        <el-button style="margin-left: 12px" type="primary" :loading="extracting" @click="onExtract">开始抽取</el-button>
      </div>
      <!-- 教材:级联多选 版本/年级/册/单元 -->
      <div v-if="extractSource === 'textbook'" class="toolbar" style="flex-wrap:wrap; gap:8px 12px; margin-top:8px">
        <span>版本：</span>
        <el-select v-model="tbVer" multiple collapse-tags clearable placeholder="全部" style="width:180px">
          <el-option v-for="v in tbVerOpts" :key="v" :label="v" :value="v" />
        </el-select>
        <span>年级：</span>
        <el-select v-model="tbGrade" multiple collapse-tags clearable placeholder="全部" style="width:160px">
          <el-option v-for="g in tbGradeOpts" :key="g" :label="g" :value="g" />
        </el-select>
        <span>册：</span>
        <el-select v-model="tbSem" multiple collapse-tags clearable placeholder="全部" style="width:120px">
          <el-option v-for="s in tbSemOpts" :key="s" :label="s" :value="s" />
        </el-select>
        <span>单元：</span>
        <el-select v-model="tbUnitIds" multiple collapse-tags clearable filterable placeholder="不选=该范围全部" style="width:280px">
          <el-option v-for="u in tbUnitOpts" :key="u.unit_id" :label="`${u.grade}·${u.semester}·U${u.unit_no} ${u.unit_title}`" :value="u.unit_id" />
        </el-select>
      </div>
      <!-- 真题:多选 版本/学段/年级/册/考试类型/地区 -->
      <div v-if="extractSource === 'platform_real'" class="toolbar" style="flex-wrap:wrap; gap:8px 12px; margin-top:8px">
        <span>版本：</span>
        <el-select v-model="rqVer" multiple collapse-tags clearable placeholder="全部" style="width:160px">
          <el-option v-for="v in realDims.textbook_version" :key="v" :label="v" :value="v" />
        </el-select>
        <span>学段：</span>
        <el-select v-model="rqStage" multiple collapse-tags clearable placeholder="全部" style="width:110px">
          <el-option v-for="s in realDims.stage" :key="s" :label="s" :value="s" />
        </el-select>
        <span>年级：</span>
        <el-select v-model="rqGrade" multiple collapse-tags clearable placeholder="全部" style="width:150px">
          <el-option v-for="g in realDims.grade" :key="g" :label="g" :value="g" />
        </el-select>
        <span>册：</span>
        <el-select v-model="rqSem" multiple collapse-tags clearable placeholder="全部" style="width:110px">
          <el-option v-for="s in realDims.semester" :key="s" :label="s" :value="s" />
        </el-select>
        <span>考试类型：</span>
        <el-select v-model="rqExam" multiple collapse-tags clearable placeholder="全部" style="width:140px">
          <el-option v-for="e in realDims.exam_type" :key="e" :label="e" :value="e" />
        </el-select>
        <span>地区：</span>
        <el-select v-model="rqRegion" multiple collapse-tags clearable filterable placeholder="全部" style="width:180px">
          <el-option v-for="r in realDims.region" :key="r.code" :label="r.name" :value="r.code" />
        </el-select>
      </div>
    </el-card>

    <!-- 释义回填(给存量句补理解检测的释义探针;带 token 预算熔断) -->
    <el-card shadow="never" class="sec">
      <template #header><b>释义回填</b>(给存量长难句补「理解检测·释义题」)</template>

      <!-- 说明:让操作人员看懂"预算熔断是什么/为什么/规则/在哪看" -->
      <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px" title="什么是「预算熔断」?为什么需要?">
        <div class="bf-help">
          · <b>做什么</b>:给还没有「释义题」的长难句补上;每补 1 句要调一次 AI(按 token 计费=花钱)。<br/>
          · <b>为什么要熔断</b>:几百句一起补可能花不少钱,设个上限,防手滑/异常一次把账户余额烧光。<br/>
          · <b>规则</b>:本次累计消耗的 token 一旦达到「Token 预算」,<b>立即停止</b>,已补全的<b>保留</b>;想继续把预算调高再点一次即可。<br/>
          · <b>在哪看</b>:就在下方结果条——顺利绿色、<b style="color:#e6a23c">触发熔断橙色</b>,都会显示扫描/补全句数与已花 token(¥)。
        </div>
      </el-alert>

      <div class="toolbar" style="flex-wrap:wrap; gap:8px 12px;">
        <span class="hint">本次最多补</span>
        <el-input-number v-model="bfLimit" :min="1" :max="2000" style="width:120px" />
        <span class="hint">句</span>
        <span class="hint" style="margin-left:8px">花费上限(Token 预算)</span>
        <el-input-number v-model="bfBudget" :min="1000" :max="5000000" :step="50000" style="width:160px" />
        <el-tag type="info" effect="plain">≈ ¥{{ bfBudgetYuan.toFixed(2) }}(粗略)</el-tag>
        <el-checkbox v-model="bfOnlyMissing" style="margin-left:8px">只补缺失的</el-checkbox>
        <el-button type="primary" :loading="bfRunning" style="margin-left:12px" @click="onBackfill">开始回填</el-button>
      </div>
      <div v-if="bfResult" style="margin-top:10px">
        <el-alert v-if="bfResult.stopped" type="warning" :closable="false" show-icon
          :title="`已达花费上限,已自动停止 —— 扫描 ${bfResult.scanned} 句 / 补全 ${bfResult.filled} 句 / 已花 ${bfResult.spent_tokens} tokens(≈¥${yuan(bfResult.spent_tokens).toFixed(3)})`"
          description="这是预算熔断:为防超支已停下,已补全的句子已保存。想继续:把「花费上限」调高后再点「开始回填」。" />
        <el-alert v-else type="success" :closable="false" show-icon
          :title="`回填完成 —— 扫描 ${bfResult.scanned} 句 / 补全 ${bfResult.filled} 句 / 已花 ${bfResult.spent_tokens} tokens(≈¥${yuan(bfResult.spent_tokens).toFixed(3)});未触发预算熔断`" />
      </div>
    </el-card>

    <!-- 审核队列 -->
    <el-card shadow="never" class="sec">
      <template #header><b>审核队列</b></template>
      <div class="toolbar" style="flex-wrap:wrap; gap:8px 0;">
        <span>状态：</span>
        <el-select v-model="status" style="width: 110px" @change="reload">
          <el-option v-for="s in statusOptions" :key="s" :label="stLabel(s)" :value="s" />
        </el-select>
        <span style="margin-left:16px">来源：</span>
        <el-select v-model="fSource" clearable placeholder="全部" style="width:120px" @change="reload">
          <el-option label="平台真题" value="platform_real" />
          <el-option label="教材" value="textbook" />
        </el-select>
        <span style="margin-left:16px">学段：</span>
        <el-select v-model="fStage" clearable placeholder="全部" style="width:90px" @change="reload">
          <el-option label="小" value="小" /><el-option label="初" value="初" /><el-option label="高" value="高" />
        </el-select>
        <span style="margin-left:16px">学期：</span>
        <el-select v-model="fSemester" clearable placeholder="全部" style="width:90px" @change="reload">
          <el-option label="上" value="上" /><el-option label="下" value="下" />
        </el-select>
        <span style="margin-left:16px">考试类型：</span>
        <el-select v-model="fExam" clearable placeholder="全部" style="width:100px" @change="reload">
          <el-option label="普通" value="普通" /><el-option label="中考" value="中考" /><el-option label="高考" value="高考" />
        </el-select>
        <span style="margin-left:16px">年级：</span>
        <el-input v-model="fGrade" clearable placeholder="如 七年级" style="width:120px" @keyup.enter="reload" />
        <span style="margin-left:16px">教材版：</span>
        <el-input v-model="fTextbook" clearable placeholder="如 译林版" style="width:120px" @keyup.enter="reload" />
        <span style="margin-left:16px">句法 node：</span>
        <el-input v-model="nodeId" clearable placeholder="可选,node id" style="width:180px" @keyup.enter="reload" />
        <el-button style="margin-left:12px" type="primary" @click="reload">查询</el-button>
        <el-button @click="resetFilters">重置</el-button>
        <span class="hint">共 {{ total }} 条</span>
        <div style="flex:1" />
        <el-button :loading="reanalyzing" @click="onReanalyze(false)"><el-icon style="vertical-align:-2px;margin-right:4px"><Refresh /></el-icon>重新解析(刷新结构)</el-button>
        <el-button type="success" :loading="reanalyzing" @click="onReanalyze(true)">重解析并发布</el-button>
        <span v-if="reJob" class="hint"><el-icon style="vertical-align:-2px;margin-right:4px"><Loading /></el-icon>{{ reJob.done }}/{{ reJob.total || '…' }}</span>
      </div>
      <el-table v-loading="loading" :data="rows" border style="width: 100%" @sort-change="onSortChange">
        <el-table-column prop="text" label="句子" min-width="280" show-overflow-tooltip />
        <el-table-column label="来源" width="80">
          <template #default="{ row }">{{ srcLabel(row.source_kind) }}</template>
        </el-table-column>
        <el-table-column label="定位" min-width="180">
          <template #default="{ row }">
            <template v-if="row.source_kind === 'textbook'">
              <span>{{ [row.textbook_version, row.grade, row.semester].filter(Boolean).join(' · ') || '—' }}</span>
            </template>
            <template v-else>
              <el-tag v-if="row.exam_type && row.exam_type !== '普通'" size="small" type="danger" effect="plain" style="margin-right:4px">{{ row.exam_type }}</el-tag>
              <span>{{ (row.exam_type && row.exam_type !== '普通' ? [row.stage] : [row.grade, row.semester]).filter(Boolean).join(' · ') || '—' }}</span>
            </template>
          </template>
        </el-table-column>
        <el-table-column label="句法点" min-width="150">
          <template #default="{ row }">
            <el-tag v-for="p in row.syntax_points" :key="p" size="small" style="margin-right:4px">{{ p }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="difficulty" label="难度" width="110" sortable="custom"
                         :sort-orders="['descending', 'ascending']">
          <template #default="{ row }">
            <el-tag v-if="row.difficulty != null" size="small"
                    :type="row.difficulty >= 80 ? 'danger' : row.difficulty >= 60 ? 'warning' : 'success'"
                    effect="light">{{ row.difficulty }}</el-tag>
            <span v-else style="color:#bbb">—</span>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="90" />
        <el-table-column label="操作" width="170" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.status !== 'published'" size="small" type="success"
                       @click="onReview(row, true)">发布</el-button>
            <el-button v-if="row.status !== 'retired'" size="small" type="danger"
                       @click="onReview(row, false)">退回</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div style="display:flex;justify-content:flex-end;margin-top:12px">
        <el-pagination layout="total, prev, pager, next, jumper" :total="total"
          :page-size="pageSize" v-model:current-page="page" @current-change="load" />
      </div>
    </el-card>

    <!-- 配置 -->
    <el-card shadow="never" class="sec">
      <template #header><b>配置</b>(long_sentence.*)</template>
      <el-form label-width="120px" style="max-width: 720px">
        <el-form-item label="抽取来源 sources">
          <el-checkbox-group v-model="cfg.sources">
            <el-checkbox v-for="s in allSources" :key="s" :label="s" :value="s">{{ s }}</el-checkbox>
          </el-checkbox-group>
        </el-form-item>
        <el-form-item label="验证题型 verify_types">
          <el-checkbox-group v-model="cfg.verify_types">
            <el-checkbox v-for="t in allVerifyTypes" :key="t" :label="t" :value="t">{{ t }}</el-checkbox>
          </el-checkbox-group>
          <span class="hint">reorder 暂未实现,即使开放学生端也不返回</span>
        </el-form-item>
        <el-form-item label="长句最小词数">
          <el-input-number v-model="cfg.min_words" :min="5" :max="60" />
        </el-form-item>
        <el-form-item label="判掌握净做对数">
          <el-input-number v-model="cfg.required_pass" :min="1" :max="10" />
        </el-form-item>
        <el-form-item label="教材难度阈值">
          <el-input-number v-model="cfg.textbook_difficulty_min" :min="0" :max="100" :step="5" clearable controls-position="right" style="width:160px" placeholder="留空=不按阈值" />
          <span class="hint">教材阅读:难度 > 此值的句子全抽;留空(或0)则改用下方「最难 N 句」</span>
        </el-form-item>
        <el-form-item label="教材每篇最难 N 句">
          <el-input-number v-model="cfg.textbook_top_n" :min="1" :max="20" />
          <span class="hint">仅在未设阈值时生效:每篇阅读取难度最高的 N 句</span>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="savingCfg" @click="saveCfg">保存配置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 上传长难句:文字 → LLM 语法点 → 关联知识图谱 -->
    <el-dialog v-model="uploadDlg" title="上传长难句" width="920px" top="6vh">
      <div class="ul-input">
        <el-input v-model="uploadText" type="textarea" :rows="4" resize="vertical"
          placeholder="粘贴一段英文(长难句/课文片段),点「LLM 解析语法点」抽出语法点,再逐点关联知识图谱" />
        <el-button type="primary" :loading="parsing" :disabled="!uploadText.trim()" style="margin-top:8px" @click="runParse">
          <el-icon style="margin-right:4px"><Loading v-if="parsing" /></el-icon>LLM 解析语法点
        </el-button>
        <span class="muted" style="margin-left:8px">解析出的语法点进下方列表,挂靠到知识图谱(词法/句法)</span>
      </div>

      <el-empty v-if="!uploadItems.length" description="还没有语法点;粘贴文字后点「LLM 解析语法点」" :image-size="50" />
      <div v-for="it in uploadItems" :key="it.id" class="ul-row">
        <div class="ul-head">
          <span class="diff-badge" :style="{ background: lsDiffColor(it.difficulty) }">{{ it.difficulty ?? '—' }}</span>
          <b class="ul-point">{{ it.point }}</b>
          <el-tag v-if="it.node_code" size="small" type="success" effect="plain" style="margin-left:6px">
            已关联 {{ it.node_name || it.node_code }} <span class="muted">{{ it.node_code }}</span>
          </el-tag>
          <el-button v-if="it.node_code && !relinkOpen[it.id]" size="small" link type="primary" @click="onLsRelink(it)">改挂</el-button>
          <el-button size="small" link type="danger" style="margin-left:auto" @click="onLsDelete(it)"><el-icon><Delete /></el-icon></el-button>
        </div>
        <div class="ul-sent">{{ it.text }}</div>
        <div v-if="!it.node_code || relinkOpen[it.id]" class="ul-link">
          <el-select v-model="pickNode[it.id]" filterable clearable :loading="kgLoading" size="small"
            style="width:300px" placeholder="选词法/句法目录节点(可输入名称/编码搜索)" @visible-change="onKgDropdown">
            <el-option v-for="o in grammarFlat" :key="o.value" :value="o.value" :label="`${o.name} ${o.code}`">
              <span :style="{ paddingLeft: o.depth * 12 + 'px' }">{{ o.name }} <span class="muted">{{ o.code }}</span></span>
            </el-option>
          </el-select>
          <el-button size="small" @click="onLsLink(it)">{{ relinkOpen[it.id] ? '覆盖挂靠' : '挂靠' }}</el-button>
          <el-button size="small" type="primary" plain @click="onLsNewNode(it)"><el-icon style="margin-right:2px"><Plus /></el-icon>目录没有→新建</el-button>
          <el-button v-if="relinkOpen[it.id]" size="small" link @click="cancelLsRelink(it)">取消</el-button>
        </div>
      </div>
      <template #footer><el-button @click="uploadDlg = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.sec { margin-bottom: 16px; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
.bf-help { font-size: 12px; line-height: 1.9; color: #5c6066; }
.muted { color: #909399; font-size: 12px; }
.ul-input { margin-bottom: 12px; }
.ul-row { border: 1px solid #ebeef5; border-radius: 8px; padding: 10px 12px; margin-bottom: 10px; background: #fafbfc; }
.ul-head { display: flex; align-items: center; gap: 6px; }
.ul-point { font-size: 14px; color: #303133; }
.ul-sent { margin: 6px 0 8px; font-size: 13px; color: #303133; line-height: 1.6; }
.ul-link { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.diff-badge { display: inline-flex; align-items: center; justify-content: center; min-width: 26px; height: 20px;
  padding: 0 6px; border-radius: 10px; color: #fff; font-size: 12px; font-weight: 600; }
</style>

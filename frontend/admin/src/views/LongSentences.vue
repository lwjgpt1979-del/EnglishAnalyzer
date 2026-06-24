<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  extractLongSentences, reanalyzeLongSentences, getLsReanalyzeJob, listLongSentences, reviewLongSentence,
  getLSConfig, setLSConfig, getLsTextbookUnits, getLsRealDimensions, backfillParaphrase,
  type LSTextbookUnit, type LSRealDimensions, type ParaphraseBackfillResult,
} from '../api/admin'
import type { LSAdminItem, LSConfig } from '../types'
import { Refresh, Loading } from '@element-plus/icons-vue'

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
  load()
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
      limit: 50,
      sort_by: sortBy.value,
      order: order.value,
    })
    rows.value = data.items
    total.value = data.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

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

onMounted(() => { load(); loadCfg(); loadExtractOptions() })
</script>

<template>
  <div>
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
      <template #header><b>释义回填</b>(给存量长难句补「理解检测·释义题」;LLM 生成,带 token 预算熔断防成本失控)</template>
      <div class="toolbar" style="flex-wrap:wrap; gap:8px 12px;">
        <span class="hint">本次上限</span>
        <el-input-number v-model="bfLimit" :min="1" :max="2000" style="width:120px" />
        <span class="hint">条</span>
        <span class="hint" style="margin-left:8px">Token 预算</span>
        <el-input-number v-model="bfBudget" :min="1000" :max="5000000" :step="50000" style="width:160px" />
        <el-checkbox v-model="bfOnlyMissing" style="margin-left:8px">只补缺失的</el-checkbox>
        <el-button type="primary" :loading="bfRunning" style="margin-left:12px" @click="onBackfill">开始回填</el-button>
      </div>
      <div v-if="bfResult" style="margin-top:10px">
        <el-alert v-if="bfResult.stopped" type="warning" :closable="false" show-icon
          :title="`已达预算上限,已停止 —— 扫描 ${bfResult.scanned} 句 / 补全 ${bfResult.filled} 句 / 已花 ${bfResult.spent_tokens} tokens`"
          description="可调高「Token 预算」后再次点击继续回填。" />
        <el-alert v-else type="success" :closable="false" show-icon
          :title="`回填完成 —— 扫描 ${bfResult.scanned} 句 / 补全 ${bfResult.filled} 句 / 已花 ${bfResult.spent_tokens} tokens(未触发预算熔断)`" />
      </div>
    </el-card>

    <!-- 审核队列 -->
    <el-card shadow="never" class="sec">
      <template #header><b>审核队列</b></template>
      <div class="toolbar" style="flex-wrap:wrap; gap:8px 0;">
        <span>状态：</span>
        <el-select v-model="status" style="width: 110px" @change="load">
          <el-option v-for="s in statusOptions" :key="s" :label="stLabel(s)" :value="s" />
        </el-select>
        <span style="margin-left:16px">来源：</span>
        <el-select v-model="fSource" clearable placeholder="全部" style="width:120px" @change="load">
          <el-option label="平台真题" value="platform_real" />
          <el-option label="教材" value="textbook" />
        </el-select>
        <span style="margin-left:16px">学段：</span>
        <el-select v-model="fStage" clearable placeholder="全部" style="width:90px" @change="load">
          <el-option label="小" value="小" /><el-option label="初" value="初" /><el-option label="高" value="高" />
        </el-select>
        <span style="margin-left:16px">学期：</span>
        <el-select v-model="fSemester" clearable placeholder="全部" style="width:90px" @change="load">
          <el-option label="上" value="上" /><el-option label="下" value="下" />
        </el-select>
        <span style="margin-left:16px">考试类型：</span>
        <el-select v-model="fExam" clearable placeholder="全部" style="width:100px" @change="load">
          <el-option label="普通" value="普通" /><el-option label="中考" value="中考" /><el-option label="高考" value="高考" />
        </el-select>
        <span style="margin-left:16px">年级：</span>
        <el-input v-model="fGrade" clearable placeholder="如 七年级" style="width:120px" @keyup.enter="load" />
        <span style="margin-left:16px">教材版：</span>
        <el-input v-model="fTextbook" clearable placeholder="如 译林版" style="width:120px" @keyup.enter="load" />
        <span style="margin-left:16px">句法 node：</span>
        <el-input v-model="nodeId" clearable placeholder="可选,node id" style="width:180px" @keyup.enter="load" />
        <el-button style="margin-left:12px" type="primary" @click="load">查询</el-button>
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
  </div>
</template>

<style scoped>
.sec { margin-bottom: 16px; }
.toolbar { display: flex; align-items: center; flex-wrap: wrap; }
.hint { margin-left: 16px; color: #909399; font-size: 12px; }
</style>

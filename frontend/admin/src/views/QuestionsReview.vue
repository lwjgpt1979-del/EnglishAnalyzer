<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listSimPapers, listPlatformQuestions, reviewPlatformQuestion, reviewPlatformBulk, type PlatformQuestion, type SimPaper } from '../api/admin'
import { Document } from '@element-plus/icons-vue'

const status = ref('draft')
const statusOptions = ['draft', 'published', 'retired']
const STATUS_LABEL: Record<string, string> = { draft: '草稿', published: '已发布', retired: '已下架' }
const stLabel = (s: string) => STATUS_LABEL[s] || s

// 一级:按来源真题卷列
const papers = ref<SimPaper[]>([])
const papersTotal = ref(0)
const papersPage = ref(1)
const papersPageSize = 20
const loadingPapers = ref(false)

// 二级:某卷整卷仿真,渲染成「试卷形式」
const curPaper = ref<SimPaper | null>(null)
const allRows = ref<PlatformQuestion[]>([])
const loadingRows = ref(false)
const curVersion = ref<number | 'all'>('all')

// 题型展示顺序(像真卷大题排布)
const TYPE_ORDER = ['听力', '单选', '填空', '短文填空', '完型', '单词检测', '句子翻译', '阅读', '写作', '其他']

function fmtOptions(o: PlatformQuestion['options']): string {
  if (!o) return ''
  if (typeof o === 'string') return o
  if (Array.isArray(o)) return o.join('   ')
  return Object.entries(o).map(([k, v]) => `${k}. ${v}`).join('   ')
}

// 该卷出现的版本(题位累加 v1/v2…)
const versions = computed(() => {
  const s = new Set<number>()
  allRows.value.forEach(r => { if (r.sim_version) s.add(r.sim_version) })
  return [...s].sort((a, b) => a - b)
})

// 按版本筛选后的题
const versionRows = computed(() =>
  curVersion.value === 'all' ? allRows.value : allRows.value.filter(r => (r.sim_version || 0) === curVersion.value))

// 题型筛选
const filterType = ref<string>('all')
const availableTypes = computed(() => {
  const order = (t: string) => { const i = TYPE_ORDER.indexOf(t); return i < 0 ? 999 : i }
  return [...new Set(versionRows.value.map(r => r.question_type || '其他'))].sort((a, b) => order(a) - order(b))
})
const shownRows = computed(() =>
  filterType.value === 'all' ? versionRows.value : versionRows.value.filter(r => (r.question_type || '其他') === filterType.value))

// 当前展示题的 id(供全选)
const shownIds = computed(() => shownRows.value.map(r => r.id))
const checkedIds = ref<string[]>([])
const allChecked = computed(() => shownIds.value.length > 0 && shownIds.value.every(id => checkedIds.value.includes(id)))
const someChecked = computed(() => checkedIds.value.length > 0 && !allChecked.value)
function toggleAll(v: boolean) { checkedIds.value = v ? [...shownIds.value] : [] }
function toggleOne(id: string, v: boolean) {
  checkedIds.value = v ? [...new Set([...checkedIds.value, id])] : checkedIds.value.filter(x => x !== id)
}
async function onBulkReview(approve: boolean) {
  const ids = checkedIds.value.length ? checkedIds.value : shownIds.value
  if (!ids.length) { ElMessage.warning('当前没有可审核的题'); return }
  const label = checkedIds.value.length ? `选中的 ${ids.length}` : `本卷当前 ${ids.length}`
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '驳回下架'}${label} 道仿真题？`, '批量审核', { type: 'warning' })
  const r = await reviewPlatformBulk(ids, approve)
  ElMessage.success(`已${approve ? '通过' : '驳回'} ${r.updated} 道`)
  checkedIds.value = []
  await loadRows()
}

// 组装成试卷:大题(题型)→ 组(短文题组 / 散题),小题连续编号
interface PaperGroup { block_id: string | null; passage: string | null; rows: PlatformQuestion[] }
interface PaperSection { type: string; groups: PaperGroup[]; count: number }
const sections = computed<PaperSection[]>(() => {
  const byType = new Map<string, PlatformQuestion[]>()
  for (const r of shownRows.value) {
    const t = r.question_type || '其他'
    if (!byType.has(t)) byType.set(t, [])
    byType.get(t)!.push(r)
  }
  const orderIdx = (t: string) => { const i = TYPE_ORDER.indexOf(t); return i < 0 ? 999 : i }
  const types = [...byType.keys()].sort((a, b) => orderIdx(a) - orderIdx(b))
  return types.map(t => {
    const rows = byType.get(t)!
    const groups: PaperGroup[] = []
    const blockMap: Record<string, PaperGroup> = {}
    for (const r of rows) {
      if (r.block_id) {
        if (!blockMap[r.block_id]) { blockMap[r.block_id] = { block_id: r.block_id, passage: r.passage || null, rows: [] }; groups.push(blockMap[r.block_id]) }
        blockMap[r.block_id].rows.push(r)
      } else {
        groups.push({ block_id: null, passage: null, rows: [r] })
      }
    }
    return { type: t, groups, count: rows.length }
  })
})

// 连续小题编号(整卷 1..N,sim 没继承原题号 → 重新编)
const seqMap = computed<Record<string, number>>(() => {
  const m: Record<string, number> = {}; let n = 0
  for (const sec of sections.value) for (const g of sec.groups) for (const q of g.rows) m[q.id] = ++n
  return m
})

async function loadPapers() {
  loadingPapers.value = true
  try {
    const r = await listSimPapers({ status: status.value, skip: (papersPage.value - 1) * papersPageSize, limit: papersPageSize })
    papers.value = r.items
    papersTotal.value = r.total
  }
  finally { loadingPapers.value = false }
}

async function openPaper(p: SimPaper) {
  curPaper.value = p; curVersion.value = 'all'; filterType.value = 'all'; checkedIds.value = []
  await loadRows()
  // 默认看最早版本(更像一张完整卷);只有一个版本就用它
  if (versions.value.length) curVersion.value = versions.value[0]
}

async function loadRows() {
  if (!curPaper.value) return
  loadingRows.value = true
  try {
    const data = await listPlatformQuestions({
      type: 'sim', status: status.value, source_paper_id: curPaper.value.paper_id, skip: 0, limit: 1000,
    })
    allRows.value = data.items
    // 校正筛选:当前选的版本/题型在新结果里不存在 → 重置(避免切状态后筛空、看似"没数据")
    const vs = versions.value
    if (curVersion.value !== 'all' && !vs.includes(curVersion.value as number)) curVersion.value = vs.length ? vs[0] : 'all'
    if (filterType.value !== 'all' && !availableTypes.value.includes(filterType.value)) filterType.value = 'all'
  } finally { loadingRows.value = false }
}

function backToPapers() { curPaper.value = null; allRows.value = []; loadPapers() }

async function onReview(row: PlatformQuestion, approve: boolean) {
  await ElMessageBox.confirm(`确认${approve ? '通过发布' : '驳回下架'}这道仿真题？`, '确认', { type: 'warning' })
  await reviewPlatformQuestion(row.id, approve)
  ElMessage.success(approve ? '已通过并发布' : '已驳回下架')
  await loadRows()
}

function onStatusChange() {
  if (curPaper.value) loadRows(); else { papersPage.value = 1; loadPapers() }
}

onMounted(loadPapers)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>状态：</span>
      <el-select v-model="status" style="width: 130px" @change="onStatusChange">
        <el-option v-for="s in statusOptions" :key="s" :label="stLabel(s)" :value="s" />
      </el-select>
      <template v-if="curPaper">
        <el-button @click="backToPapers">← 返回试卷列表</el-button>
        <span style="font-weight:600">{{ curPaper.paper_name }}</span>
        <span class="hint">共 {{ allRows.length }} 道仿真</span>
        <template v-if="versions.length > 1">
          <span style="margin-left:8px">版本：</span>
          <el-select v-model="curVersion" style="width: 120px" size="small">
            <el-option label="全部版本" value="all" />
            <el-option v-for="v in versions" :key="v" :label="'第 ' + v + ' 套(v' + v + ')'" :value="v" />
          </el-select>
        </template>
        <span style="margin-left:8px">题型：</span>
        <el-select v-model="filterType" style="width: 120px" size="small">
          <el-option label="全部题型" value="all" />
          <el-option v-for="t in availableTypes" :key="t" :label="t" :value="t" />
        </el-select>
        <el-checkbox :model-value="allChecked" :indeterminate="someChecked"
          @change="(v: any) => toggleAll(!!v)" style="margin-left:10px">全选本卷</el-checkbox>
        <el-button size="small" type="success" @click="onBulkReview(true)">
          {{ checkedIds.length ? `通过选中(${checkedIds.length})` : '全部通过' }}</el-button>
        <el-button size="small" type="danger" @click="onBulkReview(false)">
          {{ checkedIds.length ? `驳回选中(${checkedIds.length})` : '全部驳回' }}</el-button>
      </template>
      <template v-else>
        <el-button @click="loadPapers">刷新</el-button>
        <span class="hint">仿真题审核：先选真题卷,再以「试卷形式」查看该卷派生的整卷仿真。通过后学生可见。</span>
      </template>
    </div>

    <!-- 一级:试卷列表 -->
    <el-table v-if="!curPaper" v-loading="loadingPapers" :data="papers" border style="width:100%">
      <el-table-column prop="paper_name" label="真题卷" min-width="360" show-overflow-tooltip />
      <el-table-column prop="sim_count" label="仿真数" width="120" align="center" />
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="primary" @click="openPaper(row)">查看整卷</el-button>
        </template>
      </el-table-column>
      <template #empty>该状态下暂无仿真题(去「平台真题」页勾选题/题型派生仿真)</template>
    </el-table>
    <div v-if="!curPaper && papersTotal > papersPageSize" style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="papersTotal"
        :page-size="papersPageSize" v-model:current-page="papersPage" @current-change="loadPapers" />
    </div>

    <!-- 二级:试卷形式 -->
    <div v-else v-loading="loadingRows" class="paper">
      <el-empty v-if="!sections.length" description="该版本/状态下暂无题" />
      <div v-for="(sec, si) in sections" :key="sec.type" class="section">
        <div class="sec-head">{{ ['一','二','三','四','五','六','七','八','九','十'][si] || (si+1) }}、{{ sec.type }}（{{ sec.count }} 题）</div>
        <div v-for="(g, gi) in sec.groups" :key="gi" class="group">
          <div v-if="g.passage" class="passage"><el-icon style="vertical-align:-2px;margin-right:4px"><Document /></el-icon>{{ g.passage }}</div>
          <div v-for="q in g.rows" :key="q.id" class="q">
            <el-checkbox :model-value="checkedIds.includes(q.id)" @change="(v: any) => toggleOne(q.id, !!v)" class="q-check" />
            <div class="q-main">
              <div class="q-stem"><span class="q-no">{{ seqMap[q.id] }}.</span> {{ q.stem }}
                <el-tag v-if="q.sim_version" size="small" type="info" effect="plain" style="margin-left:6px">v{{ q.sim_version }}</el-tag>
              </div>
              <div v-if="fmtOptions(q.options)" class="q-opts">{{ fmtOptions(q.options) }}</div>
              <div class="q-meta">
                <span class="ans">答案：{{ q.answer || '—' }}</span>
                <span v-for="(k, i) in (q.kp_names || [])" :key="i" class="kp">{{ k }}</span>
                <span class="st" :class="q.status">{{ stLabel(q.status) }}</span>
              </div>
              <div v-if="q.explanation" class="q-exp">解析：{{ q.explanation }}</div>
            </div>
            <div class="q-act">
              <el-button size="small" type="success" @click="onReview(q, true)">通过</el-button>
              <el-button size="small" type="danger" @click="onReview(q, false)">驳回</el-button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.paper { max-width: 1000px; }
.section { margin-bottom: 22px; }
.sec-head { font-size: 16px; font-weight: 700; color: #303133; border-bottom: 2px solid #409eff; padding-bottom: 6px; margin-bottom: 12px; }
.group { margin-bottom: 10px; }
.passage { background: #f7f9fc; border: 1px solid #ebeef5; border-radius: 6px; padding: 10px 12px; font-size: 13px; color: #555; white-space: pre-wrap; margin-bottom: 10px; max-height: 220px; overflow: auto; }
.q { display: flex; gap: 12px; padding: 10px 0; border-bottom: 1px dashed #f0f0f0; }
.q-check { margin-top: 2px; flex-shrink: 0; }
.q-main { flex: 1; min-width: 0; }
.q-stem { white-space: pre-wrap; line-height: 1.6; }
.q-no { color: #909399; margin-right: 4px; }
.q-opts { color: #606266; margin-top: 4px; font-size: 13px; }
.q-meta { margin-top: 6px; display: flex; flex-wrap: wrap; gap: 8px; align-items: center; font-size: 12px; }
.ans { color: #67c23a; font-weight: 600; }
.kp { background: #ecf5ff; color: #409eff; border-radius: 3px; padding: 0 6px; }
.st { color: #909399; }
.st.published { color: #67c23a; } .st.retired { color: #f56c6c; }
.q-exp { margin-top: 4px; color: #909399; font-size: 12px; }
.q-act { flex-shrink: 0; display: flex; flex-direction: column; gap: 6px; }
</style>

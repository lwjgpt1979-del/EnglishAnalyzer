<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listVocabReviews, approveVocabReview, approveVocabBatch, rejectVocabReview,
  vocabGenStatus, type VocabReviewItem, type VocabGenStatus,
} from '../api/admin'

const status = ref('pending')
const rows = ref<VocabReviewItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const selected = ref<VocabReviewItem[]>([])

const statusOptions = [
  { label: '待审', value: 'pending' },
  { label: '已入库', value: 'approved' },
  { label: '已驳回', value: 'rejected' },
]

async function load() {
  loading.value = true
  try {
    const data = await listVocabReviews({ status: status.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = data.items
    total.value = data.total
  } finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// —— 要素生成进度轮询(入库即后台生成 文本/探针/媒体)——
const gen = ref<VocabGenStatus | null>(null)
let genTimer: ReturnType<typeof setInterval> | null = null
function startGenPolling() {
  if (genTimer) return
  genTimer = setInterval(async () => {
    try {
      const s = await vocabGenStatus()
      gen.value = s
      if (!s.running && s.total > 0 && s.done >= s.total) {
        stopGenPolling()
        ElMessage.success(`要素生成完成：成功 ${s.ok}${s.failed ? `，失败 ${s.failed}` : ''}`)
      }
    } catch { /* 忽略轮询错误 */ }
  }, 1500)
}
function stopGenPolling() {
  if (genTimer) { clearInterval(genTimer); genTimer = null }
}
onUnmounted(stopGenPolling)

// 单个入库(自动生成全要素)
async function approveOne(row: VocabReviewItem) {
  await ElMessageBox.confirm(`入库「${row.word}」并自动生成词力通全要素（释义/例句/探针/媒体）？`, '入库', { type: 'info' })
  await approveVocabReview(row.id)
  ElMessage.success('已入库，要素后台生成中')
  gen.value = { running: true, total: 1, done: 0, ok: 0, failed: 0 }
  startGenPolling()
  load()
}
// 批量入库
async function approveBatch() {
  if (!selected.value.length) return
  const ids = selected.value.map(r => r.id)
  await ElMessageBox.confirm(
    `批量入库选中的 ${ids.length} 个词，并后台自动生成词力通全要素（释义/例句/搭配/接收探针/媒体）。媒体（发音/配图）会调用付费接口。是否继续？`,
    '批量入库', { type: 'warning' })
  const res = await approveVocabBatch(ids)
  ElMessage.success(`已入库 ${res.approved} 个，后台生成要素中`)
  gen.value = { running: true, total: res.generating, done: 0, ok: 0, failed: 0 }
  selected.value = []
  startGenPolling()
  load()
}
async function reject(row: VocabReviewItem) {
  await ElMessageBox.confirm(`驳回缺词「${row.word}」？`, '驳回', { type: 'warning' })
  await rejectVocabReview(row.id)
  ElMessage.success('已驳回')
  load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="toolbar">
      <h2>词库缺词审核</h2>
      <el-radio-group v-model="status" @change="reload">
        <el-radio-button v-for="o in statusOptions" :key="o.value" :label="o.value">{{ o.label }}</el-radio-button>
      </el-radio-group>
      <el-button
        v-if="status === 'pending'" type="primary" :disabled="!selected.length"
        @click="approveBatch">批量入库{{ selected.length ? `(${selected.length})` : '' }}</el-button>
      <span class="hint">作业/课程里出现、但词库没有的词。入库即自动生成词力通全要素（释义/例句/搭配/接收探针/媒体），学生端「单词精讲」才有详解。</span>
    </div>

    <!-- 要素生成进度 -->
    <el-alert v-if="gen && (gen.running || gen.done < gen.total)" type="info" :closable="false" class="gen-bar">
      <template #title>
        要素生成中：{{ gen.done }} / {{ gen.total }}（成功 {{ gen.ok }}<span v-if="gen.failed">，失败 {{ gen.failed }}</span>）
        <el-progress :percentage="gen.total ? Math.round(gen.done / gen.total * 100) : 0" :stroke-width="10" style="margin-top:6px" />
      </template>
    </el-alert>

    <el-table v-loading="loading" :data="rows" border style="width: 100%"
              @selection-change="(rs: VocabReviewItem[]) => selected = rs">
      <el-table-column v-if="status === 'pending'" type="selection" width="44" />
      <el-table-column prop="word" label="词" min-width="160" />
      <el-table-column prop="occur_count" label="出现次数" width="100" sortable />
      <el-table-column prop="source" label="来源" width="100" />
      <el-table-column prop="created_at" label="首次出现" width="200">
        <template #default="{ row }">{{ row.created_at ? new Date(row.created_at).toLocaleString() : '—' }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="primary" @click="approveOne(row)">入库</el-button>
            <el-button size="small" @click="reject(row)">驳回</el-button>
          </template>
          <el-tag v-else :type="row.status === 'approved' ? 'success' : 'info'">
            {{ row.status === 'approved' ? '已入库' : '已驳回' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      class="pager" layout="total, prev, pager, next, jumper"
      :total="total" :page-size="pageSize" v-model:current-page="page" @current-change="load" />
  </div>
</template>

<style scoped>
.page { padding: 16px; }
.toolbar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; flex-wrap: wrap; }
.toolbar h2 { margin: 0; }
.hint { color: #909399; font-size: 13px; }
.gen-bar { margin-bottom: 12px; }
.pager { margin-top: 16px; justify-content: flex-end; }
</style>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getTaskRunsOverview, listTaskRuns, type TaskRunItem, type TaskRunRow } from '../api/admin'

const summary = ref<{ ok: number; stale: number; failing: number; total: number } | null>(null)
const items = ref<TaskRunItem[]>([])
const loading = ref(false)

async function loadOverview() {
  loading.value = true
  try {
    const r = await getTaskRunsOverview()
    summary.value = r.summary; items.value = r.items
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

function health(it: TaskRunItem): { type: string; text: string } {
  if (it.last_status === 'failed') return { type: 'danger', text: '失败' }
  if (it.last_status === 'running') return { type: 'warning', text: '运行中' }
  if (it.stale) return { type: 'warning', text: it.last_status === 'never' ? '从未运行' : '哑火(超期未成功)' }
  return { type: 'success', text: '正常' }
}
function fmt(iso: string | null) { return iso ? iso.replace('T', ' ').slice(0, 19) : '—' }
function ago(iso: string | null) {
  if (!iso) return '从未'
  const h = (Date.now() - new Date(iso).getTime()) / 3.6e6
  if (h < 1) return Math.round(h * 60) + ' 分钟前'
  if (h < 48) return Math.round(h) + ' 小时前'
  return Math.round(h / 24) + ' 天前'
}
function resultBrief(r: Record<string, unknown> | null) {
  if (!r) return '—'
  return Object.entries(r).map(([k, v]) => `${k}=${typeof v === 'object' ? JSON.stringify(v) : v}`).join(' ').slice(0, 60)
}

// ── 历史抽屉 ──
const drawer = ref(false)
const curTask = ref<TaskRunItem | null>(null)
const runs = ref<TaskRunRow[]>([])
const runsTotal = ref(0)
const rPage = ref(1)
const rSize = 20
async function openHistory(it: TaskRunItem) {
  curTask.value = it; drawer.value = true; rPage.value = 1
  await loadRuns()
}
async function loadRuns() {
  if (!curTask.value) return
  try {
    const r = await listTaskRuns({ task: curTask.value.task, skip: (rPage.value - 1) * rSize, limit: rSize })
    runs.value = r.items; runsTotal.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
}

onMounted(loadOverview)
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">定时任务健康</h3>
      <span class="hint">所有 crontab 定时任务的运行状态。「哑火/从未运行」= 超过期望间隔仍无成功记录,可能 cron 没配或挂了;失败会自动站内告警超管。</span>
      <el-button :loading="loading" @click="loadOverview">刷新</el-button>
    </div>

    <div v-if="summary" class="cards">
      <div class="card ok"><div class="n">{{ summary.ok }}</div><div class="l">正常</div></div>
      <div class="card warn"><div class="n">{{ summary.stale }}</div><div class="l">哑火/未运行</div></div>
      <div class="card bad"><div class="n">{{ summary.failing }}</div><div class="l">失败</div></div>
      <div class="card"><div class="n">{{ summary.total }}</div><div class="l">任务总数</div></div>
    </div>

    <el-table :data="items" border stripe style="width:100%" v-loading="loading">
      <el-table-column label="健康" width="130">
        <template #default="{ row }">
          <el-tag :type="(health(row).type as any)" effect="dark" size="small">{{ health(row).text }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="label" label="任务" min-width="170" />
      <el-table-column label="期望间隔" width="100" align="center">
        <template #default="{ row }">{{ row.cadence_hours ? (row.cadence_hours >= 168 ? '每周' : row.cadence_hours >= 24 ? '每天' : row.cadence_hours + 'h') : '—' }}</template>
      </el-table-column>
      <el-table-column label="上次运行" width="180">
        <template #default="{ row }">
          <span v-if="row.last_run_at">{{ ago(row.last_run_at) }}<br><span class="muted">{{ fmt(row.last_run_at) }}</span></span>
          <span v-else class="muted">从未</span>
        </template>
      </el-table-column>
      <el-table-column label="上次结果" min-width="220">
        <template #default="{ row }">
          <span v-if="row.last_status === 'failed'" class="err">{{ (row.last_error || '').slice(0, 80) }}</span>
          <span v-else>{{ resultBrief(row.last_result) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="耗时" width="90" align="right">
        <template #default="{ row }"><span class="muted">{{ row.duration_ms != null ? (row.duration_ms >= 1000 ? (row.duration_ms / 1000).toFixed(1) + 's' : row.duration_ms + 'ms') : '—' }}</span></template>
      </el-table-column>
      <el-table-column label="操作" width="90" align="center">
        <template #default="{ row }"><el-button size="small" @click="openHistory(row)">历史</el-button></template>
      </el-table-column>
    </el-table>

    <el-drawer v-model="drawer" :title="`运行历史:${curTask?.label || ''}`" size="640px">
      <div class="hint" style="margin-bottom:10px">
        期望间隔:{{ curTask?.cadence_hours ? curTask.cadence_hours + ' 小时' : '—' }};
        cron 示例:<code>python -m app.tasks.{{ curTask?.task === 'map_crawl' ? 'crawl_map_leads' : curTask?.task }}</code>
      </div>
      <el-table :data="runs" border stripe size="small">
        <el-table-column label="状态" width="80">
          <template #default="{ row }">
            <el-tag :type="row.status === 'success' ? 'success' : row.status === 'failed' ? 'danger' : 'warning'" size="small">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="开始" width="150"><template #default="{ row }">{{ fmt(row.started_at) }}</template></el-table-column>
        <el-table-column label="耗时" width="80" align="right"><template #default="{ row }">{{ row.duration_ms != null ? row.duration_ms + 'ms' : '—' }}</template></el-table-column>
        <el-table-column label="结果 / 错误" min-width="200">
          <template #default="{ row }">
            <span v-if="row.status === 'failed'" class="err">{{ (row.error || '').slice(0, 120) }}</span>
            <span v-else>{{ resultBrief(row.result) }}</span>
          </template>
        </el-table-column>
        <template #empty>该任务暂无运行记录</template>
      </el-table>
      <el-pagination
        style="margin-top:12px; justify-content:flex-end" small
        layout="total, prev, pager, next" :total="runsTotal" :current-page="rPage" :page-size="rSize"
        @current-change="(p: number) => { rPage = p; loadRuns() }" />
    </el-drawer>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.hint code { background: #f4f4f5; padding: 1px 6px; border-radius: 4px; }
.cards { display: flex; gap: 12px; margin-bottom: 16px; }
.card { flex: 1; background: #f5f7fa; border-radius: 8px; padding: 14px 18px; text-align: center; }
.card .n { font-size: 26px; font-weight: 700; color: #303133; }
.card .l { font-size: 12px; color: #909399; margin-top: 2px; }
.card.ok .n { color: #67c23a; } .card.warn .n { color: #e6a23c; } .card.bad .n { color: #f56c6c; }
.muted { color: #a0a4ab; font-size: 12px; }
.err { color: #f56c6c; font-size: 12px; }
</style>

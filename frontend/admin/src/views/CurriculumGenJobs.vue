<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { listGenJobs, retryGenJob, getGenJob, type GenJob } from '../api/admin'
import { Refresh, CircleCheck, CircleClose } from '@element-plus/icons-vue'

const jobs = ref<GenJob[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const STATUS_TAG: Record<string, string> = { running: 'warning', done: 'success', failed: 'danger' }
const STATUS_LABEL: Record<string, string> = { running: '生成中', done: '完成', failed: '有失败' }

// 结果弹窗
const dlg = ref(false)
const cur = ref<GenJob | null>(null)
const retrying = ref<Record<string, boolean>>({})

async function load() {
  loading.value = true
  try {
    const r = await listGenJobs({ skip: (page.value - 1) * pageSize, limit: pageSize })
    jobs.value = r.items
    total.value = r.total
  }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function fmt(s?: string | null) { return s ? new Date(s).toLocaleString() : '—' }
async function viewResults(j: GenJob) {
  cur.value = j; dlg.value = true
  try { cur.value = await getGenJob(j.job_id) } catch { /* 用列表里的 */ }
}
async function onRetry(j: GenJob) {
  retrying.value[j.job_id] = true
  try {
    await retryGenJob(j.job_id)
    ElMessage.success('已重试失败单元,可稍后刷新查看')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '重试失败') }
  finally { retrying.value[j.job_id] = false }
}
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <div class="toolbar">
      <h3 style="margin:0">课程生成任务</h3>
      <span class="hint">每次「上传 PDF → 开始生成」都记一条;可回看结果、重试失败单元(关页面不影响后台)。</span>
      <el-button style="margin-left:auto" @click="load">刷新</el-button>
    </div>

    <el-table :data="jobs" border stripe style="width:100%">
      <el-table-column label="教材 / 年级 / 学期" min-width="220">
        <template #default="{ row }">{{ row.textbook_version }} · {{ row.grade }} · {{ row.semester }}学期</template>
      </el-table-column>
      <el-table-column label="来源" width="80" align="center">
        <template #default="{ row }">{{ row.source === 'pdf' ? 'PDF' : '学期' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="STATUS_TAG[row.status] || 'info'" size="small">{{ STATUS_LABEL[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="进度" width="200">
        <template #default="{ row }">
          <div style="display:flex;align-items:center;gap:8px">
            <el-progress :percentage="row.total ? Math.round((row.done + row.failed) / row.total * 100) : 0"
              :status="row.failed ? 'exception' : (row.status === 'done' ? 'success' : undefined)" :stroke-width="10" style="flex:1" />
            <span style="font-size:12px;white-space:nowrap;color:#606266;display:inline-flex;align-items:center;gap:2px">
              <el-icon color="#67C23A"><CircleCheck /></el-icon>{{ row.done }}
              <span v-if="row.failed" style="color:#F56C6C;display:inline-flex;align-items:center;gap:2px"><el-icon><CircleClose /></el-icon>{{ row.failed }}</span> /{{ row.total }}
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="170">
        <template #default="{ row }">{{ fmt(row.created_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="200" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="viewResults(row)">查看结果</el-button>
          <el-button v-if="row.failed && row.status !== 'running'" size="small" type="warning"
            :loading="retrying[row.job_id]" @click="onRetry(row)"><el-icon style="margin-right:4px"><Refresh /></el-icon>重试</el-button>
        </template>
      </el-table-column>
    </el-table>
    <el-empty v-if="!loading && !jobs.length" description="暂无生成任务" />
    <div v-if="total > pageSize" style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <el-dialog v-model="dlg" :title="cur ? `生成结果 · ${cur.textbook_version} ${cur.grade} ${cur.semester}学期` : '生成结果'" width="640px">
      <el-table v-if="cur" :data="cur.results" border size="small" style="width:100%">
        <el-table-column label="状态" width="60" align="center">
          <template #default="{ row }"><el-tag :type="row.status === 'ok' ? 'success' : 'danger'" size="small"><el-icon><CircleCheck v-if="row.status === 'ok'" /><CircleClose v-else /></el-icon></el-tag></template>
        </el-table-column>
        <el-table-column label="单元" width="70" align="center"><template #default="{ row }">Unit {{ row.unit_no }}</template></el-table-column>
        <el-table-column prop="unit_title" label="标题" min-width="140" show-overflow-tooltip />
        <el-table-column label="结果（拆单元 / 挂 PDF）" min-width="180">
          <template #default="{ row }">
            <template v-if="row.status === 'ok'">
              <el-tag size="small" type="success" effect="plain">已拆单元</el-tag>
              <el-tag size="small" :type="row.pdf ? 'success' : 'info'" effect="plain" style="margin-left:6px">{{ row.pdf ? '已挂 PDF' : '未挂 PDF' }}</el-tag>
            </template>
            <span v-else style="color:#F56C6C;font-size:12px">{{ row.error }}</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button v-if="cur && cur.failed && cur.status !== 'running'" type="warning" :loading="retrying[cur.job_id]" @click="onRetry(cur)"><el-icon style="margin-right:4px"><Refresh /></el-icon>重试失败单元</el-button>
        <el-button @click="dlg = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.hint { color: #909399; font-size: 12px; }
</style>

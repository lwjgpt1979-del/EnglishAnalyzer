<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listContentFeedback, handleContentFeedback, type ContentFeedbackItem } from '../api/admin'
import { EditPen } from '@element-plus/icons-vue'

const rows = ref<ContentFeedbackItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const status = ref('pending')
const ttype = ref('all')

const TYPE: Record<string, string> = { diagnosis: '诊断有误', question: '题目有误' }
const ST: Record<string, string> = { pending: '待处理', handled: '已处理', dismissed: '已忽略' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

async function load() {
  loading.value = true
  try {
    const r = await listContentFeedback({ status: status.value, target_type: ttype.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }
async function act(r: ContentFeedbackItem, action: 'handled' | 'dismissed') {
  try {
    const { value } = await ElMessageBox.prompt(action === 'handled' ? '处理备注（如已修正题目）' : '忽略原因', action === 'handled' ? '标记已处理' : '忽略', { inputPlaceholder: '可选' })
      .catch(() => ({ value: '' }))
    await handleContentFeedback(r.id, action, value || undefined)
    ElMessage.success('已更新'); await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="cf">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><EditPen /></el-icon>内容质量反馈</h2>
      <div class="filters">
        <el-radio-group v-model="ttype" @change="reload">
          <el-radio-button label="all">全部类型</el-radio-button>
          <el-radio-button label="diagnosis">诊断有误</el-radio-button>
          <el-radio-button label="question">题目有误</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="status" @change="reload">
          <el-radio-button label="pending">待处理</el-radio-button>
          <el-radio-button label="handled">已处理</el-radio-button>
          <el-radio-button label="dismissed">已忽略</el-radio-button>
          <el-radio-button label="all">全部</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">用户上报的「诊断/题目有误」，监控 AI 与题库质量（§5.5）。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="类型" width="100">
        <template #default="{ row }"><el-tag size="small">{{ TYPE[row.target_type] || row.target_type }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="snippet" label="对象摘要" min-width="200" show-overflow-tooltip />
      <el-table-column prop="reason" label="用户说明" min-width="180" show-overflow-tooltip />
      <el-table-column prop="target_id" label="关联ID" width="160" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'handled' ? 'success' : (row.status === 'dismissed' ? 'info' : 'warning')" size="small">{{ ST[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="150"><template #default="{ row }">{{ fmt(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" link @click="act(row, 'handled')">已处理</el-button>
            <el-button size="small" link @click="act(row, 'dismissed')">忽略</el-button>
          </template>
          <span v-else class="muted">{{ row.note || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>
  </div>
</template>

<style scoped>
.cf { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>

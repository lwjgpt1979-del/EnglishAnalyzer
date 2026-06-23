<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listSuggestions, handleSuggestion, type FeedbackItem } from '../api/admin'
import { Opportunity } from '@element-plus/icons-vue'

const rows = ref<FeedbackItem[]>([])
const total = ref(0)
const loading = ref(false)
const status = ref('pending')
const kind = ref('all')

const KIND: Record<string, string> = { suggestion: '功能建议', bug: 'BUG报告' }
const ST: Record<string, string> = { pending: '待处理', reviewing: '处理中', done: '已处理', dismissed: '已忽略' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

async function load() {
  loading.value = true
  try {
    const r = await listSuggestions({ status: status.value, kind: kind.value, limit: 100 })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
async function act(r: FeedbackItem, action: 'reviewing' | 'done' | 'dismissed') {
  try {
    const { value } = await ElMessageBox.prompt('处理备注', ST[action], { inputPlaceholder: '可选' })
      .catch(() => ({ value: '' }))
    await handleSuggestion(r.id, action, value || undefined)
    ElMessage.success('已更新'); await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="fb">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Opportunity /></el-icon>意见反馈 / BUG</h2>
      <div class="filters">
        <el-radio-group v-model="kind" @change="load">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="suggestion">功能建议</el-radio-button>
          <el-radio-button label="bug">BUG报告</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="status" @change="load">
          <el-radio-button label="pending">待处理</el-radio-button>
          <el-radio-button label="reviewing">处理中</el-radio-button>
          <el-radio-button label="done">已处理</el-radio-button>
          <el-radio-button label="dismissed">已忽略</el-radio-button>
          <el-radio-button label="all">全部</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">用户提交的功能建议/BUG（§13.3，文字+截图）。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="类型" width="100">
        <template #default="{ row }"><el-tag :type="row.kind === 'bug' ? 'danger' : 'primary'" size="small">{{ KIND[row.kind] || row.kind }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="content" label="内容" min-width="260" show-overflow-tooltip />
      <el-table-column label="截图" width="120">
        <template #default="{ row }">
          <el-image v-for="(u, i) in (row.images || [])" :key="i" :src="u" :preview-src-list="row.images"
            style="width: 28px; height: 28px; margin-right: 4px; border-radius: 4px" fit="cover" />
          <span v-if="!row.images?.length" class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="contact" label="联系方式" width="130" show-overflow-tooltip />
      <el-table-column label="状态" width="100">
        <template #default="{ row }">
          <el-tag :type="row.status === 'done' ? 'success' : (row.status === 'dismissed' ? 'info' : 'warning')" size="small">{{ ST[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="时间" width="150"><template #default="{ row }">{{ fmt(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="200" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status !== 'done' && row.status !== 'dismissed'">
            <el-button v-if="row.status === 'pending'" size="small" link @click="act(row, 'reviewing')">受理</el-button>
            <el-button size="small" type="success" link @click="act(row, 'done')">已处理</el-button>
            <el-button size="small" link @click="act(row, 'dismissed')">忽略</el-button>
          </template>
          <span v-else class="muted">{{ row.note || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="muted total">共 {{ total }} 条</div>
  </div>
</template>

<style scoped>
.fb { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>

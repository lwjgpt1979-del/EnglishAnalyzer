<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listBanAppeals, reviewBanAppeal, type BanAppealItem } from '../api/admin'
import { Warning } from '@element-plus/icons-vue'

const rows = ref<BanAppealItem[]>([])
const total = ref(0)
const loading = ref(false)
const status = ref('pending')

const ST: Record<string, string> = { pending: '待审', approved: '已通过(解封)', rejected: '已驳回' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

async function load() {
  loading.value = true
  try {
    const r = await listBanAppeals({ status: status.value, limit: 100 })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function onApprove(r: BanAppealItem) {
  try {
    const { value } = await ElMessageBox.prompt('通过后将解封并按封禁时长补偿会员，备注（可选）', '通过申诉', { inputPlaceholder: '如：误判，已解封' })
    await reviewBanAppeal(r.id, true, value || undefined)
    ElMessage.success('已通过并解封'); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}
async function onReject(r: BanAppealItem) {
  try {
    const { value } = await ElMessageBox.prompt('驳回理由', '驳回申诉', { inputPattern: /\S+/, inputErrorMessage: '请填理由' })
    await reviewBanAppeal(r.id, false, value)
    ElMessage.success('已驳回'); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="ba">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Warning /></el-icon>封禁申诉</h2>
      <div class="filters">
        <el-radio-group v-model="status" @change="load">
          <el-radio-button label="pending">待审</el-radio-button>
          <el-radio-button label="approved">已通过</el-radio-button>
          <el-radio-button label="rejected">已驳回</el-radio-button>
          <el-radio-button label="all">全部</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">通过申诉将自动解封，并按封禁时长补偿等量会员时长（§5.3.1）。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="用户" width="150">
        <template #default="{ row }">
          <div>{{ row.nickname || '(未设昵称)' }}</div>
          <div class="muted">{{ row.phone || row.user_id.slice(0, 8) }}</div>
        </template>
      </el-table-column>
      <el-table-column prop="ban_reason" label="封禁原因" min-width="160" />
      <el-table-column prop="reason" label="申诉说明" min-width="200" />
      <el-table-column label="证明" width="90">
        <template #default="{ row }">
          <el-link v-for="(u, i) in row.evidence_urls" :key="i" :href="u" target="_blank" type="primary" style="display:block">图{{ i + 1 }}</el-link>
          <span v-if="!row.evidence_urls.length" class="muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.status === 'approved' ? 'success' : (row.status === 'rejected' ? 'danger' : 'warning')" size="small">{{ ST[row.status] || row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申诉时间" width="150"><template #default="{ row }">{{ fmt(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="140" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" link @click="onApprove(row)">通过解封</el-button>
            <el-button size="small" type="danger" link @click="onReject(row)">驳回</el-button>
          </template>
          <span v-else class="muted">{{ row.note || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div class="muted total">共 {{ total }} 条</div>
  </div>
</template>

<style scoped>
.ba { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>

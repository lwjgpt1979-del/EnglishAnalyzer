<template>
  <div class="page">
    <div class="toolbar">
      <el-select v-model="status" style="width:140px" @change="reload">
        <el-option label="待审批" value="pending" />
        <el-option label="已执行" value="executed" />
        <el-option label="已驳回" value="rejected" />
        <el-option label="执行失败" value="failed" />
        <el-option label="全部" value="all" />
      </el-select>
      <el-button style="margin-left:auto" @click="openConfig">阈值配置</el-button>
    </div>

    <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px"
      title="高风险操作(退款批准、批量发券)超阈值时需另一位管理员复核后才执行(事前双人复核)。不能复核自己发起的操作。" />

    <el-table :data="rows" v-loading="loading" border style="width:100%">
      <el-table-column prop="summary" label="操作" min-width="220" show-overflow-tooltip />
      <el-table-column label="类型" width="100">
        <template #default="{ row }">{{ actionLabel(row.action_type) }}</template>
      </el-table-column>
      <el-table-column label="金额/规模" width="110">
        <template #default="{ row }">{{ row.amount_fen != null ? '¥' + (row.amount_fen / 100).toFixed(2) : '—' }}</template>
      </el-table-column>
      <el-table-column label="发起人" width="150">
        <template #default="{ row }">
          <div>{{ row.maker_name || row.maker_id.slice(0, 8) }}</div>
          <div class="note" v-if="row.maker_note">{{ row.maker_note }}</div>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="96">
        <template #default="{ row }"><el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag></template>
      </el-table-column>
      <el-table-column label="复核" min-width="160">
        <template #default="{ row }">
          <div v-if="row.checker_name">{{ row.checker_name }}<span class="note" v-if="row.checker_note"> · {{ row.checker_note }}</span></div>
          <div class="note err" v-if="row.exec_error">执行失败:{{ row.exec_error }}</div>
        </template>
      </el-table-column>
      <el-table-column label="发起时间" width="150">
        <template #default="{ row }">{{ (row.created_at || '').slice(0, 16).replace('T', ' ') }}</template>
      </el-table-column>
      <el-table-column label="操作" width="150" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" @click="doDecide(row, true)">批准</el-button>
            <el-button size="small" type="danger" plain @click="doDecide(row, false)">驳回</el-button>
          </template>
          <span v-else class="note">—</span>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination style="margin-top:12px; justify-content:flex-end" layout="total, prev, pager, next, jumper"
      :total="total" :page-size="pageSize" :current-page="page" @current-change="(p: number) => { page = p; load() }" />

    <AppDialog v-model="cfgOpen" title="敏感操作审批阈值" width="480px">
      <el-form label-width="150px">
        <el-form-item label="启用二次审批"><el-switch v-model="cfg.enabled" /></el-form-item>
        <el-form-item label="退款批准阈值(元)">
          <el-input-number v-model="cfgRefundYuan" :min="0" :step="50" />
          <span class="note" style="margin-left:8px">退款金额 ≥ 此值需复核</span>
        </el-form-item>
        <el-form-item label="批量发券人数阈值">
          <el-input-number v-model="cfg.coupon_grant_count" :min="1" />
          <span class="note" style="margin-left:8px">发券人数 ≥ 此值需复核</span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="cfgOpen = false">取消</el-button>
        <el-button type="primary" @click="saveConfig">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import AppDialog from '../components/AppDialog.vue'
import {
  listApprovals, decideApproval, getApprovalConfig, updateApprovalConfig,
  type ApprovalItem, type ApprovalConfig,
} from '../api/admin'

const rows = ref<ApprovalItem[]>([])
const total = ref(0)
const loading = ref(false)
const status = ref('pending')
const page = ref(1)
const pageSize = 30

async function load() {
  loading.value = true
  try {
    const d = await listApprovals({ status: status.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = d.items
    total.value = d.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }
onMounted(load)

async function doDecide(row: ApprovalItem, approve: boolean) {
  let note: string | undefined
  if (approve) {
    try { await ElMessageBox.confirm(`确认批准并立即执行:${row.summary}?`, '批准', { type: 'warning' }) } catch { return }
  } else {
    try {
      const r = await ElMessageBox.prompt('驳回理由(可空)', '驳回审批', { inputType: 'textarea', inputValidator: () => true })
      note = r.value || undefined
    } catch { return }
  }
  try {
    await decideApproval(row.id, { approve, note })
    ElMessage.success(approve ? '已批准并执行' : '已驳回')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

function actionLabel(t: string) { return ({ refund_approve: '退款批准', coupon_grant: '批量发券' } as Record<string, string>)[t] || t }
function statusLabel(s: string) { return ({ pending: '待审批', executed: '已执行', rejected: '已驳回', failed: '执行失败' } as Record<string, string>)[s] || s }
function statusType(s: string): 'warning' | 'success' | 'info' | 'danger' {
  return ({ pending: 'warning', executed: 'success', rejected: 'info', failed: 'danger' } as Record<string, 'warning' | 'success' | 'info' | 'danger'>)[s] || 'info'
}

const cfgOpen = ref(false)
const cfg = reactive<ApprovalConfig>({ enabled: true, refund_amount_fen: 20000, coupon_grant_count: 20 })
const cfgRefundYuan = ref(200)
async function openConfig() {
  try {
    const c = await getApprovalConfig()
    Object.assign(cfg, c)
    cfgRefundYuan.value = Math.round((c.refund_amount_fen || 0) / 100)
    cfgOpen.value = true
  } catch (e: any) { ElMessage.error(e?.message || '读取配置失败') }
}
async function saveConfig() {
  try {
    const saved = await updateApprovalConfig({
      enabled: cfg.enabled,
      refund_amount_fen: Math.round(cfgRefundYuan.value * 100),
      coupon_grant_count: cfg.coupon_grant_count,
    })
    Object.assign(cfg, saved)
    cfgOpen.value = false
    ElMessage.success('已保存')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
</script>

<style scoped>
.page { padding: 8px; }
.toolbar { display: flex; align-items: center; margin-bottom: 12px; }
.note { font-size: 12px; color: #999; }
.note.err { color: #e0654f; }
</style>

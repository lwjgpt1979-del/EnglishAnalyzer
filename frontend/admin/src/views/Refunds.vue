<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listRefunds, reviewRefund, getOrderEvidence, openEvidencePdf,
  type AdminRefundItem,
} from '../api/admin'

const rows = ref<AdminRefundItem[]>([])
const total = ref(0)
const loading = ref(false)
const filterKind = ref('all')
const filterStatus = ref('pending')
const skip = ref(0)
const PAGE_SIZE = 50

const APPEAL_LABEL: Record<string, string> = {
  SYSTEM_FAULT: '平台系统故障', DESC_MISMATCH: '服务描述不符',
  DUPLICATE_PURCHASE: '重复购买', MINOR_PURCHASE: '未成年人未授权',
}
const STATE_LABEL: Record<string, string> = {
  AUTO_FULL_REFUND: '自动全额退款', MANUAL_REVIEW_PARTIAL: '待审(按比例)',
  REFUND_PARTIAL_APPROVED: '按比例已退', REFUND_REJECTED: '退款驳回',
  MANUAL_REVIEW_APPEAL: '待审(申诉)', AUTO_DUPLICATE_REFUND: '重复单已退',
  APPEAL_APPROVED: '申诉通过', APPEAL_REJECTED: '申诉驳回',
  REJECT_DUPLICATE_INELIGIBLE: '不符重复购买',
}
function stateText(s: string | null) { return s ? (STATE_LABEL[s] || s) : '-' }
function yuan(fen: number) { return (fen / 100).toFixed(2) }

async function load() {
  loading.value = true
  try {
    const r = await listRefunds({
      kind: filterKind.value, status: filterStatus.value,
      skip: skip.value, limit: PAGE_SIZE,
    })
    rows.value = r.items
    total.value = r.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally { loading.value = false }
}

function onPage(p: number) { skip.value = (p - 1) * PAGE_SIZE; load() }

async function onApprove(row: AdminRefundItem) {
  // 按比例退款需确认金额；其余默认按记录金额
  let amount = row.amount_fen
  if (row.refund_type === 'prorated' || row.kind === 'appeal') {
    try {
      const { value } = await ElMessageBox.prompt(
        `核定退款金额（元），订单实付 ¥${yuan(row.order_amount_fen)}`,
        '通过审核', { inputValue: yuan(amount), inputPattern: /^\d+(\.\d{1,2})?$/, inputErrorMessage: '请输入有效金额' },
      )
      amount = Math.round(parseFloat(value) * 100)
    } catch { return }
  } else {
    try {
      await ElMessageBox.confirm(`确认退款 ¥${yuan(amount)}？`, '通过审核')
    } catch { return }
  }
  try {
    await reviewRefund(row.id, { approve: true, amount_fen: amount })
    ElMessage.success('已通过并退款（dev-mock）')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

async function onReject(row: AdminRefundItem) {
  try {
    const { value } = await ElMessageBox.prompt('驳回理由', '驳回', { inputPlaceholder: '可填写驳回原因' })
    await reviewRefund(row.id, { approve: false, reason: value || undefined })
    ElMessage.success('已驳回')
    await load()
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error(e?.message || '操作失败')
  }
}

// 举证包
const evidenceOpen = ref(false)
const evidenceData = ref<Record<string, unknown> | null>(null)
const evidenceJson = computed(() =>
  evidenceData.value ? JSON.stringify(evidenceData.value, null, 2) : '')

async function onEvidence(row: AdminRefundItem) {
  try {
    evidenceData.value = await getOrderEvidence(row.order_id)
    evidenceOpen.value = true
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
}
async function onEvidencePdf(row: AdminRefundItem) {
  try { await openEvidencePdf(row.order_id) }
  catch (e: any) { ElMessage.error(e?.message || '打开失败') }
}

function changeFilter() { skip.value = 0; load() }

onMounted(load)
</script>

<template>
  <div class="refunds">
    <div class="toolbar">
      <h2>退款 / 申诉审核</h2>
      <div class="filters">
        <el-radio-group v-model="filterKind" @change="changeFilter">
          <el-radio-button label="all">全部</el-radio-button>
          <el-radio-button label="refund">退款</el-radio-button>
          <el-radio-button label="appeal">申诉</el-radio-button>
        </el-radio-group>
        <el-radio-group v-model="filterStatus" @change="changeFilter">
          <el-radio-button label="pending">待审</el-radio-button>
          <el-radio-button label="all">全部状态</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="类型" width="80">
        <template #default="{ row }">
          <el-tag :type="row.kind === 'appeal' ? 'warning' : 'primary'" size="small">
            {{ row.kind === 'appeal' ? '申诉' : '退款' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="order_no" label="订单号" width="200">
        <template #default="{ row }">
          {{ row.order_no }}
          <el-tag v-if="row.overdue" type="danger" size="small" effect="dark" style="margin-left:4px">超时</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="用户" width="140">
        <template #default="{ row }">
          <div>{{ row.user_nickname || '-' }}</div>
          <div class="muted">{{ row.user_phone || '' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="档位" width="90">
        <template #default="{ row }">{{ row.order_tier }}</template>
      </el-table-column>
      <el-table-column label="申诉类型/原因" min-width="180">
        <template #default="{ row }">
          <div v-if="row.appeal_type">{{ APPEAL_LABEL[row.appeal_type] || row.appeal_type }}</div>
          <div class="muted">{{ row.reason || '' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="金额(退/订单)" width="140">
        <template #default="{ row }">
          ¥{{ yuan(row.amount_fen) }} / ¥{{ yuan(row.order_amount_fen) }}
        </template>
      </el-table-column>
      <el-table-column label="状态" width="130">
        <template #default="{ row }">
          <el-tag v-if="row.status === 'pending'" type="info" size="small">待审</el-tag>
          <el-tag v-else-if="row.status === 'completed'" type="success" size="small">已完成</el-tag>
          <el-tag v-else-if="row.status === 'rejected'" type="danger" size="small">已驳回</el-tag>
          <span v-else>{{ row.status }}</span>
          <div class="muted">{{ stateText(row.state_code) }}</div>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="onEvidence(row)">举证包</el-button>
          <el-button size="small" link type="primary" @click="onEvidencePdf(row)">举证PDF</el-button>
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" @click="onApprove(row)">通过</el-button>
            <el-button size="small" type="danger" @click="onReject(row)">驳回</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>

    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="PAGE_SIZE" :current-page="Math.floor(skip / PAGE_SIZE) + 1" @current-change="onPage" />
    </div>

    <el-dialog v-model="evidenceOpen" title="纠纷举证包（§4.6.4）" width="720px">
      <pre class="evidence">{{ evidenceJson }}</pre>
    </el-dialog>
  </div>
</template>

<style scoped>
.refunds { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.muted { color: #999; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
.evidence { background: #1e1e1e; color: #d4d4d4; padding: 16px; border-radius: 6px; max-height: 60vh; overflow: auto; font-size: 12px; line-height: 1.5; white-space: pre-wrap; word-break: break-all; }
</style>

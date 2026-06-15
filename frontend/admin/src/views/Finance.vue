<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getFinanceSummary, getSettlements, computeSettlement, exportFinance,
  listBranches, type FinanceSummary, type FinanceSettlement, type BranchCompanyItem,
} from '../api/admin'

const month = ref(new Date().toISOString().slice(0, 7))   // YYYY-MM
const groupBy = ref<'account' | 'branch'>('account')
const summary = ref<FinanceSummary | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try { summary.value = await getFinanceSummary({ month: month.value, group_by: groupBy.value }) }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
async function onExport() {
  try { await exportFinance(month.value); ElMessage.success('已导出 CSV') }
  catch (e: any) { ElMessage.error(e?.message || '导出失败') }
}

// 分成结算
const branches = ref<BranchCompanyItem[]>([])
const settlements = ref<FinanceSettlement[]>([])
const setBranch = ref('')
async function loadSettlements() {
  try {
    branches.value = await listBranches()
    settlements.value = await getSettlements()
  } catch { /* ignore */ }
}
async function onCompute(persist: boolean) {
  if (!setBranch.value) { ElMessage.warning('请选择分公司'); return }
  const [y, m] = month.value.split('-').map(Number)
  const start = `${month.value}-01`
  const end = m === 12 ? `${y + 1}-01-01` : `${month.value.slice(0, 5)}${String(m + 1).padStart(2, '0')}-01`
  try {
    const r: any = await computeSettlement({ branch_id: setBranch.value, start, end, persist })
    ElMessage.success(persist ? `已结算并保存：分公司应得 ¥${r.branch_payable_yuan}` : `预览：分公司应得 ¥${r.branch_payable_yuan} / 平台 ¥${r.platform_share_yuan}`)
    if (persist) settlements.value = await getSettlements()
  } catch (e: any) { ElMessage.error(e?.message || '计算失败') }
}

onMounted(() => { load(); loadSettlements() })
</script>

<template>
  <div class="finance">
    <div class="toolbar">
      <h2>💰 财务管理</h2>
      <div class="filters">
        <el-date-picker v-model="month" type="month" value-format="YYYY-MM" placeholder="月份" @change="load" />
        <el-radio-group v-model="groupBy" @change="load">
          <el-radio-button label="account">按收款主体</el-radio-button>
          <el-radio-button label="branch">按分公司</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
        <el-button type="primary" @click="onExport">导出CSV</el-button>
      </div>
    </div>

    <div v-if="summary" class="cards">
      <div class="card"><div class="c-num">¥{{ summary.total.gross_yuan }}</div><div class="c-lbl">营收</div></div>
      <div class="card"><div class="c-num red">¥{{ summary.total.refund_yuan }}</div><div class="c-lbl">退款</div></div>
      <div class="card"><div class="c-num green">¥{{ summary.total.net_yuan }}</div><div class="c-lbl">净收入</div></div>
      <div class="card"><div class="c-num">{{ summary.total.orders }}</div><div class="c-lbl">订单数</div></div>
      <div class="card"><div class="c-num">{{ summary.total.refunds }}</div><div class="c-lbl">退款数</div></div>
    </div>

    <el-table :data="summary?.groups || []" v-loading="loading" stripe style="margin-top:16px">
      <el-table-column prop="name" :label="groupBy === 'branch' ? '分公司' : '收款主体'" min-width="200" />
      <el-table-column label="营收(元)"><template #default="{ row }">¥{{ row.gross_yuan }}</template></el-table-column>
      <el-table-column label="退款(元)"><template #default="{ row }">¥{{ row.refund_yuan }}</template></el-table-column>
      <el-table-column label="净收入(元)"><template #default="{ row }">¥{{ row.net_yuan }}</template></el-table-column>
      <el-table-column prop="orders" label="订单数" width="90" />
      <el-table-column prop="refunds" label="退款数" width="90" />
    </el-table>

    <h3 style="margin-top:28px">分公司分成结算</h3>
    <p class="hint">净收入 × 分成率 = 分公司应得（分成率在「🏢 分公司管理」配置）。</p>
    <div class="settle-form">
      <el-select v-model="setBranch" placeholder="选择分公司" style="width:220px">
        <el-option v-for="b in branches" :key="b.id" :label="b.name" :value="b.id" />
      </el-select>
      <span class="muted">周期：{{ month }}</span>
      <el-button @click="onCompute(false)">试算</el-button>
      <el-button type="primary" @click="onCompute(true)">结算并保存</el-button>
    </div>
    <el-table :data="settlements" stripe style="margin-top:12px">
      <el-table-column prop="branch_name" label="分公司" min-width="140" />
      <el-table-column label="周期"><template #default="{ row }">{{ row.period_start }} ~ {{ row.period_end }}</template></el-table-column>
      <el-table-column label="净收入"><template #default="{ row }">¥{{ row.net_yuan }}</template></el-table-column>
      <el-table-column label="分公司应得"><template #default="{ row }">¥{{ row.branch_payable_yuan }}</template></el-table-column>
      <el-table-column label="平台分成"><template #default="{ row }">¥{{ row.platform_share_yuan }}</template></el-table-column>
      <el-table-column prop="status" label="状态" width="90" />
    </el-table>
  </div>
</template>

<style scoped>
.finance { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.cards { display: flex; gap: 12px; flex-wrap: wrap; }
.card { flex: 1; min-width: 120px; background: #fff; border: 1px solid #ebeef5; border-radius: 8px; padding: 16px; text-align: center; }
.c-num { font-size: 26px; font-weight: 800; color: #303133; }
.c-num.red { color: #f56c6c; } .c-num.green { color: #67c23a; }
.c-lbl { font-size: 13px; color: #909399; margin-top: 4px; }
.hint { color: #909399; font-size: 13px; margin: 4px 0 12px; }
.settle-form { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.muted { color: #909399; font-size: 13px; }
</style>

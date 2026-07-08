<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listInvoices, issueInvoice, rejectInvoice, type AdminInvoiceItem } from '../api/admin'
import { Tickets } from '@element-plus/icons-vue'

const rows = ref<AdminInvoiceItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)
const status = ref('pending')

async function load() {
  loading.value = true
  try {
    const r = await listInvoices({ status: status.value, skip: (page.value - 1) * pageSize, limit: pageSize })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// 开具弹窗
const issueOpen = ref(false)
const cur = ref<AdminInvoiceItem | null>(null)
const form = reactive({ invoice_no: '', invoice_url: '' })
function openIssue(r: AdminInvoiceItem) {
  cur.value = r; form.invoice_no = ''; form.invoice_url = ''; issueOpen.value = true
}
async function submitIssue() {
  if (!cur.value || !form.invoice_no.trim()) { ElMessage.warning('请填写发票号码'); return }
  try {
    await issueInvoice(cur.value.id, form.invoice_no.trim(), form.invoice_url.trim() || undefined)
    ElMessage.success('已开具'); issueOpen.value = false; await load()
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function onReject(r: AdminInvoiceItem) {
  try {
    const { value } = await ElMessageBox.prompt('驳回原因', '驳回开票', { inputPlaceholder: '如抬头/税号有误' })
    await rejectInvoice(r.id, value || undefined)
    ElMessage.success('已驳回'); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}

const TT: Record<string, string> = { personal: '个人', company: '企业' }
const ST: Record<string, string> = { pending: '待开具', issued: '已开具', rejected: '已驳回' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }

onMounted(load)
</script>

<template>
  <div class="inv">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Tickets /></el-icon>发票申请</h2>
      <div class="filters">
        <el-radio-group v-model="status" @change="reload">
          <el-radio-button label="pending">待开具</el-radio-button>
          <el-radio-button label="issued">已开具</el-radio-button>
          <el-radio-button label="rejected">已驳回</el-radio-button>
          <el-radio-button label="all">全部</el-radio-button>
        </el-radio-group>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">真实发票由税控/电子发票服务商开具后，在此回填发票号与下载链接。开票方=订单收款主体。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="抬头" min-width="180">
        <template #default="{ row }">
          <div>{{ row.title }} <el-tag size="small">{{ TT[row.title_type] || row.title_type }}</el-tag></div>
          <div class="muted">{{ row.tax_no || '' }}</div>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="100"><template #default="{ row }">¥{{ row.amount_yuan }}</template></el-table-column>
      <el-table-column prop="content" label="内容" width="120" />
      <el-table-column label="开票主体" min-width="140"><template #default="{ row }">{{ row.payment_account || '-' }}</template></el-table-column>
      <el-table-column prop="order_no" label="订单号" min-width="180" />
      <el-table-column label="状态" width="110">
        <template #default="{ row }">
          <el-tag :type="row.status === 'issued' ? 'success' : (row.status === 'rejected' ? 'danger' : 'warning')" size="small">
            {{ ST[row.status] || row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="申请时间" width="150"><template #default="{ row }">{{ fmt(row.created_at) }}</template></el-table-column>
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <template v-if="row.status === 'pending'">
            <el-button size="small" type="success" link @click="openIssue(row)">开具</el-button>
            <el-button size="small" type="danger" link @click="onReject(row)">驳回</el-button>
          </template>
          <el-link v-else-if="row.invoice_url" :href="row.invoice_url" target="_blank" type="primary">查看发票</el-link>
          <span v-else class="muted">{{ row.invoice_no || '-' }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <AppDialog v-model="issueOpen" title="开具发票" width="460px">
      <el-form label-width="90px">
        <el-form-item label="发票号码"><el-input v-model="form.invoice_no" placeholder="税控系统的发票号" /></el-form-item>
        <el-form-item label="发票链接"><el-input v-model="form.invoice_url" placeholder="电子发票 PDF 下载链接（可选）" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="issueOpen = false">取消</el-button>
        <el-button type="primary" @click="submitIssue">确认开具</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.inv { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>

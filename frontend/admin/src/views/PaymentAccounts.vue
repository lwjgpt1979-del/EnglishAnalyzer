<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listPaymentAccounts, createPaymentAccount, updatePaymentAccount,
  setDefaultPaymentAccount, togglePaymentAccount,
  type PaymentAccountItem,
} from '../api/admin'

const rows = ref<PaymentAccountItem[]>([])
const loading = ref(false)

const SUBJECT: Record<string, string> = { individual: '个体工商户', company: '公司', subsidiary: '子公司' }
const PROVIDER: Record<string, string> = { wechat: '微信支付', alipay: '支付宝', apple_iap: '苹果IAP', googleplay: 'GooglePlay', stripe: 'Stripe' }

async function load() {
  loading.value = true
  try { rows.value = await listPaymentAccounts() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// 新建/编辑弹窗
const dialogOpen = ref(false)
const editing = ref<PaymentAccountItem | null>(null)
const form = reactive({
  name: '', subject_type: 'company', provider: 'wechat',
  configText: '', secret_alias: '', branch_company_id: '', is_active: true,
})

function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', subject_type: 'company', provider: 'wechat', configText: '', secret_alias: '', branch_company_id: '', is_active: true })
  dialogOpen.value = true
}
function openEdit(r: PaymentAccountItem) {
  editing.value = r
  Object.assign(form, {
    name: r.name, subject_type: r.subject_type, provider: r.provider,
    configText: JSON.stringify(r.config || {}, null, 2),
    secret_alias: r.secret_alias || '', branch_company_id: r.branch_company_id || '',
    is_active: r.is_active,
  })
  dialogOpen.value = true
}

async function save() {
  let config: Record<string, unknown> = {}
  if (form.configText.trim()) {
    try { config = JSON.parse(form.configText) }
    catch { ElMessage.error('config 不是合法 JSON'); return }
  }
  const body = {
    name: form.name, subject_type: form.subject_type, provider: form.provider,
    config, secret_alias: form.secret_alias || null,
    branch_company_id: form.branch_company_id || null, is_active: form.is_active,
  }
  try {
    if (editing.value) await updatePaymentAccount(editing.value.id, body)
    else await createPaymentAccount(body)
    ElMessage.success('已保存')
    dialogOpen.value = false
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

async function onSetDefault(r: PaymentAccountItem) {
  try { await setDefaultPaymentAccount(r.id); ElMessage.success('已设为默认'); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function onToggle(r: PaymentAccountItem) {
  try { await togglePaymentAccount(r.id); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="pa">
    <div class="toolbar">
      <h2>收款主体（多主体 / 多渠道）</h2>
      <el-button type="primary" @click="openCreate">新增收款主体</el-button>
    </div>
    <p class="hint">支撑主体演进：个体 → 公司承接 → 总公司+地方子公司；订单按收款主体固化，退款原路退回。
      密钥（私钥/APIv3 key 等）<b>不在此填写、不入库</b>，由运维写入服务器环境变量（按 secret_alias）。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column label="名称" min-width="160">
        <template #default="{ row }">
          {{ row.name }}
          <el-tag v-if="row.is_default" type="success" size="small" style="margin-left:6px">默认</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="主体类型" width="110">
        <template #default="{ row }">{{ SUBJECT[row.subject_type] || row.subject_type }}</template>
      </el-table-column>
      <el-table-column label="渠道" width="110">
        <template #default="{ row }">{{ PROVIDER[row.provider] || row.provider }}</template>
      </el-table-column>
      <el-table-column label="secret_alias" width="160">
        <template #default="{ row }"><code>{{ row.secret_alias || '-' }}</code></template>
      </el-table-column>
      <el-table-column label="密钥就绪" width="100">
        <template #default="{ row }">
          <el-tag :type="row.credentials_ready ? 'success' : 'info'" size="small">
            {{ row.credentials_ready ? '已就绪' : '未配/dev' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'primary' : 'danger'" size="small">
            {{ row.is_active ? '启用' : '停用' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="280" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button v-if="!row.is_default" size="small" link type="success" @click="onSetDefault(row)">设默认</el-button>
          <el-button size="small" link :type="row.is_active ? 'danger' : 'primary'" @click="onToggle(row)">
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="editing ? '编辑收款主体' : '新增收款主体'" width="560px">
      <el-form label-width="110px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如 XX教育科技公司" /></el-form-item>
        <el-form-item label="主体类型">
          <el-select v-model="form.subject_type">
            <el-option label="个体工商户" value="individual" />
            <el-option label="公司" value="company" />
            <el-option label="子公司" value="subsidiary" />
          </el-select>
        </el-form-item>
        <el-form-item label="支付渠道">
          <el-select v-model="form.provider">
            <el-option label="微信支付" value="wechat" />
            <el-option label="支付宝" value="alipay" />
            <el-option label="苹果IAP" value="apple_iap" />
          </el-select>
        </el-form-item>
        <el-form-item label="config(JSON)">
          <el-input v-model="form.configText" type="textarea" :rows="4"
            placeholder='微信示例: {"mch_id":"...","cert_serial":"...","app_id":"..."}' />
        </el-form-item>
        <el-form-item label="secret_alias">
          <el-input v-model="form.secret_alias" placeholder="如 company_main；密钥按 PAY__<alias>__<KEY> 写入 env" />
        </el-form-item>
        <el-form-item label="关联分公司ID">
          <el-input v-model="form.branch_company_id" placeholder="子公司收款主体填；总公司/个体留空" />
        </el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.is_active" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.pa { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.hint { color: #999; font-size: 13px; margin: 0 0 16px; line-height: 1.6; }
code { background: #f2f2f2; padding: 1px 6px; border-radius: 4px; }
</style>

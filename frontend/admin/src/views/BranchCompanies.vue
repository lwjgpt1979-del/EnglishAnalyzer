<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listBranches, createBranch, updateBranch, toggleBranch,
  addBranchCity, removeBranchCity, type BranchCompanyItem,
} from '../api/admin'

const rows = ref<BranchCompanyItem[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try { rows.value = await listBranches() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

// 新建/编辑
const dialogOpen = ref(false)
const editing = ref<BranchCompanyItem | null>(null)
const form = reactive({
  name: '', contact_phone: '', commission_rate: '', legal_name: '',
  tax_number: '', bank_name: '', bank_account: '',
})
function openCreate() {
  editing.value = null
  Object.assign(form, { name: '', contact_phone: '', commission_rate: '', legal_name: '', tax_number: '', bank_name: '', bank_account: '' })
  dialogOpen.value = true
}
function openEdit(r: BranchCompanyItem) {
  editing.value = r
  Object.assign(form, {
    name: r.name, contact_phone: r.contact_phone || '',
    commission_rate: r.commission_rate != null ? String(r.commission_rate) : '',
    legal_name: r.legal_name || '', tax_number: r.tax_number || '',
    bank_name: r.bank_name || '', bank_account: '',
  })
  dialogOpen.value = true
}
async function save() {
  const body: Record<string, unknown> = {
    name: form.name, contact_phone: form.contact_phone || null,
    commission_rate: form.commission_rate ? Number(form.commission_rate) : null,
    legal_name: form.legal_name || null, tax_number: form.tax_number || null,
    bank_name: form.bank_name || null,
  }
  if (form.bank_account.trim()) body.bank_account = form.bank_account.trim()
  try {
    if (editing.value) await updateBranch(editing.value.id, body)
    else await createBranch(body)
    ElMessage.success('已保存'); dialogOpen.value = false; await load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
async function onToggle(r: BranchCompanyItem) {
  try { await toggleBranch(r.id); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

// 模板辅助（避免内联 lambda 的 any 类型推断报错）
function activeCities(r: BranchCompanyItem) { return r.cities.filter(c => !c.effective_to) }
function accountNames(r: BranchCompanyItem) { return r.payment_accounts.map(a => a.name).join('、') }

// 城市归属
const cityOpen = ref(false)
const cityBranch = ref<BranchCompanyItem | null>(null)
const newCity = ref('')
function openCities(r: BranchCompanyItem) { cityBranch.value = r; newCity.value = ''; cityOpen.value = true }
async function addCity() {
  if (!cityBranch.value || !newCity.value.trim()) return
  try {
    await addBranchCity(cityBranch.value.id, newCity.value.trim())
    newCity.value = ''
    await load()
    cityBranch.value = rows.value.find(r => r.id === cityBranch.value!.id) || cityBranch.value
  } catch (e: any) { ElMessage.error(e?.message || '添加失败') }
}
async function delCity(cityId: string) {
  try {
    await ElMessageBox.confirm('解除该城市归属？（保留历史记录）', '确认')
    await removeBranchCity(cityId)
    await load()
    if (cityBranch.value) cityBranch.value = rows.value.find(r => r.id === cityBranch.value!.id) || null
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="branch">
    <div class="toolbar">
      <h2>分公司管理（地方子公司）</h2>
      <el-button type="primary" @click="openCreate">新增分公司</el-button>
    </div>
    <p class="hint">配好分公司 + 城市归属后，到「🏦 收款主体」新增「子公司」主体并关联此分公司；
      该城市学生下单即按分公司收款，退款原路退回。银行账户加密存储、不回显。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="name" label="分公司" min-width="160">
        <template #default="{ row }">
          {{ row.name }}
          <el-tag v-if="!row.is_active" type="danger" size="small" style="margin-left:6px">停用</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="分成率" width="90">
        <template #default="{ row }">{{ row.commission_rate != null ? (row.commission_rate * 100).toFixed(1) + '%' : '-' }}</template>
      </el-table-column>
      <el-table-column label="负责城市" min-width="180">
        <template #default="{ row }">
          <el-tag v-for="c in activeCities(row)" :key="c.id" size="small" style="margin:2px">{{ c.city_code }}</el-tag>
          <span v-if="!activeCities(row).length" class="muted">未配置</span>
        </template>
      </el-table-column>
      <el-table-column label="收款主体" min-width="140">
        <template #default="{ row }">
          <span v-if="row.payment_accounts.length">{{ accountNames(row) }}</span>
          <span v-else class="muted">未关联</span>
        </template>
      </el-table-column>
      <el-table-column label="银行账户" width="90">
        <template #default="{ row }">
          <el-tag :type="row.bank_account_set ? 'success' : 'info'" size="small">{{ row.bank_account_set ? '已配置' : '未配置' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link @click="openEdit(row)">编辑</el-button>
          <el-button size="small" link type="warning" @click="openCities(row)">城市归属</el-button>
          <el-button size="small" link :type="row.is_active ? 'danger' : 'primary'" @click="onToggle(row)">
            {{ row.is_active ? '停用' : '启用' }}
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="dialogOpen" :title="editing ? '编辑分公司' : '新增分公司'" width="540px">
      <el-form label-width="110px">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="联系电话"><el-input v-model="form.contact_phone" /></el-form-item>
        <el-form-item label="分成率"><el-input v-model="form.commission_rate" placeholder="如 0.3 表示 30%" /></el-form-item>
        <el-form-item label="法人名称"><el-input v-model="form.legal_name" /></el-form-item>
        <el-form-item label="税号"><el-input v-model="form.tax_number" /></el-form-item>
        <el-form-item label="开户行"><el-input v-model="form.bank_name" /></el-form-item>
        <el-form-item label="银行账户">
          <el-input v-model="form.bank_account" :placeholder="editing?.bank_account_set ? '已配置（留空保持不变）' : '加密存储'" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="cityOpen" :title="`城市归属 — ${cityBranch?.name || ''}`" width="500px">
      <p class="hint">一个城市同一时刻只能归一家分公司。解除后保留历史（置失效日）。</p>
      <div class="city-add">
        <el-input v-model="newCity" placeholder="城市编码（如 310100 上海）" @keyup.enter="addCity" />
        <el-button type="primary" @click="addCity">添加</el-button>
      </div>
      <el-table :data="(cityBranch?.cities || []).filter(c => !c.effective_to)" size="small" style="margin-top:12px">
        <el-table-column prop="city_code" label="城市编码" />
        <el-table-column prop="effective_from" label="生效日" width="120" />
        <el-table-column label="操作" width="90">
          <template #default="{ row }"><el-button size="small" link type="danger" @click="delCity(row.id)">解除</el-button></template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<style scoped>
.branch { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.hint { color: #999; font-size: 13px; margin: 0 0 16px; line-height: 1.6; }
.muted { color: #bbb; }
.city-add { display: flex; gap: 8px; }
</style>

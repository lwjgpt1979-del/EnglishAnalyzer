<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listCoupons, createCoupon, setCouponActive, grantCoupon, type CouponItem } from '../api/admin'
import { Tickets } from '@element-plus/icons-vue'

const rows = ref<CouponItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 50
const loading = ref(false)

const SCOPE: Record<string, string> = { all: '全部', semester: '学期会员', addon: '加量包', new: '新购', renew: '续费', upgrade: '升档' }

async function load() {
  loading.value = true
  try { const r = await listCoupons({ skip: (page.value - 1) * pageSize, limit: pageSize }); rows.value = r.items; total.value = r.total }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

const dialog = ref(false)
const form = reactive({
  name: '', discount_type: 'amount', discount_value_yuan: 10, percent: 90,
  min_amount_yuan: 0, max_discount_yuan: 0, scope: 'all', per_user_limit: 1,
  valid_days: 30, with_redeem_code: true, redeem_quota: 100,
})
function openCreate() {
  Object.assign(form, {
    name: '', discount_type: 'amount', discount_value_yuan: 10, percent: 90,
    min_amount_yuan: 0, max_discount_yuan: 0, scope: 'all', per_user_limit: 1,
    valid_days: 30, with_redeem_code: true, redeem_quota: 100,
  })
  dialog.value = true
}
async function save() {
  if (!form.name.trim()) { ElMessage.warning('券名必填'); return }
  const body: Record<string, unknown> = {
    name: form.name, discount_type: form.discount_type, scope: form.scope,
    min_amount_fen: Math.round(form.min_amount_yuan * 100),
    per_user_limit: form.per_user_limit, valid_days: form.valid_days || null,
    with_redeem_code: form.with_redeem_code,
    redeem_quota: form.with_redeem_code ? (form.redeem_quota || null) : null,
  }
  if (form.discount_type === 'amount') {
    body.discount_value = Math.round(form.discount_value_yuan * 100)
  } else {
    body.discount_value = Math.round(form.percent * 100)   // 9折→9000
    if (form.max_discount_yuan > 0) body.max_discount_fen = Math.round(form.max_discount_yuan * 100)
  }
  try {
    const r = await createCoupon(body)
    dialog.value = false
    if (r.redeem_code) {
      await ElMessageBox.alert(`兑换码：${r.redeem_code}（请复制分发给用户）`, '建券成功', { confirmButtonText: '知道了' })
    } else ElMessage.success('建券成功')
    await load()
  } catch (e: any) { ElMessage.error(e?.message || '建券失败') }
}
async function toggle(r: CouponItem) {
  try { await setCouponActive(r.id, !r.is_active); await load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function grant(r: CouponItem) {
  try {
    const { value } = await ElMessageBox.prompt('输入用户ID（多个用逗号或换行分隔）', `直发「${r.name}」`, {
      inputType: 'textarea', inputPlaceholder: 'uuid1, uuid2 ...',
    })
    const ids = (value || '').split(/[\s,，]+/).map(s => s.trim()).filter(Boolean)
    if (!ids.length) return
    const res = await grantCoupon(r.id, ids)
    ElMessage.success(`已发放 ${res.granted} 张`); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '发放失败') }
}

onMounted(load)
</script>

<template>
  <div class="cp">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Tickets /></el-icon>优惠券 / 兑换码</h2>
      <div class="filters">
        <el-button type="primary" @click="openCreate">建券</el-button>
        <el-button @click="reload">刷新</el-button>
      </div>
    </div>
    <p class="hint">满减/折扣券，支持兑换码批量发放或直发指定用户；用户下单时抵扣（SP-4）。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="name" label="券名" min-width="160" show-overflow-tooltip />
      <el-table-column prop="desc" label="优惠" min-width="180" show-overflow-tooltip />
      <el-table-column label="适用" width="100">
        <template #default="{ row }"><el-tag size="small">{{ SCOPE[row.scope] || row.scope }}</el-tag></template>
      </el-table-column>
      <el-table-column label="兑换码" width="130">
        <template #default="{ row }">
          <span v-if="row.redeem_code" class="code">{{ row.redeem_code }}</span>
          <span v-else class="muted">直发</span>
        </template>
      </el-table-column>
      <el-table-column label="领取/已用" width="110">
        <template #default="{ row }">{{ row.granted }} / {{ row.used }}</template>
      </el-table-column>
      <el-table-column label="有效期至" width="120">
        <template #default="{ row }">{{ row.valid_until ? row.valid_until.slice(0, 10) : '不限' }}</template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }">
          <el-tag :type="row.is_active ? 'success' : 'info'" size="small">{{ row.is_active ? '启用' : '停用' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="180" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="grant(row)">直发</el-button>
          <el-button size="small" link @click="toggle(row)">{{ row.is_active ? '停用' : '启用' }}</el-button>
        </template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <AppDialog v-model="dialog" title="建券" width="560px">
      <el-form label-width="92px">
        <el-form-item label="券名"><el-input v-model="form.name" maxlength="100" placeholder="如：暑期满100减20" /></el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.discount_type">
            <el-radio-button label="amount">满减</el-radio-button>
            <el-radio-button label="percent">折扣</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="form.discount_type === 'amount'" label="减免金额">
          <el-input-number v-model="form.discount_value_yuan" :min="0.01" :step="1" /> 元
        </el-form-item>
        <template v-else>
          <el-form-item label="折扣">
            <el-input-number v-model="form.percent" :min="1" :max="99" /> 折（如 90 = 9折，付90%）
          </el-form-item>
          <el-form-item label="最高减">
            <el-input-number v-model="form.max_discount_yuan" :min="0" /> 元（0=不封顶）
          </el-form-item>
        </template>
        <el-form-item label="使用门槛"><el-input-number v-model="form.min_amount_yuan" :min="0" /> 元（订单满此金额可用）</el-form-item>
        <el-form-item label="适用范围">
          <el-select v-model="form.scope" style="width: 160px">
            <el-option v-for="(v, k) in SCOPE" :key="k" :label="v" :value="k" />
          </el-select>
        </el-form-item>
        <el-form-item label="每人限领"><el-input-number v-model="form.per_user_limit" :min="1" /></el-form-item>
        <el-form-item label="有效天数"><el-input-number v-model="form.valid_days" :min="0" /> 天（0=不限）</el-form-item>
        <el-form-item label="兑换码">
          <el-switch v-model="form.with_redeem_code" /> 生成兑换码（关闭则仅后台直发）
        </el-form-item>
        <el-form-item v-if="form.with_redeem_code" label="兑换总量"><el-input-number v-model="form.redeem_quota" :min="0" /> 张（0=不限）</el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="save">建券</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.cp { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.code { font-family: monospace; font-weight: 600; color: #409eff; }
.total { margin-top: 12px; text-align: right; }
</style>

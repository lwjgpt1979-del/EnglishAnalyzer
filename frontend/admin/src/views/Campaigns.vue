<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listCampaigns, createCampaign, setCampaignActive, type CampaignItem } from '../api/admin'
import { Present } from '@element-plus/icons-vue'

const rows = ref<CampaignItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const STATUS: Record<string, { label: string; type: string }> = {
  live: { label: '进行中', type: 'success' }, upcoming: { label: '未开始', type: 'warning' },
  ended: { label: '已结束', type: 'info' }, stopped: { label: '已停用', type: 'info' },
}
const LIMIT: Record<string, string> = { none: '不限', once: '每人1次', total: '总限量' }
function fmt(s: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '-' }
function price(v: number | null) { return v && v > 0 ? `¥${v}` : '—' }

async function load() {
  loading.value = true
  try { const r = await listCampaigns({ skip: (page.value - 1) * pageSize, limit: pageSize }); rows.value = r.items; total.value = r.total }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

const dialog = ref(false)
const form = reactive({
  name: '', range: [] as string[], price_basic: 0, price_pro: 0, price_promax: 0,
  limit_type: 'none', total_quota: 100, is_promotional: true,
})
function openCreate() {
  Object.assign(form, { name: '', range: [], price_basic: 0, price_pro: 0, price_promax: 0, limit_type: 'none', total_quota: 100, is_promotional: true })
  dialog.value = true
}
async function save() {
  if (!form.name.trim()) { ElMessage.warning('活动名称必填'); return }
  if (!form.range || form.range.length !== 2) { ElMessage.warning('请选择活动时间'); return }
  if (![form.price_basic, form.price_pro, form.price_promax].some(v => v > 0)) {
    ElMessage.warning('至少为一个档位设置活动价'); return
  }
  const body: Record<string, unknown> = {
    name: form.name, starts_at: form.range[0], ends_at: form.range[1],
    limit_type: form.limit_type, is_promotional: form.is_promotional,
  }
  if (form.price_basic > 0) body.price_basic = form.price_basic
  if (form.price_pro > 0) body.price_pro = form.price_pro
  if (form.price_promax > 0) body.price_promax = form.price_promax
  if (form.limit_type === 'total') body.total_quota = form.total_quota
  try {
    await createCampaign(body); ElMessage.success('已创建'); dialog.value = false; await load()
  } catch (e: any) { ElMessage.error(e?.message || '创建失败') }
}
async function toggle(r: CampaignItem) {
  try {
    if (r.is_active) await ElMessageBox.confirm(`停用「${r.name}」？进行中活动将立即恢复原价。`, '停用')
    await setCampaignActive(r.id, !r.is_active); await load()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '操作失败') }
}

onMounted(load)
</script>

<template>
  <div class="cp">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Present /></el-icon>限时活动价</h2>
      <div class="filters">
        <el-button type="primary" @click="openCreate">新建活动</el-button>
        <el-button @click="load">刷新</el-button>
      </div>
    </div>
    <p class="hint">活动期内覆盖学期会员定价，到期自动恢复（§5.7）。原价自动作为划线价展示。仅作用于学期会员购买。</p>

    <el-table :data="rows" v-loading="loading" stripe>
      <el-table-column prop="name" label="活动名称" min-width="160" show-overflow-tooltip />
      <el-table-column label="活动价(basic/pro/promax)" width="200">
        <template #default="{ row }">{{ price(row.price_basic) }} / {{ price(row.price_pro) }} / {{ price(row.price_promax) }}</template>
      </el-table-column>
      <el-table-column label="时间" width="280">
        <template #default="{ row }">{{ fmt(row.starts_at) }} ~ {{ fmt(row.ends_at) }}</template>
      </el-table-column>
      <el-table-column label="限购" width="120">
        <template #default="{ row }">{{ LIMIT[row.limit_type] || row.limit_type }}<span v-if="row.limit_type === 'total'"> {{ row.sold_count }}/{{ row.total_quota }}</span></template>
      </el-table-column>
      <el-table-column label="退款" width="80">
        <template #default="{ row }"><el-tag size="small" :type="row.is_promotional ? 'danger' : 'success'">{{ row.is_promotional ? '不可退' : '可退' }}</el-tag></template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><el-tag size="small" :type="(STATUS[row.status]?.type as any) || 'info'">{{ STATUS[row.status]?.label || row.status }}</el-tag></template>
      </el-table-column>
      <el-table-column label="操作" width="100" fixed="right">
        <template #default="{ row }"><el-button size="small" link @click="toggle(row)">{{ row.is_active ? '停用' : '启用' }}</el-button></template>
      </el-table-column>
    </el-table>
    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <el-dialog v-model="dialog" title="新建限时活动" width="540px">
      <el-form label-width="100px">
        <el-form-item label="活动名称"><el-input v-model="form.name" maxlength="100" placeholder="如：开学季特惠" /></el-form-item>
        <el-form-item label="活动时间">
          <el-date-picker v-model="form.range" type="datetimerange" value-format="YYYY-MM-DDTHH:mm:ss"
            start-placeholder="开始" end-placeholder="结束" />
        </el-form-item>
        <el-form-item label="basic 活动价"><el-input-number v-model="form.price_basic" :min="0" /> 元/学期（0=不参加）</el-form-item>
        <el-form-item label="pro 活动价"><el-input-number v-model="form.price_pro" :min="0" /> 元/学期</el-form-item>
        <el-form-item label="promax 活动价"><el-input-number v-model="form.price_promax" :min="0" /> 元/学期</el-form-item>
        <el-form-item label="限购规则">
          <el-select v-model="form.limit_type" style="width: 160px">
            <el-option label="不限" value="none" />
            <el-option label="每人限购1次" value="once" />
            <el-option label="总限量" value="total" />
          </el-select>
        </el-form-item>
        <el-form-item v-if="form.limit_type === 'total'" label="总名额"><el-input-number v-model="form.total_quota" :min="1" /> 笔</el-form-item>
        <el-form-item label="退款规则">
          <el-switch v-model="form.is_promotional" /> 活动单不支持退款（关闭则可退）
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" @click="save">创建</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.cp { padding: 16px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 12px; }
.filters { display: flex; gap: 12px; align-items: center; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.muted { color: #909399; font-size: 12px; }
.total { margin-top: 12px; text-align: right; }
</style>

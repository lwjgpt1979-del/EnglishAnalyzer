<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getInstitutionPackages, updateInstitutionPackages,
  listInstitutions, setInstitutionPackage, getInstitutionPackageUsage,
  type PackageConfig, type AdminInstitution, type PackageUsage,
} from '../api/admin'
import { OfficeBuilding } from '@element-plus/icons-vue'

// ── 档位配置 ──
const cfg = ref<PackageConfig>({ tiers: [], warn_threshold_pct: 20, reset_day: 1 })
const loading = ref(false)
const saving = ref(false)

async function loadCfg() {
  loading.value = true
  try { cfg.value = await getInstitutionPackages() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function addTier() {
  cfg.value.tiers.push({ key: '', name: '', teacher_seats: 0, paper_pool: 0, grading_pool: 0 })
}
function removeTier(i: number) { cfg.value.tiers.splice(i, 1) }
async function saveCfg() {
  if (cfg.value.tiers.some(t => !t.key.trim())) { ElMessage.warning('每个档位需填 key'); return }
  saving.value = true
  try { cfg.value = await updateInstitutionPackages(cfg.value); ElMessage.success('已保存') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
  finally { saving.value = false }
}

// ── 给机构分配套餐 ──
const institutions = ref<AdminInstitution[]>([])
const selInst = ref('')
const assignTier = ref<string>('')
const ovSeats = ref<number | null>(null)
const ovPaper = ref<number | null>(null)
const ovGrading = ref<number | null>(null)
const usage = ref<PackageUsage | null>(null)

async function loadInsts() {
  try { institutions.value = (await listInstitutions({ status: 'active' })).items } catch { /* ignore */ }
}
async function loadUsage() {
  usage.value = null
  if (!selInst.value) return
  try { usage.value = await getInstitutionPackageUsage(selInst.value) } catch { /* ignore */ }
}
function onSelInst() {
  assignTier.value = ''; ovSeats.value = null; ovPaper.value = null; ovGrading.value = null
  loadUsage()
}
async function assign() {
  if (!selInst.value) { ElMessage.warning('请选择机构'); return }
  try {
    await setInstitutionPackage(selInst.value, {
      package_tier: assignTier.value || null,
      teacher_seats_override: ovSeats.value, paper_pool_override: ovPaper.value,
      grading_pool_override: ovGrading.value,
    })
    ElMessage.success('已设置'); await loadUsage()
  } catch (e: any) { ElMessage.error(e?.message || '设置失败') }
}

onMounted(() => { loadCfg(); loadInsts() })
</script>

<template>
  <div class="pk">
    <h2><el-icon style="vertical-align:-2px;margin-right:4px"><OfficeBuilding /></el-icon>机构套餐配置</h2>

    <el-card v-loading="loading" style="margin-bottom: 16px">
      <template #header>套餐档位与配额（增删档位即时生效，不发版）</template>
      <el-table :data="cfg.tiers" size="small">
        <el-table-column label="key(英文标识)" width="150"><template #default="{ row }"><el-input v-model="row.key" placeholder="starter" /></template></el-table-column>
        <el-table-column label="名称" width="150"><template #default="{ row }"><el-input v-model="row.name" placeholder="入门包" /></template></el-table-column>
        <el-table-column label="老师席位" width="130"><template #default="{ row }"><el-input-number v-model="row.teacher_seats" :min="0" size="small" /></template></el-table-column>
        <el-table-column label="月出卷池" width="130"><template #default="{ row }"><el-input-number v-model="row.paper_pool" :min="0" size="small" /></template></el-table-column>
        <el-table-column label="月批改池" width="130"><template #default="{ row }"><el-input-number v-model="row.grading_pool" :min="0" size="small" /></template></el-table-column>
        <el-table-column label="操作" width="80"><template #default="{ $index }"><el-button size="small" link type="danger" @click="removeTier($index)">删</el-button></template></el-table-column>
      </el-table>
      <div style="margin-top:12px; display:flex; gap:12px; align-items:center">
        <el-button @click="addTier">+ 新增档位</el-button>
        <span>预警阈值 <el-input-number v-model="cfg.warn_threshold_pct" :min="0" :max="100" size="small" /> %</span>
        <span>月度重置日 <el-input-number v-model="cfg.reset_day" :min="1" :max="28" size="small" /> 号</span>
        <el-button type="primary" :loading="saving" @click="saveCfg">保存配置</el-button>
      </div>
      <p class="hint">「定制包」无需在此建档位——给机构选 custom 并只填覆盖值即可。所有数字均后台可改，代码不写死。</p>
    </el-card>

    <el-card>
      <template #header>给机构分配套餐 / 查看池用量</template>
      <div class="assign-row">
        <el-select v-model="selInst" filterable placeholder="选择机构" style="width: 260px" @change="onSelInst">
          <el-option v-for="i in institutions" :key="i.id" :label="i.name" :value="i.id" />
        </el-select>
        <el-select v-model="assignTier" placeholder="套餐档位" style="width: 160px">
          <el-option label="（取消套餐）" value="" />
          <el-option v-for="t in cfg.tiers" :key="t.key" :label="t.name || t.key" :value="t.key" />
          <el-option label="定制(custom)" value="custom" />
        </el-select>
        <span>席位覆盖<el-input-number v-model="ovSeats" :min="0" size="small" /></span>
        <span>出卷覆盖<el-input-number v-model="ovPaper" :min="0" size="small" /></span>
        <span>批改覆盖<el-input-number v-model="ovGrading" :min="0" size="small" /></span>
        <el-button type="primary" @click="assign">设置</el-button>
      </div>
      <p class="hint">覆盖值留空=随档位默认；定制包仅看覆盖值。</p>

      <div v-if="usage && usage.package_tier" class="usage">
        <el-tag>{{ usage.package_name }}{{ usage.is_custom ? '（定制）' : '' }}</el-tag>
        <div class="usage-row" v-for="b in [
          { label: '老师席位', d: usage.teacher_seats },
          { label: '月出卷池', d: usage.paper },
          { label: '月批改池', d: usage.grading },
        ]" :key="b.label">
          <span class="ul">{{ b.label }}</span>
          <el-progress :percentage="b.d && b.d.limit ? Math.min(100, Math.round(b.d.used / b.d.limit * 100)) : 0"
            :status="b.d && b.d.remaining_pct < (usage.warn_threshold_pct || 20) ? 'warning' : ''" style="width: 240px" />
          <span class="un">{{ b.d?.used }}/{{ b.d?.limit }}</span>
        </div>
        <p class="hint">每月 {{ usage.reset_day }} 号重置。机构老师出卷/批改实时扣机构池，超额拦截；剩余低于预警阈值时通知机构管理员。</p>
      </div>
      <div v-else-if="selInst" class="hint">该机构未配置套餐。</div>
    </el-card>
  </div>
</template>

<style scoped>
.pk { padding: 16px; }
.pk h2 { margin: 0 0 16px; }
.hint { color: #909399; font-size: 12px; margin-top: 10px; }
.assign-row { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.usage { margin-top: 16px; }
.usage-row { display: flex; align-items: center; gap: 12px; margin: 8px 0; }
.ul { width: 90px; font-size: 13px; color: #606266; }
.un { font-size: 13px; color: #606266; }
</style>

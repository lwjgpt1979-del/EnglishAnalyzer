<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  getEntitlements, setEntitlementOverride, clearEntitlementOverride, setEntitlementAddon,
  type EntitlementsConfig, type FeatureItem, type FeatureRule,
} from '../api/admin'
import { Lock } from '@element-plus/icons-vue'

const cfg = ref<EntitlementsConfig | null>(null)
const loading = ref(false)

// 编辑弹窗
const editVisible = ref(false)
const editing = ref<{ feature: FeatureItem; tier: string } | null>(null)
const form = ref<{ mode: string; quota_limit: number | null; quota_period: string }>(
  { mode: 'allow', quota_limit: 3, quota_period: 'month' })
const saving = ref(false)

const tiers = computed(() => cfg.value?.tiers || [])
const tierLabel: Record<string, string> = { free: '免费', basic: '基础', pro: 'Pro', promax: 'ProMax' }

function effective(f: FeatureItem, tier: string): FeatureRule {
  return f.overrides[tier] || f.defaults[tier] || { mode: 'deny', limit: null, period: null }
}
function isOverridden(f: FeatureItem, tier: string): boolean {
  return !!f.overrides[tier]
}
function ruleText(r: FeatureRule): string {
  if (r.mode === 'allow') return '开放'
  if (r.mode === 'deny') return '禁止'
  if (r.mode === 'quota') return `配额 ${r.limit ?? '-'}/${r.period === 'day' ? '日' : '月'}`
  return r.mode
}
function tagType(r: FeatureRule): string {
  return r.mode === 'allow' ? 'success' : r.mode === 'deny' ? 'info' : 'warning'
}

async function load() {
  loading.value = true
  try { cfg.value = await getEntitlements() } finally { loading.value = false }
}
function openEdit(feature: FeatureItem, tier: string) {
  editing.value = { feature, tier }
  const r = effective(feature, tier)
  form.value = { mode: r.mode, quota_limit: r.limit ?? 3, quota_period: r.period || 'month' }
  editVisible.value = true
}
async function onSave() {
  if (!editing.value) return
  saving.value = true
  try {
    cfg.value = await setEntitlementOverride({
      feature_key: editing.value.feature.key, tier: editing.value.tier,
      mode: form.value.mode,
      quota_limit: form.value.mode === 'quota' ? form.value.quota_limit : null,
      quota_period: form.value.mode === 'quota' ? form.value.quota_period : null,
    })
    ElMessage.success('已保存覆盖，立即生效')
    editVisible.value = false
  } finally { saving.value = false }
}
async function onReset() {
  if (!editing.value) return
  saving.value = true
  try {
    cfg.value = await clearEntitlementOverride(editing.value.feature.key, editing.value.tier)
    ElMessage.success('已恢复默认')
    editVisible.value = false
  } finally { saving.value = false }
}

// 加量包编辑
const addonVisible = ref(false)
const addonFeat = ref<FeatureItem | null>(null)
const addonForm = ref<{ enabled: boolean; pack_size: number; price_yuan: number }>(
  { enabled: false, pack_size: 10, price_yuan: 9.9 })
function openAddon(f: FeatureItem) {
  addonFeat.value = f
  addonForm.value = { enabled: f.addon.enabled, pack_size: f.addon.pack_size, price_yuan: f.addon.price_fen / 100 }
  addonVisible.value = true
}
async function saveAddon() {
  if (!addonFeat.value) return
  saving.value = true
  try {
    cfg.value = await setEntitlementAddon({
      feature_key: addonFeat.value.key, enabled: addonForm.value.enabled,
      pack_size: addonForm.value.pack_size, price_fen: Math.round(addonForm.value.price_yuan * 100),
    })
    ElMessage.success('加量包已保存')
    addonVisible.value = false
  } finally { saving.value = false }
}

onMounted(load)
</script>

<template>
  <div class="ent-page">
    <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Lock /></el-icon>会员权益配置</h2>
    <p class="hint">每个功能(能力键)在各档位的开放规则。点单元格可覆盖默认值（<b>加粗=已覆盖</b>），立即全端生效。</p>

    <el-table :data="cfg?.features || []" v-loading="loading" border stripe size="small">
      <el-table-column label="功能" min-width="220">
        <template #default="{ row }">
          <div class="feat">
            <span class="feat-title">{{ row.title }}</span>
            <span class="feat-key">{{ row.key }}</span>
            <el-tag v-if="row.condition" size="small" type="danger" effect="plain">需{{ row.condition === 'purchased_semester' ? '购学期' : row.condition }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column v-for="t in tiers" :key="t" :label="tierLabel[t] || t" min-width="120" align="center">
        <template #default="{ row }">
          <el-tag
            :type="tagType(effective(row, t))"
            :effect="isOverridden(row, t) ? 'dark' : 'plain'"
            class="cell-tag" @click="openEdit(row, t)"
          >{{ ruleText(effective(row, t)) }}{{ isOverridden(row, t) ? ' *' : '' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="加量包" min-width="150" align="center">
        <template #default="{ row }">
          <el-tag v-if="!row.metered" type="info" effect="plain" size="small">不适用</el-tag>
          <el-tag v-else class="cell-tag" :type="row.addon.enabled ? 'warning' : 'info'"
            :effect="row.addon.enabled ? 'dark' : 'plain'" @click="openAddon(row)">
            {{ row.addon.enabled ? `${row.addon.pack_size}次/¥${(row.addon.price_fen / 100).toFixed(1)}` : '未开启' }}
          </el-tag>
        </template>
      </el-table-column>
    </el-table>

    <AppDialog v-model="editVisible" :title="editing ? `${editing.feature.title} · ${tierLabel[editing.tier] || editing.tier}` : ''" width="420px">
      <el-form label-width="80px">
        <el-form-item label="规则">
          <el-radio-group v-model="form.mode">
            <el-radio-button label="allow">开放</el-radio-button>
            <el-radio-button label="deny">禁止</el-radio-button>
            <el-radio-button label="quota">配额</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="form.mode === 'quota'">
          <el-form-item label="次数">
            <el-input-number v-model="form.quota_limit" :min="1" :max="999" />
          </el-form-item>
          <el-form-item label="周期">
            <el-radio-group v-model="form.quota_period">
              <el-radio-button label="month">每月</el-radio-button>
              <el-radio-button label="day">每日</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="onReset" :loading="saving">恢复默认</el-button>
        <el-button type="primary" @click="onSave" :loading="saving">保存覆盖</el-button>
      </template>
    </AppDialog>

    <AppDialog v-model="addonVisible" :title="addonFeat ? `${addonFeat.title} · 加量包` : ''" width="420px">
      <p class="hint">仅当用户已是最高档({{ cfg?.top_tier || 'promax' }})、配额用尽时出现购买；余额永久、需有会员才可用。</p>
      <el-form label-width="90px">
        <el-form-item label="开启加量包"><el-switch v-model="addonForm.enabled" /></el-form-item>
        <el-form-item label="每包次数"><el-input-number v-model="addonForm.pack_size" :min="1" :max="999" /></el-form-item>
        <el-form-item label="每包价格(元)"><el-input-number v-model="addonForm.price_yuan" :min="0" :precision="1" :step="1" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button type="primary" @click="saveAddon" :loading="saving">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.ent-page { padding: 8px 4px; }
.hint { color: #888; font-size: 13px; margin: 4px 0 16px; }
.feat { display: flex; flex-direction: column; gap: 2px; }
.feat-title { font-weight: 600; }
.feat-key { color: #aaa; font-size: 12px; }
.cell-tag { cursor: pointer; }
</style>

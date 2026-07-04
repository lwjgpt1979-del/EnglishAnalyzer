<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  type CallCenterConfig, type CallCenterVendor, type CccConfig,
  cccPull, getCallCenterConfig, getCccConfig, updateCallCenterConfig, updateCccConfig,
} from '../api/sales'

const loading = ref(false)
const saving = ref(false)

// ── 通用配置(含服务商切换)──────────────────────────────────────────────
const cc = reactive<CallCenterConfig>({
  provider: 'generic', webhook_token: '', auto_transcribe: true, field_map: {}, vendors: {},
})
const presets = ref<Record<string, CallCenterVendor>>({})
// ── 阿里云 CCC 配置 ─────────────────────────────────────────────────────
const ccc = reactive<CccConfig>({
  instance_id: '', region_id: 'cn-shanghai', endpoint: 'ccc.cn-shanghai.aliyuncs.com',
  api_version: '2020-07-01', action_get_contact: '', auto_transcribe: true,
  mock_recording_url: '', field_map: {}, dev_mock: true,
})

// field_map 编辑用行结构
interface MapRow { inner: string; src: string }
const ccRows = ref<MapRow[]>([])
const cccRows = ref<MapRow[]>([])
function toRows(m: Record<string, string>): MapRow[] {
  return Object.entries(m || {}).map(([inner, src]) => ({ inner, src: String(src ?? '') }))
}
function fromRows(rows: MapRow[]): Record<string, string> {
  const m: Record<string, string> = {}
  rows.forEach(r => { if (r.inner.trim()) m[r.inner.trim()] = r.src.trim() })
  return m
}

const webhookUrl = computed(() => {
  const base = `${window.location.origin}/api/v1/admin/sales/call-center/webhook`
  return cc.webhook_token ? `${base}?token=${cc.webhook_token}` : base
})

// ── 多服务商并行(七陌 / 合力等)─────────────────────────────────────────
interface VendorEdit {
  key: string
  label: string
  enabled: boolean
  webhook_token: string
  recording_url_prefix: string
  rows: MapRow[]
}
const vendorList = ref<VendorEdit[]>([])
function toVendorList(m: Record<string, CallCenterVendor>): VendorEdit[] {
  return Object.entries(m || {}).map(([key, v]) => ({
    key, label: v.label || key, enabled: v.enabled !== false,
    webhook_token: v.webhook_token || '', recording_url_prefix: v.recording_url_prefix || '',
    rows: toRows(v.field_map || {}),
  }))
}
function vendorWebhookUrl(v: VendorEdit): string {
  const base = `${window.location.origin}/api/v1/admin/sales/call-center/webhook?vendor=${v.key}`
  return v.webhook_token ? `${base}&token=${v.webhook_token}` : base
}
function addVendorPreset(key: string) {
  if (vendorList.value.some(v => v.key === key)) { ElMessage.warning('该服务商已添加'); return }
  const p = presets.value[key]
  if (!p) return
  vendorList.value.push({
    key, label: p.label, enabled: true, webhook_token: '',
    recording_url_prefix: p.recording_url_prefix || '', rows: toRows(p.field_map || {}),
  })
}
function addVendorCustom() {
  const key = `vendor${vendorList.value.length + 1}`
  vendorList.value.push({ key, label: '自定义服务商', enabled: true, webhook_token: '', recording_url_prefix: '', rows: [] })
}
async function removeVendor(v: VendorEdit, idx: number) {
  await ElMessageBox.confirm(`删除服务商「${v.label}」的接入配置?`, '确认', { type: 'warning' })
  vendorList.value.splice(idx, 1)
  const res = await updateCallCenterConfig({ vendors: { [v.key]: null } })
  Object.assign(cc, res)
  vendorList.value = toVendorList(res.vendors)
  ElMessage.success('已删除')
}
async function saveVendors() {
  saving.value = true
  try {
    const vendors: Record<string, CallCenterVendor> = {}
    for (const v of vendorList.value) {
      if (!v.key.trim()) continue
      vendors[v.key.trim()] = {
        label: v.label, enabled: v.enabled, webhook_token: v.webhook_token,
        recording_url_prefix: v.recording_url_prefix, field_map: fromRows(v.rows),
      }
    }
    const res = await updateCallCenterConfig({ vendors })
    Object.assign(cc, res)
    vendorList.value = toVendorList(res.vendors)
    ElMessage.success('服务商配置已保存')
  } finally {
    saving.value = false
  }
}

async function load() {
  loading.value = true
  try {
    const [a, b] = await Promise.all([getCallCenterConfig(), getCccConfig()])
    Object.assign(cc, a)
    Object.assign(ccc, b)
    ccRows.value = toRows(a.field_map)
    cccRows.value = toRows(b.field_map)
    presets.value = a.presets || {}
    vendorList.value = toVendorList(a.vendors || {})
  } finally {
    loading.value = false
  }
}
onMounted(load)

async function saveProvider(p: 'generic' | 'aliyun_ccc') {
  cc.provider = p
  await updateCallCenterConfig({ provider: p })
  ElMessage.success(`已切换服务商:${p === 'generic' ? '通用推送 webhook' : '阿里云 CCC'}`)
}

async function saveGeneric() {
  saving.value = true
  try {
    const res = await updateCallCenterConfig({
      webhook_token: cc.webhook_token, auto_transcribe: cc.auto_transcribe,
      field_map: fromRows(ccRows.value),
    })
    Object.assign(cc, res)
    ccRows.value = toRows(res.field_map)
    ElMessage.success('通用 webhook 配置已保存')
  } finally {
    saving.value = false
  }
}

async function saveCcc() {
  saving.value = true
  try {
    const res = await updateCccConfig({
      instance_id: ccc.instance_id, region_id: ccc.region_id, endpoint: ccc.endpoint,
      api_version: ccc.api_version, action_get_contact: ccc.action_get_contact,
      auto_transcribe: ccc.auto_transcribe, mock_recording_url: ccc.mock_recording_url,
      field_map: fromRows(cccRows.value),
    })
    Object.assign(ccc, res)
    cccRows.value = toRows(res.field_map)
    ElMessage.success('阿里云 CCC 配置已保存')
  } finally {
    saving.value = false
  }
}

// ── CCC 联调 ────────────────────────────────────────────────────────────
const pullContactId = ref('')
const pullPhone = ref('')
const pulling = ref(false)
const pullResult = ref('')
async function doPull() {
  if (!pullContactId.value.trim()) { ElMessage.warning('填 contactId'); return }
  pulling.value = true
  pullResult.value = ''
  try {
    const res = await cccPull(pullContactId.value.trim(), pullPhone.value.trim() || undefined)
    pullResult.value = JSON.stringify(res, null, 2)
    if (res.matched) ElMessage.success('已匹配线索并落跟进' + (res.has_recording ? ',录音已触发转写分析' : ''))
    else ElMessage.warning('未匹配到线索(按电话号匹配)')
  } finally {
    pulling.value = false
  }
}

function copyText(t: string) {
  navigator.clipboard.writeText(t)
  ElMessage.success('已复制')
}
function copyWebhook() {
  copyText(webhookUrl.value)
}
</script>

<template>
  <div v-loading="loading">
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header><b>呼叫中心服务商</b></template>
      <el-radio-group :model-value="cc.provider" @update:model-value="saveProvider($event as any)">
        <el-radio-button value="generic">通用推送 webhook(天润 / 七陌 / 合力等)</el-radio-button>
        <el-radio-button value="aliyun_ccc">阿里云 CCC(拉取)</el-radio-button>
      </el-radio-group>
      <div style="color: var(--el-text-color-secondary); font-size: 13px; margin-top: 10px">
        两条线都保留:切换只决定当前生效的接入方式,配置互不覆盖。签约谁就切谁——
        推送型服务商(多数国产 CCC)用「通用 webhook」;阿里云 CCC 用「拉取」。
      </div>
    </el-card>

    <!-- 通用推送 webhook -->
    <el-card v-show="cc.provider === 'generic'" shadow="never" style="margin-bottom: 16px">
      <template #header><b>通用推送 webhook 配置</b></template>
      <el-form label-width="130px" style="max-width: 720px">
        <el-form-item label="回调地址">
          <el-input :model-value="webhookUrl" readonly>
            <template #append><el-button @click="copyWebhook">复制</el-button></template>
          </el-input>
          <div class="tip">把这个地址配到服务商后台的「通话结束回调 / 话单推送」里</div>
        </el-form-item>
        <el-form-item label="webhook token">
          <el-input v-model="cc.webhook_token" placeholder="随机长串;服务商回调需带同一 token" />
        </el-form-item>
        <el-form-item label="自动转写分析">
          <el-switch v-model="cc.auto_transcribe" />
          <span class="tip" style="margin-left: 8px">有录音自动 ASR + 意向分析</span>
        </el-form-item>
        <el-form-item label="字段映射">
          <div style="width: 100%">
            <div v-for="(r, i) in ccRows" :key="i" style="display: flex; gap: 8px; margin-bottom: 6px">
              <el-input v-model="r.inner" placeholder="内部字段" style="width: 200px" />
              <span style="line-height: 32px">←</span>
              <el-input v-model="r.src" placeholder="服务商回调字段名" style="width: 240px" />
              <el-button text type="danger" @click="ccRows.splice(i, 1)">删</el-button>
            </div>
            <el-button text type="primary" @click="ccRows.push({ inner: '', src: '' })">+ 加一行</el-button>
            <div class="tip">内部字段:lead_id / phone / recording_url / call_duration_sec / outcome / direction</div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveGeneric">保存</el-button>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">多服务商并行(七陌 / 合力等各推各的回调,互不干扰)</el-divider>
      <div style="margin-bottom: 12px; display: flex; gap: 8px">
        <el-button v-for="(p, k) in presets" :key="k" size="small" @click="addVendorPreset(k as string)">
          + {{ p.label }}模板
        </el-button>
        <el-button size="small" @click="addVendorCustom">+ 自定义服务商</el-button>
        <el-button size="small" type="primary" :loading="saving" @click="saveVendors">保存全部服务商</el-button>
      </div>
      <el-card v-for="(v, i) in vendorList" :key="v.key" shadow="never" class="vendor-card">
        <template #header>
          <div style="display: flex; align-items: center; gap: 10px">
            <el-input v-model="v.label" style="width: 160px" size="small" />
            <el-tag size="small" type="info">key: {{ v.key }}</el-tag>
            <el-switch v-model="v.enabled" size="small" active-text="启用" />
            <el-button text type="danger" size="small" style="margin-left: auto" @click="removeVendor(v, i)">删除</el-button>
          </div>
        </template>
        <el-form label-width="130px">
          <el-form-item label="回调地址">
            <el-input :model-value="vendorWebhookUrl(v)" readonly>
              <template #append><el-button @click="copyText(vendorWebhookUrl(v))">复制</el-button></template>
            </el-input>
            <div class="tip">给{{ v.label }}后台配这个地址(话单推送)</div>
          </el-form-item>
          <el-form-item label="token">
            <el-input v-model="v.webhook_token" placeholder="该服务商专属 token(空则用顶层 token)" />
          </el-form-item>
          <el-form-item label="录音 URL 前缀">
            <el-input v-model="v.recording_url_prefix" placeholder="录音字段是相对路径时拼的域名前缀,如 https://xxx.com" />
          </el-form-item>
          <el-form-item label="字段映射">
            <div style="width: 100%">
              <div v-for="(r, j) in v.rows" :key="j" style="display: flex; gap: 8px; margin-bottom: 6px">
                <el-input v-model="r.inner" placeholder="内部字段" style="width: 200px" />
                <span style="line-height: 32px">←</span>
                <el-input v-model="r.src" placeholder="话单推送字段名" style="width: 240px" />
                <el-button text type="danger" @click="v.rows.splice(j, 1)">删</el-button>
              </div>
              <el-button text type="primary" @click="v.rows.push({ inner: '', src: '' })">+ 加一行</el-button>
              <div class="tip">⚠️ 模板字段是常见形态,签约后按对方话单文档校准</div>
            </div>
          </el-form-item>
        </el-form>
      </el-card>
    </el-card>

    <!-- 阿里云 CCC -->
    <el-card v-show="cc.provider === 'aliyun_ccc'" shadow="never" style="margin-bottom: 16px">
      <template #header>
        <b>阿里云 CCC 配置</b>
        <el-tag :type="ccc.dev_mock ? 'warning' : 'success'" size="small" style="margin-left: 10px">
          {{ ccc.dev_mock ? 'dev-mock(未配 AccessKey)' : '真 API 通道' }}
        </el-tag>
      </template>
      <el-form label-width="150px" style="max-width: 720px">
        <el-form-item label="实例 ID (instanceId)">
          <el-input v-model="ccc.instance_id" placeholder="CCC 控制台创建实例后的实例名,如 enggramer" />
        </el-form-item>
        <el-form-item label="Endpoint">
          <el-input v-model="ccc.endpoint" />
        </el-form-item>
        <el-form-item label="API 版本">
          <el-input v-model="ccc.api_version" style="width: 200px" />
        </el-form-item>
        <el-form-item label="通话记录接口名">
          <el-input v-model="ccc.action_get_contact" placeholder="如 GetConversationDetailByContactId" />
          <div class="tip">⚠️ 以实例真实接口为准;AccessKey 在服务端 .env,不在此配置</div>
        </el-form-item>
        <el-form-item label="自动转写分析">
          <el-switch v-model="ccc.auto_transcribe" />
        </el-form-item>
        <el-form-item label="联调用模拟录音 URL">
          <el-input v-model="ccc.mock_recording_url" placeholder="仅 dev-mock 联调:公网录音 URL,可一路跑到真 ASR" />
        </el-form-item>
        <el-form-item label="响应字段映射">
          <div style="width: 100%">
            <div v-for="(r, i) in cccRows" :key="i" style="display: flex; gap: 8px; margin-bottom: 6px">
              <el-input v-model="r.inner" placeholder="内部字段" style="width: 200px" />
              <span style="line-height: 32px">←</span>
              <el-input v-model="r.src" placeholder="响应取值路径,如 RecordingList.0.OssLink" style="width: 280px" />
              <el-button text type="danger" @click="cccRows.splice(i, 1)">删</el-button>
            </div>
            <el-button text type="primary" @click="cccRows.push({ inner: '', src: '' })">+ 加一行</el-button>
            <div class="tip">点分路径,数字为列表下标;内部字段:phone / recording_url / call_duration_sec / outcome</div>
          </div>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :loading="saving" @click="saveCcc">保存</el-button>
        </el-form-item>
      </el-form>

      <el-divider content-position="left">联调:按 contactId 拉一条</el-divider>
      <div style="display: flex; gap: 8px; max-width: 720px">
        <el-input v-model="pullContactId" placeholder="contactId(dev-mock 下任意串)" style="width: 260px" />
        <el-input v-model="pullPhone" placeholder="客户电话(可选,精确匹配线索)" style="width: 220px" />
        <el-button type="primary" :loading="pulling" @click="doPull">拉取并落跟进</el-button>
      </div>
      <pre v-if="pullResult" class="pull-result">{{ pullResult }}</pre>
    </el-card>
  </div>
</template>

<style scoped>
.tip { color: var(--el-text-color-secondary); font-size: 12px; line-height: 1.6; }
.pull-result {
  margin-top: 12px; padding: 10px 12px; background: var(--el-fill-color-light);
  border-radius: 6px; font-size: 12px; max-width: 720px; overflow: auto;
}
.vendor-card { max-width: 760px; margin-bottom: 12px; border-color: var(--el-border-color); }
</style>

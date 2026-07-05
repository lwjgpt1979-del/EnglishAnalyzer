<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  type Campaign, type ReachFields, type Segment, type SegmentCondition,
  CHANNEL_LABEL, createCampaign, deleteSegment, getReachFields, listCampaigns,
  listSegments, resolveSegment, runCampaign, upsertSegment,
} from '../api/reach'

const fields = ref<ReachFields['fields']>({})
const segments = ref<Segment[]>([])
const campaigns = ref<Campaign[]>([])
const loading = ref(false)

async function loadAll() {
  loading.value = true
  try {
    const [f, s, c] = await Promise.all([getReachFields(), listSegments({ limit: 100 }), listCampaigns({ limit: 100 })])
    fields.value = f.fields
    segments.value = s.items
    campaigns.value = c.items
  } finally {
    loading.value = false
  }
}
onMounted(loadAll)

const fieldKeys = computed(() => Object.keys(fields.value))
function fieldLabel(k: string) { return fields.value[k]?.label || k }

// ── 规则构建器(分群编辑对话框)────────────────────────────────────────────
const segDlg = reactive({ open: false, id: '' as string | undefined, name: '', description: '' })
const conditions = ref<SegmentCondition[]>([])
const resolveCount = ref<number | null>(null)
const resolveSample = ref<string[]>([])
const resolving = ref(false)

function openSegNew() {
  segDlg.open = true; segDlg.id = undefined; segDlg.name = ''; segDlg.description = ''
  conditions.value = []; resolveCount.value = null; resolveSample.value = []
}
function openSegEdit(s: Segment) {
  segDlg.open = true; segDlg.id = s.id; segDlg.name = s.name; segDlg.description = s.description || ''
  conditions.value = (s.rule?.conditions || []).map(c => ({ ...c }))
  resolveCount.value = s.last_count; resolveSample.value = []
}
function addCondition() {
  const k = fieldKeys.value[0]
  conditions.value.push({ field: k, value: fields.value[k]?.type === 'bool' ? true : '' })
}
function onFieldChange(c: SegmentCondition) {
  const t = fields.value[c.field]?.type
  c.value = t === 'bool' ? true : t === 'enum' ? (fields.value[c.field]?.options?.[0] ?? '') : ''
}
const currentRule = computed(() => ({ conditions: conditions.value.map(c => ({ field: c.field, value: c.value })) }))

async function tryResolve() {
  resolving.value = true
  try {
    const r = await resolveSegment(currentRule.value)
    resolveCount.value = r.count
    resolveSample.value = r.sample.map(s => s.nickname || s.phone || s.id.slice(0, 8))
  } finally {
    resolving.value = false
  }
}
async function saveSegment() {
  if (!segDlg.name.trim()) { ElMessage.warning('填分群名'); return }
  await upsertSegment({ id: segDlg.id, name: segDlg.name, description: segDlg.description, rule: currentRule.value })
  ElMessage.success('分群已保存')
  segDlg.open = false
  await loadAll()
}
async function removeSegment(s: Segment) {
  await ElMessageBox.confirm(`删除分群「${s.name}」?`, '确认', { type: 'warning' })
  await deleteSegment(s.id)
  ElMessage.success('已删除')
  await loadAll()
}

// ── 触达任务对话框 ────────────────────────────────────────────────────────
const campDlg = reactive({
  open: false, name: '', source: 'segment' as 'segment' | 'inline',
  segment_id: '' as string, channel: 'sales_lead' as 'station' | 'sales_lead',
  title: '', content: '', lead_tag: '会员将到期',
})
function openCampFrom(s?: Segment) {
  campDlg.open = true; campDlg.name = ''
  campDlg.source = 'segment'; campDlg.segment_id = s?.id || (segments.value[0]?.id ?? '')
  campDlg.channel = 'sales_lead'; campDlg.title = ''; campDlg.content = ''; campDlg.lead_tag = '会员将到期'
}
async function submitCampaign() {
  if (!campDlg.name.trim()) { ElMessage.warning('填任务名'); return }
  const body: Parameters<typeof createCampaign>[0] = {
    name: campDlg.name, channel: campDlg.channel,
    segment_id: campDlg.source === 'segment' ? campDlg.segment_id : null,
    rule: campDlg.source === 'inline' ? currentRule.value : null,
    title: campDlg.channel === 'station' ? campDlg.title : null,
    content: campDlg.channel === 'station' ? campDlg.content : null,
    lead_tag: campDlg.channel === 'sales_lead' ? campDlg.lead_tag : null,
  }
  if (campDlg.source === 'segment' && !campDlg.segment_id) { ElMessage.warning('选一个分群'); return }
  if (campDlg.channel === 'station' && !campDlg.content.trim()) { ElMessage.warning('站内通知要填内容'); return }
  await createCampaign(body)
  ElMessage.success('触达任务已创建(草稿),点「执行」下发')
  campDlg.open = false
  await loadAll()
}
const running = ref('')
async function doRun(c: Campaign) {
  const tip = c.channel === 'sales_lead' ? '将把命中用户生成电销线索(已在池的跳过)' : '将向命中用户发站内通知'
  await ElMessageBox.confirm(`执行「${c.name}」?${tip}。不可撤销。`, '确认执行', { type: 'warning' })
  running.value = c.id
  try {
    const r = await runCampaign(c.id)
    ElMessage.success(`已执行:命中${r.stats?.matched} 成功${r.stats?.sent} 跳过${r.stats?.skipped}`)
    await loadAll()
  } finally {
    running.value = ''
  }
}

function ruleSummary(s: Segment) {
  const cs = s.rule?.conditions || []
  if (!cs.length) return '全体在册学生'
  return cs.map(c => `${fieldLabel(c.field)}=${c.value}`).join(' 且 ')
}
</script>

<template>
  <div v-loading="loading">
    <el-alert type="info" :closable="false" style="margin-bottom: 14px"
      title="存量召回:圈出目标用户(如会员将到期/已流失)→ 站内通知 或 一键生成电销线索(喂电销CRM,座席拨号续费)。" />

    <!-- 触达任务 -->
    <el-card shadow="never" style="margin-bottom: 16px">
      <template #header>
        <div style="display: flex; align-items: center">
          <b>触达任务</b>
          <el-button type="primary" size="small" style="margin-left: auto" @click="openCampFrom()">+ 新建触达</el-button>
        </div>
      </template>
      <el-table :data="campaigns" size="small">
        <el-table-column prop="name" label="任务" min-width="140" />
        <el-table-column label="渠道" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="row.channel === 'sales_lead' ? 'warning' : 'info'">{{ CHANNEL_LABEL[row.channel] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'done' ? 'success' : row.status === 'failed' ? 'danger' : ''">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="结果" min-width="200">
          <template #default="{ row }">
            <span v-if="row.stats">命中 {{ row.stats.matched }} · 成功 {{ row.stats.sent }} · 跳过 {{ row.stats.skipped }}<span v-if="row.stats.failed"> · 失败 {{ row.stats.failed }}</span></span>
            <span v-else style="color: var(--el-text-color-secondary)">未执行</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button v-if="row.status === 'draft'" size="small" type="primary" :loading="running === row.id" @click="doRun(row)">执行</el-button>
            <span v-else style="color: var(--el-text-color-secondary); font-size: 12px">{{ row.executed_at?.slice(0, 16).replace('T', ' ') }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 分群管理 -->
    <el-card shadow="never">
      <template #header>
        <div style="display: flex; align-items: center">
          <b>分群</b>
          <el-button type="primary" size="small" style="margin-left: auto" @click="openSegNew">+ 新建分群</el-button>
        </div>
      </template>
      <el-table :data="segments" size="small">
        <el-table-column prop="name" label="分群" width="160" />
        <el-table-column label="规则" min-width="260">
          <template #default="{ row }"><span style="font-size: 12px">{{ ruleSummary(row) }}</span></template>
        </el-table-column>
        <el-table-column label="命中(上次)" width="110">
          <template #default="{ row }">{{ row.last_count ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="200">
          <template #default="{ row }">
            <el-button size="small" @click="openCampFrom(row)">建触达</el-button>
            <el-button size="small" text @click="openSegEdit(row)">编辑</el-button>
            <el-button size="small" text type="danger" @click="removeSegment(row)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 分群编辑对话框(规则构建器)-->
    <el-dialog v-model="segDlg.open" :title="segDlg.id ? '编辑分群' : '新建分群'" width="640px">
      <el-form label-width="80px">
        <el-form-item label="分群名"><el-input v-model="segDlg.name" style="width: 300px" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="segDlg.description" style="width: 400px" /></el-form-item>
        <el-form-item label="条件">
          <div style="width: 100%">
            <div v-for="(c, i) in conditions" :key="i" style="display: flex; gap: 8px; margin-bottom: 6px; align-items: center">
              <el-select v-model="c.field" style="width: 260px" @change="onFieldChange(c)">
                <el-option v-for="k in fieldKeys" :key="k" :label="fieldLabel(k)" :value="k" />
              </el-select>
              <template v-if="fields[c.field]?.type === 'bool'">
                <el-switch v-model="c.value as boolean" />
              </template>
              <template v-else-if="fields[c.field]?.type === 'enum'">
                <el-select v-model="c.value as string" style="width: 140px">
                  <el-option v-for="o in fields[c.field]?.options" :key="o" :label="o" :value="o" />
                </el-select>
              </template>
              <template v-else>
                <el-input v-model="c.value as string" :placeholder="fields[c.field]?.type === 'int' ? '数字(天)' : '值'" style="width: 140px" />
              </template>
              <el-button text type="danger" @click="conditions.splice(i, 1)">删</el-button>
            </div>
            <el-button text type="primary" @click="addCondition">+ 加条件</el-button>
            <span style="color: var(--el-text-color-secondary); font-size: 12px; margin-left: 8px">多条件为「且」;无条件=全体在册学生</span>
          </div>
        </el-form-item>
        <el-form-item label="试算">
          <el-button size="small" :loading="resolving" @click="tryResolve">算命中人数</el-button>
          <span v-if="resolveCount !== null" style="margin-left: 12px">
            命中 <b style="color: var(--c-primary)">{{ resolveCount }}</b> 人
            <span v-if="resolveSample.length" style="color: var(--el-text-color-secondary); font-size: 12px">(如 {{ resolveSample.slice(0, 3).join('、') }}…)</span>
          </span>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="segDlg.open = false">取消</el-button>
        <el-button type="primary" @click="saveSegment">保存分群</el-button>
      </template>
    </el-dialog>

    <!-- 新建触达对话框 -->
    <el-dialog v-model="campDlg.open" title="新建触达任务" width="560px">
      <el-form label-width="90px">
        <el-form-item label="任务名"><el-input v-model="campDlg.name" style="width: 300px" placeholder="如 7月会员到期召回" /></el-form-item>
        <el-form-item label="目标人群">
          <el-select v-model="campDlg.segment_id" style="width: 300px" placeholder="选已存分群">
            <el-option v-for="s in segments" :key="s.id" :label="`${s.name}(${s.last_count ?? '?'}人)`" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="渠道">
          <el-radio-group v-model="campDlg.channel">
            <el-radio-button value="sales_lead">生成电销线索</el-radio-button>
            <el-radio-button value="station">站内通知</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <template v-if="campDlg.channel === 'station'">
          <el-form-item label="标题"><el-input v-model="campDlg.title" style="width: 300px" /></el-form-item>
          <el-form-item label="内容"><el-input v-model="campDlg.content" type="textarea" :rows="3" style="width: 380px" /></el-form-item>
        </template>
        <template v-else>
          <el-form-item label="线索标签"><el-input v-model="campDlg.lead_tag" style="width: 200px" /></el-form-item>
          <el-form-item label=" ">
            <span style="color: var(--el-text-color-secondary); font-size: 12px">命中用户(有手机号、未在线索池)将生成电销线索,进「电销线索」页,座席可拨。</span>
          </el-form-item>
        </template>
      </el-form>
      <template #footer>
        <el-button @click="campDlg.open = false">取消</el-button>
        <el-button type="primary" @click="submitCampaign">创建(草稿)</el-button>
      </template>
    </el-dialog>
  </div>
</template>

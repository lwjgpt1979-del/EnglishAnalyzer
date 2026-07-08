<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Phone, Plus, Upload, Refresh, RefreshRight } from '@element-plus/icons-vue'
import { listRegions } from '../api/admin'
import {
  listLeads, createLead, importLeads, updateLead, claimLead, releaseLead,
  listActivities, addActivity, recommendLeads, salesBoard, recyclePublicPool,
  analyzeText, leadWecomMessages, listSeats, batchAssign,
  sourceStats, findDuplicates, mergeLeads, importExcel,
  exportLeads, getSalesConfig, updateSalesConfig, getScripts, setScripts,
  autoAssign, leaderboard, leadAudit, AUDIT_ACTION,
  LEAD_STATUS, LEAD_SOURCE, type SalesLead, type SalesActivity, type LeadListParams,
  type IntentAnalysis, type WecomMsg, type SalesBoard, type Seat,
  type SourceStat, type DupGroup, type SalesConfig, type Script,
  type SeatRank, type AuditRow,
} from '../api/sales'

const STATUS_TAG: Record<string, string> = {
  new: 'info', contacted: '', interested: 'warning',
  negotiating: 'warning', won: 'success', lost: 'danger', invalid: 'info',
}
const GRADE_TAG: Record<string, string> = { A: 'danger', B: 'warning', C: '', D: 'info' }
function fmt(s?: string | null) { return s ? s.replace('T', ' ').slice(0, 16) : '—' }

// ── 列表 ──────────────────────────────────────────────────────────────────────
const view = ref<'public' | 'mine' | 'due' | 'sla' | 'recommend'>('public')
const now = ref(Date.now())
function isOverdue(s?: string | null) { return !!s && new Date(s).getTime() <= now.value }
const rows = ref<SalesLead[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const fStatus = ref('')
const fSource = ref('')
const fTag = ref('')
const fPhone = ref<'' | 'yes' | 'no'>('')   // 电话:全部/有/无
const fQ = ref('')
const phoneParam = () => (fPhone.value === 'yes' ? true : fPhone.value === 'no' ? false : undefined)
const cfg = ref<SalesConfig>({ public_pool_recycle_days: 7, sla_overdue_hours: 48, seat_only_admin_ids: [], tag_catalog: [] })
async function loadCfg() { try { cfg.value = await getSalesConfig() } catch { /* ignore */ } }
const board = ref<SalesBoard>({ total: 0, by_status: {}, by_pool: {}, today_new: 0, today_calls: 0, today_connected: 0, connect_rate: 0, my_due: 0 })

// 地区级联(省→市),code 与 user.city_code 同源
const regionPath = ref<string[]>([])
const regionProps = {
  lazy: true,
  async lazyLoad(node: any, resolve: (n: any[]) => void) {
    try {
      const rs = await listRegions(node.value || undefined)
      const capCity = node.level >= 1
      resolve(rs.map(r => ({ value: r.code, label: r.name, leaf: capCity || r.leaf })))
    } catch { resolve([]) }
  },
}
function regionCode(path: string[]) { return path.length ? path[path.length - 1] : undefined }

async function load() {
  loading.value = true
  try {
    const skip = (page.value - 1) * pageSize
    if (view.value === 'recommend') {
      const r = await recommendLeads({ skip, limit: pageSize })
      rows.value = r.items; total.value = r.total
    } else {
      const params: LeadListParams = {
        status: fStatus.value || undefined, source: fSource.value || undefined, has_phone: phoneParam(),
        tag: fTag.value || undefined,
        region_code: regionCode(regionPath.value), q: fQ.value || undefined,
        skip, limit: pageSize,
      }
      if (view.value === 'public') params.pool = 'public'
      if (view.value === 'mine') params.mine = true
      if (view.value === 'due') { params.mine = true; params.due = true }
      if (view.value === 'sla') params.sla = true
      const r = await listLeads(params)
      rows.value = r.items; total.value = r.total
    }
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }
async function loadBoard() { try { board.value = await salesBoard(); now.value = Date.now() } catch { /* ignore */ } }

// 导出当前筛选
async function onExport() {
  try {
    const params: LeadListParams = {
      status: fStatus.value || undefined, source: fSource.value || undefined, has_phone: phoneParam(),
      tag: fTag.value || undefined, region_code: regionCode(regionPath.value), q: fQ.value || undefined,
    }
    if (view.value === 'public') params.pool = 'public'
    if (view.value === 'mine') params.mine = true
    if (view.value === 'due') { params.mine = true; params.due = true }
    if (view.value === 'sla') params.sla = true
    const blob = await exportLeads(params)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'sales_leads.xlsx'; a.click()
    URL.revokeObjectURL(url); ElMessage.success('已导出')
  } catch (e: any) { ElMessage.error(e?.message || '导出失败') }
}

// 话术库 / SOP
const scripts = ref<Script[]>([])
const scriptMgrDlg = ref(false)
async function loadScripts() { try { scripts.value = await getScripts() } catch { /* ignore */ } }
function relevantScripts() {
  const st = cur.value?.status
  return scripts.value.filter(s => !s.stage || s.stage === st)
}
function useScript(s: Script) { actForm.content = s.content; ElMessage.success('已填入跟进内容') }
async function saveScripts() {
  try { scripts.value = await setScripts(scripts.value.filter(s => s.title.trim())); scriptMgrDlg.value = false; ElMessage.success('已保存话术库') }
  catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
function addScript() { scripts.value.push({ title: '', content: '', stage: null }) }
function delScript(i: number) { scripts.value.splice(i, 1) }

// 设置(座席权限 / 回收 / SLA)
const cfgDlg = ref(false)
const cfgSeats = ref<Seat[]>([])
async function openCfg() {
  await loadCfg()
  if (!cfgSeats.value.length) { try { cfgSeats.value = await listSeats() } catch { /* ignore */ } }
  cfgDlg.value = true
}
async function saveCfg() {
  try {
    cfg.value = await updateSalesConfig({
      public_pool_recycle_days: cfg.value.public_pool_recycle_days,
      sla_overdue_hours: cfg.value.sla_overdue_hours,
      seat_only_admin_ids: cfg.value.seat_only_admin_ids,
    })
    cfgDlg.value = false; ElMessage.success('已保存设置'); load(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

// 批量派单 / 认领
const tableRef = ref()
const selected = ref<SalesLead[]>([])
function onSelectionChange(rows: SalesLead[]) { selected.value = rows }
const seats = ref<Seat[]>([])
const assignDlg = ref(false)
const assignSeat = ref('')
async function openAssign() {
  if (!selected.value.length) { ElMessage.warning('请先勾选线索'); return }
  if (!seats.value.length) { try { seats.value = await listSeats() } catch { /* ignore */ } }
  assignSeat.value = ''; assignDlg.value = true
}
async function doAssign() {
  if (!assignSeat.value) { ElMessage.warning('请选择座席'); return }
  try {
    const r = await batchAssign(selected.value.map(l => l.id), assignSeat.value)
    ElMessage.success(`已派单 ${r.assigned} 条`)
    assignDlg.value = false; tableRef.value?.clearSelection(); load(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '派单失败') }
}
async function batchClaim() {
  if (!selected.value.length) { ElMessage.warning('请先勾选线索'); return }
  try {
    const r = await batchAssign(selected.value.map(l => l.id))
    ElMessage.success(`已认领 ${r.assigned} 条到我的私海`)
    tableRef.value?.clearSelection(); load(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '认领失败') }
}

// 自动分配(公海轮询派给座席)
const autoDlg = ref(false)
const autoSeats = ref<string[]>([])
const autoCount = ref(50)
async function openAuto() {
  if (!seats.value.length) { try { seats.value = await listSeats() } catch { /* ignore */ } }
  autoSeats.value = []; autoCount.value = 50; autoDlg.value = true
}
async function doAuto() {
  if (!autoSeats.value.length) { ElMessage.warning('请选择至少一个座席'); return }
  try {
    const r = await autoAssign(autoSeats.value, autoCount.value, regionCode(regionPath.value))
    ElMessage.success(`已自动分配 ${r.assigned} 条(排除禁呼)`)
    autoDlg.value = false; load(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '自动分配失败') }
}

// 座席业绩排行
const rankDlg = ref(false)
const rankDays = ref(7)
const ranks = ref<SeatRank[]>([])
async function openRank() {
  try { ranks.value = await leaderboard(rankDays.value); rankDlg.value = true }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
}
async function reloadRank() { try { ranks.value = await leaderboard(rankDays.value) } catch { /* ignore */ } }

// 操作审计(线索详情里)
const auditRows = ref<AuditRow[]>([])
async function loadAudit(id: string) { try { auditRows.value = (await leadAudit(id, { limit: 50 })).items } catch { auditRows.value = [] } }
function switchView(v: 'public' | 'mine' | 'due' | 'sla' | 'recommend') { view.value = v; reload() }
function viewSla() { view.value = 'sla'; reload() }

// 来源统计
const srcDlg = ref(false)
const srcStats = ref<SourceStat[]>([])
async function openSourceStats() {
  try { srcStats.value = await sourceStats(); srcDlg.value = true }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
}

// 查重合并
const dupDlg = ref(false)
const dupGroups = ref<DupGroup[]>([])
const dupLoading = ref(false)
async function openDup() {
  dupDlg.value = true; dupLoading.value = true
  try { dupGroups.value = await findDuplicates() }
  catch (e: any) { ElMessage.error(e?.message || '查重失败') }
  finally { dupLoading.value = false }
}
async function doMerge(g: DupGroup, survivorId: string) {
  const dupIds = g.leads.map(l => l.id).filter(id => id !== survivorId)
  try {
    await ElMessageBox.confirm(`把其余 ${dupIds.length} 条合并到选中主线索?跟进/企微记录会迁移,重复线索删除。`, '合并', { type: 'warning' })
    const r = await mergeLeads(survivorId, dupIds)
    ElMessage.success(`已合并 ${r.merged} 条(迁移跟进 ${r.moved_activities}、企微 ${r.moved_wecom})`)
    dupGroups.value = await findDuplicates(); load(); loadBoard()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '合并失败') }
}

// Excel 导入
const impFile = ref<File | null>(null)
function onExcelPick(e: Event) { impFile.value = (e.target as HTMLInputElement).files?.[0] || null }
async function saveExcel() {
  if (!impFile.value) { ElMessage.warning('请选择 .xlsx 文件'); return }
  try {
    const r = await importExcel(impFile.value, impSource.value)
    ElMessage.success(`导入完成:新增 ${r.created}、跳过重复 ${r.skipped}`)
    impDlg.value = false; impFile.value = null; reload(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '导入失败') }
}

async function onClaim(r: SalesLead) {
  try { await claimLead(r.id); ElMessage.success('已认领进私海'); load() }
  catch (e: any) { ElMessage.error(e?.message || '认领失败') }
}
async function onRelease(r: SalesLead) {
  try { await releaseLead(r.id); ElMessage.success('已退回公海'); load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function toggleDnc(r: SalesLead) {
  try { await updateLead(r.id, { dnc: !r.dnc }); ElMessage.success(r.dnc ? '已移出拒接' : '已加入拒接(禁呼)'); load() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}
async function onRecycle() {
  try {
    await ElMessageBox.confirm('把超期未跟进的私海线索回收到公海?', '公海回收', { type: 'warning' })
    const r = await recyclePublicPool()
    ElMessage.success(`已回收 ${r.recycled} 条`); load(); loadBoard()
  } catch (e: any) { if (e !== 'cancel') ElMessage.error(e?.message || '回收失败') }
}

// ── 新增线索 ──────────────────────────────────────────────────────────────────
const addDlg = ref(false)
const addForm = reactive({ name: '', contact_name: '', phone: '', wechat_id: '', industry: '', source: 'manual', source_note: '', consent: false, dnc: false })
const addRegion = ref<string[]>([])
function openAdd() {
  Object.assign(addForm, { name: '', contact_name: '', phone: '', wechat_id: '', industry: '', source: 'manual', source_note: '', consent: false, dnc: false })
  addRegion.value = []
  addDlg.value = true
}
async function saveAdd() {
  if (!addForm.name.trim()) { ElMessage.warning('商家名必填'); return }
  try {
    await createLead({ ...addForm, region_code: regionCode(addRegion.value) })
    ElMessage.success('已录入'); addDlg.value = false; reload(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '录入失败') }
}

// ── 批量导入(粘贴:名称,电话,城市,行业)────────────────────────────────────
const impDlg = ref(false)
const impText = ref('')
const impSource = ref('import')
function openImport() { impText.value = ''; impSource.value = 'import'; impDlg.value = true }
async function saveImport() {
  const items = impText.value.split('\n').map(l => l.trim()).filter(Boolean).map(l => {
    const [name, phone, city, industry] = l.split(/[,，\t]/).map(s => (s || '').trim())
    return { name, phone: phone || undefined, region_name: city || undefined, industry: industry || undefined }
  }).filter(it => it.name)
  if (!items.length) { ElMessage.warning('请粘贴线索(每行:名称,电话,城市,行业)'); return }
  try {
    const r = await importLeads(items, impSource.value)
    ElMessage.success(`导入完成:新增 ${r.created}、跳过重复 ${r.skipped}`)
    impDlg.value = false; reload(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '导入失败') }
}

// ── 详情抽屉 + 跟进 ────────────────────────────────────────────────────────────
const drawer = ref(false)
const cur = ref<SalesLead | null>(null)
const acts = ref<SalesActivity[]>([])
const actsLoading = ref(false)
const actForm = reactive({ channel: 'call', outcome: '', content: '', next_follow_at: '', status: '' })
const wecomMsgs = ref<WecomMsg[]>([])
// 合规编辑(consent / dnc / source_note)+ 标签
const curConsent = ref(false)
const curDnc = ref(false)
const curSourceNote = ref('')
const curTags = ref<string[]>([])
async function openDetail(r: SalesLead) {
  cur.value = r; drawer.value = true
  Object.assign(actForm, { channel: 'call', outcome: '', content: '', next_follow_at: '', status: '' })
  anaText.value = ''; anaResult.value = null
  curConsent.value = r.consent; curDnc.value = r.dnc; curSourceNote.value = r.source_note || ''
  curTags.value = Array.isArray(r.tags) ? [...r.tags] : []
  await loadActs()
  try { wecomMsgs.value = (await leadWecomMessages(r.id, { limit: 50 })).items } catch { wecomMsgs.value = [] }
  await loadAudit(r.id)
}
async function saveTags() {
  if (!cur.value) return
  try { const u = await updateLead(cur.value.id, { tags: curTags.value }); cur.value = u; load() }
  catch (e: any) { ElMessage.error(e?.message || '更新失败') }
}
async function saveCompliance() {
  if (!cur.value) return
  try {
    const u = await updateLead(cur.value.id, { consent: curConsent.value, dnc: curDnc.value, source_note: curSourceNote.value })
    cur.value = u; ElMessage.success('已更新合规信息'); load()
  } catch (e: any) { ElMessage.error(e?.message || '更新失败') }
}
async function loadActs() {
  if (!cur.value) return
  actsLoading.value = true
  try { acts.value = (await listActivities(cur.value.id, { limit: 100 })).items }
  finally { actsLoading.value = false }
}
async function saveAct() {
  if (!cur.value) return
  try {
    await addActivity(cur.value.id, {
      channel: actForm.channel, outcome: actForm.outcome || undefined,
      content: actForm.content || undefined, next_follow_at: actForm.next_follow_at || undefined,
      status: actForm.status || undefined,
    })
    ElMessage.success('已记录跟进')
    Object.assign(actForm, { outcome: '', content: '', next_follow_at: '', status: '' })
    await loadActs(); load(); loadBoard()
  } catch (e: any) { ElMessage.error(e?.message || '记录失败') }
}
async function setStatus(status: string) {
  if (!cur.value) return
  try { const u = await updateLead(cur.value.id, { status }); cur.value = u; ElMessage.success('状态已更新'); load(); loadBoard() }
  catch (e: any) { ElMessage.error(e?.message || '更新失败') }
}

// 意向分析(P1 试跑):粘贴通话/会话转写 → LLM 打分 + 抽产品意见
const anaText = ref('')
const anaResult = ref<IntentAnalysis | null>(null)
const anaLoading = ref(false)
async function runAnalyze() {
  if (!anaText.value.trim()) { ElMessage.warning('请粘贴通话/会话转写'); return }
  anaLoading.value = true
  try { anaResult.value = await analyzeText(anaText.value) }
  catch (e: any) { ElMessage.error(e?.message || '分析失败') }
  finally { anaLoading.value = false }
}

onMounted(() => { load(); loadBoard(); loadCfg(); loadScripts() })
</script>

<template>
  <div class="sales">
    <div class="toolbar">
      <h2><el-icon style="vertical-align:-2px;margin-right:4px"><Phone /></el-icon>电销线索</h2>
      <div class="stat">
        共 {{ board.total }} · 公海 {{ board.by_pool.public || 0 }} / 私海 {{ board.by_pool.private || 0 }}
        · 成交 {{ board.by_status.won || 0 }} · 谈单 {{ board.by_status.negotiating || 0 }}
        <span class="stat-sep">|</span>
        今日新增 {{ board.today_new }} · 拨打 {{ board.today_calls }} · 接通率 {{ (board.connect_rate * 100).toFixed(0) }}%
      </div>
      <div style="flex:1" />
      <template v-if="selected.length">
        <el-button type="warning" plain @click="openAssign">派单({{ selected.length }})</el-button>
        <el-button type="success" plain @click="batchClaim">认领({{ selected.length }})</el-button>
      </template>
      <el-button type="primary" :icon="Plus" @click="openAdd">新增</el-button>
      <el-button :icon="Upload" @click="openImport">批量导入</el-button>
      <el-button @click="onExport">导出</el-button>
      <el-button @click="openSourceStats">来源统计</el-button>
      <el-button @click="openDup">查重</el-button>
      <el-button @click="openAuto">自动派单</el-button>
      <el-button @click="openRank">业绩排行</el-button>
      <el-button @click="scriptMgrDlg = true">话术库</el-button>
      <el-button :icon="RefreshRight" @click="onRecycle">公海回收</el-button>
      <el-button @click="openCfg">设置</el-button>
      <el-button :icon="Refresh" @click="() => { load(); loadBoard() }">刷新</el-button>
    </div>

    <el-alert v-if="board.sla_breach" type="error" show-icon :closable="false" style="margin-bottom:12px">
      <template #title>
        有 {{ board.sla_breach }} 条线索跟进已超时超过 {{ board.sla_overdue_hours }} 小时(SLA 违约)。
        <el-button link type="primary" @click="viewSla">立即查看</el-button>
      </template>
    </el-alert>

    <div class="tabs">
      <el-radio-group :model-value="view" @change="(v: any) => switchView(v)">
        <el-radio-button label="public">公海</el-radio-button>
        <el-radio-button label="mine">我的私海</el-radio-button>
        <el-radio-button label="due">
          <el-badge :value="board.my_due" :hidden="!board.my_due" :max="99" type="danger">今日待办</el-badge>
        </el-radio-button>
        <el-radio-button label="sla">
          <el-badge :value="board.sla_breach" :hidden="!board.sla_breach" :max="99" type="danger">SLA 违约</el-badge>
        </el-radio-button>
        <el-radio-button label="recommend">今日推荐(赢单反查)</el-radio-button>
      </el-radio-group>
      <template v-if="view !== 'recommend'">
        <el-select v-model="fStatus" placeholder="状态" clearable style="width:120px" @change="reload">
          <el-option v-for="(v, k) in LEAD_STATUS" :key="k" :label="v" :value="k" />
        </el-select>
        <el-select v-model="fSource" placeholder="来源" clearable style="width:120px" @change="reload">
          <el-option v-for="(v, k) in LEAD_SOURCE" :key="k" :label="v" :value="k" />
        </el-select>
        <el-select v-model="fTag" placeholder="标签" clearable style="width:120px" @change="reload">
          <el-option v-for="t in cfg.tag_catalog" :key="t" :label="t" :value="t" />
        </el-select>
        <el-select v-model="fPhone" placeholder="电话" clearable style="width:110px" @change="reload">
          <el-option label="有电话" value="yes" />
          <el-option label="无电话(待补号)" value="no" />
        </el-select>
        <el-cascader v-model="regionPath" :props="regionProps" placeholder="地区" clearable
          style="width:180px" @change="reload" />
        <el-input v-model="fQ" placeholder="搜商家/电话/联系人" clearable style="width:180px"
          @keyup.enter="reload" @clear="reload" />
      </template>
      <span v-else class="hint">按「成交客户画像(行业/地区/经营特征)」给公海新线索打分排序,分越高越像你的赢单客户。</span>
    </div>

    <el-table ref="tableRef" :data="rows" v-loading="loading" stripe
      :row-class-name="({ row }) => row.dnc ? 'dnc-row' : ''" @selection-change="onSelectionChange">
      <el-table-column type="selection" width="42" />
      <el-table-column label="商家 / 联系人" min-width="200">
        <template #default="{ row }">
          <div>{{ row.name }}</div>
          <div class="muted">{{ row.contact_name || '' }}</div>
          <div v-if="Array.isArray(row.tags) && row.tags.length" style="margin-top:2px">
            <el-tag v-for="t in row.tags" :key="t" size="small" effect="plain" style="margin-right:4px">{{ t }}</el-tag>
          </div>
        </template>
      </el-table-column>
      <el-table-column prop="phone" label="电话" width="130" />
      <el-table-column label="地区" width="110"><template #default="{ row }">{{ row.region_name || '—' }}</template></el-table-column>
      <el-table-column prop="industry" label="行业" width="110" />
      <el-table-column label="来源" width="90">
        <template #default="{ row }">
          <el-tooltip :content="row.source_note || '无来源依据说明'" placement="top">
            <el-tag size="small" effect="plain" :type="row.source_note ? 'success' : 'info'">{{ LEAD_SOURCE[row.source] || row.source }}</el-tag>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="合规" width="110">
        <template #default="{ row }">
          <el-tag :type="row.consent ? 'success' : 'info'" size="small" effect="plain">{{ row.consent ? '已同意' : '未同意' }}</el-tag>
          <el-tag v-if="row.dnc" type="danger" size="small" effect="dark" style="margin-left:4px">禁呼</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90">
        <template #default="{ row }"><el-tag size="small" :type="(STATUS_TAG[row.status] as any)">{{ LEAD_STATUS[row.status] || row.status }}</el-tag></template>
      </el-table-column>
      <el-table-column label="意向" width="90">
        <template #default="{ row }">
          <el-tag v-if="row.intent_grade" size="small" :type="(GRADE_TAG[row.intent_grade] as any)">{{ row.intent_grade }}{{ row.intent_score != null ? ` ${row.intent_score}` : '' }}</el-tag>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column v-if="view === 'recommend'" label="相似分" width="80">
        <template #default="{ row }">{{ row.similar_score != null ? row.similar_score.toFixed(1) : '—' }}</template>
      </el-table-column>
      <el-table-column label="下次跟进" width="140">
        <template #default="{ row }">
          <span :class="{ overdue: isOverdue(row.next_follow_at) }">{{ fmt(row.next_follow_at) }}</span>
          <el-tag v-if="isOverdue(row.next_follow_at)" type="danger" size="small" effect="dark" style="margin-left:4px">到期</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" link type="primary" @click="openDetail(row)">详情</el-button>
          <el-button v-if="row.pool === 'public'" size="small" link type="success" @click="onClaim(row)">认领</el-button>
          <el-button v-else size="small" link @click="onRelease(row)">退回</el-button>
          <el-button size="small" link :type="row.dnc ? 'info' : 'danger'" @click="toggleDnc(row)">{{ row.dnc ? '解除禁呼' : '禁呼' }}</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <!-- 新增 -->
    <AppDialog v-model="addDlg" title="新增线索" width="520px">
      <el-form label-width="80px">
        <el-form-item label="商家名"><el-input v-model="addForm.name" maxlength="200" /></el-form-item>
        <el-form-item label="联系人"><el-input v-model="addForm.contact_name" /></el-form-item>
        <el-form-item label="电话"><el-input v-model="addForm.phone" /></el-form-item>
        <el-form-item label="微信/企微"><el-input v-model="addForm.wechat_id" /></el-form-item>
        <el-form-item label="地区"><el-cascader v-model="addRegion" :props="regionProps" clearable style="width:100%" /></el-form-item>
        <el-form-item label="行业"><el-input v-model="addForm.industry" /></el-form-item>
        <el-form-item label="来源">
          <el-select v-model="addForm.source"><el-option v-for="(v, k) in LEAD_SOURCE" :key="k" :label="v" :value="k" /></el-select>
        </el-form-item>
        <el-form-item label="来源说明"><el-input v-model="addForm.source_note" placeholder="合规:线索来源与合法性依据" /></el-form-item>
        <el-form-item label="标记">
          <el-checkbox v-model="addForm.consent">已同意营销联系</el-checkbox>
          <el-checkbox v-model="addForm.dnc">拒接(禁呼)</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="addDlg = false">取消</el-button><el-button type="primary" @click="saveAdd">保存</el-button></template>
    </AppDialog>

    <!-- 导入 -->
    <AppDialog v-model="impDlg" title="批量导入线索" width="560px">
      <el-tabs>
        <el-tab-pane label="粘贴文本">
          <p class="hint">每行一条,逗号/Tab 分隔:<b>名称,电话,城市,行业</b>。城市走 region 匹配,按 phone 去重。</p>
          <el-input v-model="impText" type="textarea" :rows="9" placeholder="示例:新东方常州校区,13800001111,常州市,教育培训" />
          <div style="margin-top:12px"><el-button type="primary" @click="saveImport">导入文本</el-button></div>
        </el-tab-pane>
        <el-tab-pane label="Excel 文件">
          <p class="hint">上传 <b>.xlsx</b>,首行表头含 名称/电话/城市/行业/来源说明(列名可容忍),按 phone 去重。</p>
          <input type="file" accept=".xlsx" @change="onExcelPick" />
          <div style="margin-top:12px"><el-button type="primary" :disabled="!impFile" @click="saveExcel">导入 Excel</el-button></div>
        </el-tab-pane>
      </el-tabs>
      <el-form-item label="来源" style="margin-top:8px">
        <el-select v-model="impSource" style="width:160px"><el-option v-for="(v, k) in LEAD_SOURCE" :key="k" :label="v" :value="k" /></el-select>
      </el-form-item>
    </AppDialog>

    <!-- 来源统计 -->
    <AppDialog v-model="srcDlg" title="线索来源统计" width="480px">
      <el-table :data="srcStats" border size="small">
        <el-table-column label="来源"><template #default="{ row }">{{ LEAD_SOURCE[row.source] || row.source }}</template></el-table-column>
        <el-table-column prop="total" label="线索数" width="90" align="center" />
        <el-table-column prop="won" label="成交" width="80" align="center" />
        <el-table-column label="转化率" width="100" align="center"><template #default="{ row }">{{ (row.conversion * 100).toFixed(1) }}%</template></el-table-column>
      </el-table>
    </AppDialog>

    <!-- 查重合并 -->
    <AppDialog v-model="dupDlg" title="重复线索查重合并(按电话)" width="640px">
      <div v-loading="dupLoading">
        <el-empty v-if="!dupGroups.length && !dupLoading" description="没有重复线索" :image-size="70" />
        <div v-for="g in dupGroups" :key="g.phone" class="dup-group">
          <div class="dup-phone">电话 {{ g.phone }} · {{ g.leads.length }} 条</div>
          <div v-for="l in g.leads" :key="l.id" class="dup-lead">
            <span>{{ l.name }} <span class="muted">{{ l.region_name || '' }} · {{ LEAD_STATUS[l.status] || l.status }} · {{ (l.created_at || '').slice(0,10) }}</span></span>
            <el-button size="small" type="primary" plain @click="doMerge(g, l.id)">以此为主合并</el-button>
          </div>
        </div>
      </div>
    </AppDialog>

    <!-- 设置(座席权限 / 回收 / SLA)-->
    <AppDialog v-model="cfgDlg" title="电销 CRM 设置" width="520px">
      <el-form label-width="140px">
        <el-form-item label="公海回收天数"><el-input-number v-model="cfg.public_pool_recycle_days" :min="1" /> 天未跟进回收</el-form-item>
        <el-form-item label="SLA 超时告警"><el-input-number v-model="cfg.sla_overdue_hours" :min="1" /> 小时</el-form-item>
        <el-form-item label="座席(只看自己线索)">
          <el-select v-model="cfg.seat_only_admin_ids" multiple filterable placeholder="选座席;名单内只看公海+自己私海,名单外看全部" style="width:100%">
            <el-option v-for="s in cfgSeats" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer><el-button @click="cfgDlg = false">取消</el-button><el-button type="primary" @click="saveCfg">保存</el-button></template>
    </AppDialog>

    <!-- 话术库 / SOP -->
    <AppDialog v-model="scriptMgrDlg" title="话术库 / 跟进 SOP" width="640px">
      <p class="hint">按阶段配话术;跟进时在对应状态的线索里一键填入。stage 留空=通用。</p>
      <div v-for="(s, i) in scripts" :key="i" class="script-row">
        <el-input v-model="s.title" placeholder="标题" style="width:150px" />
        <el-select v-model="s.stage" placeholder="阶段" clearable style="width:110px">
          <el-option v-for="(v, k) in LEAD_STATUS" :key="k" :label="v" :value="k" />
        </el-select>
        <el-input v-model="s.content" placeholder="话术内容" style="flex:1" />
        <el-button size="small" type="danger" plain @click="delScript(i)">删</el-button>
      </div>
      <el-button size="small" @click="addScript" style="margin-top:8px">+ 加一条</el-button>
      <template #footer><el-button @click="scriptMgrDlg = false">取消</el-button><el-button type="primary" @click="saveScripts">保存</el-button></template>
    </AppDialog>

    <!-- 自动派单 -->
    <AppDialog v-model="autoDlg" title="自动分配公海线索" width="480px">
      <p class="hint">把公海线索(排除禁呼/DNC,可按地区)按数量轮询平均派给选定座席。</p>
      <el-form label-width="80px">
        <el-form-item label="座席">
          <el-select v-model="autoSeats" multiple filterable placeholder="选座席(轮询分配)" style="width:100%">
            <el-option v-for="s in seats" :key="s.id" :label="s.name" :value="s.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="地区"><el-cascader v-model="regionPath" :props="regionProps" clearable placeholder="不选=全部公海" style="width:100%" /></el-form-item>
        <el-form-item label="分配数量"><el-input-number v-model="autoCount" :min="1" :max="5000" /> 条(取最早跟进/最新的公海线索)</el-form-item>
      </el-form>
      <template #footer><el-button @click="autoDlg = false">取消</el-button><el-button type="primary" @click="doAuto">自动分配</el-button></template>
    </AppDialog>

    <!-- 座席业绩排行 -->
    <AppDialog v-model="rankDlg" title="座席业绩排行" width="720px">
      <div style="margin-bottom:10px">
        统计周期
        <el-select v-model="rankDays" style="width:120px" @change="reloadRank">
          <el-option :label="'近 7 天'" :value="7" /><el-option :label="'近 30 天'" :value="30" /><el-option :label="'近 90 天'" :value="90" />
        </el-select>
      </div>
      <el-table :data="ranks" border size="small">
        <el-table-column type="index" label="#" width="50" />
        <el-table-column prop="name" label="座席" min-width="120" />
        <el-table-column prop="leads" label="私海线索" width="90" align="center" />
        <el-table-column prop="won" label="成交" width="70" align="center" />
        <el-table-column label="转化率" width="90" align="center"><template #default="{ row }">{{ (row.conversion * 100).toFixed(1) }}%</template></el-table-column>
        <el-table-column prop="calls" label="拨打" width="70" align="center" />
        <el-table-column prop="connected" label="接通" width="70" align="center" />
        <el-table-column label="接通率" width="90" align="center"><template #default="{ row }">{{ (row.connect_rate * 100).toFixed(0) }}%</template></el-table-column>
      </el-table>
    </AppDialog>

    <!-- 批量派单 -->
    <AppDialog v-model="assignDlg" title="批量派单" width="420px">
      <p class="hint">把选中的 {{ selected.length }} 条线索分配给座席(进其私海)。</p>
      <el-select v-model="assignSeat" placeholder="选择座席" filterable style="width:100%">
        <el-option v-for="s in seats" :key="s.id" :label="s.name" :value="s.id" />
      </el-select>
      <template #footer><el-button @click="assignDlg = false">取消</el-button><el-button type="primary" @click="doAssign">派单</el-button></template>
    </AppDialog>

    <!-- 详情 + 跟进 -->
    <el-drawer v-model="drawer" :title="cur?.name || '线索详情'" size="560px">
      <template v-if="cur">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item label="联系人">{{ cur.contact_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="电话">{{ cur.phone || '—' }}</el-descriptions-item>
          <el-descriptions-item label="地区">{{ cur.region_name || '—' }}</el-descriptions-item>
          <el-descriptions-item label="行业">{{ cur.industry || '—' }}</el-descriptions-item>
          <el-descriptions-item label="来源">{{ LEAD_SOURCE[cur.source] || cur.source }}</el-descriptions-item>
          <el-descriptions-item label="意向">{{ cur.intent_grade || '—' }} {{ cur.intent_score ?? '' }}</el-descriptions-item>
        </el-descriptions>

        <div class="sec-title">合规</div>
        <div class="compliance">
          <el-switch v-model="curConsent" @change="saveCompliance" />
          <span class="muted">已同意营销联系</span>
          <el-checkbox v-model="curDnc" @change="saveCompliance" style="margin-left:16px">拒接(禁呼)</el-checkbox>
        </div>
        <el-input v-model="curSourceNote" placeholder="来源与合法性依据(合规留痕)" size="small"
          style="margin-top:8px" @change="saveCompliance" />

        <div class="sec-title">标签</div>
        <el-select v-model="curTags" multiple filterable allow-create default-first-option
          placeholder="选择或输入标签" style="width:100%" @change="saveTags">
          <el-option v-for="t in cfg.tag_catalog" :key="t" :label="t" :value="t" />
        </el-select>

        <div class="sec-title">状态</div>
        <el-radio-group :model-value="cur.status" @change="(v: any) => setStatus(v)">
          <el-radio-button v-for="(v, k) in LEAD_STATUS" :key="k" :label="k">{{ v }}</el-radio-button>
        </el-radio-group>

        <div class="sec-title">记录跟进</div>
        <el-form label-width="72px">
          <el-form-item label="方式">
            <el-radio-group v-model="actForm.channel">
              <el-radio-button label="call">电话</el-radio-button>
              <el-radio-button label="wechat">微信</el-radio-button>
              <el-radio-button label="note">备注</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <el-form-item v-if="actForm.channel === 'call'" label="结果">
            <el-select v-model="actForm.outcome" clearable placeholder="通话结果" style="width:160px">
              <el-option label="接通" value="connected" />
              <el-option label="未接" value="no_answer" />
              <el-option label="拒接" value="rejected" />
              <el-option label="约回访" value="callback" />
            </el-select>
          </el-form-item>
          <el-form-item v-if="relevantScripts().length" label="话术">
            <el-tag v-for="s in relevantScripts()" :key="s.title" class="script-chip"
              @click="useScript(s)">{{ s.title }}</el-tag>
          </el-form-item>
          <el-form-item label="内容"><el-input v-model="actForm.content" type="textarea" :rows="2" /></el-form-item>
          <el-form-item label="下次跟进"><el-date-picker v-model="actForm.next_follow_at" type="datetime" value-format="YYYY-MM-DDTHH:mm:ss" style="width:220px" /></el-form-item>
          <el-form-item label="推进到">
            <el-select v-model="actForm.status" clearable placeholder="可选:更新状态" style="width:160px">
              <el-option v-for="(v, k) in LEAD_STATUS" :key="k" :label="v" :value="k" />
            </el-select>
          </el-form-item>
          <el-button type="primary" @click="saveAct">保存跟进</el-button>
        </el-form>

        <div class="sec-title">意向分析(试跑)</div>
        <p class="hint">粘贴通话/微信会话转写,AI 判成交意向 + 抽产品意见(呼叫中心/ASR 接入后自动跑)。</p>
        <el-input v-model="anaText" type="textarea" :rows="3" placeholder="例:你们这课多少钱?能支持中考冲刺吗?我们再考虑下…" />
        <el-button type="primary" plain size="small" style="margin-top:8px" :loading="anaLoading" @click="runAnalyze">试跑分析</el-button>
        <div v-if="anaResult" class="ana-box">
          <div>意向分:<b>{{ anaResult.intent_score }}</b>
            <el-tag size="small" style="margin-left:6px">{{ anaResult.summary }}</el-tag>
          </div>
          <div class="ana-sig">
            <el-tag v-if="anaResult.signals.asked_price" size="small" type="success" effect="plain">问价</el-tag>
            <el-tag v-if="anaResult.signals.asked_next_step" size="small" type="success" effect="plain">问合作</el-tag>
            <el-tag v-for="o in anaResult.signals.objections" :key="o" size="small" type="warning" effect="plain">异议:{{ o }}</el-tag>
            <el-tag v-for="r in anaResult.signals.red_flags" :key="r" size="small" type="danger" effect="plain">{{ r }}</el-tag>
          </div>
          <div v-if="anaResult.product_feedback.length" class="muted">产品意见:{{ anaResult.product_feedback.join(' / ') }}</div>
          <div v-if="anaResult.next_action" class="muted">建议下一步:{{ anaResult.next_action }}</div>
        </div>

        <div class="sec-title">跟进时间线</div>
        <el-timeline v-loading="actsLoading">
          <el-timeline-item v-for="a in acts" :key="a.id" :timestamp="fmt(a.created_at)" placement="top">
            <b>{{ a.channel === 'call' ? '电话' : a.channel === 'wechat' ? '微信' : a.channel === 'note' ? '备注' : a.channel }}</b>
            <span v-if="a.outcome" class="muted"> · {{ a.outcome }}</span>
            <div>{{ a.content || '' }}</div>
          </el-timeline-item>
          <el-empty v-if="!actsLoading && !acts.length" description="暂无跟进" :image-size="60" />
        </el-timeline>

        <div class="sec-title">企微会话</div>
        <div v-if="wecomMsgs.length" class="wecom-list">
          <div v-for="m in wecomMsgs" :key="m.id" class="wecom-msg">
            <span class="muted">{{ fmt(m.msgtime) }} · {{ m.from_userid === cur.wechat_id ? '客户' : '座席' }}</span>
            <div>{{ m.content_text || `[${m.msgtype}]` }}</div>
          </div>
        </div>
        <el-empty v-else description="暂无企微会话(接入会话存档后自动同步分析)" :image-size="60" />

        <div class="sec-title">操作审计</div>
        <el-timeline v-if="auditRows.length">
          <el-timeline-item v-for="a in auditRows" :key="a.id" :timestamp="fmt(a.created_at)" placement="top" size="normal">
            <b>{{ AUDIT_ACTION[a.action] || a.action }}</b>
            <span v-if="a.detail && a.detail.after" class="muted"> → {{ LEAD_STATUS[a.detail.after] || a.detail.after }}</span>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无操作记录" :image-size="60" />
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.sales { padding: 16px; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.toolbar h2 { margin: 0; }
.stat { color: #606266; font-size: 13px; }
.stat-sep { margin: 0 6px; color: #dcdfe6; }
.overdue { color: #f56c6c; font-weight: 600; }
.compliance { display: flex; align-items: center; gap: 6px; }
.dup-group { border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; margin-bottom: 10px; }
.dup-phone { font-weight: 600; margin-bottom: 6px; color: #303133; }
.dup-lead { display: flex; align-items: center; justify-content: space-between; padding: 4px 0; font-size: 13px; }
.script-chip { cursor: pointer; margin: 0 6px 4px 0; }
.script-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.tabs { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 13px; margin: 0; }
.muted { color: #909399; font-size: 12px; }
.sec-title { font-weight: 600; margin: 18px 0 10px; color: #303133; }
.ana-box { margin-top: 10px; padding: 10px 12px; background: #f5f7fa; border-radius: 6px; font-size: 13px; line-height: 1.9; }
.ana-sig { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0; }
.wecom-list { display: flex; flex-direction: column; gap: 8px; }
.wecom-msg { font-size: 13px; padding: 6px 10px; background: #f5f7fa; border-radius: 6px; }
:deep(.dnc-row) { background: #fef0f0 !important; }
</style>

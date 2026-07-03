<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listRegions, type RegionNode,
  getBaiduAk, setBaiduAk, baiduFetch,
  getAmapKey, setAmapKey, amapFetch, type BaiduPoi,
  getMapUsage, setMapQuota, ingestMapItems, type MapUsage,
} from '../api/admin'

// 数据源:百度 / 高德(同一套流程,各自的 Key)
const source = ref<'baidu' | 'amap'>('baidu')
const srcLabel = computed(() => source.value === 'baidu' ? '百度地图' : '高德地图')
const akLabel = computed(() => source.value === 'baidu' ? '百度地图 AK' : '高德地图 Key')

// AK / Key
const akMasked = ref('')
const akSet = ref(false)
const akInput = ref('')
async function loadAk() {
  try {
    const r = source.value === 'baidu' ? await getBaiduAk() : await getAmapKey()
    akSet.value = r.ak_set; akMasked.value = r.ak_masked
  } catch { /* ignore */ }
}
async function saveAk() {
  if (!akInput.value.trim()) { ElMessage.warning(`请填入 ${akLabel.value}`); return }
  try {
    const r = source.value === 'baidu' ? await setBaiduAk(akInput.value.trim()) : await setAmapKey(akInput.value.trim())
    akMasked.value = r.ak_masked; akSet.value = true; akInput.value = ''; ElMessage.success('已保存')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
async function onSource() { akInput.value = ''; await loadAk(); await loadUsage() }

// 地区:省 → 市 → 区/县(单选,下钻)→ 乡镇/街道(多选,检索时逐个循环)
const provinces = ref<RegionNode[]>([])
const cities = ref<RegionNode[]>([])
const counties = ref<RegionNode[]>([])       // 区/县(单选)
const towns = ref<RegionNode[]>([])          // 乡镇/街道(多选)
const provCode = ref('')
const cityCode = ref('')
const countyCode = ref('')
const pickedTowns = ref<string[]>([])        // 选中乡镇名(多选;循环检索)
const cityName = computed(() => cities.value.find(c => c.code === cityCode.value)?.name || '')
const countyName = computed(() => counties.value.find(c => c.code === countyCode.value)?.name || '')
// 检索区域:选了乡镇→循环各乡镇;只选区县→查该区县;都不选→整市
const searchRegions = computed(() =>
  pickedTowns.value.length ? pickedTowns.value : (countyName.value ? [countyName.value] : []))
async function onProv() {
  cityCode.value = ''; countyCode.value = ''
  cities.value = []; counties.value = []; towns.value = []; pickedTowns.value = []
  if (provCode.value) cities.value = await listRegions(provCode.value)
}
async function onCity() {
  countyCode.value = ''; counties.value = []; towns.value = []; pickedTowns.value = []
  if (cityCode.value) counties.value = await listRegions(cityCode.value)
}
async function onCounty() {
  towns.value = []; pickedTowns.value = []
  if (countyCode.value) towns.value = await listRegions(countyCode.value)
}

// 关键词
const kwInput = ref('')
const keywords = ref<string[]>(['英语', '晚托', '高中英语', '少儿英语', '学科英语', '英语培训', '外语培训'])
function addKw() {
  const v = kwInput.value.trim()
  if (v && !keywords.value.includes(v)) keywords.value.push(v)
  kwInput.value = ''
}
function delKw(k: string) { keywords.value = keywords.value.filter(x => x !== k) }

// 行业(两家都生效):高德→POI 类目(types);百度→类目词并入 query。可多选/自定义。
const industries = ref<string[]>([])
// amap 用高德官方 POI 类目码(科教文化服务:学校 1412xx、培训机构 141400),精确不歧义;baidu 用类目词
const INDUSTRY_PRESETS: { label: string; baidu: string; amap: string }[] = [
  { label: '培训机构', baidu: '培训机构', amap: '141400' },
  { label: '教育培训', baidu: '教育培训', amap: '141400' },
  { label: '少儿培训', baidu: '少儿培训', amap: '141400' },
  { label: '语言/外语培训', baidu: '外语培训', amap: '141400' },
  { label: '学校(全部)', baidu: '学校', amap: '141200' },
  { label: '高等院校', baidu: '大学', amap: '141201' },
  { label: '中学', baidu: '中学', amap: '141202' },
  { label: '小学', baidu: '小学', amap: '141203' },
  { label: '幼儿园', baidu: '幼儿园', amap: '141204' },
]
const _indMap: Record<string, { baidu: string; amap: string }> =
  Object.fromEntries(INDUSTRY_PRESETS.map(i => [i.label, { baidu: i.baidu, amap: i.amap }]))
const indBaidu = (l: string) => _indMap[l]?.baidu ?? l
const indAmap = (l: string) => _indMap[l]?.amap ?? l
// 高德:行业→types;百度:行业→并入关键词(类目词)
const useTypes = computed(() => source.value === 'amap' ? industries.value.map(indAmap) : [])
const effKeywords = computed(() => source.value === 'baidu'
  ? [...keywords.value, ...industries.value.map(indBaidu)]
  : keywords.value)

const pages = ref(3)
const loading = ref(false)
const rows = ref<BaiduPoi[]>([])
const stat = ref<{ fetched: number; with_phone: number; quota_stopped: boolean; region: string } | null>(null)
const ingestInfo = ref<{ created: number; skipped: number; shared_phone: number; no_phone: number; region_unresolved: number } | null>(null)

// 省/市/区没解析出(至少要到「县/区」)→ 标「地址待核」,便于人工挑出来补
function needReview(row: BaiduPoi): boolean { return !row.region_district }
function rowClass({ row }: { row: BaiduPoi }): string { return needReview(row) ? 'need-review' : '' }
const reviewCount = computed(() => rows.value.filter(needReview).length)

// 每日查询次数上限 + 用量
const usage = ref<MapUsage | null>(null)
const quotaInput = ref(100)
const curUsage = computed(() => usage.value ? usage.value[source.value] : null)
async function loadUsage() {
  try { usage.value = await getMapUsage(); quotaInput.value = usage.value[source.value].quota } catch { /* ignore */ }
}
async function saveQuota() {
  try {
    await setMapQuota(source.value === 'baidu' ? { baidu: quotaInput.value } : { amap: quotaInput.value })
    await loadUsage(); ElMessage.success('已设置每日上限')
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}

const fetchFn = computed(() => source.value === 'baidu' ? baiduFetch : amapFetch)
function srcNote(region: string) { return `${srcLabel.value};区域=${region};关键词=${keywords.value.join('/')}` }
function validate(): boolean {
  if (!akSet.value) { ElMessage.warning(`请先设置${akLabel.value}`); return false }
  if (!cityName.value) { ElMessage.warning('请选择城市'); return false }
  if (!keywords.value.length && !industries.value.length) { ElMessage.warning('请至少加一个关键词,或选一个行业'); return false }
  if (!searchRegions.value.length) { ElMessage.warning('请选乡镇/区县(或至少选到市)'); return false }
  return true
}
function afterFetchTip(r: { quota_stopped: boolean; daily_cap_stopped?: boolean }): boolean {
  if (r.daily_cap_stopped) { ElMessage.warning('已达每日查询上限,已自动停止'); return true }
  if (r.quota_stopped) { ElMessage.warning(`${srcLabel.value} API 额度已用尽,已自动停止`); return true }
  return false
}

// 检索预览(不入库,一次查全部搜索区域)
async function preview() {
  if (!validate()) return
  loading.value = true; ingestInfo.value = null
  try {
    const r = await fetchFn.value({ region_name: cityName.value, districts: searchRegions.value, keywords: effKeywords.value, types: useTypes.value, pages: pages.value, ingest: false })
    rows.value = r.preview || []
    stat.value = { fetched: r.fetched, with_phone: r.with_phone, quota_stopped: r.quota_stopped, region: r.region }
    await loadUsage()
    if (!afterFetchTip(r)) ElMessage.success(`检索到 ${r.fetched} 条`)
  } catch (e: any) { ElMessage.error(e?.message || '检索失败') }
  finally { loading.value = false }
}

// 全自动:按各乡镇/区域逐个 检索+入库(每个区域入库一次)
const mode = ref<'auto' | 'manual'>('auto')
const progress = ref<{ cur: string; done: number; total: number } | null>(null)
async function runAuto() {
  if (!validate()) return
  const regions = [...searchRegions.value]
  try { await ElMessageBox.confirm(`全自动:按 ${regions.length} 个区域逐个检索并入库(来源=${srcLabel.value})。是否继续?`, '全自动入库', { type: 'warning' }) } catch { return }
  loading.value = true; rows.value = []
  const acc = { created: 0, skipped: 0, shared_phone: 0, no_phone: 0, region_unresolved: 0 }
  progress.value = { cur: '', done: 0, total: regions.length }
  try {
    for (const rg of regions) {
      progress.value = { cur: rg, done: progress.value.done, total: regions.length }
      const r = await fetchFn.value({ region_name: cityName.value, districts: [rg], keywords: effKeywords.value, types: useTypes.value, pages: pages.value, ingest: true })
      rows.value.push(...(r.preview || []))
      if (r.ingest) { acc.created += r.ingest.created; acc.skipped += r.ingest.skipped; acc.shared_phone += (r.ingest.shared_phone || 0); acc.no_phone += r.ingest.no_phone; acc.region_unresolved += r.ingest.region_unresolved }
      ingestInfo.value = { ...acc }
      progress.value.done++
      await loadUsage()
      if (afterFetchTip(r)) break
    }
    ElMessage.success(`自动完成:入库 ${acc.created} 条(跳过重复 ${acc.skipped})`)
  } catch (e: any) { ElMessage.error(e?.message || '采集失败') }
  finally { loading.value = false; progress.value = null }
}

// 手动逐个:每个区域 检索(不入库)→ 展示 → 确认入库 → 下一个
const manualRegions = ref<string[]>([])
const manualIdx = ref(0)
const manualActive = computed(() => manualIdx.value < manualRegions.value.length)
const manualCur = computed(() => manualRegions.value[manualIdx.value] || '')
async function manualStart() {
  if (!validate()) return
  manualRegions.value = [...searchRegions.value]; manualIdx.value = 0; ingestInfo.value = null
  await manualFetch()
}
async function manualFetch() {
  if (!manualActive.value) return
  loading.value = true
  try {
    const r = await fetchFn.value({ region_name: cityName.value, districts: [manualCur.value], keywords: effKeywords.value, types: useTypes.value, pages: pages.value, ingest: false })
    rows.value = r.preview || []
    stat.value = { fetched: r.fetched, with_phone: r.with_phone, quota_stopped: r.quota_stopped, region: r.region }
    await loadUsage()
    if (afterFetchTip(r)) manualIdx.value = manualRegions.value.length   // 撞顶 → 结束流程
  } catch (e: any) { ElMessage.error(e?.message || '检索失败') }
  finally { loading.value = false }
}
async function manualNext() {
  manualIdx.value++
  if (manualActive.value) await manualFetch()
  else ElMessage.success('手动流程已完成')
}
async function manualIngest() {
  if (!rows.value.length) { ElMessage.info('本区域无结果,跳到下一个'); return manualNext() }
  loading.value = true
  try {
    const r = await ingestMapItems(rows.value, source.value, srcNote(manualCur.value))
    ElMessage.success(`「${manualCur.value}」入库 ${r.created} 条(跳过重复 ${r.skipped})`)
    await manualNext()
  } catch (e: any) { ElMessage.error(e?.message || '入库失败') }
  finally { loading.value = false }
}

onMounted(async () => { await loadAk(); await loadUsage(); provinces.value = await listRegions() })
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">地图获客</h3>
      <el-radio-group v-model="source" @change="onSource" size="small">
        <el-radio-button label="baidu">百度地图</el-radio-button>
        <el-radio-button label="amap">高德地图</el-radio-button>
      </el-radio-group>
      <span class="hint">官方 API 按 城市(+区县)+ 关键词 检索机构 → 去重入库电销 CRM。额度用尽自动停。</span>
    </div>

    <!-- AK / Key 设置 -->
    <el-card shadow="never" class="blk">
      <div class="row">
        <span class="lbl">{{ akLabel }}</span>
        <el-tag v-if="akSet" type="success" effect="plain">已设置 {{ akMasked }}</el-tag>
        <el-tag v-else type="danger" effect="plain">未设置</el-tag>
        <el-input v-model="akInput" :placeholder="`填入服务端 ${source === 'baidu' ? 'AK' : 'Key'} 覆盖`" style="width:320px" show-password />
        <el-button @click="saveAk">保存</el-button>
      </div>
      <div class="tip">仅用官方 API(非爬虫)。{{ source === 'baidu' ? 'AK 到百度地图开放平台建「服务端」应用获取' : 'Key 到高德开放平台建「Web 服务」应用获取' }};有日配额。电销须守 PIPL/营销规,管好禁呼名单。</div>
    </el-card>

    <!-- 检索条件 -->
    <el-card shadow="never" class="blk">
      <div class="row">
        <span class="lbl">地区</span>
        <el-select v-model="provCode" placeholder="省" filterable style="width:150px" @change="onProv">
          <el-option v-for="p in provinces" :key="p.code" :label="p.name" :value="p.code" />
        </el-select>
        <el-select v-model="cityCode" placeholder="市" filterable style="width:160px" :disabled="!provCode" @change="onCity">
          <el-option v-for="c in cities" :key="c.code" :label="c.name" :value="c.code" />
        </el-select>
        <el-select v-model="countyCode" placeholder="区/县" filterable clearable style="width:150px"
          :disabled="!cityCode" @change="onCounty">
          <el-option v-for="d in counties" :key="d.code" :label="d.name" :value="d.code" />
        </el-select>
        <el-select v-model="pickedTowns" placeholder="乡镇/街道(可多选;不选=整区县)" multiple collapse-tags collapse-tags-tooltip
          filterable clearable style="min-width:280px" :disabled="!countyCode">
          <el-option v-for="t in towns" :key="t.code" :label="t.name" :value="t.name" />
        </el-select>
      </div>
      <div v-if="pickedTowns.length" class="row">
        <span class="lbl" />
        <span class="muted">将按 {{ pickedTowns.length }} 个乡镇/街道逐个循环检索(每个各自翻页去重)</span>
      </div>
      <div class="row">
        <span class="lbl">关键词</span>
        <el-tag v-for="k in keywords" :key="k" closable @close="delKw(k)" style="margin-right:6px">{{ k }}</el-tag>
        <el-input v-model="kwInput" placeholder="加关键词回车,如 少儿英语" style="width:200px" @keyup.enter="addKw" />
        <el-button @click="addKw">加</el-button>
      </div>
      <div class="row">
        <span class="lbl">行业</span>
        <el-select v-model="industries" multiple filterable allow-create default-first-option collapse-tags collapse-tags-tooltip
          placeholder="选行业类目(可多选/自定义;选了可不填关键词)" style="min-width:360px">
          <el-option v-for="t in INDUSTRY_PRESETS" :key="t.label" :label="t.label" :value="t.label" />
        </el-select>
        <span class="muted">{{ source === 'baidu' ? '百度按类目词并入检索' : '高德按 POI 类目精确捞(可填类目码如 141201)' }}</span>
      </div>
      <div class="row">
        <span class="lbl">每词翻页</span>
        <el-input-number v-model="pages" :min="1" :max="10" />
        <span class="muted">每页 ~20 条,页数越多越耗配额</span>
      </div>
      <div class="row">
        <span class="lbl">每日上限</span>
        <el-input-number v-model="quotaInput" :min="1" :max="1000000" />
        <el-button size="small" @click="saveQuota">保存上限({{ srcLabel }})</el-button>
        <span v-if="usage" class="muted">今日 API 调用:
          <b>百度</b> {{ usage.baidu.used }}/{{ usage.baidu.quota }}(余
          <b :style="{ color: usage.baidu.remaining > 0 ? '#67c23a' : '#f56c6c' }">{{ usage.baidu.remaining }}</b>)
          &nbsp;·&nbsp; <b>高德</b> {{ usage.amap.used }}/{{ usage.amap.quota }}(余
          <b :style="{ color: usage.amap.remaining > 0 ? '#67c23a' : '#f56c6c' }">{{ usage.amap.remaining }}</b>)</span>
      </div>
      <div class="row">
        <span class="lbl">入库方式</span>
        <el-radio-group v-model="mode">
          <el-radio-button label="auto">全自动(逐区域自动入库)</el-radio-button>
          <el-radio-button label="manual">手动(逐区域确认)</el-radio-button>
        </el-radio-group>
      </div>
      <div class="row">
        <el-button type="primary" :loading="loading" @click="preview">检索预览</el-button>
        <template v-if="mode === 'auto'">
          <el-button type="success" :loading="loading" @click="runAuto">全自动采集入库</el-button>
          <span v-if="progress" class="muted">正在采「{{ progress.cur }}」… {{ progress.done }}/{{ progress.total }}</span>
        </template>
        <template v-else>
          <el-button type="success" :loading="loading" :disabled="manualActive" @click="manualStart">开始逐个采集</el-button>
          <template v-if="manualActive">
            <span class="muted">当前「<b>{{ manualCur }}</b>」({{ manualIdx + 1 }}/{{ manualRegions.length }})</span>
            <el-button type="success" :loading="loading" @click="manualIngest">入库这批 → 下一个</el-button>
            <el-button :loading="loading" @click="manualNext">跳过 → 下一个</el-button>
          </template>
        </template>
      </div>
    </el-card>

    <!-- 结果 -->
    <el-alert v-if="stat?.quota_stopped" type="warning" show-icon :closable="false" style="margin-bottom:12px"
      title="百度 API 额度已用尽,本次已提前停止。可明日再跑或换 AK。" />
    <div v-if="stat" class="summary">
      <el-tag size="large" effect="plain">区域 <b>{{ stat.region }}</b></el-tag>
      <el-tag size="large" effect="plain">检索 <b>{{ stat.fetched }}</b></el-tag>
      <el-tag size="large" type="success" effect="plain">有电话 <b>{{ stat.with_phone }}</b></el-tag>
      <el-tag v-if="reviewCount" size="large" type="warning" effect="plain">地址待核 <b>{{ reviewCount }}</b></el-tag>
      <template v-if="ingestInfo">
        <el-tag size="large" type="success" effect="dark">入库 <b>{{ ingestInfo.created }}</b></el-tag>
        <el-tag v-if="ingestInfo.shared_phone" size="large" type="warning" effect="dark" title="同一电话挂不同地址,疑似一个老板多店">同号多机构 <b>{{ ingestInfo.shared_phone }}</b></el-tag>
        <el-tag size="large" type="info" effect="plain">重复跳过 <b>{{ ingestInfo.skipped }}</b></el-tag>
        <el-tag v-if="ingestInfo.no_phone" size="large" type="info" effect="plain" title="无电话的机构也已入库(按同名+地址去重),需人工补号后再外呼">无电话(已入库) <b>{{ ingestInfo.no_phone }}</b></el-tag>
      </template>
    </div>

    <el-table :data="rows" border stripe style="width:100%" v-loading="loading" :row-class-name="rowClass">
      <el-table-column type="index" label="#" width="56" />
      <el-table-column label="解析" width="96" align="center">
        <template #default="{ row }">
          <el-tag v-if="needReview(row)" type="warning" size="small" effect="dark" title="省/市/区未解析出,请人工核对地址">地址待核</el-tag>
          <el-tag v-else type="success" size="small" effect="plain">已定位</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="name" label="机构名" min-width="200" show-overflow-tooltip />
      <el-table-column prop="phone" label="电话" width="150">
        <template #default="{ row }"><span :class="{ muted: !row.phone }">{{ row.phone || '无' }}</span></template>
      </el-table-column>
      <el-table-column prop="business" label="主营业务" width="180" show-overflow-tooltip />
      <el-table-column prop="address" label="地址" min-width="240" show-overflow-tooltip />
      <el-table-column prop="region_province" label="省" width="90" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ muted: !row.region_province }">{{ row.region_province || '—' }}</span></template>
      </el-table-column>
      <el-table-column prop="region_city" label="市" width="100" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ muted: !row.region_city }">{{ row.region_city || '—' }}</span></template>
      </el-table-column>
      <el-table-column prop="region_district" label="县/区" width="100" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ muted: !row.region_district }">{{ row.region_district || '—' }}</span></template>
      </el-table-column>
      <el-table-column prop="region_town" label="乡镇/街道" width="110" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ muted: !row.region_town }">{{ row.region_town || '—' }}</span></template>
      </el-table-column>
      <template #empty>暂无结果 —— 选好地区/关键词后点「检索预览」</template>
    </el-table>
    <div v-if="rows.length >= 100" class="muted" style="margin-top:8px">仅预览前 100 条;全部结果已在检索/入库时处理。</div>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.hint { color: #909399; font-size: 12px; }
.blk { margin-bottom: 14px; }
.row { display: flex; align-items: center; gap: 10px; margin: 8px 0; flex-wrap: wrap; }
.lbl { width: 76px; color: #606266; font-size: 14px; }
.tip { color: #909399; font-size: 12px; margin-top: 6px; }
.muted { color: #a0a4ab; font-size: 12px; }
.summary { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; flex-wrap: wrap; }
.summary b { font-size: 15px; margin-left: 4px; }
/* 地址待核行:淡黄底,一眼挑出来 */
:deep(.el-table .need-review td) { background: #fdf6ec !important; }
</style>

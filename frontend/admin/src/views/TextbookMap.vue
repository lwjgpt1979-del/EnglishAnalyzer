<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listTextbookMap, getTextbookVersions, upsertTextbookMap, deleteTextbookMap, seedTextbookMap,
  listRegions, type RegionNode, type TextbookRow,
} from '../api/admin'

const LEVEL_LABEL: Record<number, string> = { 1: '省', 2: '市', 3: '区县' }

const rows = ref<TextbookRow[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const levelFilter = ref<number | ''>('')
const loading = ref(false)
const versionOptions = ref<string[]>([])

async function load() {
  loading.value = true
  try {
    const r = await listTextbookMap({
      level: levelFilter.value === '' ? undefined : levelFilter.value,
      skip: (page.value - 1) * pageSize.value, limit: pageSize.value,
    })
    rows.value = r.items; total.value = r.total
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// ── 编辑/新增 ──
const dlg = ref(false)
const editing = ref(false)          // true=改已有(锁地区),false=新增地市例外
const form = ref<{ region_code: string; region_name: string; versions: string[]; note: string; verified: boolean }>(
  { region_code: '', region_name: '', versions: [], note: '', verified: true })

// 新增例外时的地区级联(省→市→区县)
const provinces = ref<RegionNode[]>([])
const cities = ref<RegionNode[]>([])
const counties = ref<RegionNode[]>([])
const provCode = ref(''); const cityCode = ref(''); const countyCode = ref('')
async function onProv() { cityCode.value = ''; countyCode.value = ''; cities.value = []; counties.value = []; if (provCode.value) cities.value = await listRegions(provCode.value); pickRegion(provCode.value, provinces.value) }
async function onCity() { countyCode.value = ''; counties.value = []; if (cityCode.value) counties.value = await listRegions(cityCode.value); pickRegion(cityCode.value, cities.value) }
async function onCounty() { pickRegion(countyCode.value, counties.value) }
function pickRegion(code: string, list: RegionNode[]) {
  const n = list.find(x => x.code === code)
  if (n) { form.value.region_code = n.code; form.value.region_name = n.name }
}

function openEdit(row: TextbookRow) {
  editing.value = true
  form.value = { region_code: row.region_code, region_name: row.region_name, versions: [...row.versions], note: row.note || '', verified: row.verified }
  dlg.value = true
}
async function openNew() {
  editing.value = false
  form.value = { region_code: '', region_name: '', versions: [], note: '', verified: true }
  provCode.value = ''; cityCode.value = ''; countyCode.value = ''; cities.value = []; counties.value = []
  if (!provinces.value.length) provinces.value = await listRegions()
  dlg.value = true
}
async function save() {
  if (!form.value.region_code) { ElMessage.warning('请选择地区'); return }
  if (!form.value.versions.length) { ElMessage.warning('请至少选一个教材版本'); return }
  try {
    await upsertTextbookMap({ region_code: form.value.region_code, versions: form.value.versions, note: form.value.note || null, verified: form.value.verified })
    ElMessage.success('已保存'); dlg.value = false; load()
  } catch (e: any) { ElMessage.error(e?.message || '保存失败') }
}
async function del(row: TextbookRow) {
  try { await ElMessageBox.confirm(`删除「${row.region_name}」的教材映射?`, '确认', { type: 'warning' }) } catch { return }
  try { await deleteTextbookMap(row.region_code); ElMessage.success('已删除'); load() }
  catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}
async function seed() {
  try { await ElMessageBox.confirm('按省灌入省级默认(只补缺,不覆盖已校对的行)。继续?', '灌省级默认', { type: 'info' }) } catch { return }
  try { const r = await seedTextbookMap(false); ElMessage.success(`已写入 ${r.written} 个省(跳过 ${r.skipped})`); reload() }
  catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

onMounted(async () => { versionOptions.value = (await getTextbookVersions()).versions; await load() })
</script>

<template>
  <div>
    <div class="toolbar">
      <h3 style="margin:0">教材版本地图</h3>
      <span class="hint">地区↔英语教材版本(以初中英语为主)。省级为公开信息整理的<b>默认值,需人工校对</b>;地市有差异时「加地市例外」按区县覆盖省级默认。</span>
    </div>

    <div class="bar">
      <span class="lbl">层级</span>
      <el-select v-model="levelFilter" placeholder="全部" clearable style="width:120px" @change="reload">
        <el-option label="省" :value="1" />
        <el-option label="市" :value="2" />
        <el-option label="区县" :value="3" />
      </el-select>
      <el-button type="primary" @click="openNew">加地市例外</el-button>
      <el-button @click="seed">灌省级默认</el-button>
      <span class="hint">共 {{ total }} 条</span>
    </div>

    <el-table :data="rows" border stripe style="width:100%" v-loading="loading">
      <el-table-column label="层级" width="80" align="center">
        <template #default="{ row }"><el-tag size="small" effect="plain">{{ LEVEL_LABEL[row.level] || row.level }}</el-tag></template>
      </el-table-column>
      <el-table-column prop="region_name" label="地区" min-width="140" show-overflow-tooltip />
      <el-table-column label="教材版本" min-width="220">
        <template #default="{ row }">
          <el-tag v-for="v in row.versions" :key="v" size="small" type="success" effect="plain" style="margin-right:6px">{{ v }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="note" label="备注/地市差异" min-width="220" show-overflow-tooltip>
        <template #default="{ row }"><span :class="{ muted: !row.note }">{{ row.note || '—' }}</span></template>
      </el-table-column>
      <el-table-column label="校对" width="96" align="center">
        <template #default="{ row }">
          <el-tag v-if="row.verified" size="small" type="success">已校对</el-tag>
          <el-tag v-else size="small" type="warning">待校对</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="150" align="center">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="danger" plain @click="del(row)">删除</el-button>
        </template>
      </el-table-column>
      <template #empty>暂无数据 —— 点「灌省级默认」初始化省级映射</template>
    </el-table>

    <el-pagination
      style="margin-top:14px; justify-content:flex-end"
      layout="total, prev, pager, next, jumper"
      :total="total" :current-page="page" :page-size="pageSize"
      @current-change="(p: number) => { page = p; load() }" />

    <AppDialog v-model="dlg" :title="editing ? `编辑 ${form.region_name}` : '加地市例外'" width="520px">
      <el-form label-width="90px">
        <el-form-item v-if="!editing" label="地区">
          <div style="display:flex; gap:8px; flex-wrap:wrap">
            <el-select v-model="provCode" placeholder="省" filterable style="width:140px" @change="onProv">
              <el-option v-for="p in provinces" :key="p.code" :label="p.name" :value="p.code" />
            </el-select>
            <el-select v-model="cityCode" placeholder="市" filterable style="width:150px" :disabled="!provCode" @change="onCity">
              <el-option v-for="c in cities" :key="c.code" :label="c.name" :value="c.code" />
            </el-select>
            <el-select v-model="countyCode" placeholder="区县(可选)" filterable clearable style="width:150px" :disabled="!cityCode" @change="onCounty">
              <el-option v-for="d in counties" :key="d.code" :label="d.name" :value="d.code" />
            </el-select>
          </div>
        </el-form-item>
        <el-form-item v-else label="地区"><b>{{ form.region_name }}</b></el-form-item>
        <el-form-item label="教材版本">
          <el-select v-model="form.versions" multiple filterable allow-create default-first-option
            placeholder="选/输入教材版本(可多选)" style="width:100%">
            <el-option v-for="v in versionOptions" :key="v" :label="v" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.note" type="textarea" :rows="2" placeholder="地市差异说明,如「深圳用牛津深圳版」" />
        </el-form-item>
        <el-form-item label="标记校对">
          <el-switch v-model="form.verified" active-text="已校对" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dlg = false">取消</el-button>
        <el-button type="primary" @click="save">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }
.bar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.lbl { color: #606266; font-size: 14px; }
.hint { color: #909399; font-size: 12px; }
.muted { color: #a0a4ab; }
</style>

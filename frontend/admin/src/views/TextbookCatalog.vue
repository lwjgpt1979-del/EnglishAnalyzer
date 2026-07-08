<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Plus, Delete } from '@element-plus/icons-vue'
import {
  listCatalog, getCatalogOptions, addCatalog, setCatalogStatus, deleteCatalog,
  type CatalogItem, type CatalogOptions,
} from '../api/admin'

// ── 列表 + 服务端分页 ───────────────────────────────────────────────────────────
const rows = ref<CatalogItem[]>([])
const loading = ref(false)
const total = ref(0)
const page = ref(1)
const pageSize = 50

const filterVersion = ref('')
const filterGrade = ref('')
const filterSemester = ref('')

// 候选建议(已有 + 规范全量;新增时可自定义)
const opts = ref<CatalogOptions>({ textbook_versions: [], grades: [], semesters: [] })

async function load() {
  loading.value = true
  try {
    const r = await listCatalog({
      textbook_version: filterVersion.value || undefined,
      grade: filterGrade.value || undefined,
      semester: filterSemester.value || undefined,
      skip: (page.value - 1) * pageSize, limit: pageSize,
    })
    rows.value = r.items
    total.value = r.total
    if (!rows.value.length && page.value > 1 && total.value > 0) {
      page.value = Math.ceil(total.value / pageSize)
      return await load()
    }
  } catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
function reload() { page.value = 1; load() }

// 筛选下拉:用候选建议(含已有版本/年级/学期)
const versionOptions = computed(() => opts.value.textbook_versions)
const gradeOptions = computed(() => opts.value.grades)
const semesterOptions = computed(() => opts.value.semesters)

// ── 上架 / 下架 ─────────────────────────────────────────────────────────────────
async function toggleStatus(row: CatalogItem) {
  const next = row.status === 'published' ? 'draft' : 'published'
  try {
    await setCatalogStatus(row.id, next)
    row.status = next
    ElMessage.success(next === 'published' ? '已上架(学生 / 机构可见)' : '已下架(仅后台可见)')
  } catch (e: any) { ElMessage.error(e?.message || '操作失败') }
}

async function removeRow(row: CatalogItem) {
  try {
    await ElMessageBox.confirm(
      `确认删除目录「${row.textbook_version} ${row.grade} ${row.semester}学期」?\n仅移除该组合的可选项 / 可见闸门,不删已上传的教材单元内容。`,
      '删除目录', { type: 'warning' })
  } catch { return }
  try {
    await deleteCatalog(row.id)
    ElMessage.success('已删除')
    load()
  } catch (e: any) { ElMessage.error(e?.message || '删除失败') }
}

// ── 新增目录 ────────────────────────────────────────────────────────────────────
const addDlg = ref(false)
const adding = ref(false)
const form = ref({ textbook_version: '', grade: '', semester: '' })
function openAdd() {
  form.value = { textbook_version: '', grade: '', semester: '' }
  addDlg.value = true
}
async function submitAdd() {
  const f = form.value
  if (!f.textbook_version || !f.grade || !f.semester) {
    ElMessage.warning('版本 / 年级 / 学期均需填写'); return
  }
  adding.value = true
  try {
    await addCatalog({ textbook_version: f.textbook_version, grade: f.grade, semester: f.semester })
    ElMessage.success('已新增(默认下架,确认后再上架)')
    addDlg.value = false
    await refreshOptions()
    reload()
  } catch (e: any) { ElMessage.error(e?.message || '新增失败') }
  finally { adding.value = false }
}

async function refreshOptions() {
  try { opts.value = await getCatalogOptions() } catch { /* 忽略 */ }
}

onMounted(async () => { await refreshOptions(); await load() })
</script>

<template>
  <div class="page">
    <div class="hd">
      <h2>教材版本维护</h2>
      <p class="hint">
        教材「版本 / 年级 / 学期」的唯一真源 + 上下架。<b>学生小程序、机构平台只见已上架</b>;后台此处上架 / 下架全部可见可管。
        可先建版本(内容后补);上架粒度 = 版本 + 年级 + 学期。全站相关下拉与学生内容可见性均来源于此。
      </p>
    </div>

    <div class="toolbar">
      <el-select v-model="filterVersion" placeholder="教材版本" clearable filterable style="width:180px" @change="reload">
        <el-option v-for="v in versionOptions" :key="v" :label="v" :value="v" />
      </el-select>
      <el-select v-model="filterGrade" placeholder="年级" clearable filterable style="width:150px" @change="reload">
        <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="filterSemester" placeholder="学期" clearable style="width:110px" @change="reload">
        <el-option v-for="s in semesterOptions" :key="s" :label="s + '学期'" :value="s" />
      </el-select>
      <el-button @click="load" :loading="loading"><el-icon style="margin-right:4px"><Refresh /></el-icon>刷新</el-button>
      <span class="stat-txt">共 {{ total }} 条目录 · 已上架 {{ rows.filter(r => r.status === 'published').length }} / 本页</span>
      <div style="flex:1" />
      <el-button type="primary" @click="openAdd"><el-icon style="margin-right:4px"><Plus /></el-icon>新增目录</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width:100%">
      <el-table-column prop="textbook_version" label="教材版本" min-width="160" />
      <el-table-column prop="grade" label="年级" width="140" />
      <el-table-column label="学期" width="110">
        <template #default="{ row }">{{ row.semester }}学期</template>
      </el-table-column>
      <el-table-column label="状态" width="120">
        <template #default="{ row }">
          <el-tag :type="row.status === 'published' ? 'success' : 'info'" effect="plain">
            {{ row.status === 'published' ? '已上架' : '已下架' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :type="row.status === 'published' ? 'warning' : 'success'" plain
            @click="toggleStatus(row)">{{ row.status === 'published' ? '下架' : '上架' }}</el-button>
          <el-button size="small" type="danger" plain @click="removeRow(row)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="total > pageSize" style="display:flex;justify-content:flex-end;margin-top:12px">
      <el-pagination layout="total, prev, pager, next, jumper" :total="total"
        :page-size="pageSize" v-model:current-page="page" @current-change="load" />
    </div>

    <!-- 新增目录 -->
    <AppDialog v-model="addDlg" title="新增教材目录" width="460px">
      <p class="hint" style="margin-top:0">版本 / 年级 / 学期均可从下拉选择或直接输入新值(支持自定义)。新增后默认<b>下架</b>,确认无误再上架。</p>
      <el-form label-width="80px">
        <el-form-item label="教材版本">
          <el-select v-model="form.textbook_version" filterable allow-create default-first-option
            placeholder="选择或输入,如 译林版 / 人教版" style="width:100%">
            <el-option v-for="v in versionOptions" :key="v" :label="v" :value="v" />
          </el-select>
        </el-form-item>
        <el-form-item label="年级">
          <el-select v-model="form.grade" filterable allow-create default-first-option
            placeholder="选择或输入,如 初中7年级" style="width:100%">
            <el-option v-for="g in gradeOptions" :key="g" :label="g" :value="g" />
          </el-select>
        </el-form-item>
        <el-form-item label="学期">
          <el-select v-model="form.semester" filterable allow-create default-first-option
            placeholder="选择或输入,如 上 / 下" style="width:100%">
            <el-option v-for="s in semesterOptions" :key="s" :label="s" :value="s" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="primary" :loading="adding" @click="submitAdd">确定</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.page { padding: 4px 2px; }
.hd h2 { margin: 0 0 4px; font-size: 18px; }
.hint { color: var(--el-text-color-secondary); font-size: 13px; margin: 0 0 12px; line-height: 1.6; }
.toolbar { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; flex-wrap: wrap; }
.stat-txt { color: var(--el-text-color-secondary); font-size: 13px; }
</style>

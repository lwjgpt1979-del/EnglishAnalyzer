<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Delete, RefreshRight } from '@element-plus/icons-vue'
import {
  listVocabLists, createVocabList, listVocabItems, addVocabItems,
  deleteVocabItem, rebuildExamFreq, type VocabListStats,
} from '../api/admin'
import type { VocabListItem2, VocabWordItem } from '../types'

const lists = ref<VocabListItem2[]>([])
const loading = ref(false)
const current = ref<VocabListItem2 | null>(null)
const items = ref<VocabWordItem[]>([])
const itemsTotal = ref(0)        // 当前筛选后的总数(分页用)
const stats = ref<VocabListStats | null>(null)
const itemsPage = ref(1)
const itemsPageSize = ref(50)
const itemsLoading = ref(false)

// 搜索/筛选/排序
const filters = reactive({ q: '', band: '', source: '', verified: '', sort: 'freq' })
const bandOpts = [
  { label: '全部频档', value: '' }, { label: '高频', value: 'high' },
  { label: '中频', value: 'mid' }, { label: '低频', value: 'low' }, { label: '未命中真题', value: 'none' },
]
const sourceOpts = [
  { label: '全部来源', value: '' }, { label: '考纲原生', value: 'syllabus' }, { label: '真题补录', value: 'exam' },
]
const verifiedOpts = [
  { label: '全部', value: '' }, { label: '已核', value: 'yes' }, { label: '未核', value: 'no' },
]
const sortOpts = [
  { label: '按真题频次', value: 'freq' }, { label: '按考纲排名', value: 'rank' }, { label: '按字母', value: 'word' },
]

// 词库类型(决定右侧是否显示真题频次相关列 + 反哺按钮)
function srcLabel(l: VocabListItem2 | null): { text: string; type: 'success' | 'warning' | 'info' | 'primary' } {
  const s = l?.source_type || ''
  if (s === 'official_syllabus') return { text: '考纲', type: 'primary' }
  if (s === 'phrase') return { text: '短语', type: 'warning' }
  if (s === 'exam_frequency') return { text: '真题频次', type: 'success' }
  return { text: s || '其他', type: 'info' }
}
const isSyllabus = (l: VocabListItem2 | null) => !!l && (l.exam_level === 'junior' || l.exam_level === 'senior')
// 有真题频次维度的表(考纲)才显示频次/频档/来自真题列 + 反哺
const showFreqCols = computed(() => isSyllabus(current.value))

// 新建词库 / 加词
const createDlg = ref(false)
const form = ref({ name: '', exam_level: '', source_type: 'official_syllabus', status: 'published' })
const examLevels = ['primary', 'junior', 'senior', 'cet4', 'cet6']
const addDlg = ref(false)
const wordsText = ref('')

async function load() {
  loading.value = true
  try { lists.value = (await listVocabLists()).items }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

function resetFilters() {
  filters.q = ''; filters.band = ''; filters.source = ''; filters.verified = ''; filters.sort = 'freq'
}

async function openItems(row: VocabListItem2) {
  current.value = row
  resetFilters()
  itemsPage.value = 1
  await loadItems()
}

async function loadItems() {
  if (!current.value) return
  itemsLoading.value = true
  try {
    const r = await listVocabItems(current.value.id, {
      skip: (itemsPage.value - 1) * itemsPageSize.value, limit: itemsPageSize.value,
      q: filters.q.trim() || undefined,
      band: filters.band || undefined,
      source: filters.source || undefined,
      verified: filters.verified === 'yes' ? true : filters.verified === 'no' ? false : undefined,
      sort: filters.sort,
    })
    items.value = r.items
    itemsTotal.value = r.total
    if (r.stats) stats.value = r.stats
  }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { itemsLoading.value = false }
}

// 筛选变更回第一页
function applyFilter() { itemsPage.value = 1; loadItems() }
let searchTimer: any = null
function onSearchInput() { clearTimeout(searchTimer); searchTimer = setTimeout(applyFilter, 350) }
// 统计条数字点击 → 快捷筛选
function quickFilter(patch: Partial<typeof filters>) {
  Object.assign(filters, { band: '', source: '', verified: '' }, patch); applyFilter()
}
function onSizeChange(s: number) { itemsPageSize.value = s; applyFilter() }

async function removeItem(row: VocabWordItem) {
  if (!current.value) return
  try {
    await ElMessageBox.confirm(`从「${current.value.name}」移除「${row.word}」?(不删全局主词)`, '移除词条',
      { type: 'warning', confirmButtonText: '移除', cancelButtonText: '取消' })
  } catch { return }
  try {
    await deleteVocabItem(current.value.id, row.word_id)
    ElMessage.success('已移除')
    if (current.value) current.value.item_count = Math.max(0, (current.value.item_count || 1) - 1)
    await loadItems()
  } catch (e: any) { ElMessage.error(e?.message || '移除失败') }
}

// 真题词频反哺
const reflowing = ref(false)
async function reflowFromExam() {
  if (!current.value) return
  const examType = current.value.exam_level === 'senior' ? '高考' : '中考'
  try {
    await ElMessageBox.confirm(
      `将统计全部「${examType}真题」词频(整卷去重、词形还原),反哺到「${current.value.name}」:` +
      `命中的考纲词写真题卷频次 + 高/中/低频档;真题里有、考纲没有的内容词补录进表(标「真题补录」)。约需 1 分钟。`,
      '从真题反哺词频', { type: 'warning', confirmButtonText: '开始统计', cancelButtonText: '取消' })
  } catch { return }
  reflowing.value = true
  try {
    const r = await rebuildExamFreq({ exam_type: examType, list_name: current.value.name })
    ElMessage.success(
      `完成:${r.papers_unique}/${r.papers_total} 卷(去重 ${r.papers_duplicated})· ` +
      `命中 ${r.matched}、补录 ${r.added} · 高 ${r.freq_high}/中 ${r.freq_mid}/低 ${r.freq_low}`)
    resetFilters(); itemsPage.value = 1
    await Promise.all([loadItems(), load()])   // 补录会改条数,左栏也刷新
  } catch (e: any) { ElMessage.error(e?.message || '统计失败') }
  finally { reflowing.value = false }
}

async function confirmCreate() {
  if (!form.value.name.trim()) { ElMessage.warning('请填词库名'); return }
  const vl = await createVocabList({
    name: form.value.name.trim(), exam_level: form.value.exam_level || undefined,
    source_type: form.value.source_type, status: form.value.status,
  })
  ElMessage.success('已创建')
  createDlg.value = false; form.value.name = ''
  await load()
  await openItems(vl as any)
}

async function confirmAdd() {
  if (!current.value) return
  const words = wordsText.value.split(/[\s,，\n]+/).map(s => s.trim()).filter(Boolean)
  if (!words.length) { ElMessage.warning('请输入词(空格/逗号/换行分隔)'); return }
  const payload = words.map((w, i) => ({ word: w, rank: i + 1 }))
  const res = await addVocabItems(current.value.id, payload)
  ElMessage.success(`已加入,当前共 ${res.total} 词`)
  addDlg.value = false; wordsText.value = ''
  await load(); resetFilters(); itemsPage.value = 1
  await loadItems()
}

onMounted(load)
</script>

<template>
  <div class="wrap">
    <!-- 左:词库列表 -->
    <div class="left">
      <div class="toolbar">
        <b>通用词库</b>
        <div style="flex:1" />
        <el-button size="small" type="success" @click="createDlg = true">+ 新建</el-button>
        <el-button size="small" :icon="RefreshRight" @click="load" />
      </div>
      <el-table v-loading="loading" :data="lists" border highlight-current-row
                :current-row-key="current?.id" row-key="id"
                style="width: 100%" @row-click="openItems">
        <el-table-column label="词库" min-width="150">
          <template #default="{ row }">
            <div class="list-name">{{ row.name }}</div>
            <div class="list-sub">
              <el-tag size="small" :type="srcLabel(row).type" effect="plain">{{ srcLabel(row).text }}</el-tag>
              <span v-if="row.exam_level" class="muted">{{ row.exam_level }}</span>
              <span class="muted">· {{ row.item_count ?? 0 }} 词</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'published' ? 'success' : 'info'" effect="light">
              {{ row.status === 'published' ? '已发布' : row.status === 'draft' ? '草稿' : row.status }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 右:词条 -->
    <div class="right">
      <div v-if="!current" class="empty-hint">
        <el-empty description="选择左侧词库查看 / 管理词条" :image-size="70" />
      </div>

      <template v-else>
        <!-- 工具栏:标题 + 操作 -->
        <div class="toolbar">
          <b>「{{ current.name }}」词条</b>
          <div style="flex:1" />
          <el-button v-if="isSyllabus(current)" size="small" type="warning" plain :loading="reflowing"
                     title="统计对应考试真题词频(整卷去重),写回频次/频档并补录未收录词" @click="reflowFromExam">
            从真题反哺频次
          </el-button>
          <el-button size="small" type="primary" @click="addDlg = true">+ 加词</el-button>
        </div>

        <!-- 统计条(考纲表才有真题频次维度)-->
        <div v-if="showFreqCols && stats" class="stat-bar">
          <span class="stat" @click="quickFilter({})">共 <b>{{ stats.total }}</b> 词</span>
          <span class="stat clk" @click="quickFilter({ band: 'none' })">未命中真题 <b>{{ stats.total - stats.with_freq }}</b></span>
          <span class="stat clk hi" @click="quickFilter({ band: 'high' })">高频 <b>{{ stats.high }}</b></span>
          <span class="stat clk mi" @click="quickFilter({ band: 'mid' })">中频 <b>{{ stats.mid }}</b></span>
          <span class="stat clk lo" @click="quickFilter({ band: 'low' })">低频 <b>{{ stats.low }}</b></span>
          <span class="stat clk ex" @click="quickFilter({ source: 'exam' })">真题补录 <b>{{ stats.added }}</b></span>
        </div>
        <div v-else-if="stats" class="stat-bar">
          <span class="stat">共 <b>{{ stats.total }}</b> 词条</span>
          <span class="muted" style="font-size:12px">(短语/非考纲表不参与真题词频)</span>
        </div>

        <!-- 筛选栏 -->
        <div class="filter-bar">
          <el-input v-model="filters.q" :prefix-icon="Search" clearable size="small" style="width:200px"
                    placeholder="搜索词/词组" @input="onSearchInput" @clear="applyFilter" />
          <template v-if="showFreqCols">
            <el-select v-model="filters.band" size="small" style="width:120px" @change="applyFilter">
              <el-option v-for="o in bandOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <el-select v-model="filters.source" size="small" style="width:120px" @change="applyFilter">
              <el-option v-for="o in sourceOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
          <el-select v-model="filters.verified" size="small" style="width:100px" @change="applyFilter">
            <el-option v-for="o in verifiedOpts" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <el-select v-model="filters.sort" size="small" style="width:130px" @change="applyFilter">
            <el-option v-for="o in sortOpts" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
          <span class="muted" style="font-size:12px">筛选后 {{ itemsTotal }} 条</span>
        </div>

        <!-- 词条表 -->
        <el-table v-loading="itemsLoading" :data="items" border style="width: 100%" size="small">
          <el-table-column prop="rank" label="考纲排名" width="82" align="center">
            <template #default="{ row }"><span v-if="row.rank != null">{{ row.rank }}</span><span v-else class="muted">—</span></template>
          </el-table-column>
          <el-table-column prop="word" label="词 / 词组" min-width="150" show-overflow-tooltip />
          <template v-if="showFreqCols">
            <el-table-column label="真题频次" width="92" align="center">
              <template #default="{ row }">
                <span v-if="row.frequency">{{ row.frequency }} 卷</span>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="频档" width="78" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.star >= 1" size="small" effect="light"
                        :type="row.star === 3 ? 'danger' : row.star === 2 ? 'warning' : 'info'">
                  {{ ['', '低频', '中频', '高频'][row.star] }}
                </el-tag>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
            <el-table-column label="来自真题" width="94" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.added_from_exam" type="success" size="small" effect="plain">真题补录</el-tag>
                <el-tag v-else-if="row.frequency > 0" type="success" size="small" effect="light">是</el-tag>
                <span v-else class="muted">否</span>
              </template>
            </el-table-column>
          </template>
          <el-table-column label="已核" width="60" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.verified" type="success" size="small" effect="plain">✓</el-tag>
              <span v-else class="muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60" align="center" fixed="right">
            <template #default="{ row }">
              <el-button size="small" link type="danger" :icon="Delete" title="从本表移除" @click="removeItem(row)" />
            </template>
          </el-table-column>
        </el-table>

        <div style="display:flex;justify-content:flex-end;margin-top:12px">
          <el-pagination
            layout="total, sizes, prev, pager, next, jumper" :total="itemsTotal"
            :page-sizes="[50, 100, 200]" :page-size="itemsPageSize" v-model:current-page="itemsPage"
            @size-change="onSizeChange" @current-change="loadItems" />
        </div>
      </template>
    </div>

    <!-- 新建词库 -->
    <AppDialog v-model="createDlg" title="新建通用词库" width="420px">
      <el-form label-width="72px">
        <el-form-item label="名称"><el-input v-model="form.name" placeholder="如 高考3500" /></el-form-item>
        <el-form-item label="层级">
          <el-select v-model="form.exam_level" clearable style="width:100%">
            <el-option v-for="l in examLevels" :key="l" :label="l" :value="l" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="form.status" style="width:100%">
            <el-option label="已发布" value="published" />
            <el-option label="草稿" value="draft" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createDlg = false">取消</el-button>
        <el-button type="success" @click="confirmCreate">创建</el-button>
      </template>
    </AppDialog>

    <!-- 加词 -->
    <AppDialog v-model="addDlg" title="批量加词(空格/逗号/换行分隔,按顺序排名)" width="480px">
      <el-input v-model="wordsText" type="textarea" :rows="8" placeholder="abandon ability able ..." />
      <template #footer>
        <el-button @click="addDlg = false">取消</el-button>
        <el-button type="primary" @click="confirmAdd">加入</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.wrap { display: flex; gap: 16px; }
.left { width: 40%; min-width: 340px; }
.right { flex: 1; min-width: 0; }
.toolbar { margin-bottom: 12px; display: flex; align-items: center; gap: 10px; }
.empty-hint { padding-top: 60px; }
.list-name { font-weight: 500; color: #303133; }
.list-sub { margin-top: 3px; display: flex; align-items: center; gap: 6px; }
.muted { color: #909399; }
.stat-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px;
  padding: 8px 12px; background: #f7f9fc; border: 1px solid #ebeef5; border-radius: 8px; font-size: 13px;
}
.stat { color: #606266; padding: 2px 8px; border-radius: 12px; }
.stat b { color: #303133; }
.stat.clk { cursor: pointer; background: #fff; border: 1px solid #e4e7ed; }
.stat.clk:hover { border-color: var(--c-primary, #3d8bf5); }
.stat.hi b { color: #f56c6c; }
.stat.mi b { color: #e6a23c; }
.stat.lo b { color: #909399; }
.stat.ex b { color: #67c23a; }
.filter-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; }
</style>

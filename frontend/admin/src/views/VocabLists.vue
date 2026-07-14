<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listVocabLists, createVocabList, listVocabItems, addVocabItems, rebuildExamFreq } from '../api/admin'
import type { VocabListItem2, VocabWordItem } from '../types'

const lists = ref<VocabListItem2[]>([])
const loading = ref(false)
const current = ref<VocabListItem2 | null>(null)
const items = ref<VocabWordItem[]>([])
const itemsTotal = ref(0)
const itemsPage = ref(1)
const itemsPageSize = 50
const itemsLoading = ref(false)

// 新建词库
const createDlg = ref(false)
const form = ref({ name: '', exam_level: '', source_type: 'official_syllabus', status: 'published' })
const examLevels = ['primary', 'junior', 'senior', 'cet4', 'cet6']

// 加词条
const addDlg = ref(false)
const wordsText = ref('')

async function load() {
  loading.value = true
  try { lists.value = (await listVocabLists()).items }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}

async function openItems(row: VocabListItem2) {
  current.value = row
  itemsPage.value = 1
  await loadItems()
}

async function loadItems() {
  if (!current.value) return
  itemsLoading.value = true
  try {
    const r = await listVocabItems(current.value.id, { skip: (itemsPage.value - 1) * itemsPageSize, limit: itemsPageSize })
    items.value = r.items
    itemsTotal.value = r.total
  }
  finally { itemsLoading.value = false }
}

// 真题词频反哺:选中考纲词表 → 统计对应考试真题词频 → 写回频次/频档 + 补录未收录词
const reflowing = ref(false)
const isSyllabus = (l: VocabListItem2 | null) => !!l && (l.exam_level === 'junior' || l.exam_level === 'senior')
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
    itemsPage.value = 1
    await loadItems()
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
  createDlg.value = false
  form.value.name = ''
  await load()
  await openItems(vl)
}

async function confirmAdd() {
  if (!current.value) return
  const words = wordsText.value.split(/[\s,，\n]+/).map(s => s.trim()).filter(Boolean)
  if (!words.length) { ElMessage.warning('请输入词(空格/逗号/换行分隔)'); return }
  const payload = words.map((w, i) => ({ word: w, rank: i + 1 }))
  const res = await addVocabItems(current.value.id, payload)
  ElMessage.success(`已加入 ${res.total} 个词条`)
  addDlg.value = false
  wordsText.value = ''
  itemsPage.value = 1
  await loadItems()
}

onMounted(load)
</script>

<template>
  <div class="wrap">
    <div class="left">
      <div class="toolbar">
        <span>通用词库</span>
        <el-button size="small" type="success" @click="createDlg = true">+ 新建</el-button>
        <el-button size="small" @click="load">刷新</el-button>
      </div>
      <el-table v-loading="loading" :data="lists" border highlight-current-row
                style="width: 100%" @row-click="openItems">
        <el-table-column prop="name" label="词库" min-width="140" show-overflow-tooltip />
        <el-table-column prop="exam_level" label="层级" width="80" />
        <el-table-column prop="status" label="状态" width="90" />
      </el-table>
    </div>

    <div class="right">
      <div class="toolbar">
        <span>{{ current ? `「${current.name}」词条` : '选择左侧词库查看词条' }}</span>
        <el-button v-if="current" size="small" type="primary" @click="addDlg = true">+ 加词</el-button>
        <el-button v-if="isSyllabus(current)" size="small" type="warning" plain :loading="reflowing"
                   title="统计对应考试真题词频(整卷去重),写回频次/频档并补录未收录词" @click="reflowFromExam">
          从真题反哺频次
        </el-button>
      </div>
      <el-table v-if="current" v-loading="itemsLoading" :data="items" border style="width: 100%">
        <el-table-column prop="rank" label="考纲排名" width="86" />
        <el-table-column prop="word" label="词" min-width="150" show-overflow-tooltip />
        <el-table-column label="真题频次" width="92" align="center">
          <template #default="{ row }">
            <span v-if="row.frequency">{{ row.frequency }} 卷</span>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="频档" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.star >= 1" size="small" effect="light"
                    :type="row.star === 3 ? 'danger' : row.star === 2 ? 'warning' : 'info'">
              {{ ['', '低频', '中频', '高频'][row.star] }}
            </el-tag>
            <span v-else style="color:#c0c4cc">—</span>
          </template>
        </el-table-column>
        <el-table-column label="来自真题" width="98" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.added_from_exam" type="success" size="small" effect="plain">真题补录</el-tag>
            <el-tag v-else-if="row.frequency > 0" type="success" size="small" effect="light">是</el-tag>
            <span v-else style="color:#c0c4cc">否</span>
          </template>
        </el-table-column>
        <el-table-column prop="verified" label="已核" width="66" />
      </el-table>
      <div v-if="current && itemsTotal > itemsPageSize" style="display:flex;justify-content:flex-end;margin-top:12px">
        <el-pagination layout="total, prev, pager, next, jumper" :total="itemsTotal"
          :page-size="itemsPageSize" v-model:current-page="itemsPage" @current-change="loadItems" />
      </div>
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
.left { width: 42%; }
.right { flex: 1; }
.toolbar { margin-bottom: 12px; display: flex; align-items: center; gap: 10px; }
</style>

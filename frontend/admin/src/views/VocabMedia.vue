<script setup lang="ts">
import AppDialog from '../components/AppDialog.vue'
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listVocabMedia, generateVocabMedia, reviewVocabMedia, updateVocabMedia, deleteVocabWords, vocabTextbookOptions } from '../api/admin'
import type { AdminVocabMediaItem } from '../types'
import { Refresh, Cpu, CircleCheck, CircleClose, EditPen, VideoPlay, Search, Delete } from '@element-plus/icons-vue'

const rows = ref<AdminVocabMediaItem[]>([])
const total = ref(0)
const loading = ref(false)
const generating = ref<Record<string, boolean>>({})
const selected = ref<AdminVocabMediaItem[]>([])

// 筛选（服务端：搜索全库，非当前页）
const filterStatus = ref('draft')
const searchWord = ref('')
const fTextbook = ref('')
const fGrade = ref('')
const fSemester = ref('')
const opts = ref<{ textbook_versions: string[]; grades: string[]; semesters: string[] }>(
  { textbook_versions: [], grades: [], semesters: [] })
const page = ref(1)
const limit = 20

async function loadOptions() {
  try { opts.value = await vocabTextbookOptions() } catch { /* 静默 */ }
}

async function load() {
  loading.value = true
  try {
    const result = await listVocabMedia({
      media_status: filterStatus.value, q: searchWord.value || undefined,
      textbook: fTextbook.value || undefined, grade: fGrade.value || undefined,
      semester: fSemester.value || undefined,
      skip: (page.value - 1) * limit, limit,
    })
    rows.value = result.items
    total.value = result.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}
function reload() { page.value = 1; load() }

// 音频播放（内联）
let audioEl: HTMLAudioElement | null = null
function play(url: string | null) {
  if (!url) return
  try {
    if (audioEl) audioEl.pause()
    audioEl = new Audio(url)
    audioEl.play().catch(() => ElMessage.warning('音频播放失败'))
  } catch { ElMessage.warning('音频播放失败') }
}
function audioCount(row: AdminVocabMediaItem) {
  return (row.word_audio_url ? 1 : 0) + (row.en_desc_audio_url ? 1 : 0)
}

async function onGenerate(row: AdminVocabMediaItem) {
  generating.value[row.word_id] = true
  try {
    const result = await generateVocabMedia(row.word_id)
    ElMessage.success(`「${row.word}」媒体生成完成（草稿）`)
    patchRow(result)
    if (filterStatus.value && filterStatus.value !== result.media_status) {
      rows.value = rows.value.filter(r => r.word_id !== row.word_id)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value[row.word_id] = false
  }
}

async function onReview(row: AdminVocabMediaItem, approve: boolean) {
  try {
    const result = await reviewVocabMedia(row.word_id, approve)
    ElMessage.success(`「${row.word}」已${approve ? '发布' : '驳回'}`)
    patchRow(result)
    if (filterStatus.value === 'draft') rows.value = rows.value.filter(r => r.word_id !== row.word_id)
  } catch (e: any) {
    ElMessage.error(e?.message || '操作失败')
  }
}

// —— 批量操作 ——
const batch = ref({ running: false, total: 0, done: 0, ok: 0, failed: 0 })
async function batchGenerate() {
  if (!selected.value.length) return
  try {
    await ElMessageBox.confirm(
      `为选中的 ${selected.value.length} 个词生成媒体（英文描述 + 单词/描述发音 + 配图，会调用付费接口）。是否继续？`,
      '批量生成媒体', { type: 'warning' })
  } catch { return }
  const items = [...selected.value]
  batch.value = { running: true, total: items.length, done: 0, ok: 0, failed: 0 }
  for (const row of items) {
    try { patchRow(await generateVocabMedia(row.word_id)); batch.value.ok++ }
    catch { batch.value.failed++ }
    batch.value.done++
  }
  batch.value.running = false
  ElMessage.success(`批量生成完成：成功 ${batch.value.ok}${batch.value.failed ? `，失败 ${batch.value.failed}` : ''}`)
  load()
}
async function batchReview(approve: boolean) {
  if (!selected.value.length) return
  const label = approve ? '发布' : '驳回'
  try {
    await ElMessageBox.confirm(`批量${label}选中的 ${selected.value.length} 个词的媒体？`, label,
      { type: approve ? 'info' : 'warning' })
  } catch { return }
  let ok = 0
  for (const row of [...selected.value]) {
    try { await reviewVocabMedia(row.word_id, approve); ok++ } catch { /* 跳过失败项 */ }
  }
  ElMessage.success(`已${label} ${ok} 个`)
  selected.value = []
  load()
}
async function batchDelete() {
  if (!selected.value.length) return
  const n = selected.value.length
  try {
    await ElMessageBox.confirm(
      `彻底删除选中的 ${n} 个词条？将从整个词力通移除：词库词条 + 课程单元挂载 + 学生学习记录 + 媒体 + 词单。此操作不可恢复！`,
      '批量删除词条', { type: 'error', confirmButtonText: '确认删除', confirmButtonClass: 'el-button--danger' })
  } catch { return }
  try {
    const res = await deleteVocabWords(selected.value.map(r => r.word_id))
    ElMessage.success(`已删除 ${res.deleted} 个词条`)
    selected.value = []
    load()
  } catch (e: any) {
    ElMessage.error(e?.message || '删除失败')
  }
}

// 编辑弹窗
const editDialogVisible = ref(false)
const editingRow = ref<AdminVocabMediaItem | null>(null)
const editEnDesc = ref('')
const editImageUrls = ref('')
function openEdit(row: AdminVocabMediaItem) {
  editingRow.value = row
  editEnDesc.value = row.en_description ?? ''
  editImageUrls.value = (row.image_urls ?? []).join('\n')
  editDialogVisible.value = true
}
async function onSaveEdit() {
  if (!editingRow.value) return
  const urls = editImageUrls.value.split('\n').map(s => s.trim()).filter(Boolean)
  try {
    const result = await updateVocabMedia(editingRow.value.word_id, {
      en_description: editEnDesc.value || undefined,
      image_urls: urls.length ? urls : undefined,
    })
    ElMessage.success('保存成功')
    patchRow(result)
    editDialogVisible.value = false
  } catch (e: any) {
    ElMessage.error(e?.message || '保存失败')
  }
}

function patchRow(updated: AdminVocabMediaItem) {
  const idx = rows.value.findIndex(r => r.word_id === updated.word_id)
  if (idx !== -1) rows.value[idx] = updated
}

function statusTag(status: string): 'warning' | 'success' | 'info' {
  return status === 'draft' ? 'warning' : status === 'published' ? 'success' : 'info'
}
function statusLabel(status: string): string {
  return { draft: '草稿', published: '已发布', retired: '已驳回' }[status] ?? status
}

onMounted(() => { loadOptions(); load() })
</script>

<template>
  <div class="page">
    <!-- 筛选 + 批量工具栏 -->
    <div class="toolbar">
      <el-select v-model="filterStatus" style="width: 110px" @change="reload">
        <el-option label="全部状态" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="已发布" value="published" />
        <el-option label="已驳回" value="retired" />
      </el-select>
      <el-select v-model="fTextbook" placeholder="教材版本" clearable style="width: 130px" @change="reload">
        <el-option v-for="t in opts.textbook_versions" :key="t" :label="t" :value="t" />
      </el-select>
      <el-select v-model="fGrade" placeholder="年级" clearable style="width: 120px" @change="reload">
        <el-option v-for="g in opts.grades" :key="g" :label="g" :value="g" />
      </el-select>
      <el-select v-model="fSemester" placeholder="上/下册" clearable style="width: 100px" @change="reload">
        <el-option v-for="s in opts.semesters" :key="s" :label="s + '册'" :value="s" />
      </el-select>
      <el-input v-model="searchWord" placeholder="搜索单词（全库）" clearable style="width: 180px"
        :prefix-icon="Search" @keyup.enter="reload" @clear="reload" />
      <el-button :loading="loading" @click="reload"><el-icon><Refresh /></el-icon>&nbsp;刷新</el-button>

      <div class="spacer" />

      <template v-if="selected.length">
        <span class="sel-hint">已选 {{ selected.length }}</span>
        <el-button type="primary" :icon="Cpu" @click="batchGenerate">批量生成</el-button>
        <el-button type="success" :icon="CircleCheck" @click="batchReview(true)">批量发布</el-button>
        <el-button type="warning" plain :icon="CircleClose" @click="batchReview(false)">批量驳回</el-button>
        <el-button type="danger" :icon="Delete" @click="batchDelete">批量删除</el-button>
      </template>
      <span class="count">共 {{ total }} 个词</span>
    </div>

    <!-- 批量生成进度 -->
    <el-alert v-if="batch.running || (batch.total > 0 && batch.done < batch.total)" type="info" :closable="false" class="gen-bar">
      <template #title>
        批量生成中：{{ batch.done }} / {{ batch.total }}（成功 {{ batch.ok }}<span v-if="batch.failed">，失败 {{ batch.failed }}</span>）
        <el-progress :percentage="batch.total ? Math.round(batch.done / batch.total * 100) : 0" :stroke-width="10" style="margin-top:6px" />
      </template>
    </el-alert>

    <!-- 词列表 -->
    <el-table v-loading="loading" :data="rows" border style="width: 100%" row-key="word_id"
              @selection-change="(rs: AdminVocabMediaItem[]) => selected = rs">
      <el-table-column type="selection" width="44" reserve-selection />
      <el-table-column prop="word" label="单词" width="150" fixed="left" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.media_status)" size="small">{{ statusLabel(row.media_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="配图" width="130" align="center">
        <template #default="{ row }">
          <div v-if="row.image_urls?.length" class="thumbs">
            <el-image v-for="(u, i) in row.image_urls.slice(0, 3)" :key="i" :src="u"
              :preview-src-list="row.image_urls" :initial-index="i" fit="cover"
              class="thumb" preview-teleported hide-on-click-modal />
            <span v-if="row.image_urls.length > 3" class="more">+{{ row.image_urls.length - 3 }}</span>
          </div>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="发音" width="120" align="center">
        <template #default="{ row }">
          <el-button-group v-if="audioCount(row)">
            <el-tooltip content="单词发音" placement="top">
              <el-button size="small" :disabled="!row.word_audio_url" @click="play(row.word_audio_url)">
                <el-icon><VideoPlay /></el-icon>词
              </el-button>
            </el-tooltip>
            <el-tooltip content="描述发音" placement="top">
              <el-button size="small" :disabled="!row.en_desc_audio_url" @click="play(row.en_desc_audio_url)">
                <el-icon><VideoPlay /></el-icon>述
              </el-button>
            </el-tooltip>
          </el-button-group>
          <span v-else class="muted">—</span>
        </template>
      </el-table-column>
      <el-table-column label="英文描述" min-width="220" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.en_description" class="desc">{{ row.en_description }}</span>
          <span v-else class="muted">暂无</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right" align="center">
        <template #default="{ row }">
          <el-button size="small" :loading="generating[row.word_id]" @click="onGenerate(row)">
            <el-icon><Cpu /></el-icon>&nbsp;生成
          </el-button>
          <el-tooltip content="发布" placement="top">
            <el-button size="small" type="success" :icon="CircleCheck"
              :disabled="row.media_status === 'published'" @click="onReview(row, true)" />
          </el-tooltip>
          <el-tooltip content="驳回" placement="top">
            <el-button size="small" type="danger" plain :icon="CircleClose"
              :disabled="row.media_status === 'retired'" @click="onReview(row, false)" />
          </el-tooltip>
          <el-tooltip content="编辑描述/配图" placement="top">
            <el-button size="small" :icon="EditPen" @click="openEdit(row)" />
          </el-tooltip>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div class="pager">
      <el-pagination
        v-model:current-page="page" :page-size="limit" :total="total"
        layout="total, prev, pager, next, jumper" @current-change="load" />
    </div>

    <!-- 编辑弹窗 -->
    <AppDialog v-model="editDialogVisible" :title="`编辑：${editingRow?.word}`" width="560px">
      <el-form label-width="100px">
        <el-form-item label="英文描述">
          <el-input v-model="editEnDesc" type="textarea" :rows="4" placeholder="用英文描述单词含义…" />
        </el-form-item>
        <el-form-item label="图片 URLs">
          <el-input v-model="editImageUrls" type="textarea" :rows="3" placeholder="每行一条图片 URL" />
        </el-form-item>
        <el-form-item v-if="editImageUrls.trim()" label="预览">
          <div class="thumbs">
            <el-image v-for="(u, i) in editImageUrls.split('\n').map(s => s.trim()).filter(Boolean)" :key="i"
              :src="u" fit="cover" class="thumb-lg" preview-teleported
              :preview-src-list="editImageUrls.split('\n').map(s => s.trim()).filter(Boolean)" :initial-index="i" />
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSaveEdit">保存</el-button>
      </template>
    </AppDialog>
  </div>
</template>

<style scoped>
.page { padding: 4px; }
.toolbar { margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
.toolbar .spacer { flex: 1; }
.sel-hint { color: var(--el-color-primary); font-weight: 600; font-size: 13px; }
.count { color: #909399; font-size: 13px; }
.gen-bar { margin-bottom: 12px; }
.thumbs { display: flex; gap: 4px; align-items: center; justify-content: center; }
.thumb { width: 38px; height: 38px; border-radius: 4px; border: 1px solid var(--el-border-color-lighter); }
.thumb-lg { width: 72px; height: 72px; border-radius: 6px; border: 1px solid var(--el-border-color-lighter); }
.more { font-size: 12px; color: #909399; }
.muted { color: #c0c4cc; font-size: 13px; }
.desc { color: #606266; font-size: 13px; }
.pager { margin-top: 16px; display: flex; justify-content: flex-end; }
</style>

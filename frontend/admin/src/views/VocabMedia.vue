<script setup lang="ts">
import { onMounted, ref, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { listVocabMedia, generateVocabMedia, reviewVocabMedia, updateVocabMedia } from '../api/admin'
import type { AdminVocabMediaItem } from '../types'

const rows = ref<AdminVocabMediaItem[]>([])
const total = ref(0)
const loading = ref(false)
const generating = ref<Record<string, boolean>>({})

// 筛选
const filterStatus = ref('draft')
const searchWord = ref('')
const skip = ref(0)
const limit = 20

const filteredRows = computed(() => {
  if (!searchWord.value) return rows.value
  return rows.value.filter(r => r.word.includes(searchWord.value))
})

async function load() {
  loading.value = true
  try {
    const result = await listVocabMedia({ media_status: filterStatus.value, skip: skip.value, limit })
    rows.value = result.items
    total.value = result.total
  } catch (e: any) {
    ElMessage.error(e?.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function onGenerate(row: AdminVocabMediaItem) {
  generating.value[row.word_id] = true
  try {
    const result = await generateVocabMedia(row.word_id)
    ElMessage.success(`「${row.word}」媒体生成完成（草稿）`)
    patchRow(result)
    if (filterStatus.value !== 'draft' && filterStatus.value !== result.media_status) {
      rows.value = rows.value.filter(r => r.word_id !== row.word_id)
    }
  } catch (e: any) {
    ElMessage.error(e?.message || '生成失败')
  } finally {
    generating.value[row.word_id] = false
  }
}

async function onApprove(row: AdminVocabMediaItem) {
  try {
    const result = await reviewVocabMedia(row.word_id, true)
    ElMessage.success(`「${row.word}」已发布`)
    patchRow(result)
    if (filterStatus.value === 'draft') rows.value = rows.value.filter(r => r.word_id !== row.word_id)
  } catch (e: any) {
    ElMessage.error(e?.message || '审核失败')
  }
}

async function onReject(row: AdminVocabMediaItem) {
  try {
    const result = await reviewVocabMedia(row.word_id, false)
    ElMessage.success(`「${row.word}」已驳回`)
    patchRow(result)
    if (filterStatus.value === 'draft') rows.value = rows.value.filter(r => r.word_id !== row.word_id)
  } catch (e: any) {
    ElMessage.error(e?.message || '驳回失败')
  }
}

// 编辑弹窗
const editDialogVisible = ref(false)
const editingRow = ref<AdminVocabMediaItem | null>(null)
const editEnDesc = ref('')
const editImageUrls = ref('')  // 每行一条 URL

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
  else rows.value.unshift(updated)
}

function statusTag(status: string): 'warning' | 'success' | 'info' {
  if (status === 'draft') return 'warning'
  if (status === 'published') return 'success'
  return 'info'
}

function statusLabel(status: string): string {
  return { draft: '草稿', published: '已发布', retired: '已驳回' }[status] ?? status
}

onMounted(load)
</script>

<template>
  <div>
    <!-- 筛选工具栏 -->
    <div style="margin-bottom: 16px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;">
      <el-select v-model="filterStatus" placeholder="媒体状态" style="width: 120px" @change="() => { skip = 0; load() }">
        <el-option label="全部" value="" />
        <el-option label="草稿" value="draft" />
        <el-option label="已发布" value="published" />
        <el-option label="已驳回" value="retired" />
      </el-select>
      <el-input
        v-model="searchWord"
        placeholder="搜索单词"
        clearable
        style="width: 160px"
      />
      <el-button @click="load" :loading="loading">🔄 刷新</el-button>
      <span style="color: #909399; font-size: 13px;">
        共 {{ total }} 个词 · 当前显示 {{ filteredRows.length }} 个
      </span>
    </div>

    <!-- 词列表 -->
    <el-table v-loading="loading" :data="filteredRows" border style="width: 100%">
      <el-table-column prop="word" label="单词" width="140" />
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTag(row.media_status)" size="small">{{ statusLabel(row.media_status) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="英文描述" min-width="200" show-overflow-tooltip>
        <template #default="{ row }">
          <span v-if="row.en_description" style="color: #606266; font-size: 13px;">{{ row.en_description }}</span>
          <span v-else style="color: #c0c4cc; font-size: 13px;">暂无</span>
        </template>
      </el-table-column>
      <el-table-column label="图片" width="70" align="center">
        <template #default="{ row }">
          <span>{{ row.image_urls?.length ?? 0 }} 张</span>
        </template>
      </el-table-column>
      <el-table-column label="音频" width="80" align="center">
        <template #default="{ row }">
          <span>{{ (row.word_audio_url ? 1 : 0) + (row.en_desc_audio_url ? 1 : 0) }} / 2</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="240" fixed="right">
        <template #default="{ row }">
          <el-button size="small" :loading="generating[row.word_id]" @click="onGenerate(row)">🤖 生成</el-button>
          <el-button size="small" type="success" @click="onApprove(row)" :disabled="row.media_status === 'published'">✅</el-button>
          <el-button size="small" type="danger" plain @click="onReject(row)" :disabled="row.media_status === 'retired'">❌</el-button>
          <el-button size="small" @click="openEdit(row)">✏️</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 分页 -->
    <div style="margin-top: 16px; display: flex; justify-content: flex-end;">
      <el-pagination
        v-model:current-page="skip"
        :page-size="limit"
        :total="total"
        layout="prev, pager, next, total"
        @current-change="(p: number) => { skip = (p - 1) * limit; load() }"
      />
    </div>

    <!-- 编辑弹窗 -->
    <el-dialog v-model="editDialogVisible" :title="`编辑：${editingRow?.word}`" width="520px">
      <el-form label-width="100px">
        <el-form-item label="英文描述">
          <el-input v-model="editEnDesc" type="textarea" :rows="4" placeholder="用英文描述单词含义…" />
        </el-form-item>
        <el-form-item label="图片 URLs">
          <el-input v-model="editImageUrls" type="textarea" :rows="3" placeholder="每行一条图片 URL" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="onSaveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

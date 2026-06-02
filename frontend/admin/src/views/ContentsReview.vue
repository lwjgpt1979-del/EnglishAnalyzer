<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listContents, reviewContent, updateContent } from '../api/admin'
import type { AdminContentItem, ReviewStatus } from '../types'

const status = ref<ReviewStatus>('draft')
const rows = ref<AdminContentItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const statusOptions: ReviewStatus[] = ['draft', 'reviewing', 'published', 'retired']

// 编辑弹窗
const editVisible = ref(false)
const editing = reactive({ id: '', content_md: '' })

async function load() {
  loading.value = true
  try {
    const data = await listContents({
      status: status.value,
      skip: (page.value - 1) * pageSize,
      limit: pageSize,
    })
    rows.value = data.items
    total.value = data.total
  } finally {
    loading.value = false
  }
}

function openEdit(row: AdminContentItem) {
  editing.id = row.id
  editing.content_md = row.content_md
  editVisible.value = true
}

async function saveEdit() {
  await updateContent(editing.id, { content_md: editing.content_md })
  ElMessage.success('已保存')
  editVisible.value = false
  await load()
}

async function onReview(row: AdminContentItem, approve: boolean) {
  await ElMessageBox.confirm(
    `确认${approve ? '通过' : '驳回'}这条内容？`, '确认', { type: 'warning' },
  )
  await reviewContent(row.id, approve)
  ElMessage.success(approve ? '已通过并发布' : '已驳回')
  await load()
}

function onStatusChange() {
  page.value = 1
  load()
}

onMounted(load)
</script>

<template>
  <div>
    <div class="toolbar">
      <span>状态：</span>
      <el-select v-model="status" style="width: 160px" @change="onStatusChange">
        <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
      </el-select>
      <el-button style="margin-left: 12px" @click="load">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="rows" border style="width: 100%">
      <el-table-column prop="dimension" label="维度" width="110" />
      <el-table-column prop="content_md" label="正文" min-width="320" show-overflow-tooltip />
      <el-table-column prop="generated_by" label="来源" width="170" />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="230" fixed="right">
        <template #default="{ row }">
          <el-button size="small" @click="openEdit(row)">编辑</el-button>
          <el-button size="small" type="success" @click="onReview(row, true)">通过</el-button>
          <el-button size="small" type="danger" @click="onReview(row, false)">驳回</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      style="margin-top: 16px; justify-content: flex-end"
      layout="total, prev, pager, next"
      :total="total" :page-size="pageSize" :current-page="page"
      @current-change="(p: number) => { page = p; load() }"
    />

    <el-dialog v-model="editVisible" title="编辑内容正文" width="640px">
      <el-input v-model="editing.content_md" type="textarea" :rows="14" placeholder="Markdown 正文" />
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; }
</style>

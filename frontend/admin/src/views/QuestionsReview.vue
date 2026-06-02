<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { listQuestions, reviewQuestion } from '../api/admin'
import type { AdminQuestionItem, ReviewStatus } from '../types'

const status = ref<ReviewStatus>('draft')
const rows = ref<AdminQuestionItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

const statusOptions: ReviewStatus[] = ['draft', 'reviewing', 'published', 'retired']

async function load() {
  loading.value = true
  try {
    const data = await listQuestions({
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

async function onReview(row: AdminQuestionItem, approve: boolean) {
  await ElMessageBox.confirm(
    `确认${approve ? '通过' : '驳回'}这道题？`, '确认', { type: 'warning' },
  )
  await reviewQuestion(row.id, approve)
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
      <el-table-column prop="question_type" label="题型" width="80" />
      <el-table-column prop="dimension" label="维度" width="100" />
      <el-table-column prop="stem" label="题干" min-width="240" show-overflow-tooltip />
      <el-table-column prop="answer" label="答案" width="120" show-overflow-tooltip />
      <el-table-column prop="explanation" label="解析" min-width="180" show-overflow-tooltip />
      <el-table-column prop="difficulty" label="难度" width="70" />
      <el-table-column prop="status" label="状态" width="90" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
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
  </div>
</template>

<style scoped>
.toolbar { margin-bottom: 16px; display: flex; align-items: center; }
</style>

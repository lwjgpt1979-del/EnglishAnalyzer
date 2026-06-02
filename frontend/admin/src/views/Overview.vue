<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getOverview } from '../api/admin'
import type { AdminOverview } from '../types'

const data = ref<AdminOverview | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await getOverview()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <h2 class="page-title">数据大盘</h2>

    <el-row :gutter="16">
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="待审仿真题（draft）" :value="data?.questions_by_status.draft ?? 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="待审知识点内容（draft）" :value="data?.contents_by_status.draft ?? 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="用户总数" :value="data?.total_users ?? 0" />
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card shadow="hover">
          <el-statistic title="已支付订单" :value="data?.paid_orders ?? 0" />
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>仿真题各状态</template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="draft">{{ data?.questions_by_status.draft ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="reviewing">{{ data?.questions_by_status.reviewing ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="published">{{ data?.questions_by_status.published ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="retired">{{ data?.questions_by_status.retired ?? 0 }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
      <el-col :span="12">
        <el-card shadow="never">
          <template #header>知识点内容各状态</template>
          <el-descriptions :column="2" border>
            <el-descriptions-item label="draft">{{ data?.contents_by_status.draft ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="reviewing">{{ data?.contents_by_status.reviewing ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="published">{{ data?.contents_by_status.published ?? 0 }}</el-descriptions-item>
            <el-descriptions-item label="retired">{{ data?.contents_by_status.retired ?? 0 }}</el-descriptions-item>
          </el-descriptions>
        </el-card>
      </el-col>
    </el-row>

    <el-button style="margin-top: 16px" @click="load">刷新</el-button>
  </div>
</template>

<style scoped>
.page-title { margin: 0 0 16px; font-size: 20px; color: #303133; }
</style>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { getLearningCenter, type LearningCenter } from '../api/institution'

const data = ref<LearningCenter | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try { data.value = await getLearningCenter() }
  catch (e: any) { ElMessage.error(e?.message || '加载失败') }
  finally { loading.value = false }
}
onMounted(load)
</script>

<template>
  <div v-loading="loading">
    <h2 class="page-title">学情数据中心</h2>
    <p class="hint">名下学生近 30 天的活跃与薄弱情况，用于机构健康度运营（5B.4）。</p>

    <el-row :gutter="16">
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="学生总数" :value="data?.total_students ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="近30天活跃" :value="data?.active_30d ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover" :class="(data?.active_rate_pct ?? 0) < 50 ? 'card-warn' : ''"><el-statistic title="活跃率(%)" :value="data?.active_rate_pct ?? 0" /></el-card></el-col>
      <el-col :span="6"><el-card shadow="hover"><el-statistic title="近30天打卡人数" :value="data?.checkin_students_30d ?? 0" /></el-card></el-col>
    </el-row>

    <el-card shadow="never" style="margin-top: 16px">
      <template #header>名下学生薄弱知识点 Top（正确率低，涉及学生数）</template>
      <el-table :data="data?.weak_kp_top || []" stripe>
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="kp_key" label="知识点" min-width="200" />
        <el-table-column prop="description" label="说明" min-width="240" show-overflow-tooltip />
        <el-table-column prop="student_count" label="涉及学生" width="120" />
      </el-table>
      <el-empty v-if="!(data?.weak_kp_top || []).length" description="暂无薄弱知识点数据" />
    </el-card>

    <el-button style="margin-top: 16px" @click="load">刷新</el-button>
  </div>
</template>

<style scoped>
.page-title { margin: 0 0 6px; font-size: 20px; color: #303133; }
.hint { color: #909399; font-size: 13px; margin: 0 0 16px; }
.card-warn :deep(.el-statistic__number) { color: #e6a23c; }
</style>

<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { getOverview } from '../api/institution'

const data = reactive({ teacher_count: 0, student_count: 0, member_count: 0, active_7d_count: 0 })

onMounted(async () => {
  Object.assign(data, await getOverview())
})
</script>

<template>
  <div class="overview">
    <h2 class="title">机构概览</h2>
    <el-row :gutter="16">
      <el-col :span="6">
        <el-card><div class="label">老师数</div><div class="num">{{ data.teacher_count }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card><div class="label">学生数</div><div class="num">{{ data.student_count }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card><div class="label">付费会员</div><div class="num">{{ data.member_count }}</div></el-card>
      </el-col>
      <el-col :span="6">
        <el-card><div class="label">近 7 日活跃</div><div class="num">{{ data.active_7d_count }}</div></el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.label { color: #888; font-size: 14px; }
.num { font-size: 32px; font-weight: 700; margin-top: 8px; }
</style>

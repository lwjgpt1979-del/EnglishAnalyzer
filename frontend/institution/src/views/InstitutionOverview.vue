<script setup lang="ts">
import { onMounted, reactive } from 'vue'
import { getOverview } from '../api/institution'

const data = reactive({
  teacher_count: 0, student_count: 0, member_count: 0, active_7d_count: 0,
  expiring_30d_count: 0, month_purchase_fen: 0,
  tier_distribution: { basic: 0, pro: 0, promax: 0 } as Record<string, number>,
})

onMounted(async () => {
  Object.assign(data, await getOverview())
})
</script>

<template>
  <div class="overview">
    <h2 class="title">机构概览</h2>
    <el-row :gutter="16">
      <el-col :span="6"><el-card><div class="label">老师数</div><div class="num">{{ data.teacher_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">学生数</div><div class="num">{{ data.student_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">付费会员</div><div class="num">{{ data.member_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">近 7 日活跃</div><div class="num">{{ data.active_7d_count }}</div></el-card></el-col>
    </el-row>
    <el-row :gutter="16" style="margin-top: 16px">
      <el-col :span="6"><el-card><div class="label">近 30 天到期</div><div class="num">{{ data.expiring_30d_count }}</div></el-card></el-col>
      <el-col :span="6"><el-card><div class="label">本月采购额(元)</div><div class="num">{{ (data.month_purchase_fen / 100).toFixed(2) }}</div></el-card></el-col>
      <el-col :span="12">
        <el-card>
          <div class="label">会员档位分布</div>
          <div class="tiers">
            <span>基础 {{ data.tier_distribution.basic }}</span>
            <span>Pro {{ data.tier_distribution.pro }}</span>
            <span>ProMax {{ data.tier_distribution.promax }}</span>
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.label { color: #888; font-size: 14px; }
.num { font-size: 32px; font-weight: 700; margin-top: 8px; }
.tiers { display: flex; gap: 32px; font-size: 20px; font-weight: 600; margin-top: 12px; }
</style>

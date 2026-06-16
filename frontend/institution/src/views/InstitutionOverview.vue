<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { getOverview, getMyPackage, type MyPackage } from '../api/institution'

const data = reactive({
  teacher_count: 0, student_count: 0, member_count: 0, active_7d_count: 0,
  expiring_30d_count: 0, month_purchase_fen: 0,
  tier_distribution: { basic: 0, pro: 0, promax: 0 } as Record<string, number>,
})
const pkg = ref<MyPackage | null>(null)

onMounted(async () => {
  Object.assign(data, await getOverview())
  try { pkg.value = await getMyPackage() } catch { /* ignore */ }
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

    <!-- 机构套餐 + 池用量（§9.1，只读）-->
    <el-card v-if="pkg && pkg.package_tier" style="margin-top: 16px">
      <template #header>
        我的套餐：{{ pkg.package_name }}<span v-if="pkg.is_custom">（定制）</span>
        <span class="reset">每月 {{ pkg.reset_day }} 号重置</span>
      </template>
      <div class="pool-row" v-for="b in [
        { label: '老师席位', d: pkg.teacher_seats },
        { label: '本月出卷池', d: pkg.paper },
        { label: '本月批改池', d: pkg.grading },
      ]" :key="b.label">
        <span class="pl">{{ b.label }}</span>
        <el-progress :percentage="b.d && b.d.limit ? Math.min(100, Math.round(b.d.used / b.d.limit * 100)) : 0"
          :status="b.d && b.d.remaining_pct < (pkg.warn_threshold_pct || 20) ? 'warning' : ''" style="flex:1" />
        <span class="pn">{{ b.d?.used }}/{{ b.d?.limit }}</span>
      </div>
      <p class="pool-hint">额度由平台按套餐分配，机构内老师共享；如需调整请联系平台。</p>
    </el-card>
  </div>
</template>

<style scoped>
.title { margin: 0 0 16px; font-size: 18px; }
.label { color: #888; font-size: 14px; }
.num { font-size: 32px; font-weight: 700; margin-top: 8px; }
.tiers { display: flex; gap: 32px; font-size: 20px; font-weight: 600; margin-top: 12px; }
.reset { font-size: 12px; color: #909399; margin-left: 12px; font-weight: 400; }
.pool-row { display: flex; align-items: center; gap: 12px; margin: 10px 0; }
.pl { width: 110px; font-size: 14px; color: #606266; }
.pn { width: 90px; text-align: right; font-size: 13px; color: #606266; }
.pool-hint { color: #909399; font-size: 12px; margin-top: 8px; }
</style>

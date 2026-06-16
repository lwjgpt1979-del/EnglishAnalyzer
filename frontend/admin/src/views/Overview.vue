<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getOverview, getDashboard, type DashboardData } from '../api/admin'
import type { AdminOverview } from '../types'

const data = ref<AdminOverview | null>(null)
const dash = ref<DashboardData | null>(null)
const loading = ref(false)

const ROLE: Record<string, string> = { student: '学生', teacher: '教师', relative: '家长', institution_admin: '机构管理员', branch_admin: '分公司管理员', platform_admin: '平台管理员' }
const TIER: Record<string, string> = { free: '免费', basic: '基础', pro: 'Pro', promax: 'ProMax' }
const USAGE: Record<string, string> = { checkins: '词力通打卡', practice: 'AI练习', wrong_upload: '错题上传', essays: '作文精修', shadow: '跟读' }

async function load() {
  loading.value = true
  try {
    [data.value, dash.value] = await Promise.all([getOverview(), getDashboard()])
  } finally {
    loading.value = false
  }
}

function barH(c: number): number {
  const max = Math.max(1, ...(dash.value?.active.trend_7d.map(t => t.count) || [1]))
  return Math.round((c / max) * 80)
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
      <el-col :span="6">
        <el-card shadow="hover" :class="(data?.pending_teachers ?? 0) > 0 ? 'card-warn' : ''">
          <el-statistic title="待审教师认证" :value="data?.pending_teachers ?? 0">
            <template #suffix>
              <router-link v-if="(data?.pending_teachers ?? 0) > 0" to="/teacher-cert" style="font-size:13px;margin-left:6px;">去审核→</router-link>
            </template>
          </el-statistic>
        </el-card>
      </el-col>
    </el-row>

    <!-- ── 活跃（DAU/MAU/趋势，§5.5）── -->
    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="DAU(今日活跃)" :value="dash.active.dau" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="MAU(近30天)" :value="dash.active.mau" /></el-card></el-col>
      <el-col :span="16"><el-card shadow="hover">
        <template #header>近 7 天活跃趋势</template>
        <div class="trend">
          <div v-for="t in dash.active.trend_7d" :key="t.date" class="trend-bar">
            <div class="tb-fill" :style="{ height: barH(t.count) + 'px' }"></div>
            <div class="tb-num">{{ t.count }}</div>
            <div class="tb-date">{{ t.date.slice(5) }}</div>
          </div>
        </div>
      </el-card></el-col>
    </el-row>

    <!-- ── 数据大盘深化（§5.5）── -->
    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="本月GMV(元)" :value="dash.revenue.gmv_month_yuan" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="今日GMV(元)" :value="dash.revenue.gmv_today_yuan" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="付费会员数" :value="dash.membership.paid_members" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="付费转化率(%)" :value="dash.membership.pay_conversion_pct" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="本月退款率(%)" :value="dash.revenue.refund_rate_pct" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="在驻机构" :value="dash.institution.active" /></el-card></el-col>
    </el-row>

    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="4"><el-card shadow="hover" :class="dash.feedback.pending > 0 ? 'card-warn' : ''">
        <el-statistic title="待处理内容反馈" :value="dash.feedback.pending">
          <template #suffix><router-link v-if="dash.feedback.pending > 0" to="/content-feedback" style="font-size:13px;margin-left:6px">去处理→</router-link></template>
        </el-statistic>
      </el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="本月诊断报错" :value="dash.feedback.diagnosis" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="本月题目报错" :value="dash.feedback.question" /></el-card></el-col>
    </el-row>

    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="今日新增用户" :value="dash.users.new_today" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="近7天新增" :value="dash.users.new_7d" /></el-card></el-col>
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="近30天新增" :value="dash.users.new_30d" /></el-card></el-col>
      <el-col :span="12"><el-card shadow="hover">
        <template #header>各档位有效会员</template>
        <el-space wrap>
          <el-tag v-for="(c, t) in dash.membership.active_by_tier" :key="t" type="success">{{ TIER[t] || t }}：{{ c }}</el-tag>
        </el-space>
      </el-card></el-col>
    </el-row>

    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="8"><el-card shadow="never">
        <template #header>用户角色分布</template>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item v-for="(c, r) in dash.users.roles" :key="r" :label="ROLE[r] || r">{{ c }}</el-descriptions-item>
        </el-descriptions>
      </el-card></el-col>
      <el-col :span="8"><el-card shadow="never">
        <template #header>今日核心功能使用</template>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item v-for="(c, k) in dash.usage_today" :key="k" :label="USAGE[k] || k">{{ c }}</el-descriptions-item>
        </el-descriptions>
      </el-card></el-col>
      <el-col :span="8"><el-card shadow="never">
        <template #header>地区 Top（城市编码）</template>
        <el-descriptions :column="1" border size="small">
          <el-descriptions-item v-for="r in dash.users.regions_top" :key="r.city_code" :label="r.city_code">{{ r.count }}</el-descriptions-item>
          <el-descriptions-item v-if="!dash.users.regions_top.length" label="（暂无）">-</el-descriptions-item>
        </el-descriptions>
      </el-card></el-col>
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
.trend { display: flex; align-items: flex-end; gap: 12px; height: 120px; }
.trend-bar { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: flex-end; }
.tb-fill { width: 60%; background: linear-gradient(180deg,#79bbff,#409eff); border-radius: 4px 4px 0 0; min-height: 2px; }
.tb-num { font-size: 12px; color: #606266; margin-top: 4px; }
.tb-date { font-size: 11px; color: #909399; }
</style>

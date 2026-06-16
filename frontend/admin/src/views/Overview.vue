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
      <el-col :span="4"><el-card shadow="hover"><el-statistic title="本月ARPU(元)" :value="dash.revenue.arpu_month_yuan" /></el-card></el-col>
    </el-row>

    <!-- ── 内容与产品质量（§5.5）── -->
    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="6"><el-card shadow="hover">
        <el-statistic title="错题复盘率(%)" :value="dash.content_quality.review_rate.rate_pct" />
        <div class="muted">已掌握 {{ dash.content_quality.review_rate.mastered }} / {{ dash.content_quality.review_rate.total }} · 验证{{ dash.content_quality.review_rate.by_review }} 手动{{ dash.content_quality.review_rate.by_manual }}</div>
      </el-card></el-col>
      <el-col :span="6"><el-card shadow="hover">
        <el-statistic title="OCR成功率·错题(%)" :value="dash.content_quality.ocr_success.wrong_questions.rate_pct" />
        <div class="muted">{{ dash.content_quality.ocr_success.wrong_questions.completed }} / {{ dash.content_quality.ocr_success.wrong_questions.total }}</div>
      </el-card></el-col>
      <el-col :span="6"><el-card shadow="hover">
        <el-statistic title="OCR成功率·整卷(%)" :value="dash.content_quality.ocr_success.uploaded_papers.rate_pct" />
        <div class="muted">{{ dash.content_quality.ocr_success.uploaded_papers.completed }} / {{ dash.content_quality.ocr_success.uploaded_papers.total }}</div>
      </el-card></el-col>
      <el-col :span="6"><el-card shadow="hover">
        <el-statistic title="机构账号续费率(%)" :value="dash.institution.renewal.rate_pct" />
        <div class="muted">复购 {{ dash.institution.renewal.institutions_repurchased }} / {{ dash.institution.renewal.institutions_purchased }} 家（近似）</div>
      </el-card></el-col>
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

    <!-- ── 增长分析（§5.5）：渠道来源 / 续费率 / 转化漏斗 ── -->
    <el-row v-if="dash" :gutter="16" style="margin-top: 16px">
      <el-col :span="8"><el-card shadow="never">
        <template #header>渠道来源分布（学生）</template>
        <div v-for="c in dash.growth.channels.items" :key="c.channel" class="ch-row">
          <span class="ch-label">{{ c.label }}</span>
          <div class="ch-bar"><div class="ch-fill" :style="{ width: c.pct + '%' }"></div></div>
          <span class="ch-val">{{ c.count }}（{{ c.pct }}%）</span>
        </div>
        <div v-if="!dash.growth.channels.items.length" class="muted">暂无数据</div>
      </el-card></el-col>

      <el-col :span="8"><el-card shadow="never">
        <template #header>续费率（近 {{ dash.growth.renewal.days }} 天）· 总 {{ dash.growth.renewal.overall_rate_pct }}%</template>
        <el-table :data="dash.growth.renewal.by_tier" size="small" :show-header="true">
          <el-table-column label="档位"><template #default="{ row }">{{ TIER[row.tier] || row.tier }}</template></el-table-column>
          <el-table-column prop="expiring" label="到期" width="70" />
          <el-table-column prop="renewed" label="续费" width="70" />
          <el-table-column label="续费率" width="90"><template #default="{ row }">{{ row.rate_pct }}%</template></el-table-column>
        </el-table>
        <div class="muted" style="margin-top:6px">分母=窗口内到期会员数，分子=已支付续费订单数（近似口径）</div>
      </el-card></el-col>

      <el-col :span="8"><el-card shadow="never">
        <template #header>会员转化漏斗</template>
        <div v-for="s in dash.growth.funnel.stages" :key="s.key" class="fn-row">
          <span class="fn-label">{{ s.label }}</span>
          <div class="fn-bar"><div class="fn-fill" :style="{ width: Math.max(2, s.pct_of_registered) + '%' }">{{ s.count }}</div></div>
          <span class="fn-val">{{ s.pct_of_registered }}%<span class="muted" v-if="s.key !== 'registered'"> · 环比{{ s.pct_of_prev }}%</span></span>
        </div>
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
.muted { color: #909399; font-size: 12px; }
.ch-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.ch-label { width: 72px; font-size: 13px; color: #606266; }
.ch-bar { flex: 1; height: 14px; background: #f0f2f5; border-radius: 7px; overflow: hidden; }
.ch-fill { height: 100%; background: linear-gradient(90deg,#79bbff,#409eff); border-radius: 7px; }
.ch-val { width: 96px; text-align: right; font-size: 12px; color: #606266; }
.fn-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.fn-label { width: 84px; font-size: 13px; color: #606266; }
.fn-bar { flex: 1; background: #f0f2f5; border-radius: 4px; overflow: hidden; }
.fn-fill { background: linear-gradient(90deg,#95d475,#67c23a); color: #fff; font-size: 12px; text-align: right; padding: 2px 6px; border-radius: 4px; min-width: 24px; box-sizing: border-box; }
.fn-val { width: 130px; text-align: right; font-size: 12px; color: #606266; }
</style>

<!-- src/pages/diagnosis/index.vue -->
<template>
  <view class="diag-page">
    <view v-if="loading" class="center-tip">生成报告中…</view>
    <view v-else-if="!report" class="center-tip">暂无数据</view>
    <view v-else>

      <!-- 总览卡片 -->
      <view class="card overview">
        <view class="stat-row">
          <view class="stat-item">
            <text class="stat-num">{{ report.total_questions }}</text>
            <text class="stat-label">累计错题</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ report.total_analyzed }}</text>
            <text class="stat-label">已分析</text>
          </view>
          <view class="stat-item">
            <text class="stat-num">{{ (report.mastery_rate * 100).toFixed(0) }}%</text>
            <text class="stat-label">掌握率</text>
          </view>
        </view>
      </view>

      <!-- 我的班级排名（学生端百分位，不显示他人姓名） -->
      <view class="card rank-card" v-if="examRank && examRank.ranked">
        <view class="card-title">我的班级排名</view>
        <view class="rank-hero">
          <text class="rank-num">第 {{ examRank.my_rank }} 名</text>
          <text class="rank-total">/ {{ examRank.total_ranked }} 人</text>
        </view>
        <text class="rank-pct" v-if="examRank.percentile !== null">
          超过班级 {{ Math.round(examRank.percentile * 100) }}% 的同学
        </text>
        <view class="rank-compare">
          <view class="rank-compare-item">
            <text class="rank-compare-label">我的平均</text>
            <text class="rank-compare-val" :class="accClass(examRank.my_avg_accuracy || 0)">
              {{ ((examRank.my_avg_accuracy || 0) * 100).toFixed(0) }}%
            </text>
          </view>
          <view class="rank-compare-item">
            <text class="rank-compare-label">班级平均</text>
            <text class="rank-compare-val">
              {{ ((examRank.class_avg_accuracy || 0) * 100).toFixed(0) }}%
            </text>
          </view>
        </view>
        <text class="rank-hint">基于模拟考平均正确率排名 · 仅展示你的名次，保护同学隐私</text>
      </view>

      <!-- 高频错误类型（CSS 进度条） -->
      <view class="card" v-if="report.top_error_types.length > 0">
        <view class="card-title">高频错误类型 TOP 5</view>
        <view
          v-for="item in report.top_error_types.slice(0, 5)"
          :key="item.error_type"
          class="bar-item"
        >
          <text class="bar-label">{{ item.error_type }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :style="{ width: barWidth(item.count, maxErrorCount) + '%' }"
            />
          </view>
          <text class="bar-count">{{ item.count }}</text>
        </view>
      </view>

      <!-- 薄弱知识点 -->
      <view class="card" v-if="report.top_weak_knowledge_points.length > 0">
        <view class="card-title">薄弱知识点</view>
        <view class="tags">
          <text
            v-for="kp in report.top_weak_knowledge_points.slice(0, 8)"
            :key="kp.knowledge_point"
            class="tag-kp"
          >
            {{ kp.knowledge_point }}（{{ kp.count }}）
          </text>
        </view>
      </view>

      <!-- 知识点正确率（V2 练习/模拟考） -->
      <view class="card" v-if="kpAccuracy && kpAccuracy.items.length > 0">
        <view class="card-title">知识点正确率</view>
        <text class="acc-overall">
          累计作答 {{ kpAccuracy.total_attempts }} 次 · 总正确率 {{ (kpAccuracy.overall_accuracy * 100).toFixed(0) }}%
        </text>
        <view
          v-for="kp in kpAccuracy.items.slice(0, 10)"
          :key="kp.knowledge_point_id"
          class="bar-item"
        >
          <text class="bar-label">{{ kp.knowledge_point_name }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :class="accClass(kp.accuracy)"
              :style="{ width: Math.round(kp.accuracy * 100) + '%' }"
            />
          </view>
          <text class="bar-count">{{ (kp.accuracy * 100).toFixed(0) }}%</text>
        </view>
        <text class="acc-hint">弱项（正确率低）排在前面，建议优先练习</text>
      </view>

      <!-- 按学期掌握情况（M3 / D-094，来自练习作答记录） -->
      <view class="card" v-if="report.semester_dimension.length > 0">
        <view class="card-title">按学期掌握情况</view>
        <view
          v-for="sem in report.semester_dimension"
          :key="sem.label"
          class="bar-item"
        >
          <text class="bar-label">{{ sem.label }}</text>
          <view class="bar-track">
            <view
              class="bar-fill"
              :class="accClass(sem.accuracy)"
              :style="{ width: Math.round(sem.accuracy * 100) + '%' }"
            />
          </view>
          <text class="bar-count">{{ (sem.accuracy * 100).toFixed(0) }}%</text>
        </view>
        <text class="acc-hint">基于各学期知识点练习作答统计</text>
      </view>

      <!-- 按知识点掌握情况（M3 / D-094，弱项高亮） -->
      <view class="card" v-if="report.kp_dimension.length > 0">
        <view class="card-title">按知识点掌握情况</view>
        <view
          v-for="kp in report.kp_dimension.slice(0, 10)"
          :key="kp.knowledge_point_id"
          class="kpdim-item"
          :class="{ 'kpdim-weak': kp.accuracy < 0.6 }"
        >
          <view class="kpdim-head">
            <text class="kpdim-name">{{ kp.knowledge_point_name }}</text>
            <text class="kpdim-acc" :class="accClass(kp.accuracy)">{{ (kp.accuracy * 100).toFixed(0) }}%</text>
          </view>
          <view class="bar-track">
            <view
              class="bar-fill"
              :class="accClass(kp.accuracy)"
              :style="{ width: Math.round(kp.accuracy * 100) + '%' }"
            />
          </view>
          <text class="kpdim-sub">作答 {{ kp.attempts }} 次 · 答对 {{ kp.correct }} 次</text>
        </view>
        <text class="acc-hint">弱项（正确率低于 60%）已高亮，建议优先攻克</text>
      </view>

      <!-- 模拟考成绩趋势 + 历史 -->
      <view class="card" v-if="examHistory && examHistory.items.length > 0">
        <view class="card-title">模拟考成绩趋势</view>

        <!-- CSS 柱状趋势图（左旧右新，高度=正确率） -->
        <view class="trend-chart" v-if="examTrend.length > 1">
          <view
            v-for="(pt, i) in examTrend"
            :key="pt.id"
            class="trend-col"
          >
            <view class="trend-bar-wrap">
              <text class="trend-val">{{ Math.round(pt.accuracy * 100) }}</text>
              <view
                class="trend-bar"
                :class="accClass(pt.accuracy)"
                :style="{ height: Math.max(pt.accuracy * 100, 4) + '%' }"
              />
            </view>
            <text class="trend-x">{{ i + 1 }}</text>
          </view>
        </view>
        <text class="trend-hint" v-if="examTrend.length > 1">
          横轴为第几场模拟考（左早右新）· 纵轴为正确率
        </text>
        <text class="trend-hint" v-else>再考一场即可看到趋势曲线</text>

        <view class="exam-divider" />

        <view
          v-for="ex in examHistory.items"
          :key="ex.id"
          class="exam-row"
        >
          <text class="exam-date">{{ formatDate(ex.created_at) }}</text>
          <text class="exam-score">{{ ex.correct_count }}/{{ ex.total }}</text>
          <text class="exam-acc" :class="accClass(ex.accuracy)">{{ (ex.accuracy * 100).toFixed(0) }}%</text>
        </view>
      </view>

      <!-- 近30天活跃度方格 -->
      <view class="card">
        <view class="card-title">近30天提交</view>
        <view class="activity-grid">
          <view
            v-for="day in report.recent_daily_activity"
            :key="day.date"
            class="activity-cell"
            :class="activityClass(day.count)"
          />
        </view>
        <text class="activity-hint">颜色越深表示提交越多</text>
      </view>

      <!-- AI 学习建议 -->
      <view class="card" v-if="report.top_suggestions.length > 0">
        <view class="card-title">AI 学习建议</view>
        <view
          v-for="(s, i) in report.top_suggestions"
          :key="i"
          class="suggestion-item"
        >
          <text class="suggestion-num">{{ i + 1 }}</text>
          <text class="suggestion-text">{{ s }}</text>
        </view>
      </view>

      <!-- 针对薄弱点练习入口 -->
      <view class="card practice-entry">
        <view class="card-title">智能练习</view>
        <text class="practice-desc">基于你的薄弱知识点，AI 实时生成针对性练习题。</text>
        <button class="btn-practice" @tap="goPractice">开始 AI 练习</button>
      </view>

    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDiagnosisReport } from '@/api/diagnosis'
import { getKpAccuracy, getExamHistory, getExamRank } from '@/api/questions'
import { useAuthStore } from '@/stores/auth'
import type { DiagnosisReport, KPAccuracyOut, ExamHistoryOut, ExamRankOut } from '@/types/api'

const auth = useAuthStore()
const report = ref<DiagnosisReport | null>(null)
const kpAccuracy = ref<KPAccuracyOut | null>(null)
const examHistory = ref<ExamHistoryOut | null>(null)
const examRank = ref<ExamRankOut | null>(null)
const loading = ref(true)  // true until first fetch completes, prevents "暂无数据" flash

const maxErrorCount = computed(() => {
  if (!report.value || report.value.top_error_types.length === 0) return 1
  return Math.max(...report.value.top_error_types.map((e) => e.count))
})

// 趋势图按时间正序（最早→最新，左→右）；examHistory 本身最新在前，故反转
const examTrend = computed(() => {
  if (!examHistory.value) return []
  return examHistory.value.items
    .slice()
    .reverse()
    .map((ex) => ({ id: ex.id, accuracy: ex.accuracy }))
})

onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try {
    report.value = await getDiagnosisReport()
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    loading.value = false
  }
  // 知识点正确率独立拉取，失败不影响主报告
  try {
    kpAccuracy.value = await getKpAccuracy()
  } catch {
    kpAccuracy.value = null
  }
  // 模拟考成绩历史独立拉取，失败不影响主报告
  try {
    examHistory.value = await getExamHistory()
  } catch {
    examHistory.value = null
  }
  // 班级排名独立拉取，失败不影响主报告
  try {
    examRank.value = await getExamRank()
  } catch {
    examRank.value = null
  }
})

function formatDate(iso: string): string {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${m}-${day} ${hh}:${mm}`
}

function accClass(accuracy: number): string {
  if (accuracy < 0.6) return 'acc-low'
  if (accuracy < 0.85) return 'acc-mid'
  return 'acc-high'
}

function goPractice() {
  uni.navigateTo({ url: '/pages/practice/index' })
}

function barWidth(count: number, max: number): number {
  return max === 0 ? 0 : Math.round((count / max) * 100)
}

function activityClass(count: number): string {
  if (count === 0) return 'activity-0'
  if (count === 1) return 'activity-1'
  if (count <= 3) return 'activity-2'
  return 'activity-3'
}
</script>

<style scoped>
.diag-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 20rpx; color: var(--c-ink); }

/* 总览 */
.stat-row { display: flex; justify-content: space-around; }
.stat-item { text-align: center; }
.stat-num { font-size: 56rpx; font-weight: 800; color: var(--c-ink); display: block; }
.stat-label { font-size: 24rpx; color: var(--c-text-hint); }

/* 进度条 */
.bar-item { display: flex; align-items: center; margin-bottom: 16rpx; }
.bar-label { width: 160rpx; font-size: 26rpx; color: var(--c-text-body); flex-shrink: 0; }
.bar-track { flex: 1; background: var(--c-bg-soft); height: 16rpx; border-radius: var(--r-pill); margin: 0 16rpx; }
.bar-fill { height: 100%; background: var(--c-gold); border-radius: var(--r-pill); }
.bar-count { font-size: 24rpx; color: var(--c-text-second); width: 48rpx; text-align: right; }

/* 知识点正确率 */
.acc-overall { display: block; font-size: 24rpx; color: var(--c-text-second); margin-bottom: 20rpx; }
.acc-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.bar-fill.acc-low { background: var(--c-danger); }
.bar-fill.acc-mid { background: var(--c-gold); }
.bar-fill.acc-high { background: #2ecc71; }

/* 按知识点掌握情况（D-094） */
.kpdim-item { margin-bottom: 20rpx; padding: 16rpx; border-radius: var(--r-md); background: var(--c-bg-soft); }
.kpdim-item.kpdim-weak { background: #fdecea; }
.kpdim-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 10rpx; }
.kpdim-name { font-size: 26rpx; font-weight: 600; color: var(--c-ink); }
.kpdim-acc { font-size: 28rpx; font-weight: 700; }
.kpdim-acc.acc-low { color: var(--c-danger); }
.kpdim-acc.acc-mid { color: var(--c-gold); }
.kpdim-acc.acc-high { color: #2ecc71; }
.kpdim-sub { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }

/* 我的班级排名 */
.rank-card { }
.rank-hero { display: flex; align-items: baseline; }
.rank-num { font-size: 52rpx; font-weight: 800; color: var(--c-ink); }
.rank-total { font-size: 28rpx; color: var(--c-text-hint); margin-left: 12rpx; }
.rank-pct { display: block; font-size: 26rpx; color: var(--c-gold); font-weight: 600; margin-top: 8rpx; }
.rank-compare { display: flex; gap: 24rpx; margin-top: 20rpx; }
.rank-compare-item { flex: 1; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; text-align: center; }
.rank-compare-label { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 6rpx; }
.rank-compare-val { font-size: 36rpx; font-weight: 700; color: var(--c-ink); }
.rank-compare-val.acc-low { color: var(--c-danger); }
.rank-compare-val.acc-mid { color: var(--c-gold); }
.rank-compare-val.acc-high { color: #2ecc71; }
.rank-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 16rpx; line-height: 1.5; }

/* 模拟考成绩趋势图 */
.trend-chart { display: flex; align-items: flex-end; height: 200rpx; gap: 8rpx; padding: 8rpx 0; }
.trend-col { flex: 1; display: flex; flex-direction: column; align-items: center; height: 100%; }
.trend-bar-wrap { flex: 1; width: 100%; display: flex; flex-direction: column; justify-content: flex-end; align-items: center; }
.trend-val { font-size: 18rpx; color: var(--c-text-hint); margin-bottom: 4rpx; }
.trend-bar { width: 70%; max-width: 40rpx; border-radius: 6rpx 6rpx 0 0; background: var(--c-gold); transition: height 0.3s; }
.trend-bar.acc-low { background: var(--c-danger); }
.trend-bar.acc-mid { background: var(--c-gold); }
.trend-bar.acc-high { background: #2ecc71; }
.trend-x { font-size: 20rpx; color: var(--c-text-hint); margin-top: 6rpx; }
.trend-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.exam-divider { height: 1rpx; background: var(--c-bg-soft); margin: 20rpx 0; }

/* 模拟考成绩历史 */
.exam-row { display: flex; align-items: center; padding: 14rpx 0; border-bottom: 1rpx solid var(--c-bg-soft); }
.exam-row:last-child { border-bottom: none; }
.exam-date { flex: 1; font-size: 26rpx; color: var(--c-text-body); }
.exam-score { font-size: 26rpx; color: var(--c-text-second); margin-right: 24rpx; }
.exam-acc { font-size: 28rpx; font-weight: 700; width: 80rpx; text-align: right; }
.exam-acc.acc-low { color: var(--c-danger); }
.exam-acc.acc-mid { color: var(--c-gold); }
.exam-acc.acc-high { color: #2ecc71; }

/* 知识点标签 */
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp {
  background: #eaeac4;
  color: #6b6b2e;
  font-size: 24rpx;
  font-weight: 600;
  padding: 6rpx 16rpx;
  border-radius: var(--r-pill);
}

/* 活跃度方格 */
.activity-grid { display: flex; flex-wrap: wrap; gap: 6rpx; margin-bottom: 12rpx; }
.activity-cell { width: 28rpx; height: 28rpx; border-radius: 6rpx; }
.activity-0 { background: var(--c-bg-soft); }
.activity-1 { background: #fdf0b4; }
.activity-2 { background: var(--c-primary); }
.activity-3 { background: var(--c-gold); }
.activity-hint { font-size: 22rpx; color: var(--c-text-hint); }

/* 建议 */
.suggestion-item { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.suggestion-num {
  width: 44rpx;
  height: 44rpx;
  background: var(--c-primary);
  color: var(--c-ink);
  border-radius: 50%;
  font-size: 24rpx;
  font-weight: 700;
  line-height: 44rpx;
  text-align: center;
  flex-shrink: 0;
  margin-right: 16rpx;
}
.suggestion-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }

.practice-entry { }
.practice-desc { font-size: 24rpx; color: var(--c-text-second); display: block; margin-bottom: 12rpx; line-height: 1.5; }
.btn-practice { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 16rpx; font-size: 28rpx; font-weight: 700; text-align: center; }
</style>

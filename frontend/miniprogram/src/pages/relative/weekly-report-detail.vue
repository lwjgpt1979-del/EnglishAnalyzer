<!-- 家长端：学情周报详情页（V2 M32）
  数据来源：消息通知 meta 字段（weekly_report_service 写入）
  路由参数：?data=<JSON.stringify(meta)>
-->
<template>
  <view class="page">

    <!-- 顶部摘要卡片 -->
    <view class="summary-card">
      <view class="summary-head">
        <text class="student-name">{{ studentName }}</text>
        <text class="week-range">{{ weekRange }}</text>
      </view>

      <view class="stat-row">
        <view class="stat-item">
          <text class="stat-num" :class="checkinClass">{{ report.checkin_days }}</text>
          <text class="stat-den">/7</text>
          <text class="stat-lbl">打卡天数</text>
        </view>
        <view class="stat-divider" />
        <view class="stat-item">
          <text class="stat-num">{{ report.practice_count + report.wrong_paper_count }}</text>
          <text class="stat-lbl">做题总数</text>
        </view>
        <view class="stat-divider" />
        <view class="stat-item">
          <text class="stat-num streak">{{ report.max_streak }}</text>
          <text class="stat-lbl">最高连续</text>
        </view>
      </view>

      <!-- 打卡进度条 -->
      <view class="checkin-bar-wrap">
        <view class="checkin-bar">
          <view
            class="checkin-fill"
            :style="{ width: (report.checkin_days / 7 * 100) + '%' }"
            :class="checkinClass"
          />
        </view>
        <text class="checkin-hint">{{ checkinHint }}</text>
      </view>
    </view>

    <!-- 做题来源分布 -->
    <view class="card" v-if="report.practice_count + report.wrong_paper_count > 0">
      <view class="card-title">📝 做题来源</view>
      <view class="source-row">
        <view class="source-item">
          <text class="source-count">{{ report.practice_count }}</text>
          <text class="source-lbl">仿真练习</text>
        </view>
        <view class="source-item">
          <text class="source-count">{{ report.wrong_paper_count }}</text>
          <text class="source-lbl">整卷错题</text>
        </view>
      </view>
    </view>

    <!-- 薄弱知识点 -->
    <view class="card" v-if="report.weak_kp_names && report.weak_kp_names.length">
      <view class="card-title">⚠️ 本周薄弱点</view>
      <view class="kp-list">
        <view
          v-for="(kp, i) in report.weak_kp_names"
          :key="kp"
          class="kp-item"
          :class="i === 0 ? 'kp-top' : ''"
        >
          <text class="kp-rank">{{ i + 1 }}</text>
          <text class="kp-name">{{ kp }}</text>
          <text v-if="i === 0" class="kp-badge">最弱</text>
        </view>
      </view>
      <text class="kp-tip">建议孩子多做这几个知识点的练习题</text>
    </view>

    <!-- 空状态：本周零学习 -->
    <view class="card empty-card" v-if="report.checkin_days === 0 && report.practice_count === 0 && report.wrong_paper_count === 0">
      <text class="empty-emoji">😴</text>
      <text class="empty-text">孩子本周暂无学习记录</text>
      <text class="empty-sub">鼓励 TA 打开应用，从词力通打卡开始！</text>
    </view>

    <!-- 鼓励语 -->
    <view class="encourage-card">
      <text class="encourage-text">{{ encourageText }}</text>
    </view>

    <!-- 跳转按钮：查看完整学情 -->
    <view class="btn-wrap">
      <button class="btn-secondary" @tap="goStudentDiag">查看完整学情报告 →</button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

// ── 从路由参数解析周报数据 ─────────────────────────────────────────────────────
interface WeeklyReportMeta {
  student_id: string
  week_start: string
  week_end: string
  checkin_days: number
  practice_count: number
  wrong_paper_count: number
  max_streak: number
  weak_kp_names: string[]
}

const report = ref<WeeklyReportMeta>({
  student_id: '',
  week_start: '',
  week_end: '',
  checkin_days: 0,
  practice_count: 0,
  wrong_paper_count: 0,
  max_streak: 0,
  weak_kp_names: [],
})

const studentName = ref('孩子')
const notifTitle = ref('')

onMounted(() => {
  const pages = getCurrentPages()
  const current = pages[pages.length - 1]
  const opts = (current as any)?.options || {}

  if (opts.data) {
    try {
      const parsed = JSON.parse(decodeURIComponent(opts.data))
      report.value = parsed
    } catch { /* 解析失败用默认值 */ }
  }
  if (opts.student_name) {
    studentName.value = decodeURIComponent(opts.student_name)
  }
  if (opts.title) {
    notifTitle.value = decodeURIComponent(opts.title)
  }
})

// ── 计算属性 ───────────────────────────────────────────────────────────────────
const weekRange = computed(() => {
  const s = report.value.week_start
  const e = report.value.week_end
  if (!s || !e) return ''
  return `${s.slice(5)} ～ ${e.slice(5)}`  // MM-DD ～ MM-DD
})

const checkinClass = computed(() => {
  const d = report.value.checkin_days
  if (d >= 6) return 'excellent'
  if (d >= 4) return 'good'
  if (d >= 2) return 'fair'
  return 'poor'
})

const checkinHint = computed(() => {
  const d = report.value.checkin_days
  if (d === 7) return '完美！7 天全勤 🔥'
  if (d >= 5) return '非常棒，继续保持！'
  if (d >= 3) return '还不错，可以更努力哦'
  if (d >= 1) return '本周学习天数偏少，多鼓励一下 TA'
  return '本周没有打卡记录'
})

const encourageText = computed(() => {
  const d = report.value.checkin_days
  const q = report.value.practice_count + report.value.wrong_paper_count
  if (d >= 6 && q >= 10) return '🌟 本周表现优秀！坚持就是胜利，继续加油！'
  if (d >= 4) return '👍 学习态度不错！帮孩子把薄弱点补上，会有大进步。'
  if (q > 0) return '💪 做题量不错！建议每天保持打卡习惯，效果会更好。'
  return '📱 提醒孩子每天用 engGramer 打卡学习，一点一滴积累！'
})

// ── 跳转 ───────────────────────────────────────────────────────────────────────
function goStudentDiag() {
  const studentId = report.value.student_id
  if (studentId) {
    uni.navigateTo({ url: `/pages/relative/student-view?studentId=${studentId}` })
  }
}
</script>

<style scoped>
.page {
  padding: 24rpx;
  background: var(--c-bg-page, #f5f5f5);
  min-height: 100vh;
}

/* ── 摘要卡片 ── */
.summary-card {
  background: #fff;
  border-radius: 24rpx;
  padding: 40rpx 32rpx 36rpx;
  margin-bottom: 20rpx;
  box-shadow: 0 4rpx 24rpx rgba(0,0,0,0.06);
}
.summary-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 32rpx;
}
.student-name {
  font-size: 36rpx;
  font-weight: 800;
  color: #1a1a1a;
}
.week-range {
  font-size: 24rpx;
  color: #999;
}
.stat-row {
  display: flex;
  justify-content: space-around;
  align-items: center;
  margin-bottom: 32rpx;
}
.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;
}
.stat-num {
  font-size: 56rpx;
  font-weight: 900;
  color: #1a1a1a;
  line-height: 1;
}
.stat-num.excellent { color: #22c55e; }
.stat-num.good      { color: #f5c518; }
.stat-num.fair      { color: #f97316; }
.stat-num.poor      { color: #ef4444; }
.stat-num.streak    { color: #f97316; }
.stat-den {
  font-size: 28rpx;
  color: #bbb;
  font-weight: 600;
  margin-top: 4rpx;
}
.stat-lbl {
  font-size: 22rpx;
  color: #999;
}
.stat-divider {
  width: 2rpx;
  height: 60rpx;
  background: #f0f0f0;
}

/* 打卡进度条 */
.checkin-bar-wrap {
  display: flex;
  align-items: center;
  gap: 20rpx;
}
.checkin-bar {
  flex: 1;
  height: 16rpx;
  background: #f0f0f0;
  border-radius: 999rpx;
  overflow: hidden;
}
.checkin-fill {
  height: 100%;
  border-radius: 999rpx;
  transition: width 0.4s;
  background: #ccc;
}
.checkin-fill.excellent { background: #22c55e; }
.checkin-fill.good      { background: #f5c518; }
.checkin-fill.fair      { background: #f97316; }
.checkin-fill.poor      { background: #ef4444; }
.checkin-hint {
  font-size: 22rpx;
  color: #888;
  white-space: nowrap;
}

/* ── 通用卡片 ── */
.card {
  background: #fff;
  border-radius: 24rpx;
  padding: 32rpx;
  margin-bottom: 20rpx;
  box-shadow: 0 4rpx 16rpx rgba(0,0,0,0.04);
}
.card-title {
  font-size: 28rpx;
  font-weight: 700;
  color: #1a1a1a;
  margin-bottom: 24rpx;
}

/* ── 做题来源 ── */
.source-row {
  display: flex;
  justify-content: space-around;
}
.source-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8rpx;
}
.source-count {
  font-size: 48rpx;
  font-weight: 800;
  color: #1a1a1a;
}
.source-lbl {
  font-size: 24rpx;
  color: #999;
}

/* ── 薄弱知识点 ── */
.kp-list {
  display: flex;
  flex-direction: column;
  gap: 16rpx;
  margin-bottom: 20rpx;
}
.kp-item {
  display: flex;
  align-items: center;
  gap: 16rpx;
  padding: 16rpx 20rpx;
  background: #fafafa;
  border-radius: 16rpx;
}
.kp-item.kp-top {
  background: #fff8e0;
  border: 2rpx solid #f5c518;
}
.kp-rank {
  width: 36rpx;
  height: 36rpx;
  border-radius: 50%;
  background: #e0e0e0;
  color: #666;
  font-size: 22rpx;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  line-height: 36rpx;
}
.kp-item.kp-top .kp-rank {
  background: #f5c518;
  color: #1a1a1a;
}
.kp-name {
  flex: 1;
  font-size: 28rpx;
  color: #1a1a1a;
  font-weight: 600;
}
.kp-badge {
  font-size: 20rpx;
  color: #e8a800;
  background: #fff3c0;
  padding: 4rpx 12rpx;
  border-radius: 999rpx;
  font-weight: 700;
}
.kp-tip {
  font-size: 22rpx;
  color: #aaa;
  display: block;
  padding-top: 4rpx;
}

/* ── 空状态 ── */
.empty-card {
  text-align: center;
  padding: 60rpx 32rpx;
}
.empty-emoji {
  font-size: 80rpx;
  display: block;
  margin-bottom: 24rpx;
}
.empty-text {
  font-size: 30rpx;
  color: #666;
  font-weight: 600;
  display: block;
  margin-bottom: 12rpx;
}
.empty-sub {
  font-size: 26rpx;
  color: #aaa;
  display: block;
}

/* ── 鼓励语 ── */
.encourage-card {
  background: linear-gradient(135deg, #fff8e0, #fffef0);
  border-radius: 24rpx;
  padding: 28rpx 32rpx;
  margin-bottom: 20rpx;
  border: 2rpx solid #f5e090;
}
.encourage-text {
  font-size: 26rpx;
  color: #8a6800;
  line-height: 1.7;
  display: block;
}

/* ── 底部按钮 ── */
.btn-wrap {
  padding: 8rpx 0 40rpx;
}
.btn-secondary {
  width: 100%;
  background: #fff;
  color: #1a1a1a;
  border: 2rpx solid #e0e0e0;
  border-radius: 999rpx;
  font-size: 28rpx;
  font-weight: 600;
  padding: 24rpx 0;
}
</style>

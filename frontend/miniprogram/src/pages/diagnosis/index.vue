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
import { useAuthStore } from '@/stores/auth'
import type { DiagnosisReport } from '@/types/api'

const auth = useAuthStore()
const report = ref<DiagnosisReport | null>(null)
const loading = ref(true)  // true until first fetch completes, prevents "暂无数据" flash

const maxErrorCount = computed(() => {
  if (!report.value || report.value.top_error_types.length === 0) return 1
  return Math.max(...report.value.top_error_types.map((e) => e.count))
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
})

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
.diag-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx; color: #999; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx; }
.card-title { font-size: 30rpx; font-weight: bold; margin-bottom: 20rpx; color: #222; }

/* 总览 */
.stat-row { display: flex; justify-content: space-around; }
.stat-item { text-align: center; }
.stat-num { font-size: 56rpx; font-weight: bold; color: #1677ff; display: block; }
.stat-label { font-size: 24rpx; color: #999; }

/* 进度条 */
.bar-item { display: flex; align-items: center; margin-bottom: 16rpx; }
.bar-label { width: 160rpx; font-size: 26rpx; color: #333; flex-shrink: 0; }
.bar-track { flex: 1; background: #f0f0f0; height: 16rpx; border-radius: 8rpx; margin: 0 16rpx; }
.bar-fill { height: 100%; background: #1677ff; border-radius: 8rpx; }
.bar-count { font-size: 24rpx; color: #666; width: 48rpx; text-align: right; }

/* 知识点标签 */
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp {
  background: #f5f0ff;
  color: #722ed1;
  font-size: 24rpx;
  padding: 6rpx 16rpx;
  border-radius: 8rpx;
}

/* 活跃度方格 */
.activity-grid { display: flex; flex-wrap: wrap; gap: 6rpx; margin-bottom: 12rpx; }
.activity-cell { width: 28rpx; height: 28rpx; border-radius: 4rpx; }
.activity-0 { background: #eee; }
.activity-1 { background: #bce7ff; }
.activity-2 { background: #69c0ff; }
.activity-3 { background: #1677ff; }
.activity-hint { font-size: 22rpx; color: #bbb; }

/* 建议 */
.suggestion-item { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.suggestion-num {
  width: 44rpx;
  height: 44rpx;
  background: #1677ff;
  color: #fff;
  border-radius: 50%;
  font-size: 24rpx;
  line-height: 44rpx;
  text-align: center;
  flex-shrink: 0;
  margin-right: 16rpx;
}
.suggestion-text { flex: 1; font-size: 28rpx; color: #333; line-height: 1.7; }

.practice-entry { }
.practice-desc { font-size: 24rpx; color: #888; display: block; margin-bottom: 12rpx; line-height: 1.5; }
.btn-practice { background: #1677ff; color: #fff; border-radius: 8rpx; padding: 16rpx; font-size: 28rpx; text-align: center; }
</style>

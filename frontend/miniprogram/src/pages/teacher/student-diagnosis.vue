<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!report" class="tip">暂无数据</view>
    <view v-else>
      <view class="card">
        <view class="stat-row">
          <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">累计错题</text></view>
          <view class="stat"><text class="num">{{ report.total_analyzed }}</text><text class="lbl">已分析</text></view>
          <view class="stat"><text class="num">{{ Math.round(report.mastery_rate * 100) }}%</text><text class="lbl">掌握率</text></view>
        </view>
      </view>
      <view v-if="report.top_error_types.length" class="card">
        <view class="card-title">高频错误</view>
        <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.error_type" class="row">
          <text>{{ e.error_type }}</text><text class="count">{{ e.count }}</text>
        </view>
      </view>
      <view v-if="report.top_weak_knowledge_points.length" class="card">
        <view class="card-title">薄弱知识点</view>
        <view class="tags">
          <text v-for="kp in report.top_weak_knowledge_points.slice(0, 8)" :key="kp.knowledge_point" class="tag-kp">
            {{ kp.knowledge_point }}（{{ kp.count }}）
          </text>
        </view>
      </view>
      <view v-if="report.top_suggestions?.length" class="card">
        <view class="card-title">AI 学习建议</view>
        <view v-for="(s, i) in report.top_suggestions" :key="i" class="sug">
          <text class="sug-num">{{ i + 1 }}</text>
          <text class="sug-text">{{ s }}</text>
        </view>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getStudentDiagnosis } from '@/api/teacher'
const report = ref<any>(null)
const loading = ref(true)
onMounted(async () => {
  const pages = getCurrentPages()
  const sid = (pages[pages.length - 1] as any).options?.studentId
  if (!sid) { loading.value = false; return }
  try { const r: any = await getStudentDiagnosis(sid); report.value = r.data }
  finally { loading.value = false }
})
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 56rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 24rpx; color: var(--c-text-hint); }
.row { display: flex; justify-content: space-between; padding: 8rpx 0; border-bottom: 1rpx solid var(--c-border); font-size: 26rpx; color: var(--c-text-body); }
.count { color: var(--c-gold); font-weight: 700; }
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp { background: #eaeac4; color: #6b6b2e; font-size: 24rpx; font-weight: 600; padding: 6rpx 16rpx; border-radius: var(--r-pill); }
.sug { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.sug-num { width: 44rpx; height: 44rpx; background: var(--c-primary); color: var(--c-ink); border-radius: 50%; font-size: 24rpx; font-weight: 700; line-height: 44rpx; text-align: center; flex-shrink: 0; margin-right: 16rpx; }
.sug-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
</style>

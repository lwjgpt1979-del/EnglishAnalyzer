<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!report" class="tip">暂无数据</view>
    <view v-else>

      <!-- 总览 -->
      <view class="card">
        <view class="stat-row">
          <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">累计错题</text></view>
          <view class="stat"><text class="num">{{ report.total_analyzed }}</text><text class="lbl">已分析</text></view>
          <view class="stat"><text class="num">{{ report.mastered_count ?? 0 }}</text><text class="lbl">已掌握</text></view>
          <view class="stat"><text class="num">{{ Math.round(report.mastery_rate * 100) }}%</text><text class="lbl">掌握率</text></view>
        </view>
      </view>

      <!-- 高频错误 -->
      <view v-if="report.top_error_types?.length" class="card">
        <view class="card-title">高频错误</view>
        <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.error_type" class="bar-item">
          <text class="bar-label">{{ e.error_type }}</text>
          <view class="bar-track">
            <view class="bar-fill" :style="{ width: barWidth(e.count, maxErrorCount) + '%' }" />
          </view>
          <text class="bar-count">{{ e.count }}</text>
        </view>
      </view>

      <!-- 题型分布 -->
      <view v-if="qtKeys.length > 0" class="card">
        <view class="card-title">题型分布</view>
        <view v-for="[type, cnt] in distEntries(report.question_type_distribution)" :key="type" class="bar-item">
          <text class="bar-label">{{ type }}</text>
          <view class="bar-track">
            <view class="bar-fill" :style="{ width: barWidth(cnt, maxDistCount(report.question_type_distribution)) + '%' }" />
          </view>
          <text class="bar-count">{{ cnt }}</text>
        </view>
      </view>

      <!-- 难度分布 -->
      <view v-if="ddKeys.length > 0" class="card">
        <view class="card-title">难度分布</view>
        <view v-for="[key, cnt] in distEntries(report.difficulty_distribution)" :key="key" class="bar-item">
          <text class="bar-label">{{ difficultyLabel(key) }}</text>
          <view class="bar-track">
            <view class="bar-fill" :class="difficultyBarClass(key)" :style="{ width: barWidth(cnt, maxDistCount(report.difficulty_distribution)) + '%' }" />
          </view>
          <text class="bar-count">{{ cnt }}</text>
        </view>
      </view>

      <!-- 薄弱知识点 -->
      <view v-if="report.top_weak_knowledge_points?.length" class="card">
        <view class="card-title">薄弱知识点</view>
        <view class="tags">
          <text v-for="kp in report.top_weak_knowledge_points.slice(0, 8)" :key="kp.knowledge_point" class="tag-kp">
            {{ kp.knowledge_point }}（{{ kp.count }}）
          </text>
        </view>
      </view>

      <!-- AI 学习建议 -->
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
import { computed, onMounted, ref } from 'vue'
import { getStudentDiagnosis } from '@/api/teacher'

const report = ref<any>(null)
const loading = ref(true)

onMounted(async () => {
  const pages = getCurrentPages()
  const sid = (pages[pages.length - 1] as any).options?.studentId
  if (!sid) { loading.value = false; return }
  try {
    const r: any = await getStudentDiagnosis(sid)
    report.value = r.data
  } finally {
    loading.value = false
  }
})

const maxErrorCount = computed<number>(() => {
  if (!report.value?.top_error_types?.length) return 1
  return Math.max(...report.value.top_error_types.map((e: any) => e.count))
})

const qtKeys = computed(() => Object.keys(report.value?.question_type_distribution ?? {}))
const ddKeys = computed(() => Object.keys(report.value?.difficulty_distribution ?? {}))

function distEntries(dist: Record<string, number>): [string, number][] {
  return Object.entries(dist ?? {}).sort((a, b) => b[1] - a[1])
}

function maxDistCount(dist: Record<string, number>): number {
  const vals = Object.values(dist ?? {})
  return vals.length === 0 ? 1 : Math.max(...vals)
}

function barWidth(count: number, max: number): number {
  return max === 0 ? 0 : Math.round((count / max) * 100)
}

function difficultyLabel(key: string): string {
  const map: Record<string, string> = { '1': '简单', '2': '中等', '3': '困难', 'easy': '简单', 'medium': '中等', 'hard': '困难' }
  return map[key] ?? key
}

function difficultyBarClass(key: string): string {
  if (key === '1' || key === 'easy') return 'acc-high'
  if (key === '3' || key === 'hard') return 'acc-low'
  return 'acc-mid'
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 48rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 22rpx; color: var(--c-text-hint); }
/* 进度条 */
.bar-item { display: flex; align-items: center; margin-bottom: 14rpx; }
.bar-label { width: 160rpx; font-size: 24rpx; color: var(--c-text-body); flex-shrink: 0; }
.bar-track { flex: 1; background: var(--c-bg-soft); height: 14rpx; border-radius: var(--r-pill); margin: 0 12rpx; }
.bar-fill { height: 100%; background: var(--c-gold); border-radius: var(--r-pill); }
.bar-fill.acc-low { background: var(--c-danger); }
.bar-fill.acc-mid { background: var(--c-gold); }
.bar-fill.acc-high { background: #2ecc71; }
.bar-count { font-size: 22rpx; color: var(--c-text-second); width: 48rpx; text-align: right; }
/* 知识点标签 */
.tags { display: flex; flex-wrap: wrap; gap: 12rpx; }
.tag-kp { background: #eaeac4; color: #6b6b2e; font-size: 24rpx; font-weight: 600; padding: 6rpx 16rpx; border-radius: var(--r-pill); }
/* 建议 */
.sug { display: flex; align-items: flex-start; margin-bottom: 20rpx; }
.sug-num { width: 44rpx; height: 44rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: 50%; font-size: 24rpx; font-weight: 700; line-height: 44rpx; text-align: center; flex-shrink: 0; margin-right: 16rpx; }
.sug-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
</style>

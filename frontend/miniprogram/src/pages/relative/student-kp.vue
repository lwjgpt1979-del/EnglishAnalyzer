<!-- src/pages/relative/student-kp.vue — M45 家长查看孩子知识点台账 -->
<template>
  <view class="page">

    <view v-if="loading" class="tip">加载中…</view>

    <view v-else-if="items.length === 0" class="empty-wrap">
      <text class="empty-icon">📚</text>
      <text class="empty-title">暂无知识点记录</text>
      <text class="empty-hint">孩子完成练习、提交作业或上传试卷后，数据将自动汇总到这里</text>
    </view>

    <view v-else>

      <!-- 总览 -->
      <view class="card overview-card">
        <view class="ov-row">
          <view class="ov-item">
            <text class="ov-num">{{ items.length }}</text>
            <text class="ov-label">知识点</text>
          </view>
          <view class="ov-item">
            <text class="ov-num" :class="accClass(avgAccuracy)">
              {{ pct(avgAccuracy) }}
            </text>
            <text class="ov-label">平均正确率</text>
          </view>
          <view class="ov-item">
            <text class="ov-num text-green">{{ masteredCount }}</text>
            <text class="ov-label">已掌握≥80%</text>
          </view>
          <view class="ov-item">
            <text class="ov-num text-red">{{ weakCount }}</text>
            <text class="ov-label">需加强&lt;60%</text>
          </view>
        </view>
      </view>

      <!-- 来源筛选 -->
      <scroll-view class="filter-scroll" scroll-x enhanced>
        <view class="filter-bar">
          <text
            v-for="f in FILTERS"
            :key="f.value"
            class="filter-chip"
            :class="{ active: activeFilter === f.value }"
            @tap="activeFilter = f.value"
          >{{ f.label }}</text>
        </view>
      </scroll-view>

      <!-- KP 列表 -->
      <view v-for="item in filteredItems" :key="item.kp_key" class="card kp-card">

        <view class="kp-header">
          <view class="kp-dot" :class="dotClass(item.accuracy)" />
          <text class="kp-name">{{ item.kp_key }}</text>
          <text class="kp-acc" :class="accClass(item.accuracy)">{{ pct(item.accuracy) }}</text>
        </view>

        <view class="bar-track">
          <view
            class="bar-fill"
            :class="accClass(item.accuracy)"
            :style="{ width: Math.max(4, Math.round(item.accuracy * 100)) + '%' }"
          />
        </view>

        <view class="kp-stats">
          <text class="stat-ok">✓ {{ item.correct_count }} 对</text>
          <text class="stat-wrong">✗ {{ item.wrong_count }} 错</text>
          <text class="stat-total">共 {{ item.correct_count + item.wrong_count }} 题</text>
        </view>

        <view class="kp-footer">
          <view class="source-tags">
            <text
              v-for="src in item.sources"
              :key="src"
              class="src-tag"
              :class="`src-${src}`"
            >{{ SOURCE_LABEL[src] || src }}</text>
          </view>
          <text v-if="item.kp_description" class="kp-desc">{{ item.kp_description }}</text>
        </view>

        <text v-if="item.last_activity_at" class="kp-time">
          最近：{{ formatDate(item.last_activity_at) }}
        </text>

        <!-- 复习建议（M7c，家长可执行指引） -->
        <view v-if="item.suggestion" class="kp-suggestion" :class="`sug-${item.level}`">
          <text class="sug-badge" :class="`badge-${item.level}`">{{ levelLabel(item.level) }}</text>
          <text class="sug-text">💡 {{ item.suggestion }}</text>
        </view>

      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getChildKpMastery, type ChildKpMasteryItem } from '@/api/relative'

const loading = ref(true)
const items = ref<ChildKpMasteryItem[]>([])
const activeFilter = ref('all')

onMounted(async () => {
  const pages = getCurrentPages()
  const page = pages[pages.length - 1] as any
  const studentId: string = page.options?.studentId || ''
  const nickname: string = page.options?.nickname || ''

  const title = nickname ? `${nickname}的知识点` : '知识点台账'
  uni.setNavigationBarTitle({ title })

  if (!studentId) { loading.value = false; return }

  try {
    items.value = await getChildKpMastery(studentId)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

const FILTERS = [
  { value: 'all',             label: '全部' },
  { value: 'practice',       label: '练习' },
  { value: 'assignment',     label: '作业' },
  { value: 'paper_upload',   label: '整卷' },
  { value: 'wrong_question', label: '错题' },
]

const SOURCE_LABEL: Record<string, string> = {
  practice:       '练习',
  assignment:     '作业',
  paper_upload:   '整卷',
  wrong_question: '错题',
}

const filteredItems = computed(() =>
  activeFilter.value === 'all'
    ? items.value
    : items.value.filter(i => i.sources.includes(activeFilter.value))
)

const avgAccuracy = computed(() => {
  if (!items.value.length) return 0
  return items.value.reduce((s, i) => s + i.accuracy, 0) / items.value.length
})
const masteredCount = computed(() =>
  items.value.filter(i => i.accuracy >= 0.8 && (i.correct_count + i.wrong_count) > 0).length
)
const weakCount = computed(() =>
  items.value.filter(i => i.accuracy < 0.6 && (i.correct_count + i.wrong_count) > 0).length
)

function levelLabel(level: string) {
  return ({ weak: '薄弱', medium: '待巩固', good: '已掌握' } as Record<string, string>)[level] || level
}
function pct(acc: number) { return `${(acc * 100).toFixed(0)}%` }
function accClass(acc: number) {
  if (acc >= 0.8) return 'acc-green'
  if (acc >= 0.6) return 'acc-yellow'
  return 'acc-red'
}
function dotClass(acc: number) {
  if (acc >= 0.8) return 'dot-green'
  if (acc >= 0.6) return 'dot-yellow'
  return 'dot-red'
}
function formatDate(iso: string) {
  const d = new Date(iso)
  return `${d.getMonth() + 1}月${d.getDate()}日`
}
</script>

<style lang="scss" scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }

.tip { margin-top: 120rpx; text-align: center; color: #999; font-size: 28rpx; }

.empty-wrap {
  display: flex; flex-direction: column; align-items: center;
  margin-top: 120rpx; padding: 0 60rpx;
  .empty-icon { font-size: 80rpx; }
  .empty-title { margin-top: 24rpx; font-size: 32rpx; font-weight: 600; color: #333; }
  .empty-hint { margin-top: 16rpx; font-size: 26rpx; color: #999; text-align: center; line-height: 1.6; }
}

.card {
  background: #fff; border-radius: 20rpx; padding: 28rpx 24rpx;
  margin-bottom: 20rpx; box-shadow: 0 2rpx 12rpx rgba(0,0,0,.06);
}

.overview-card {
  .ov-row { display: flex; justify-content: space-around; }
  .ov-item { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
  .ov-num { font-size: 40rpx; font-weight: 700; color: #333; }
  .ov-label { font-size: 22rpx; color: #999; }
}

.filter-scroll { margin-bottom: 16rpx; white-space: nowrap; }
.filter-bar { display: flex; gap: 16rpx; padding: 4rpx 0; }
.filter-chip {
  display: inline-block; padding: 10rpx 28rpx; border-radius: 32rpx;
  background: #fff; font-size: 26rpx; color: #666;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.06); white-space: nowrap;
  &.active { background: #1677ff; color: #fff; }
}

.kp-card { padding: 24rpx; }
.kp-header { display: flex; align-items: center; margin-bottom: 14rpx; }
.kp-dot { width: 16rpx; height: 16rpx; border-radius: 50%; margin-right: 12rpx; flex-shrink: 0; }
.kp-name { flex: 1; font-size: 30rpx; font-weight: 600; color: #222; }
.kp-acc { font-size: 32rpx; font-weight: 700; }

.bar-track {
  height: 14rpx; background: #f0f0f0; border-radius: 7rpx; overflow: hidden; margin-bottom: 14rpx;
}
.bar-fill { height: 100%; border-radius: 7rpx; }

.kp-stats { display: flex; gap: 24rpx; font-size: 24rpx; margin-bottom: 12rpx; }
.stat-ok    { color: #52c41a; }
.stat-wrong { color: #ff4d4f; }
.stat-total { color: #999; }

.kp-footer { display: flex; flex-wrap: wrap; align-items: center; gap: 10rpx; margin-bottom: 8rpx; }
.source-tags { display: flex; gap: 8rpx; flex-wrap: wrap; }
.src-tag {
  font-size: 20rpx; padding: 4rpx 14rpx; border-radius: 20rpx; color: #fff;
  &.src-practice       { background: #1677ff; }
  &.src-assignment     { background: #722ed1; }
  &.src-paper_upload   { background: #fa8c16; }
  &.src-wrong_question { background: #f5222d; }
}
.kp-desc { font-size: 22rpx; color: #999; line-height: 1.5; flex: 1; min-width: 0; }
.kp-time { font-size: 22rpx; color: #ccc; }

.acc-green, .dot-green { color: #52c41a; }
.bar-fill.acc-green   { background: #52c41a; }
.acc-yellow, .dot-yellow { color: #ffb020; }
.bar-fill.acc-yellow  { background: #ffb020; }
.acc-red, .dot-red    { color: #ff7a59; }
.bar-fill.acc-red     { background: #ff9078; }
.dot-green  { background: #52c41a; }
.dot-yellow { background: #ffb020; }
.dot-red    { background: #ff9078; }

.text-green { color: #52c41a !important; }
.text-red   { color: #ff7a59 !important; }

/* ── 复习建议（M7c）── */
.kp-suggestion {
  margin-top: 14rpx; padding: 14rpx 16rpx; border-radius: 12rpx;
  display: flex; align-items: flex-start; gap: 10rpx;
  &.sug-weak   { background: #fff2f0; }
  &.sug-medium { background: #eef5ff; }
  &.sug-good   { background: #f6ffed; }
}
.sug-badge {
  flex-shrink: 0; font-size: 20rpx; padding: 2rpx 14rpx; border-radius: 20rpx; color: #fff;
  &.badge-weak   { background: #ff7a59; }
  &.badge-medium { background: #ffb020; }
  &.badge-good   { background: #52c41a; }
}
.sug-text { flex: 1; font-size: 24rpx; color: #555; line-height: 1.5; }
</style>

<!-- src/pages/kp-mastery/index.vue — M42 知识点掌握图谱 -->
<template>
  <view class="kp-page">

    <!-- 加载 -->
    <view v-if="loading" class="center-tip">
      <text>加载中…</text>
    </view>

    <!-- 空态 -->
    <view v-else-if="items.length === 0" class="empty-wrap">
      <view class="ic ic-books empty-icon" />
      <text class="empty-title">还没有知识点记录</text>
      <text class="empty-hint">完成练习、上传试卷、做作业后，知识点掌握情况会自动汇总到这里</text>
    </view>

    <view v-else>

      <!-- 总览卡片 -->
      <view class="card overview-card">
        <view class="overview-row">
          <view class="ov-item">
            <text class="ov-num">{{ items.length }}</text>
            <text class="ov-label">已覆盖知识点</text>
          </view>
          <view class="ov-item">
            <text class="ov-num" :class="accClass(avgAccuracy)">
              {{ (avgAccuracy * 100).toFixed(0) }}%
            </text>
            <text class="ov-label">平均正确率</text>
          </view>
          <view class="ov-item">
            <text class="ov-num text-green">{{ masteredCount }}</text>
            <text class="ov-label">已掌握 ≥80%</text>
          </view>
          <view class="ov-item">
            <text class="ov-num text-red">{{ weakCount }}</text>
            <text class="ov-label">需加强 &lt;60%</text>
          </view>
        </view>
        <text class="ov-hint">弱项优先排列，建议从正确率最低的知识点开始练习</text>
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

      <!-- 知识点列表 -->
      <view
        v-for="item in filteredItems"
        :key="item.kp_key"
        class="card kp-card"
        @tap="goTrend(item.kp_key)"
      >
        <!-- 标题行 -->
        <view class="kp-header">
          <view class="kp-dot" :class="dotClass(item.accuracy)" />
          <text class="kp-name">{{ item.kp_key }}</text>
          <text class="kp-acc" :class="accClass(item.accuracy)">
            {{ (item.accuracy * 100).toFixed(0) }}%
          </text>
        </view>

        <!-- 进度条 -->
        <view class="bar-track">
          <view
            class="bar-fill"
            :class="accClass(item.accuracy)"
            :style="{ width: Math.max(4, Math.round(item.accuracy * 100)) + '%' }"
          />
        </view>

        <!-- 统计行 -->
        <view class="kp-stats">
          <view class="stat-ok"><view class="ic ic-check stat-mark" /><text>{{ item.correct_count }} 对</text></view>
          <view class="stat-wrong"><view class="ic ic-x-circle stat-mark" /><text>{{ item.wrong_count }} 错</text></view>
          <text class="stat-total">共 {{ item.correct_count + item.wrong_count }} 题</text>
        </view>

        <!-- 来源标签 + 描述 -->
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

        <!-- 最近活动 -->
        <text v-if="item.last_activity_at" class="kp-time">
          最近：{{ formatDate(item.last_activity_at) }}
        </text>
      </view>

    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { getKpMastery, type KpMasteryItem } from '@/api/kpMastery'

// ── 数据 ──────────────────────────────────────────────────────────────────────
const loading = ref(true)
const items = ref<KpMasteryItem[]>([])
const activeFilter = ref('all')

onMounted(async () => {
  try {
    items.value = await getKpMastery()
  } catch {
    uni.showToast({ title: '加载失败，请稍后重试', icon: 'none' })
  } finally {
    loading.value = false
  }
})

// ── 来源筛选 ──────────────────────────────────────────────────────────────────
const FILTERS = [
  { value: 'all',            label: '全部' },
  { value: 'practice',      label: '练习' },
  { value: 'assignment',    label: '作业' },
  { value: 'paper_upload',  label: '整卷' },
  { value: 'wrong_question', label: '错题' },
]

const SOURCE_LABEL: Record<string, string> = {
  practice:      '练习',
  assignment:    '作业',
  paper_upload:  '整卷',
  wrong_question: '错题',
}

const filteredItems = computed(() => {
  if (activeFilter.value === 'all') return items.value
  return items.value.filter(i => i.sources.includes(activeFilter.value))
})

// ── 统计 ──────────────────────────────────────────────────────────────────────
const avgAccuracy = computed(() => {
  if (!items.value.length) return 0
  const total = items.value.reduce((s, i) => s + i.accuracy, 0)
  return total / items.value.length
})

const masteredCount = computed(() =>
  items.value.filter(i => i.accuracy >= 0.8 && (i.correct_count + i.wrong_count) > 0).length
)

const weakCount = computed(() =>
  items.value.filter(i => i.accuracy < 0.6 && (i.correct_count + i.wrong_count) > 0).length
)

// ── 工具函数 ──────────────────────────────────────────────────────────────────
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
  const M = d.getMonth() + 1
  const D = d.getDate()
  return `${M}月${D}日`
}

// M46 — 跳转趋势页
function goTrend(kpKey: string) {
  uni.navigateTo({ url: `/pages/kp-mastery/trend?kpKey=${encodeURIComponent(kpKey)}` })
}
</script>

<style lang="scss" scoped>
.kp-page {
  padding: 24rpx;
  background: #f5f5f5;
  min-height: 100vh;
}

/* ── 加载 / 空态 ── */
.center-tip {
  margin-top: 120rpx;
  text-align: center;
  color: #999;
  font-size: 28rpx;
}

.empty-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  margin-top: 120rpx;
  padding: 0 60rpx;

  .empty-icon { width: 80rpx; height: 80rpx; }
  .empty-title {
    margin-top: 24rpx;
    font-size: 32rpx;
    font-weight: 600;
    color: #333;
  }
  .empty-hint {
    margin-top: 16rpx;
    font-size: 26rpx;
    color: #999;
    text-align: center;
    line-height: 1.6;
  }
}

/* ── 通用卡片 ── */
.card {
  background: #fff;
  border-radius: 20rpx;
  padding: 28rpx 24rpx;
  margin-bottom: 20rpx;
  box-shadow: 0 2rpx 12rpx rgba(0,0,0,.06);
}

/* ── 总览 ── */
.overview-card {
  .overview-row {
    display: flex;
    justify-content: space-around;
    margin-bottom: 16rpx;
  }
  .ov-item {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 6rpx;
  }
  .ov-num {
    font-size: 40rpx;
    font-weight: 700;
    color: #333;
  }
  .ov-label {
    font-size: 22rpx;
    color: #999;
  }
  .ov-hint {
    font-size: 22rpx;
    color: #aaa;
    text-align: center;
  }
}

/* ── 来源筛选 ── */
.filter-scroll {
  margin-bottom: 16rpx;
  white-space: nowrap;
}
.filter-bar {
  display: flex;
  gap: 16rpx;
  padding: 4rpx 0;
}
.filter-chip {
  display: inline-block;
  padding: 10rpx 28rpx;
  border-radius: 32rpx;
  background: #fff;
  font-size: 26rpx;
  color: #666;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.06);
  white-space: nowrap;

  &.active {
    background: var(--c-primary);
    color: var(--c-on-primary);
  }
}

/* ── KP 卡片 ── */
.kp-card {
  padding: 24rpx;

  .kp-header {
    display: flex;
    align-items: center;
    margin-bottom: 14rpx;
  }
  .kp-dot {
    width: 16rpx;
    height: 16rpx;
    border-radius: 50%;
    margin-right: 12rpx;
    flex-shrink: 0;
  }
  .kp-name {
    flex: 1;
    font-size: 30rpx;
    font-weight: 600;
    color: #222;
  }
  .kp-acc {
    font-size: 32rpx;
    font-weight: 700;
  }
}

/* ── 进度条 ── */
.bar-track {
  height: 14rpx;
  background: #f0f0f0;
  border-radius: 7rpx;
  overflow: hidden;
  margin-bottom: 14rpx;
}
.bar-fill {
  height: 100%;
  border-radius: 7rpx;
  transition: width .3s;
}

/* ── 统计 ── */
.kp-stats {
  display: flex;
  gap: 24rpx;
  font-size: 24rpx;
  margin-bottom: 12rpx;

  .stat-ok    { color: #52c41a; display: flex; align-items: center; gap: 6rpx; }
  .stat-wrong { color: #ff4d4f; display: flex; align-items: center; gap: 6rpx; }
  .stat-total { color: #999; }
  .stat-mark  { width: 26rpx; height: 26rpx; flex-shrink: 0; }
}

/* ── 来源标签 ── */
.kp-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10rpx;
  margin-bottom: 8rpx;
}
.source-tags { display: flex; gap: 8rpx; flex-wrap: wrap; }
.src-tag {
  font-size: 20rpx;
  padding: 4rpx 14rpx;
  border-radius: 20rpx;
  color: #fff;

  &.src-practice      { background: #1677ff; }
  &.src-assignment    { background: #722ed1; }
  &.src-paper_upload  { background: #fa8c16; }
  &.src-wrong_question { background: #f5222d; }
}

.kp-desc {
  font-size: 22rpx;
  color: #999;
  line-height: 1.5;
  flex: 1;
  min-width: 0;
}

.kp-time {
  font-size: 22rpx;
  color: #ccc;
}

/* ── 颜色语义（文字仅 color；圆点/进度条才 background，避免百分比文字变实心色块）──
   弱项用柔和珊瑚(主题 accent)而非刺眼正红，融入天空蓝基调，同时保留暖色警示语义 */
.acc-green { color: #2fc58a; }
.acc-yellow { color: #f5a623; }
.acc-red { color: #ff7a59; }
.dot-green, .bar-fill.acc-green { background: #2fc58a; }
.dot-yellow, .bar-fill.acc-yellow { background: #f7b955; }
.dot-red, .bar-fill.acc-red { background: #ff9078; }

// ov-num 直接加颜色类
.text-green { color: #2fc58a !important; }
.text-red   { color: #ff7a59 !important; }
</style>

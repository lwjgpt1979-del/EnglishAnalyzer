<!-- src/pages/kp-mastery/trend.vue — M46 KP 正确率趋势图 -->
<template>
  <view class="page">

    <view v-if="loading" class="tip">加载中…</view>

    <view v-else-if="points.length === 0" class="empty-wrap">
      <view class="ic ic-chart empty-icon" />
      <text class="empty-title">暂无趋势数据</text>
      <text class="empty-hint">完成更多练习、作业或上传试卷后，趋势图将自动生成</text>
    </view>

    <view v-else>

      <!-- 当前掌握度概览 -->
      <view class="card overview-card">
        <view class="ov-kp">{{ kpName }}</view>
        <view class="ov-row">
          <view class="ov-item">
            <text class="ov-num" :class="accClass(latest.mastery)">
              {{ pct(latest.mastery) }}
            </text>
            <text class="ov-label">当前掌握度</text>
          </view>
          <view class="ov-item">
            <text class="ov-num">{{ latest.mastery_events }}</text>
            <text class="ov-label">判定事件数</text>
          </view>
        </view>
        <text v-if="latest.mastery_events < 10" class="ov-evidence">证据不足:多练几题评估更准</text>
      </view>

      <!-- 天数切换 -->
      <view class="period-bar">
        <text
          v-for="d in PERIODS"
          :key="d"
          class="period-chip"
          :class="{ active: selectedDays === d }"
          @tap="onDaysChange(d)"
        >近{{ d }}天</text>
      </view>

      <!-- CSS Sparkline 趋势图 -->
      <view class="card chart-card">
        <view class="chart-title">掌握度趋势</view>

        <!-- 纵轴刻度 -->
        <view class="chart-area">
          <view class="y-axis">
            <text class="y-label">100%</text>
            <text class="y-label">70%</text>
            <text class="y-label">40%</text>
            <text class="y-label">0%</text>
          </view>

          <!-- 柱状趋势图 -->
          <scroll-view class="bars-scroll" scroll-x enhanced>
            <view class="bars-wrap">
              <view
                v-for="(p, i) in displayPoints"
                :key="p.date"
                class="bar-col"
                @tap="selectedPoint = i"
              >
                <!-- 柱子 -->
                <view class="bar-track">
                  <view
                    class="bar-fill"
                    :class="accClass(p.mastery)"
                    :style="{ height: barHeight(p.mastery) }"
                  />
                </view>
                <!-- 日期标签（每隔几天显示一个） -->
                <text class="bar-date">{{ shortDate(p.date, i) }}</text>
              </view>
            </view>
          </scroll-view>
        </view>

        <!-- 参考线 -->
        <view class="ref-lines">
          <view class="ref-line ref-70" />
          <view class="ref-line ref-40" />
        </view>

        <!-- 图例（分档 0.4/0.7）-->
        <view class="legend-row">
          <view class="legend-item">
            <view class="legend-dot dot-green" /><text class="legend-label">≥70% 已掌握</text>
          </view>
          <view class="legend-item">
            <view class="legend-dot dot-yellow" /><text class="legend-label">40-70% 待巩固</text>
          </view>
          <view class="legend-item">
            <view class="legend-dot dot-red" /><text class="legend-label">&lt;40% 需加强</text>
          </view>
        </view>
      </view>

      <!-- 选中点详情 / 默认最新一条 -->
      <view class="card detail-card">
        <view class="detail-date"><view class="ic ic-calendar detail-date-ic" /><text>{{ displayPoints[selectedPoint]?.date ?? '' }}</text></view>
        <view class="detail-row">
          <view class="detail-item">
            <text class="detail-num" :class="accClass(displayPoints[selectedPoint]?.mastery ?? 0)">
              {{ pct(displayPoints[selectedPoint]?.mastery ?? 0) }}
            </text>
            <text class="detail-label">掌握度</text>
          </view>
          <view class="detail-item">
            <text class="detail-num">{{ displayPoints[selectedPoint]?.mastery_events ?? 0 }}</text>
            <text class="detail-label">判定事件数</text>
          </view>
        </view>
      </view>

      <!-- 历史列表 -->
      <view class="card">
        <view class="list-title">历史记录</view>
        <view
          v-for="p in [...displayPoints].reverse()"
          :key="p.date"
          class="list-row"
        >
          <text class="list-date">{{ p.date }}</text>
          <view class="list-bar-track">
            <view
              class="list-bar-fill"
              :class="accClass(p.mastery)"
              :style="{ width: Math.max(4, Math.round(p.mastery * 100)) + '%' }"
            />
          </view>
          <text class="list-pct" :class="accClass(p.mastery)">{{ pct(p.mastery) }}</text>
        </view>
      </view>

    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { getKpTrend, type KpTrendPoint } from '@/api/kpMastery'

const loading = ref(true)
const nodeId = ref('')
const kpName = ref('')
const points = ref<KpTrendPoint[]>([])
const selectedDays = ref(30)
const selectedPoint = ref(0)

const PERIODS = [7, 14, 30]

onMounted(async () => {
  const pages = getCurrentPages()
  const page = pages[pages.length - 1] as any
  nodeId.value = decodeURIComponent(page.options?.nodeId || '')
  kpName.value = decodeURIComponent(page.options?.name || '')
  uni.setNavigationBarTitle({ title: (kpName.value || '掌握度') + ' 趋势' })
  await loadTrend()
})

async function loadTrend() {
  loading.value = true
  try {
    points.value = await getKpTrend(nodeId.value, selectedDays.value)
    selectedPoint.value = Math.max(0, points.value.length - 1)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function onDaysChange(d: number) {
  selectedDays.value = d
  await loadTrend()
}

// 只显示查询范围内的数据点
const displayPoints = computed(() => points.value)

const latest = computed(() =>
  points.value.length > 0
    ? points.value[points.value.length - 1]
    : { mastery: 0, mastery_events: 0, date: '' }
)

/** 柱高度 0% ~ 100%，最低保留 4rpx 可见 */
function barHeight(mastery: number): string {
  const pctVal = Math.max(3, Math.round(mastery * 100))
  return `${pctVal}%`
}

function pct(m: number) { return `${(m * 100).toFixed(0)}%` }

function accClass(m: number) {
  if (m >= 0.7) return 'acc-green'
  if (m >= 0.4) return 'acc-yellow'
  return 'acc-red'
}

/** 稀疏显示日期标签：每隔 step 显示一个 */
function shortDate(dateStr: string, i: number): string {
  const total = displayPoints.value.length
  const step = total <= 7 ? 1 : total <= 14 ? 2 : 5
  if (i % step !== 0 && i !== total - 1) return ''
  const d = new Date(dateStr)
  return `${d.getMonth() + 1}/${d.getDate()}`
}
</script>

<style lang="scss" scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }

.tip { margin-top: 120rpx; text-align: center; color: #999; font-size: 28rpx; }
.empty-wrap {
  display: flex; flex-direction: column; align-items: center;
  margin-top: 120rpx; padding: 0 60rpx;
  .empty-icon { width: 80rpx; height: 80rpx; }
  .empty-title { margin-top: 24rpx; font-size: 32rpx; font-weight: 600; color: #333; }
  .empty-hint { margin-top: 16rpx; font-size: 26rpx; color: #999; text-align: center; line-height: 1.6; }
}

.card {
  background: #fff; border-radius: 20rpx; padding: 28rpx 24rpx;
  margin-bottom: 20rpx; box-shadow: 0 2rpx 12rpx rgba(0,0,0,.06);
}

/* 总览卡 */
.overview-card {
  .ov-kp { font-size: 28rpx; font-weight: 700; color: #333; margin-bottom: 20rpx; }
  .ov-row { display: flex; justify-content: space-around; }
  .ov-item { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
  .ov-num { font-size: 40rpx; font-weight: 700; color: #333; }
  .ov-label { font-size: 22rpx; color: #999; }
  .ov-evidence { display: block; margin-top: 16rpx; font-size: 22rpx; color: #bbb; }
}

/* 天数选择 */
.period-bar { display: flex; gap: 16rpx; margin-bottom: 16rpx; }
.period-chip {
  flex: 1; text-align: center; padding: 14rpx 0; border-radius: 32rpx;
  background: #fff; font-size: 26rpx; color: #666;
  box-shadow: 0 2rpx 8rpx rgba(0,0,0,.06);
  &.active { background: #1677ff; color: #fff; }
}

/* 图表 */
.chart-card { position: relative; padding-bottom: 40rpx; }
.chart-title { font-size: 26rpx; font-weight: 600; color: #333; margin-bottom: 16rpx; }

.chart-area { display: flex; align-items: flex-end; height: 200rpx; }

.y-axis {
  display: flex; flex-direction: column; justify-content: space-between;
  height: 200rpx; padding-bottom: 32rpx; margin-right: 8rpx; flex-shrink: 0;
}
.y-label { font-size: 18rpx; color: #ccc; }

.bars-scroll { flex: 1; height: 200rpx; }
.bars-wrap { display: flex; align-items: flex-end; height: 168rpx; padding-bottom: 32rpx; gap: 6rpx; }

.bar-col { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; width: 32rpx; }
.bar-track {
  width: 24rpx; height: 140rpx; background: #f5f5f5; border-radius: 6rpx;
  display: flex; align-items: flex-end; overflow: hidden;
}
.bar-fill {
  width: 100%; border-radius: 6rpx; transition: height 0.3s;
  &.acc-green  { background: #52c41a; }
  &.acc-yellow { background: #ffb020; }
  &.acc-red    { background: #ff4d4f; }
}
.bar-date { font-size: 16rpx; color: #bbb; margin-top: 6rpx; white-space: nowrap; }

/* 参考线（绝对定位在 chart-card 内） */
.ref-lines { position: relative; pointer-events: none; }
.ref-line {
  position: absolute; left: 52rpx; right: 24rpx; height: 1rpx; border-top: 1rpx dashed;
}
.ref-70 { bottom: 206rpx; border-color: #52c41a; }  /* 70% 掌握线（≈2rpx/1%）*/
.ref-40 { bottom: 146rpx; border-color: #ffb020; }  /* 40% 薄弱线 */

/* 图例 */
.legend-row { display: flex; gap: 24rpx; margin-top: 16rpx; flex-wrap: wrap; }
.legend-item { display: flex; align-items: center; gap: 8rpx; }
.legend-dot { width: 16rpx; height: 16rpx; border-radius: 50%; }
.dot-green  { background: #52c41a; }
.dot-yellow { background: #ffb020; }
.dot-red    { background: #ff4d4f; }
.legend-label { font-size: 22rpx; color: #666; }

/* 详情卡 */
.detail-card { }
.detail-date { font-size: 24rpx; color: #999; margin-bottom: 16rpx; display: flex; align-items: center; gap: 8rpx; }
.detail-date-ic { width: 28rpx; height: 28rpx; flex-shrink: 0; }
.detail-row { display: flex; justify-content: space-around; }
.detail-item { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.detail-num { font-size: 40rpx; font-weight: 700; }
.detail-label { font-size: 22rpx; color: #999; }

/* 历史列表 */
.list-title { font-size: 26rpx; font-weight: 600; color: #333; margin-bottom: 16rpx; }
.list-row {
  display: flex; align-items: center; gap: 16rpx; padding: 10rpx 0;
  border-bottom: 1rpx solid #f5f5f5;
  &:last-child { border-bottom: none; }
}
.list-date { font-size: 24rpx; color: #999; width: 140rpx; flex-shrink: 0; }
.list-bar-track {
  flex: 1; height: 12rpx; background: #f0f0f0; border-radius: 6rpx; overflow: hidden;
}
.list-bar-fill { height: 100%; border-radius: 6rpx; }
.list-pct { font-size: 26rpx; font-weight: 700; width: 70rpx; text-align: right; flex-shrink: 0; }

.acc-green { color: #52c41a; }
.acc-yellow { color: #ffb020; }
.acc-red { color: #ff4d4f; }
.text-green { color: #52c41a !important; }
.text-red { color: #ff4d4f !important; }
</style>

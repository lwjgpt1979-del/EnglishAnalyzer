<template>
  <view class="ibl">
    <!-- 顶部状态筛选 Tab(有进度数据才显示) -->
    <view v-if="hasProgress" class="seg">
      <text class="seg-i" :class="{ on: tab === 'all' }" @tap="tab = 'all'">全部 {{ counts.all }}</text>
      <text class="seg-i" :class="{ on: tab === 'todo' }" @tap="tab = 'todo'">未学 {{ counts.todo }}</text>
      <text class="seg-i" :class="{ on: tab === 'doing' }" @tap="tab = 'doing'">学习中 {{ counts.doing }}</text>
      <text class="seg-i" :class="{ on: tab === 'done' }" @tap="tab = 'done'">已学 {{ counts.done }}</text>
    </view>

    <view v-if="!groups.length" class="ibl-empty">该状态下暂无作业</view>

    <!-- 时间分段 + 竖线时间轴 -->
    <view v-for="g in groups" :key="g.key" class="grp">
      <text class="grp-h" :class="{ 'grp-h-stale': g.key === 'earlier' && g.hasStale }">{{ g.label }}</text>
      <view v-for="(b, i) in g.items" :key="b.id" class="row" @tap="emit('open', b.id)">
        <!-- 时间轴:圆点 + 竖线 -->
        <view class="rail">
          <view class="dot" :class="'dot-' + statusOf(b)"></view>
          <view v-if="i < g.items.length - 1" class="line"></view>
        </view>
        <!-- 进度填充卡 -->
        <view class="bcard" :class="{ 'bcard-done': statusOf(b) === 'done', 'bcard-stale': isStale(b) }">
          <view class="fill" :class="'fill-' + statusOf(b)" :style="{ width: pct(b) + '%' }"></view>
          <view class="bmain">
            <view class="btop">
              <text class="btitle">{{ b.title }}</text>
              <text v-if="isNew(b)" class="flag flag-new">新加入</text>
              <text v-else-if="isStale(b)" class="flag flag-stale">超1周未学</text>
            </view>
            <text class="bsub" :class="'sub-' + statusOf(b)">{{ subText(b) }}</text>
          </view>
          <!-- 右侧进度指示 -->
          <view v-if="hasProgress" class="bright">
            <template v-if="statusOf(b) === 'done'">
              <view class="ic-check"></view>
            </template>
            <text v-else class="bpct" :class="'sub-' + statusOf(b)">{{ pct(b) }}%</text>
          </view>
          <text v-else class="barrow">›</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'

export interface BatchItem { id: string; title: string; date: string; count: number; studied?: number }
type Status = 'todo' | 'doing' | 'done'

const props = withDefaults(defineProps<{ batches: BatchItem[]; unit?: string }>(), { unit: '题' })
const emit = defineEmits<{ (e: 'open', id: string): void }>()

const hasProgress = computed(() => props.batches.some(b => typeof b.studied === 'number'))

function statusOf(b: BatchItem): Status {
  const s = b.studied
  if (typeof s !== 'number' || s <= 0) return 'todo'
  if (s >= b.count) return 'done'
  return 'doing'
}
function daysAgo(date: string): number {
  if (!date) return 999
  const t = new Date(String(date).replace(/-/g, '/') + ' 00:00:00').getTime()
  if (isNaN(t)) return 999
  const now = new Date()
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  return Math.round((today - t) / 86400000)
}
function isNew(b: BatchItem): boolean { return daysAgo(b.date) <= 1 }
function isStale(b: BatchItem): boolean { return daysAgo(b.date) >= 7 && statusOf(b) !== 'done' }
function pct(b: BatchItem): number {
  if (typeof b.studied !== 'number' || !b.count) return 0
  return Math.min(100, Math.round((b.studied / b.count) * 100))
}
function subText(b: BatchItem): string {
  const st = statusOf(b)
  const stub = st === 'todo' ? '未学' : st === 'doing' ? '学习中' : '已学'
  if (hasProgress.value) {
    const prog = st === 'todo' ? `${b.count} ${props.unit}` : `${b.studied || 0}/${b.count}`
    return `${stub} · ${prog}${b.date ? ' · ' + b.date : ''}`
  }
  return `${b.count} ${props.unit}${b.date ? ' · ' + b.date : ''}`
}

const tab = ref<'all' | Status>('all')
const counts = computed(() => {
  const c = { all: props.batches.length, todo: 0, doing: 0, done: 0 }
  for (const b of props.batches) c[statusOf(b)]++
  return c
})
const filtered = computed(() => tab.value === 'all' ? props.batches : props.batches.filter(b => statusOf(b) === tab.value))
const groups = computed(() => {
  const g = [
    { key: 'today', label: '今天', items: [] as BatchItem[], hasStale: false },
    { key: 'week', label: '本周', items: [] as BatchItem[], hasStale: false },
    { key: 'earlier', label: '更早', items: [] as BatchItem[], hasStale: false },
  ]
  for (const b of filtered.value) {
    const d = daysAgo(b.date)
    const bucket = d <= 0 ? g[0] : d < 7 ? g[1] : g[2]
    bucket.items.push(b)
    if (isStale(b)) bucket.hasStale = true
  }
  return g.filter(x => x.items.length)
})
</script>

<style scoped>
.ibl { width: 100%; }
/* 顶部筛选 Tab */
.seg { display: flex; gap: 6rpx; background: #e8edf4; border-radius: 14rpx; padding: 6rpx; margin-bottom: 20rpx; }
.seg-i { flex: 1; text-align: center; font-size: 22rpx; color: #6b7688; padding: 12rpx 0; border-radius: 10rpx; }
.seg-i.on { color: #fff; font-weight: 700; background: #3d8bf5; box-shadow: 0 3rpx 10rpx rgba(61, 139, 245, .28); }
.ibl-empty { text-align: center; color: #93a0b3; font-size: 24rpx; padding: 50rpx 0; }

/* 时间分段 */
.grp-h { display: block; font-size: 21rpx; font-weight: 700; color: #93a0b3; letter-spacing: 2rpx; margin: 4rpx 0 14rpx 4rpx; }
.grp-h-stale { color: #c47a35; }

/* 时间轴行 */
.row { display: flex; gap: 18rpx; }
.rail { width: 22rpx; flex: none; display: flex; flex-direction: column; align-items: center; padding-top: 26rpx; }
.dot { width: 20rpx; height: 20rpx; border-radius: 50%; flex: none; }
.dot-todo { background: #94a3b8; box-shadow: 0 0 0 6rpx #eef1f6; }
.dot-doing { background: #3d8bf5; box-shadow: 0 0 0 6rpx #e3eefd; }
.dot-done { background: #2fa98a; box-shadow: 0 0 0 6rpx #e4f4ef; }
.line { flex: 1; width: 3rpx; background: #e4e9f0; margin-top: 4rpx; }

/* 进度填充卡 */
.bcard { flex: 1; min-width: 0; position: relative; display: flex; align-items: center; background: #fff; border: 2rpx solid #e9edf3; border-radius: 20rpx; padding: 22rpx 22rpx; margin-bottom: 22rpx; overflow: hidden; box-shadow: 0 4rpx 18rpx rgba(45, 80, 150, .05); }
.bcard-done { background: #fbfdfc; border-color: #e2efe9; }
.bcard-stale { border-color: #f1e6d8; }
.fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; }
.fill-doing { background: linear-gradient(90deg, #e8f2ff, #f4f9ff); }
.fill-done { background: linear-gradient(90deg, #e9f6f1, #f4fbf8); }
.bmain { position: relative; flex: 1; min-width: 0; }
.btop { display: flex; align-items: center; gap: 10rpx; }
.btitle { font-size: 27rpx; font-weight: 700; color: #1f2733; max-width: 62%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.bcard-done .btitle { color: #5c6b7a; }
.flag { font-size: 18rpx; border-radius: 6rpx; padding: 2rpx 12rpx; flex: none; }
.flag-new { color: #2f74d6; background: #e6f0fd; border: 2rpx solid #cfe1fb; }
.flag-stale { color: #c47a35; background: #fbeede; }
.bsub { display: block; font-size: 21rpx; margin-top: 8rpx; }
.sub-todo { color: #94a3b8; }
.sub-doing { color: #3d8bf5; }
.sub-done { color: #2fa98a; }
.bright { position: relative; flex: none; margin-left: 12rpx; }
.bpct { font-size: 24rpx; font-weight: 800; }
.barrow { position: relative; flex: none; margin-left: 12rpx; color: #b7c2d4; font-size: 34rpx; }
.ic-check { width: 30rpx; height: 30rpx; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232fa98a' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E"); background-size: contain; background-repeat: no-repeat; }
</style>

<template>
  <view class="pcl" :class="{ flat }">
    <!-- 卷头:进度即底色(背景填充式,全项目统一) + 状态 -->
    <view class="hd-card">
      <view class="hd-fill" :class="'hf-' + status" :style="{ width: pct + '%' }"></view>
      <view class="hd-top">
        <view class="hd-num"><text class="hd-studied">{{ studied }}</text><text class="hd-total">/{{ total }}</text></view>
        <view class="hd-info">
          <view class="hd-status" :class="'st-' + status">{{ statusLabel }}<text class="hd-pct">{{ pct }}%</text></view>
          <text class="hd-sub">{{ subText }}</text>
        </view>
      </view>
    </view>
    <view v-if="total" class="cta" @tap="onStart"><view class="ic ic-play-w cta-ic"></view><text>{{ ctaLabel }}</text></view>

    <view v-if="total" class="list-h">本卷清单</view>
    <view v-if="!total" class="empty"><slot name="empty">本卷暂无内容</slot></view>

    <!-- 待学清单 -->
    <view v-for="(it, i) in items" :key="i"
          class="row" :class="{ done: it.studied, next: i === firstUnstudied, first: i === 0, last: i === items.length - 1 }"
          @tap="emit('open', it, i)">
      <slot name="tick" :item="it" :index="i" :done="!!it.studied">
        <view class="tick" :class="it.studied ? 'tick-done' : (i === firstUnstudied ? 'tick-next' : 'tick-todo')"></view>
      </slot>
      <view class="row-body"><slot name="item" :item="it" :index="i" :done="!!it.studied" /></view>
      <text class="row-act" :class="{ 'act-next': i === firstUnstudied && !it.studied }">{{ it.studied ? '复看 ›' : '去学 ›' }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  items: Array<{ studied?: boolean; [k: string]: any }>
  date?: string
  unit?: string
  flat?: boolean   // 清单从「每项独立卡」→「一卡内连续行 + 细线分隔」(单词模块用,还原 H 大图行)
}>(), { unit: '项', date: '', flat: false })
const emit = defineEmits<{ (e: 'open', item: any, index: number): void; (e: 'start', index: number): void }>()

const total = computed(() => props.items.length)
const studied = computed(() => props.items.filter(i => i.studied).length)
const pct = computed(() => (total.value ? Math.round((studied.value / total.value) * 100) : 0))
const status = computed(() => (studied.value <= 0 ? 'todo' : studied.value >= total.value ? 'done' : 'doing'))
const statusLabel = computed(() => ({ todo: '未学', doing: '学习中', done: '已学' }[status.value]))
const firstUnstudied = computed(() => props.items.findIndex(i => !i.studied))
const subText = computed(() => `${props.date ? props.date + ' · ' : ''}共 ${total.value} ${props.unit}`)
const ctaLabel = computed(() => {
  if (status.value === 'done') return '复习本卷'
  if (status.value === 'todo') return '开始学习'
  return `继续学习 · 从第 ${firstUnstudied.value + 1} ${props.unit}`
})
function onStart() {
  const idx = firstUnstudied.value >= 0 ? firstUnstudied.value : 0
  emit('start', idx)
}
</script>

<style scoped>
.pcl { width: 100%; }
/* 卷头 */
.hd-card { position: relative; overflow: hidden; background: #fff; border: 2rpx solid #e6ebf2; border-radius: 20rpx; padding: 22rpx; margin-bottom: 16rpx; box-shadow: 0 6rpx 22rpx rgba(45, 80, 150, .06); }
/* 进度即底色:背景左→右填充(全项目统一进度样式) */
.hd-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; transition: width .3s; }
.hf-todo { background: transparent; }
.hf-doing { background: linear-gradient(90deg, #e8f2ff, #f4f9ff); }
.hf-done { background: linear-gradient(90deg, #e9f6f1, #f4fbf8); }
.hd-top { position: relative; display: flex; align-items: center; gap: 18rpx; }
.hd-num { flex: none; min-width: 96rpx; text-align: center; }
.hd-studied { font-size: 46rpx; font-weight: 800; color: #3d7bf0; line-height: 1; }
.hd-total { font-size: 26rpx; font-weight: 700; color: #b7c2d4; }
.hd-info { flex: 1; min-width: 0; }
.hd-status { font-size: 27rpx; font-weight: 800; display: flex; align-items: center; gap: 10rpx; }
.st-todo { color: #94a3b8; }
.st-doing { color: #3d8bf5; }
.st-done { color: #2fa98a; }
.hd-pct { font-size: 20rpx; font-weight: 700; color: #3d8bf5; background: #eaf2fe; border-radius: 6rpx; padding: 2rpx 10rpx; }
.st-done .hd-pct { color: #2fa98a; background: #e8f6ef; }
.st-todo .hd-pct { color: #94a3b8; background: #eef1f6; }
.hd-sub { display: block; font-size: 21rpx; color: #93a0b3; margin-top: 8rpx; }
.cta { display: flex; align-items: center; justify-content: center; gap: 12rpx; font-size: 27rpx; font-weight: 700; color: #fff; background: linear-gradient(135deg, #4c97f7, #3d7bf0); border-radius: 14rpx; padding: 20rpx 0; box-shadow: 0 6rpx 16rpx rgba(61, 123, 240, .28); }
.cta-ic { width: 28rpx; height: 28rpx; }

.list-h { font-size: 21rpx; font-weight: 700; color: #93a0b3; letter-spacing: 2rpx; margin: 4rpx 0 14rpx 4rpx; }
.empty { text-align: center; color: #93a0b3; font-size: 24rpx; padding: 50rpx 0; }

/* 清单行 */
.row { display: flex; align-items: center; gap: 18rpx; background: #fff; border: 2rpx solid #e9edf3; border-radius: 18rpx; padding: 20rpx 20rpx; margin-bottom: 16rpx; box-shadow: 0 3rpx 14rpx rgba(45, 80, 150, .04); }
.row.done { background: #fbfdfc; border-color: #e2efe9; }
.row.next { border: 3rpx solid #bcd6fb; box-shadow: 0 6rpx 18rpx rgba(61, 123, 240, .12); }
.tick { width: 40rpx; height: 40rpx; border-radius: 50%; flex: none; box-sizing: border-box; }
.tick-todo { border: 4rpx solid #cbd3e0; }
.tick-next { border: 4rpx solid #3d8bf5; background: #eaf2fe; }
.tick-done { background: #2fa98a url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='3.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E") center/22rpx no-repeat; }
.row-body { flex: 1; min-width: 0; }
.row-act { flex: none; font-size: 22rpx; color: #93a0b3; }
.act-next { color: #3d8bf5; font-weight: 700; }

/* flat 变体:一卡内连续行 + 细线分隔(单词模块,还原 H 大图行);默认关,不影响其它模块 */
.flat .row { margin: 0; border: 2rpx solid #e9edf3; border-top: none; border-radius: 0; box-shadow: none; background: #fff; }
.flat .row.first { border-top: 2rpx solid #e9edf3; border-top-left-radius: 18rpx; border-top-right-radius: 18rpx; }
.flat .row.last { border-bottom-left-radius: 18rpx; border-bottom-right-radius: 18rpx; }
.flat .row.done { background: #fbfdfc; }
.flat .row.next { background: linear-gradient(90deg, #eef6ff, #f6fbff); }
</style>

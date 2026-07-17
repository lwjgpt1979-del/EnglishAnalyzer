<template>
  <view class="ulm">
    <!-- 学期头:标题 + 本册进度 -->
    <view v-if="title" class="ulm-hd">
      <text class="ulm-title">{{ title }}</text>
      <view class="ulm-bar"><view class="ulm-fill" :style="{ width: pct + '%' }" /></view>
      <text class="ulm-cnt">{{ doneCount }}/{{ units.length }}</text>
    </view>

    <view v-if="!units.length" class="ulm-empty">该学期暂无内容</view>

    <!-- 关卡路径 -->
    <view v-for="(u, i) in decorated" :key="u.unit_id" class="ulm-row" :class="'a-' + (i % 3)">
      <view v-if="i > 0" class="ulm-link" :class="{ 'link-done': decorated[i - 1].done }" />
      <view class="ulm-node-wrap" @tap="tap(u)">
        <view class="ulm-node" :class="u.state">
          <view v-if="u.state === 'done'" class="ic ic-check ulm-ic" />
          <view v-else-if="u.state === 'locked'" class="ic ic-lock ulm-ic" />
          <view v-else class="ic ic-play-w ulm-ic" />
        </view>
        <view class="ulm-label">
          <text class="ulm-ut" :class="u.state">U{{ u.unit_no }} · {{ u.unit_title }}</text>
          <text class="ulm-us" :class="'s-' + u.state">{{ subText(u) }}</text>
        </view>
      </view>
    </view>

    <view v-if="nextHint" class="ulm-next"><view class="ic ic-chevrons-down ulm-next-ic" />{{ nextHint }}</view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

interface UnitItem { unit_id: string; unit_no: number; unit_title: string; total?: number; studied?: number; unlocked?: boolean }
const props = withDefaults(defineProps<{
  units: UnitItem[]
  unit?: string          // 词/点/句
  title?: string         // 学期标题,如「初二上册」
  nextHint?: string      // 底部提示,如「闯完本册接入初二下册」
}>(), { unit: '项', title: '', nextHint: '' })
const emit = defineEmits<{ (e: 'open', unitId: string): void }>()

type State = 'done' | 'current' | 'next' | 'locked'
const decorated = computed(() => {
  let currentSet = false
  return props.units.map((u) => {
    const total = u.total ?? 0
    const studied = u.studied ?? 0
    const done = total > 0 && studied >= total
    let state: State
    if (done) state = 'done'
    else if (!u.unlocked) state = 'locked'
    else if (!currentSet) { state = 'current'; currentSet = true }
    else state = 'next'   // 已解锁但非「当前主推」关(有进度/可继续)
    return { ...u, total, studied, done, state }
  })
})
const doneCount = computed(() => decorated.value.filter(u => u.done).length)
const pct = computed(() => props.units.length ? Math.round((doneCount.value / props.units.length) * 100) : 0)

function subText(u: { state: State; studied: number; total: number }): string {
  if (u.state === 'done') return `已通关 · ${u.total} ${props.unit}`
  if (u.state === 'locked') return `待解锁 · ${u.total} ${props.unit}`
  return `${u.studied}/${u.total} ${props.unit}`
}
function tap(u: { unit_id: string; state: State }) {
  if (u.state === 'locked') { uni.showToast({ title: '先通关前面的单元', icon: 'none' }); return }
  emit('open', u.unit_id)
}
</script>

<style scoped>
.ulm { width: 100%; }
.ulm-hd { display: flex; align-items: center; gap: 12rpx; margin-bottom: 20rpx; }
.ulm-title { font-size: 26rpx; font-weight: 700; color: #334155; flex: none; }
.ulm-bar { flex: 1; height: 12rpx; background: #e6ecf3; border-radius: 999rpx; overflow: hidden; }
.ulm-fill { height: 100%; background: #3d8bf5; border-radius: 999rpx; transition: width .3s; }
.ulm-cnt { font-size: 22rpx; font-weight: 700; color: #3d8bf5; flex: none; }
.ulm-empty { text-align: center; color: #93a0b3; font-size: 24rpx; padding: 60rpx 0; }

.ulm-row { display: flex; flex-direction: column; }
.a-0 { align-items: flex-start; }
.a-1 { align-items: center; }
.a-2 { align-items: flex-end; }
.ulm-link { width: 4rpx; height: 26rpx; background: #e4e9f0; margin: 0 46rpx; }
.link-done { background: #cfe3dc; }
.ulm-node-wrap { display: flex; align-items: center; gap: 14rpx; max-width: 90%; }
.a-2 .ulm-node-wrap { flex-direction: row-reverse; }
.ulm-node { width: 92rpx; height: 92rpx; border-radius: 50%; flex: none; display: flex; align-items: center; justify-content: center; }
.ulm-node.done { background: #2fa98a; box-shadow: 0 0 0 8rpx #e4f4ef; }
.ulm-node.current { background: #3d8bf5; box-shadow: 0 0 0 10rpx #e3eefd; }
.ulm-node.next { background: #eaf2fe; box-shadow: 0 0 0 8rpx #f2f7ff; }
.ulm-node.locked { background: #eef1f6; border: 3rpx solid #d7dee7; }
.ulm-ic { width: 42rpx; height: 42rpx; }
.ulm-node.next .ulm-ic { filter: brightness(0) saturate(100%) invert(52%) sepia(66%) saturate(1500%) hue-rotate(191deg); }
.ulm-label { display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.a-2 .ulm-label { align-items: flex-end; text-align: right; }
.ulm-ut { font-size: 25rpx; font-weight: 700; color: #1f2733; }
.ulm-ut.done, .ulm-ut.locked { color: #94a3b8; font-weight: 600; }
.ulm-us { font-size: 21rpx; }
.s-done { color: #2fa98a; }
.s-current, .s-next { color: #3d8bf5; }
.s-locked { color: #b0bbc9; }
.ulm-next { display: flex; align-items: center; gap: 8rpx; margin-top: 18rpx; padding-top: 14rpx; border-top: 1rpx dashed #e4e9f0; font-size: 22rpx; color: #b0bbc9; }
.ulm-next-ic { width: 26rpx; height: 26rpx; }
</style>

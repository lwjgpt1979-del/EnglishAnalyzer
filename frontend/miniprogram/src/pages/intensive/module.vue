<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · {{ kindLabel }}</text>
      <text class="hd-sub">{{ groupHint }}</text>
    </view>
    <view class="card build">
      <text class="build-t">该模块内容建设中</text>
      <text class="build-x">{{ modeLabel }}的{{ kindLabel }}将按{{ mode === 'homework' ? '批次(日期/每份卷)' : '版本→年级→上下册→单元' }}下钻呈现。</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'

const mode = ref('homework')
const kind = ref('word')
const KIND: Record<string, string> = { word: '单词', grammar: '语法精讲', sentence: '长难句' }
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))
const kindLabel = computed(() => KIND[kind.value] || '单词')
const groupHint = computed(() => mode.value === 'homework'
  ? '按批次(日期 / 每份卷)组织' : '按 版本 → 年级 → 上下册 → 单元 组织')

onLoad((q: any) => { mode.value = q.mode || 'homework'; kind.value = q.kind || 'word' })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 38rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 23rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; }
.card { background: #fff; border-radius: 20rpx; padding: 40rpx 24rpx; }
.build { display: flex; flex-direction: column; align-items: center; gap: 14rpx; }
.build-t { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.build-x { font-size: 24rpx; color: var(--c-text-sub); text-align: center; line-height: 1.6; }
</style>

<template>
  <view v-if="visible" class="sdm-mask" @tap="emit('close')">
    <view class="sdm-card" @tap.stop>
      <view class="sdm-badge"><view class="ic ic-trophy sdm-tr" /></view>
      <text class="sdm-title">{{ semesterLabel }} · {{ unitLabel }}全通关</text>
      <text class="sdm-sub">{{ unitTotal }} 个单元{{ contentTotal ? ' · ' + contentTotal + ' ' + unitLabel : '' }} 全部学过</text>

      <view class="sdm-acts">
        <view class="sdm-btn primary" @tap.stop="emit('quiz')">
          <view class="ic ic-clipboard-check sdm-ic w" /><text>来次学期测验</text>
        </view>
        <view v-if="nextSemester" class="sdm-btn ghost" @tap.stop="emit('preview')">
          <view class="ic ic-arrow-right sdm-ic" /><text>预习 {{ nextLabel }}</text>
        </view>
        <view class="sdm-btn plain" @tap.stop="emit('review')">
          <view class="ic ic-refresh sdm-ic" /><text>复习本学期</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  visible: boolean
  semesterLabel: string                 // 如「初二上册」
  unitLabel?: string                    // 词/语法/长难句
  unitTotal: number
  contentTotal?: number
  nextSemester: { grade: string; semester: string } | null
}>()
const emit = defineEmits<{ (e: 'quiz'): void; (e: 'preview'): void; (e: 'review'): void; (e: 'close'): void }>()

const unitLabel = computed(() => props.unitLabel || '单词')
const nextLabel = computed(() =>
  props.nextSemester ? `${props.nextSemester.grade}${props.nextSemester.semester}册` : '')
</script>

<style scoped>
.sdm-mask { position: fixed; inset: 0; background: rgba(20, 28, 40, .55); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 48rpx; }
.sdm-card { width: 100%; max-width: 560rpx; background: #fff; border-radius: 28rpx; padding: 40rpx 32rpx; box-sizing: border-box; text-align: center; }
.sdm-badge { width: 120rpx; height: 120rpx; margin: 0 auto; border-radius: 50%; background: #fff6e6; display: flex; align-items: center; justify-content: center; }
.sdm-tr { width: 64rpx; height: 64rpx; }
.sdm-title { display: block; font-size: 32rpx; font-weight: 800; color: #1f2733; margin-top: 22rpx; }
.sdm-sub { display: block; font-size: 24rpx; color: #64748b; margin-top: 10rpx; }
.sdm-acts { display: flex; flex-direction: column; gap: 18rpx; margin-top: 32rpx; }
.sdm-btn { display: flex; align-items: center; justify-content: center; gap: 12rpx; border-radius: 20rpx; padding: 22rpx; font-size: 26rpx; font-weight: 700; }
.sdm-btn.primary { background: #3d8bf5; color: #fff; }
.sdm-btn.ghost { background: #fff; border: 2rpx solid #cbd6e4; color: #3d8bf5; }
.sdm-btn.plain { color: #64748b; }
.sdm-ic { width: 32rpx; height: 32rpx; flex: none; }
.sdm-ic.w { filter: brightness(0) invert(1); }
</style>

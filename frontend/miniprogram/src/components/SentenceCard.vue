<template>
  <view v-if="text" class="card-mask" @tap="emit('close')">
    <view class="card-pop" @tap.stop>
      <view class="cp-head">
        <view class="ic ic-idea cp-ic"></view>
        <text class="cp-tt">长难句</text>
      </view>
      <text class="cp-text">{{ text }}</text>
      <text class="cp-hint">结构较复杂,点击查看逐句精讲(结构 · 语法 · 重点词)</text>
      <view class="cp-go" @tap="goFull">
        <text>查看完整精讲</text>
        <view class="ic ic-arrow-right cp-go-ic"></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
const props = defineProps<{ text: string | null; paperId?: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

function goFull() {
  if (!props.text) return
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(props.text)}&paperId=${props.paperId || ''}` })
}
</script>

<style scoped>
.card-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 300; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; }
.cp-head { display: flex; align-items: center; gap: 10rpx; }
.cp-ic { width: 32rpx; height: 32rpx; flex: none; }
.cp-tt { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.cp-text { display: block; font-size: 27rpx; color: var(--c-ink); line-height: 1.7; margin-top: 16rpx; }
.cp-hint { display: block; font-size: 23rpx; color: var(--c-text-sub); line-height: 1.6; margin-top: 14rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 12rpx; padding: 14rpx 16rpx; }
.cp-go { margin-top: 20rpx; display: flex; align-items: center; justify-content: center; gap: 6rpx; font-size: 26rpx; font-weight: 700; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 16rpx; }
.cp-go-ic { width: 26rpx; height: 26rpx; filter: brightness(0) invert(1); }
</style>

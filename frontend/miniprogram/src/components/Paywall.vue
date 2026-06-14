<!-- 统一会员墙：传入 feature(权益条目) 或 title/requiredTiers -->
<template>
  <view v-if="open" class="pw-mask" @tap.self="$emit('close')">
    <view class="pw-card">
      <text class="pw-emoji">{{ emoji }}🔒</text>
      <text class="pw-title">{{ title || feature?.title || '会员专享功能' }}</text>
      <text class="pw-desc">{{ desc }}</text>
      <button class="pw-btn" @tap="goMembership">{{ ctaText }}</button>
      <text class="pw-close" @tap="$emit('close')">暂不</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { requiredTierText } from '@/stores/entitlements'
import type { FeatureEntitlement } from '@/api/entitlements'

const props = defineProps<{
  open: boolean
  feature?: FeatureEntitlement | null
  title?: string
  emoji?: string
}>()
defineEmits<{ (e: 'close'): void }>()

const tierText = computed(() => requiredTierText(props.feature?.required_tiers))
const ctaText = computed(() => `去开通${tierText.value}会员`)
const emoji = computed(() => props.emoji || '✨')
const desc = computed(() => {
  const q = props.feature
  if (q && q.mode === 'quota' && (q.quota_left ?? 0) <= 0) {
    return `本周期次数已用完，升级到 ${tierText.value} 可不限次使用。`
  }
  return `开通 ${tierText.value} 会员后即可使用此功能。`
})

function goMembership() {
  uni.navigateTo({ url: '/pages/membership/activate' })
}
</script>

<style scoped>
.pw-mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1000; }
.pw-card { width: 560rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 44rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; }
.pw-emoji { font-size: 72rpx; }
.pw-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); text-align: center; }
.pw-desc { font-size: 26rpx; color: var(--c-text-second); text-align: center; line-height: 1.6; }
.pw-btn { width: 100%; margin-top: 8rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 30rpx; font-weight: 700; height: 80rpx; line-height: 80rpx; }
.pw-close { font-size: 26rpx; color: var(--c-text-hint); padding: 8rpx; }
</style>

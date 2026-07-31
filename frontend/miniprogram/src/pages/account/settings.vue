<template>
  <view class="page">
    <view class="card row" @tap.stop>
      <view class="row-main">
        <text class="row-title">细目闯关 · 进题听原句</text>
        <text class="row-sub">挖空/改错/选用进入时自动朗读原句（关则静默，仍可点喇叭）</text>
      </view>
      <switch
        :checked="facetSpeak"
        color="#3d8bf5"
        @change="onFacetSpeakChange"
      />
    </view>
    <view class="card" @tap="goCancel">
      <text class="row-title">注销账号</text>
      <text class="row-arrow">›</text>
    </view>
    <view class="card" @tap="goAgreement">
      <text class="row-title">用户协议</text>
      <text class="row-arrow">›</text>
    </view>
    <view class="card" @tap="goPrivacy">
      <text class="row-title">隐私政策</text>
      <text class="row-arrow">›</text>
    </view>
  </view>
</template>
<script setup lang="ts">
/**
 * 账号设置：含细目闯关进题听原句开关(方案 B,本地记忆)。
 */
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getFacetAutoSpeak, setFacetAutoSpeak } from '@/utils/readSeq'

const facetSpeak = ref(getFacetAutoSpeak())

onShow(() => {
  facetSpeak.value = getFacetAutoSpeak()
})

/** @param e switch change event */
function onFacetSpeakChange(e: { detail: { value: boolean } }) {
  const on = !!e.detail.value
  facetSpeak.value = on
  setFacetAutoSpeak(on)
  uni.showToast({ title: on ? '已开启进题听原句' : '已关闭进题听原句', icon: 'none' })
}

function goCancel() { uni.navigateTo({ url: '/pages/account/cancel' }) }
function goAgreement() { uni.navigateTo({ url: '/pages/account/agreement' }) }
function goPrivacy() { uni.navigateTo({ url: '/pages/account/privacy' }) }
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card {
  background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; margin-bottom: 16rpx;
  display: flex; align-items: center; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04);
}
.card.row { align-items: flex-start; gap: 16rpx; }
.row-main { flex: 1; min-width: 0; }
.row-title { flex: 1; font-size: 28rpx; color: var(--c-ink); display: block; }
.row-sub { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; line-height: 1.45; }
.row-arrow { font-size: 32rpx; color: var(--c-text-hint); }
</style>

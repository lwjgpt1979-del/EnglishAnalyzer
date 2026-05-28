<template>
  <view class="page">
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
function goCancel() { uni.navigateTo({ url: '/pages/account/cancel' }) }
function goAgreement() { uni.showToast({ title: '协议占位（MVP）', icon: 'none' }) }
function goPrivacy() { uni.showToast({ title: '隐私政策占位（MVP）', icon: 'none' }) }
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; margin-bottom: 16rpx; display: flex; align-items: center; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.row-title { flex: 1; font-size: 28rpx; color: var(--c-ink); }
.row-arrow { font-size: 32rpx; color: var(--c-text-hint); }
</style>

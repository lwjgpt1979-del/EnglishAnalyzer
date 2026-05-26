<!-- src/pages/index/index.vue -->
<template>
  <view class="home-page">
    <view class="hero">
      <text class="hero-title">engGramer</text>
      <text class="hero-sub">英语 AI 错题诊断</text>
    </view>

    <view class="quick-grid">
      <view
        class="quick-card"
        @tap="() => uni.navigateTo({ url: '/pages/upload/index' })"
      >
        <text class="quick-icon">📷</text>
        <text class="quick-label">上传错题</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.switchTab({ url: '/pages/wrong-questions/list' })"
      >
        <text class="quick-icon">📚</text>
        <text class="quick-label">我的错题</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.switchTab({ url: '/pages/diagnosis/index' })"
      >
        <text class="quick-icon">📊</text>
        <text class="quick-label">学情报告</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.switchTab({ url: '/pages/profile/index' })"
      >
        <text class="quick-icon">👤</text>
        <text class="quick-label">个人中心</text>
      </view>
    </view>

    <view v-if="!auth.isLoggedIn()" class="login-banner">
      <text class="login-tip">登录后解锁 AI 分析功能</text>
      <button class="btn-login" @tap="auth.login()">微信一键登录</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
</script>

<style scoped>
.home-page { padding: 40rpx 24rpx; background: #f5f5f5; min-height: 100vh; }
.hero { text-align: center; padding: 60rpx 0 48rpx; }
.hero-title { font-size: 60rpx; font-weight: bold; color: #1677ff; display: block; }
.hero-sub { font-size: 30rpx; color: #888; display: block; margin-top: 12rpx; }
.quick-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; margin-bottom: 32rpx; }
.quick-card {
  background: #fff;
  border-radius: 20rpx;
  padding: 40rpx 0;
  text-align: center;
}
.quick-icon { font-size: 56rpx; display: block; margin-bottom: 16rpx; }
.quick-label { font-size: 28rpx; color: #333; }
.login-banner {
  background: #fff;
  border-radius: 20rpx;
  padding: 36rpx 32rpx;
  text-align: center;
}
.login-tip { font-size: 28rpx; color: #666; display: block; margin-bottom: 24rpx; }
.btn-login { background: #1677ff; color: #fff; border-radius: 12rpx; font-size: 30rpx; }
</style>

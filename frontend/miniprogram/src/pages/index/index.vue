<!-- src/pages/index/index.vue -->
<template>
  <view class="home-page">
    <view class="topbar">
      <view class="bell-wrap" @tap="goMessages">
        <text class="bell">🔔</text>
        <text v-if="unreadCount > 0" class="badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</text>
      </view>
    </view>
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
        @tap="() => uni.navigateTo({ url: '/pages/vocabulary/index' })"
      >
        <text class="quick-icon">🔤</text>
        <text class="quick-label">词力通</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.navigateTo({ url: '/pages/essay/index' })"
      >
        <text class="quick-icon">✍️</text>
        <text class="quick-label">作文精修</text>
      </view>
      <view
        class="quick-card"
        @tap="() => uni.navigateTo({ url: '/pages/assignments/index' })"
      >
        <text class="quick-icon">📋</text>
        <text class="quick-label">老师任务</text>
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
import { onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { onShow } from '@dcloudio/uni-app'
import { getUnreadCount } from '@/api/notifications'

const auth = useAuthStore()

const unreadCount = ref(0)
async function loadUnread() {
  if (!auth.isLoggedIn()) { unreadCount.value = 0; return }
  try { const r = await getUnreadCount(); unreadCount.value = r.data?.count || 0 } catch { /* ignore */ }
}
function goMessages() { uni.navigateTo({ url: '/pages/messages/index' }) }
onShow(loadUnread)

onMounted(() => {
  if (auth.isLoggedIn() && auth.user && (auth.user as any).profile_completed === false) {
    uni.redirectTo({ url: '/pages/auth/complete-profile' })
    return
  }
  loadUnread()
})
</script>

<style scoped>
.home-page { padding: 40rpx 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.hero { text-align: center; padding: 60rpx 0 48rpx; }
.hero-title { font-size: var(--fs-display); font-weight: 800; color: var(--c-ink); display: block; }
.hero-sub { font-size: var(--fs-h2); color: var(--c-text-hint); display: block; margin-top: 12rpx; }
.quick-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; margin-bottom: 32rpx; }
.quick-card {
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: 40rpx 0;
  text-align: center;
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04);
}
.quick-icon { font-size: 56rpx; display: block; margin-bottom: 16rpx; }
.quick-label { font-size: var(--fs-body); color: var(--c-text-body); }
.login-banner {
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: 36rpx 32rpx;
  text-align: center;
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04);
}
.login-tip { font-size: var(--fs-body); color: var(--c-text-second); display: block; margin-bottom: 24rpx; }
.btn-login { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); font-size: var(--fs-h2); font-weight: 700; }
.topbar { display: flex; justify-content: flex-end; padding: 8rpx 0 16rpx; }
.bell-wrap { position: relative; padding: 8rpx; }
.bell { font-size: 40rpx; }
.badge { position: absolute; top: 0; right: 0; background: var(--c-danger); color: #fff; font-size: 20rpx; min-width: 28rpx; height: 28rpx; line-height: 28rpx; padding: 0 6rpx; border-radius: 999rpx; text-align: center; font-weight: 700; }
</style>

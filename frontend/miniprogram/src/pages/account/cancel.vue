<template>
  <view class="page">
    <view class="card">
      <view class="title">注销账号</view>
      <text class="warn">注销后历史数据不可恢复、剩余会员时长不退款。账号将进入 30 天冷静期，期间可撤销。</text>

      <view v-if="!sent && !inCooling">
        <button class="btn-danger" :disabled="loading" @tap="onRequest">{{ loading ? '发送中…' : '申请注销' }}</button>
      </view>

      <view v-else-if="sent && !inCooling">
        <input v-model="code" class="input" placeholder="6位验证码" />
        <text class="dev-hint">（开发模式：固定码 123456）</text>
        <button class="btn-danger" :disabled="loading" @tap="onConfirm">{{ loading ? '确认中…' : '确认注销' }}</button>
      </view>

      <view v-else class="cooling">
        <text class="cooling-title">⏳ 待注销中</text>
        <text class="cooling-days">剩余 {{ daysRemaining }} 天</text>
        <button class="btn-primary" :disabled="loading" @tap="onRevoke">{{ loading ? '撤销中…' : '撤销注销' }}</button>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { requestCancel, confirmCancel, revokeCancel } from '@/api/compliance'
const auth = useAuthStore()
const sent = ref(false)
const inCooling = ref(false)
const code = ref('')
const loading = ref(false)
const daysRemaining = ref<number | null>(null)
onMounted(() => {
  const u: any = auth.user
  if (u?.deactivation_scheduled_at) {
    inCooling.value = true
    daysRemaining.value = u.days_until_cancellation ?? null
  }
})
async function onRequest() {
  loading.value = true
  try {
    await requestCancel()
    sent.value = true
    uni.showToast({ title: '已发送验证码', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '发送失败', icon: 'none' })
  } finally { loading.value = false }
}
async function onConfirm() {
  loading.value = true
  try {
    const r = await confirmCancel(code.value)
    inCooling.value = true
    daysRemaining.value = r?.days_remaining ?? 30
    uni.showToast({ title: '已进入冷静期', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '确认失败', icon: 'none' })
  } finally { loading.value = false }
}
async function onRevoke() {
  loading.value = true
  try {
    await revokeCancel()
    inCooling.value = false
    sent.value = false
    uni.showToast({ title: '已撤销', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 800)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '撤销失败', icon: 'none' })
  } finally { loading.value = false }
}
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); margin-bottom: 16rpx; }
.warn { font-size: 26rpx; color: var(--c-danger-dark); display: block; line-height: 1.6; margin-bottom: 24rpx; padding: 16rpx; background: var(--c-danger-bg); border-radius: var(--r-md); }
.input { width: 100%; border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin: 16rpx 0 8rpx; box-sizing: border-box; }
.btn-danger { background: var(--c-danger); color: #fff; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-danger[disabled] { opacity: .5; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.cooling { text-align: center; padding: 24rpx 0; }
.cooling-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-orange); display: block; margin-bottom: 8rpx; }
.cooling-days { font-size: var(--fs-display); font-weight: 800; color: var(--c-ink); display: block; margin-bottom: 24rpx; }
.dev-hint { font-size: 22rpx; color: var(--c-text-hint); display: block; margin-bottom: 12rpx; }
</style>

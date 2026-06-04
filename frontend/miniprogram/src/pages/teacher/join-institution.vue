<template>
  <view class="page">
    <view class="hint">输入机构管理员提供的 6 位邀请码加入机构</view>
    <input class="code-input" v-model="code" placeholder="6 位邀请码" maxlength="6" />
    <button class="btn" :disabled="code.length < 6" @tap="submit">加入机构</button>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { joinInstitution } from '@/api/teacher'

const code = ref('')

async function submit() {
  try {
    await joinInstitution(code.value.trim().toUpperCase())
    uni.showToast({ title: '加入成功', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1200)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
</script>

<style scoped>
.page { padding: 48rpx; }
.hint { color: var(--c-text-second); font-size: 28rpx; margin-bottom: 32rpx; }
.code-input { background: var(--c-bg-card); border-radius: var(--r-md); padding: 24rpx; font-size: 36rpx; letter-spacing: 8rpx; text-align: center; }
.btn { margin-top: 48rpx; background: var(--c-primary); color: var(--c-ink); font-weight: 700; border-radius: var(--r-btn); }
</style>

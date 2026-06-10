<template>
  <view class="page">
    <view class="hint">输入机构发放的激活码，激活学生会员</view>
    <input class="code-input" v-model="code" placeholder="激活码" maxlength="12" />
    <button class="btn" :disabled="code.length < 6" @tap="submit">激活</button>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { activateCode } from '@/api/memberships'

const code = ref('')

async function submit() {
  try {
    await activateCode(code.value.trim().toUpperCase())
    uni.showToast({ title: '激活成功', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1200)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
</script>

<style scoped>
.page { padding: 48rpx; }
.hint { color: var(--c-text-second); font-size: 28rpx; margin-bottom: 32rpx; }
.code-input { background: var(--c-bg-card); border-radius: var(--r-md); padding: 24rpx; font-size: 34rpx; letter-spacing: 6rpx; text-align: center; }
.btn { margin-top: 48rpx; background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; border-radius: var(--r-btn); }
</style>

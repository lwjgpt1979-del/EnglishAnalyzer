<template>
  <view class="page">
    <view class="card">
      <view class="title">完善资料</view>
      <view class="row col">
        <text class="label">出生年份</text>
        <input v-model="birthYear" type="number" class="input" placeholder="如 2012" />
      </view>
      <view v-if="needGuardian" class="row col">
        <text class="label">监护人手机号</text>
        <input v-model="guardianPhone" class="input" placeholder="11位手机号" />
      </view>
      <view class="row col">
        <text class="label">本人手机号（可选）</text>
        <input v-model="userPhone" class="input" placeholder="用于注销验证" />
      </view>
      <view class="agree">
        <checkbox :checked="agreed" @tap="agreed = !agreed" /><text>我已阅读并同意《用户协议》《隐私政策》</text>
      </view>
      <button class="btn-primary" :disabled="!canSubmit || submitting" @tap="onSubmit">
        {{ submitting ? '提交中…' : '提交' }}
      </button>

      <view v-if="codeSent" class="row col" style="margin-top:24rpx">
        <text class="label">监护人收到的验证码</text>
        <input v-model="code" class="input" placeholder="6位数字" />
        <text class="dev-hint">（开发模式：固定码 123456）</text>
        <button class="btn-primary" :disabled="verifying" @tap="onVerify">
          {{ verifying ? '验证中…' : '完成验证' }}
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { completeProfile, guardianVerify } from '@/api/compliance'
const birthYear = ref('')
const guardianPhone = ref('')
const userPhone = ref('')
const agreed = ref(false)
const submitting = ref(false)
const verifying = ref(false)
const codeSent = ref(false)
const code = ref('')
const currentYear = new Date().getFullYear()
const age = computed(() => Number(birthYear.value) ? currentYear - Number(birthYear.value) : 0)
const needGuardian = computed(() => age.value > 0 && age.value < 14)
const canSubmit = computed(() =>
  Number(birthYear.value) >= 1900 && Number(birthYear.value) <= currentYear
  && agreed.value
  && (!needGuardian.value || guardianPhone.value.length === 11),
)
async function onSubmit() {
  submitting.value = true
  try {
    const r = await completeProfile({
      birth_year: Number(birthYear.value),
      guardian_phone: needGuardian.value ? guardianPhone.value : undefined,
      user_phone: userPhone.value || undefined,
      agreement_version: 'v1.0',
    })
    if (r?.needs_guardian_verify) {
      codeSent.value = true
      uni.showToast({ title: '已向监护人发送验证码', icon: 'success' })
    } else {
      uni.showToast({ title: '完善成功', icon: 'success' })
      setTimeout(() => uni.reLaunch({ url: '/pages/index/index' }), 800)
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}
async function onVerify() {
  verifying.value = true
  try {
    await guardianVerify(code.value)
    uni.showToast({ title: '验证通过', icon: 'success' })
    setTimeout(() => uni.reLaunch({ url: '/pages/index/index' }), 800)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '验证失败', icon: 'none' })
  } finally {
    verifying.value = false
  }
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); margin-bottom: 24rpx; }
.row { padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row.col { display: flex; flex-direction: column; gap: 8rpx; border-bottom: none; padding: 12rpx 0; }
.label { color: var(--c-text-second); font-size: 28rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; color: var(--c-text-body); box-sizing: border-box; width: 100%; }
.agree { display: flex; align-items: center; gap: 8rpx; margin: 24rpx 0 8rpx; font-size: 26rpx; color: var(--c-text-second); }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.dev-hint { font-size: 22rpx; color: var(--c-text-hint); }
</style>

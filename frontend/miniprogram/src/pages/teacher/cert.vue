<template>
  <view class="page">
    <view class="card">
      <view class="title">教师认证</view>
      <text class="status" :class="statusClass">当前状态：{{ statusLabel }}</text>
      <view class="row col">
        <text class="label">证书图片 URL（MVP）</text>
        <input v-model="url" class="input" placeholder="https://..." />
      </view>
      <text class="dev-hint">提示：dev 模式默认自动审核通过；提交后状态会变 certified。</text>
      <button class="btn-primary" :disabled="!url || submitting" @tap="onSubmit">
        {{ submitting ? '提交中…' : '提交认证' }}
      </button>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { submitCert } from '@/api/teacher'
import { request } from '@/utils/request'
const url = ref('')
const submitting = ref(false)
const certStatus = ref<string>('uncertified')
const statusLabel = computed(() => ({ uncertified: '未认证', pending: '审核中', certified: '已认证', rejected: '已拒绝' } as any)[certStatus.value] || certStatus.value)
const statusClass = computed(() => `s-${certStatus.value}`)

async function loadStatus() {
  try {
    const r: any = await request('/api/v1/teacher/profile', { method: 'POST', data: {} })
    certStatus.value = r.data?.cert_status || 'uncertified'
    url.value = r.data?.cert_doc_url || ''
  } catch {}
}
async function onSubmit() {
  submitting.value = true
  try {
    const r: any = await submitCert(url.value)
    certStatus.value = r.data?.cert_status || certStatus.value
    uni.showToast({ title: '已提交', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally { submitting.value = false }
}
onMounted(loadStatus)
</script>
<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); margin-bottom: 16rpx; }
.status { display: block; font-size: 28rpx; font-weight: 700; margin-bottom: 24rpx; padding: 12rpx; border-radius: var(--r-md); }
.s-uncertified, .s-pending { background: var(--c-primary-faint); color: var(--c-ink); }
.s-certified { background: var(--c-success-bg); color: var(--c-success-dark); }
.s-rejected { background: var(--c-danger-bg); color: var(--c-danger-dark); }
.row.col { display: flex; flex-direction: column; gap: 8rpx; margin-bottom: 16rpx; }
.label { color: var(--c-text-second); font-size: 28rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; }
.dev-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
</style>

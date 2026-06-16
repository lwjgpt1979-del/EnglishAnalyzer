<!-- 提交客服工单（§13.1）-->
<template>
  <view class="new-page">
    <view class="card">
      <text class="label">问题类型</text>
      <view class="cats">
        <view v-for="(v, k) in CAT" :key="k" class="cat" :class="{ on: category === k }" @tap="category = k">{{ v }}</view>
      </view>
      <text class="label">标题</text>
      <input v-model="subject" class="ipt" placeholder="一句话描述问题" maxlength="120" />
      <text class="label">详细描述</text>
      <textarea v-model="content" class="ta" placeholder="请详细描述您遇到的问题…" maxlength="1000" />
      <button class="submit" :disabled="submitting" @tap="submit">{{ submitting ? '提交中…' : '提交工单' }}</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { createTicket } from '@/api/support'

const CAT: Record<string, string> = { feature: '功能问题', refund: '退款咨询', order: '订单问题', complaint: '投诉', other: '其他' }
const category = ref('feature')
const subject = ref('')
const content = ref('')
const submitting = ref(false)

async function submit() {
  if (!subject.value.trim() || !content.value.trim()) {
    uni.showToast({ title: '请填写标题和描述', icon: 'none' }); return
  }
  submitting.value = true
  try {
    await createTicket({ category: category.value, subject: subject.value.trim(), content: content.value.trim() })
    uni.showToast({ title: '已提交，客服将尽快回复', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally { submitting.value = false }
}
</script>

<style scoped>
.new-page { padding: 24rpx; background: #f5f6f8; min-height: 100vh; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; }
.label { font-size: 26rpx; color: #666; display: block; margin: 20rpx 0 12rpx; }
.cats { display: flex; flex-wrap: wrap; gap: 16rpx; }
.cat { padding: 12rpx 28rpx; border-radius: 999rpx; background: #f0f2f5; font-size: 26rpx; color: #555; }
.cat.on { background: #409eff; color: #fff; }
.ipt { background: #f7f8fa; border-radius: 12rpx; padding: 20rpx; font-size: 28rpx; }
.ta { background: #f7f8fa; border-radius: 12rpx; padding: 20rpx; font-size: 28rpx; height: 220rpx; width: 100%; box-sizing: border-box; }
.submit { background: #409eff; color: #fff; border-radius: 999rpx; font-size: 30rpx; margin-top: 32rpx; }
</style>

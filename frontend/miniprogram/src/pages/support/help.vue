<!-- 帮助与反馈中心（§13）：FAQ 自助 + 联系客服 + 意见反馈 -->
<template>
  <view class="help-page">
    <!-- 快捷入口 -->
    <view class="entries">
      <view class="entry" @tap="goTickets">
        <view class="ic ic-headphone entry-ic" /><text class="entry-t">联系客服</text>
      </view>
      <view class="entry" @tap="goFeedback">
        <view class="ic ic-idea entry-ic" /><text class="entry-t">意见反馈</text>
      </view>
      <view class="entry" @tap="goCoupons">
        <view class="ic ic-tag entry-ic" /><text class="entry-t">我的优惠券</text>
      </view>
    </view>

    <!-- FAQ -->
    <view class="card">
      <text class="card-title">常见问题</text>
      <view v-if="!groups.length" class="muted">暂无常见问题</view>
      <view v-for="g in groups" :key="g.category" class="faq-group">
        <text class="faq-cat">{{ g.category }}</text>
        <view v-for="it in g.items" :key="it.id" class="faq-item" @tap="toggle(it.id)">
          <view class="faq-q-row">
            <text class="faq-q">{{ it.question }}</text>
            <text class="faq-arrow">{{ open[it.id] ? '−' : '+' }}</text>
          </view>
          <text v-if="open[it.id]" class="faq-a">{{ it.answer }}</text>
        </view>
      </view>
    </view>

    <view class="card hint-card">
      工作日 9:00-21:00，30 分钟内首次响应；非工作时间次日 9:00 前统一响应。
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getFaq, type FaqGroup } from '@/api/support'

const groups = ref<FaqGroup[]>([])
const open = ref<Record<string, boolean>>({})

function toggle(id: string) { open.value = { ...open.value, [id]: !open.value[id] } }
function goTickets() { uni.navigateTo({ url: '/pages/support/tickets' }) }
function goFeedback() { uni.navigateTo({ url: '/pages/support/feedback' }) }
function goCoupons() { uni.navigateTo({ url: '/pages/coupons/index' }) }

onMounted(async () => {
  try { groups.value = (await getFaq('c')).categories } catch { /* ignore */ }
})
</script>

<style scoped>
.help-page { padding: 24rpx; background: #f5f6f8; min-height: 100vh; }
.entries { display: flex; gap: 16rpx; margin-bottom: 24rpx; }
.entry { flex: 1; background: #fff; border-radius: 16rpx; padding: 28rpx 0; display: flex; flex-direction: column; align-items: center; gap: 10rpx; }
.entry-ic { width: 44rpx; height: 44rpx; }
.entry-t { font-size: 26rpx; color: #333; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 24rpx; }
.card-title { font-size: 30rpx; font-weight: 600; color: #222; display: block; margin-bottom: 16rpx; }
.muted { color: #999; font-size: 26rpx; }
.faq-group { margin-bottom: 16rpx; }
.faq-cat { font-size: 24rpx; color: #409eff; font-weight: 600; display: block; margin: 12rpx 0 6rpx; }
.faq-item { border-bottom: 1rpx solid #f0f0f0; padding: 16rpx 0; }
.faq-q-row { display: flex; justify-content: space-between; align-items: center; }
.faq-q { font-size: 28rpx; color: #333; flex: 1; }
.faq-arrow { font-size: 32rpx; color: #999; width: 40rpx; text-align: center; }
.faq-a { font-size: 26rpx; color: #666; line-height: 1.6; margin-top: 12rpx; display: block; white-space: pre-wrap; }
.hint-card { color: #999; font-size: 24rpx; line-height: 1.6; }
</style>

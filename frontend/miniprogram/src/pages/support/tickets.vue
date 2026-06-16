<!-- 我的客服工单（§13.1）-->
<template>
  <view class="tk-page">
    <button class="new-btn" @tap="goNew">+ 提交新工单</button>
    <view v-if="!items.length" class="empty">暂无工单</view>
    <view v-for="t in items" :key="t.id" class="tk-card" @tap="goDetail(t.id)">
      <view class="tk-row">
        <text class="tk-subject">{{ t.subject }}</text>
        <text class="tk-status" :class="t.status">{{ ST[t.status] || t.status }}</text>
      </view>
      <view class="tk-meta">
        <text class="tk-cat">{{ CAT[t.category] || t.category }}</text>
        <text class="tk-time">{{ fmt(t.updated_at) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { myTickets, type Ticket } from '@/api/support'

const items = ref<Ticket[]>([])
const CAT: Record<string, string> = { refund: '退款咨询', feature: '功能问题', complaint: '投诉', order: '订单问题', other: '其他' }
const ST: Record<string, string> = { open: '待回复', replied: '客服已回复', closed: '已结案' }
function fmt(s: string | null) { return (s || '').replace('T', ' ').slice(0, 16) }
function goNew() { uni.navigateTo({ url: '/pages/support/ticket-new' }) }
function goDetail(id: string) { uni.navigateTo({ url: `/pages/support/ticket-detail?id=${id}` }) }

onShow(async () => {
  try { items.value = (await myTickets()).items } catch { /* ignore */ }
})
</script>

<style scoped>
.tk-page { padding: 24rpx; background: #f5f6f8; min-height: 100vh; }
.new-btn { background: #409eff; color: #fff; border-radius: 999rpx; font-size: 28rpx; margin-bottom: 24rpx; }
.empty { color: #999; text-align: center; padding: 80rpx 0; font-size: 28rpx; }
.tk-card { background: #fff; border-radius: 16rpx; padding: 24rpx; margin-bottom: 16rpx; }
.tk-row { display: flex; justify-content: space-between; align-items: center; }
.tk-subject { font-size: 30rpx; color: #222; font-weight: 600; flex: 1; }
.tk-status { font-size: 24rpx; }
.tk-status.open { color: #e6a23c; }
.tk-status.replied { color: #67c23a; }
.tk-status.closed { color: #999; }
.tk-meta { display: flex; justify-content: space-between; margin-top: 12rpx; }
.tk-cat { font-size: 24rpx; color: #409eff; }
.tk-time { font-size: 24rpx; color: #999; }
</style>

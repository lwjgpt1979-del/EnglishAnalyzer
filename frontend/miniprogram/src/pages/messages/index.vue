<template>
  <view class="page">
    <!-- 频道筛选 -->
    <scroll-view scroll-x class="channels-wrap">
      <view class="channels">
        <text
          v-for="c in channels"
          :key="c.key"
          class="ch"
          :class="{ active: activeChannel === c.key }"
          @tap="switchChannel(c.key)"
        >{{ c.label }}</text>
      </view>
    </scroll-view>

    <!-- 操作栏 -->
    <view v-if="items.length > 0" class="actions">
      <text class="action-btn" @tap="onMarkAll">全部已读</text>
      <text class="action-btn" @tap="onDeleteRead">删除已读</text>
    </view>

    <!-- 列表 -->
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="items.length === 0" class="tip">暂无消息</view>
    <view
      v-for="n in items"
      :key="n.id"
      class="msg"
      :class="{ unread: !n.is_read }"
      @tap="onTap(n)"
    >
      <view v-if="!n.is_read" class="dot" />
      <view class="msg-body">
        <view class="msg-head">
          <text class="msg-title">{{ n.title }}</text>
          <text class="msg-time">{{ n.created_at.slice(5, 16).replace('T', ' ') }}</text>
        </view>
        <text class="msg-content">{{ n.content }}</text>
        <text class="msg-channel">{{ channelLabel(n.channel) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listNotifications, markRead, markAllRead, deleteRead } from '@/api/notifications'
import type { NotificationOut } from '@/types/api'

const channels = [
  { key: '', label: '全部' },
  { key: 'study', label: '📚 学习' },
  { key: 'membership', label: '💳 会员' },
  { key: 'system', label: '🔔 系统' },
  { key: 'teacher', label: '👩‍🏫 老师' },
  { key: 'relative', label: '👨‍👩‍👧 亲人' },
]
const activeChannel = ref('')
const items = ref<NotificationOut[]>([])
const loading = ref(false)

function channelLabel(c: string): string {
  const m: Record<string, string> = { study: '学习', membership: '会员', system: '系统', teacher: '老师', relative: '亲人' }
  return m[c] || c
}

async function load() {
  loading.value = true
  try {
    const r = await listNotifications({ channel: activeChannel.value || undefined, limit: 50 })
    items.value = r.data?.items || []
  } finally { loading.value = false }
}

async function switchChannel(c: string) {
  activeChannel.value = c
  await load()
}

async function onTap(n: NotificationOut) {
  if (!n.is_read) {
    try { await markRead(n.id); n.is_read = true } catch { /* ignore */ }
  }
  if (n.meta?.wq_id) {
    uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${n.meta.wq_id}` })
  } else if (n.type === 'weekly_report' && n.meta) {
    // 周报详情：将 meta 整体 JSON 传给详情页，student_name 从通知标题中提取
    const data = encodeURIComponent(JSON.stringify(n.meta))
    const studentName = encodeURIComponent(n.title || '孩子')
    uni.navigateTo({ url: `/pages/relative/weekly-report-detail?data=${data}&student_name=${studentName}` })
  } else if (n.channel === 'membership') {
    uni.switchTab({ url: '/pages/profile/index' })
  }
}

async function onMarkAll() {
  try { await markAllRead(); await load(); uni.showToast({ title: '已全部标已读', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '操作失败', icon: 'none' }) }
}

async function onDeleteRead() {
  try { await deleteRead(); await load(); uni.showToast({ title: '已清空已读', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '操作失败', icon: 'none' }) }
}

onMounted(load)
</script>

<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.channels-wrap { white-space: nowrap; }
.channels { display: inline-flex; gap: 8rpx; padding: 8rpx 4rpx 16rpx; }
.ch { padding: 8rpx 18rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 24rpx; color: var(--c-text-second); white-space: nowrap; }
.ch.active { background: var(--c-primary); color: var(--c-ink); font-weight: 700; }
.actions { display: flex; gap: 16rpx; padding: 8rpx 8rpx 16rpx; }
.action-btn { font-size: 24rpx; color: var(--c-gold); font-weight: 600; padding: 4rpx 12rpx; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); font-size: 26rpx; }
.msg { display: flex; gap: 12rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 12rpx; box-shadow: 0 2rpx 12rpx rgba(0,0,0,.03); }
.msg.unread { background: var(--c-primary-faint); border-left: 4rpx solid var(--c-gold); }
.dot { width: 12rpx; height: 12rpx; background: var(--c-orange); border-radius: 50%; margin-top: 12rpx; flex-shrink: 0; }
.msg-body { flex: 1; }
.msg-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6rpx; }
.msg-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.msg-time { font-size: 22rpx; color: var(--c-text-hint); }
.msg-content { font-size: 26rpx; color: var(--c-text-body); line-height: 1.5; display: block; margin-bottom: 6rpx; }
.msg-channel { font-size: 22rpx; color: var(--c-text-hint); }
</style>

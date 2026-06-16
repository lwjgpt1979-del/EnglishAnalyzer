<!-- 平台公告（§5.6）-->
<template>
  <view class="ann-page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!items.length" class="tip">暂无公告</view>
    <view v-for="a in items" :key="a.id" class="ann-card" @tap="toggle(a.id)">
      <view class="ann-head">
        <text v-if="a.pinned" class="pin">置顶</text>
        <text class="ann-title">{{ a.title }}</text>
      </view>
      <text class="ann-time">{{ (a.created_at || '').replace('T', ' ').slice(0, 16) }}</text>
      <text class="ann-content" :class="{ collapsed: !open[a.id] }">{{ a.content }}</text>
      <text class="ann-toggle">{{ open[a.id] ? '收起' : '展开全文' }}</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getAnnouncements, type Announcement } from '@/api/announcements'

const items = ref<Announcement[]>([])
const loading = ref(true)
const open = ref<Record<string, boolean>>({})
function toggle(id: string) { open.value = { ...open.value, [id]: !open.value[id] } }

onMounted(async () => {
  try { items.value = (await getAnnouncements()).items } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.ann-page { padding: 24rpx; background: #f5f6f8; min-height: 100vh; }
.tip { text-align: center; color: #999; padding: 80rpx 0; font-size: 28rpx; }
.ann-card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 16rpx; }
.ann-head { display: flex; align-items: center; gap: 10rpx; }
.pin { background: #ff6b35; color: #fff; font-size: 20rpx; padding: 2rpx 10rpx; border-radius: 6rpx; }
.ann-title { font-size: 30rpx; font-weight: 600; color: #222; flex: 1; }
.ann-time { font-size: 22rpx; color: #999; display: block; margin: 8rpx 0; }
.ann-content { font-size: 27rpx; color: #555; line-height: 1.6; display: block; white-space: pre-wrap; }
.ann-content.collapsed { overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.ann-toggle { font-size: 24rpx; color: #409eff; margin-top: 10rpx; display: block; }
</style>

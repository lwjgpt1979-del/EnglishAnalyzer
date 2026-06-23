<!-- src/pages/user-papers/list.vue -->
<template>
  <view class="list-page">
    <!-- 顶部上传入口 -->
    <view class="upload-entry" @tap="goUpload">
      <view class="ue-icon"><view class="ic ic-plus" style="width:40rpx;height:40rpx" /></view>
      <view class="ue-text">
        <text class="ue-title">拍整张试卷</text>
        <text class="ue-sub">1~9 张图片，自动识别并拆题</text>
      </view>
      <text class="ue-arrow">›</text>
    </view>

    <!-- 加载态 -->
    <view v-if="loading && items.length === 0" class="center-tip">加载中…</view>

    <!-- 空状态 -->
    <view v-else-if="!loading && items.length === 0" class="center-tip">
      <text>还没有上传整卷，点上方按钮试试 📄</text>
    </view>

    <!-- 列表 -->
    <view v-else>
      <view
        v-for="p in items"
        :key="p.id"
        class="paper-card"
        @tap="goDetail(p.id)"
      >
        <view class="pc-head">
          <text class="pc-title">{{ p.title || '未命名试卷' }}</text>
          <text class="status" :class="statusClass(p.ocr_status)">{{ statusText(p.ocr_status) }}</text>
        </view>
        <text class="pc-meta">{{ p.source_image_urls.length }} 张图片 · {{ p.question_count }} 道题</text>
        <text class="pc-date">{{ p.created_at.slice(0, 10) }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listUserPapers } from '@/api/userPapers'
import { useAuthStore } from '@/stores/auth'
import type { PaperOcrStatus, UserPaperOut } from '@/types/api'

const auth = useAuthStore()
const items = ref<UserPaperOut[]>([])
const loading = ref(false)

onShow(async () => {
  if (!auth.isLoggedIn()) {
    await auth.login()
  }
  await load()
})

async function load() {
  if (loading.value) return
  loading.value = true
  try {
    const res = await listUserPapers()
    items.value = res.items
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

function statusText(s: PaperOcrStatus): string {
  const map: Record<string, string> = {
    pending: '排队中',
    processing: '识别中',
    completed: '已完成',
    failed: '失败',
  }
  return map[s || ''] || '未知'
}

function statusClass(s: PaperOcrStatus): string {
  if (s === 'completed') return 'ok'
  if (s === 'failed') return 'bad'
  return 'wait'
}

function goUpload() {
  uni.navigateTo({ url: '/pages/user-papers/upload' })
}

function goDetail(id: string) {
  uni.navigateTo({ url: `/pages/user-papers/detail?id=${id}` })
}
</script>

<style scoped>
.list-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }
.upload-entry {
  display: flex;
  align-items: center;
  gap: 20rpx;
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: 28rpx;
  margin-bottom: 24rpx;
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04);
}
.ue-icon {
  width: 72rpx;
  height: 72rpx;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--c-primary-soft);
  border-radius: var(--r-md);
}
.ue-text { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.ue-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.ue-sub { font-size: 24rpx; color: var(--c-text-hint); }
.ue-arrow { font-size: 40rpx; color: var(--c-text-hint); }
.paper-card {
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: 28rpx;
  margin-bottom: 20rpx;
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04);
  display: flex;
  flex-direction: column;
  gap: 12rpx;
}
.pc-head { display: flex; align-items: center; gap: 16rpx; }
.pc-title { flex: 1; font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.status { font-size: 22rpx; padding: 4rpx 16rpx; border-radius: var(--r-pill); }
.status.ok { background: #eafaf1; color: #2ecc71; }
.status.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status.wait { background: var(--c-primary-faint); color: #b9892e; }
.pc-meta { font-size: 24rpx; color: var(--c-text-second); }
.pc-date { font-size: 24rpx; color: var(--c-text-hint); }
</style>

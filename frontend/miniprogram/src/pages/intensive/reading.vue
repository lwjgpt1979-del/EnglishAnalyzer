<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">作业精讲 · 阅读理解</text>
      <text class="hd-sub">来自你上传作业里的阅读理解,按卷复习:读短文、看题、对答案。</text>
    </view>

    <!-- 阅读学情入口:跨卷聚合薄弱点 -->
    <view v-if="batches.length" class="ae" @tap="goAnalytics">
      <view class="ic-chart ae-ic"></view>
      <text class="ae-t">阅读学情 · 找薄弱点</text>
      <text class="ae-go">查看 ›</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!batches.length" class="tip">还没有阅读理解——上传含阅读理解的作业即可在此复习。</view>

    <!-- 批次列表:点作业名 → 跳该卷阅读详情页,返回即回来 -->
    <IntensiveBatchList v-else :batches="batchItems" unit="题" @open="openById" />
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { rdHwBatches, type IntensiveBatch } from '@/api/curriculum'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'

const batches = ref<IntensiveBatch[]>([])
const loading = ref(true)
const batchItems = computed<BatchItem[]>(() => batches.value.map(b => ({
  id: b.paper_id, title: b.title, date: b.date, count: b.count, studied: (b as any).studied,
})))

function goAnalytics() { uni.navigateTo({ url: '/pages/intensive/reading-analytics' }) }

// 点作业名 → 跳独立阅读详情页(reading-paper),原生返回回到本列表
function openById(id: string) {
  const b = batches.value.find(x => x.paper_id === id)
  if (!b) return
  uni.navigateTo({ url: `/pages/intensive/reading-paper?paperId=${id}&title=${encodeURIComponent(b.title || '阅读理解精讲')}` })
}

async function loadBatches() {
  try { batches.value = (await rdHwBatches()).batches } catch { /* ignore */ }
  finally { loading.value = false }
}

onLoad(loadBatches)
// 从阅读详情页返回 → 刷新卷进度打勾(跳过 onLoad 后首次)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } loadBatches() })
</script>

<style scoped>
.page { min-height: 100vh; background: #f4f6fa; padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: #1f2733; display: block; }
.hd-sub { font-size: 24rpx; color: #93a0b3; margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: #93a0b3; padding: 60rpx 0; }

/* 阅读学情入口 */
.ae { display: flex; align-items: center; gap: 12rpx; background: #fff; border: 2rpx solid #e6ebf2; border-radius: 16rpx; padding: 20rpx 22rpx; margin-bottom: 18rpx; box-shadow: 0 4rpx 16rpx rgba(45, 80, 150, .05); }
.ae-ic { width: 34rpx; height: 34rpx; flex: none; background-size: contain; background-repeat: no-repeat; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='18' y1='20' x2='18' y2='10'/%3E%3Cline x1='12' y1='20' x2='12' y2='4'/%3E%3Cline x1='6' y1='20' x2='6' y2='14'/%3E%3C/svg%3E"); }
.ae-t { font-size: 28rpx; font-weight: 700; color: #1f2733; }
.ae-go { margin-left: auto; font-size: 24rpx; font-weight: 600; color: #3d8bf5; }
</style>

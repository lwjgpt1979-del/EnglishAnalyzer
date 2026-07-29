<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">作业精讲 · 完形填空</text>
      <text class="hd-sub">上传作业里的完形，按卷复习：读语篇、抠空、看详解。</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!batches.length" class="tip">还没有完形填空——在作业详情点「加入完形填空精讲」后会出现在这里。</view>
    <IntensiveBatchList v-else :batches="batchItems" unit="空" @open="openById" />
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { czHwBatches, type IntensiveBatch } from '@/api/curriculum'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'

const batches = ref<IntensiveBatch[]>([])
const loading = ref(true)
const batchItems = computed<BatchItem[]>(() => batches.value.map(b => ({
  id: b.paper_id, title: b.title, date: b.date, count: b.count, studied: (b as any).studied,
})))

function openById(id: string) {
  const b = batches.value.find(x => x.paper_id === id)
  if (!b) return
  uni.navigateTo({
    url: `/pages/intensive/cloze-paper?paperId=${id}&title=${encodeURIComponent(b.title || '完形填空精讲')}`,
  })
}

async function loadBatches() {
  try { batches.value = (await czHwBatches()).batches } catch { /* ignore */ }
  finally { loading.value = false }
}

onLoad(loadBatches)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } loadBatches() })
</script>

<style scoped>
.page { min-height: 100vh; background: #f0f6fc; padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: #1f2733; display: block; }
.hd-sub { font-size: 24rpx; color: #93a0b3; margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: #93a0b3; padding: 60rpx 0; }
</style>

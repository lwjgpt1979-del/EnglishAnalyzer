<!-- src/pages/essay/error-book.vue 作文写作错因本 -->
<template>
  <view class="eb-page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!data || !data.items.length" class="tip">还没有写作错误记录，去写一篇试试 ✍️</view>
    <view v-else>
      <view class="eb-sum">
        <text v-for="t in data.by_type" :key="t.type" class="eb-chip">{{ t.type }} {{ t.count }}</text>
      </view>
      <view v-for="(it, i) in data.items" :key="i" class="eb-item">
        <text class="eb-type">{{ it.type }}</text>
        <view class="eb-o" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-x-circle" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ it.original }}</text></view>
        <view class="eb-s" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-check-circle" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ it.suggestion }}</text></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getEssayErrorLog, type EssayErrorLog } from '@/api/essay'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const data = ref<EssayErrorLog | null>(null)

onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  try { data.value = await getEssayErrorLog() } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally { loading.value = false }
})
</script>

<style scoped>
.eb-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 140rpx 40rpx; color: var(--c-text-hint); line-height: 1.8; }
.eb-sum { display: flex; flex-wrap: wrap; gap: 12rpx; margin-bottom: 18rpx; }
.eb-chip { font-size: 24rpx; font-weight: 700; color: #d6457e; background: #fff0f5; border-radius: 999rpx; padding: 6rpx 20rpx; }
.eb-item { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 20rpx; margin-bottom: 14rpx; display: flex; flex-direction: column; gap: 6rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.eb-type { font-size: 20rpx; font-weight: 700; color: #d6457e; background: #fff0f5; border-radius: 999rpx; padding: 2rpx 14rpx; align-self: flex-start; }
.eb-o { font-size: 26rpx; color: #ff6b6b; }
.eb-s { font-size: 26rpx; color: #1b7a3d; }
</style>

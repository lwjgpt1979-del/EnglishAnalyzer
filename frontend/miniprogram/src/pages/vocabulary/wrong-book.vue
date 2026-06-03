<!-- src/pages/vocabulary/wrong-book.vue 词力通错词本 -->
<template>
  <view class="wb-page">
    <view v-if="loading" class="center-tip">加载中…</view>
    <view v-else-if="!items.length" class="center-tip">还没有错词，继续加油 🎉</view>
    <view v-else>
      <view class="wb-hint">共 {{ items.length }} 个错词 · 错得多的排在前面</view>
      <view v-for="it in items" :key="it.word_id" class="wb-item">
        <view class="wb-head">
          <text class="wb-word">{{ it.word }}</text>
          <text class="wb-badge">错 {{ it.wrong_count }} 次</text>
        </view>
        <text v-if="it.phonetic" class="wb-ph">/{{ it.phonetic }}/</text>
        <text class="wb-def">{{ defText(it) }}</text>
        <text class="wb-level">熟练度：{{ it.level }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getWrongWords } from '@/api/vocabulary'
import { useAuthStore } from '@/stores/auth'
import type { VocabWrongItem } from '@/types/api'

const auth = useAuthStore()
const loading = ref(true)
const items = ref<VocabWrongItem[]>([])

function defText(it: VocabWrongItem): string {
  const d = it.definitions
  if (Array.isArray(d)) return d.map((x: any) => `${x.pos ? x.pos + ' ' : ''}${x.meaning}`).join('；')
  return ''
}

async function load() {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try {
    items.value = (await getWrongWords()).items
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<style scoped>
.wb-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); }
.wb-hint { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.wb-item { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,0.04); }
.wb-head { display: flex; justify-content: space-between; align-items: baseline; }
.wb-word { font-size: 36rpx; font-weight: 800; color: var(--c-ink); }
.wb-badge { font-size: 24rpx; color: var(--c-danger); font-weight: 600; }
.wb-ph { display: block; font-size: 26rpx; color: var(--c-text-second); margin-top: 4rpx; }
.wb-def { display: block; font-size: 28rpx; color: var(--c-text-body); margin-top: 10rpx; }
.wb-level { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
</style>

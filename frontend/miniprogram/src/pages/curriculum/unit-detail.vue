<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="detail">
      <view class="header">
        <text class="badge">U{{ detail.unit_no }}</text>
        <text class="title">{{ detail.unit_title }}</text>
        <text class="meta">{{ detail.knowledge_points.length }} 知识点 · {{ detail.words.length }} 词</text>
      </view>

      <view class="card">
        <view class="card-title">知识点</view>
        <view
          v-for="kp in detail.knowledge_points"
          :key="kp.id"
          class="kp-row"
          @tap="goKp(kp.id)"
        >
          <view class="kp-body">
            <text class="kp-name">{{ kp.name }}</text>
            <text class="kp-cat">{{ catLabel(kp.category) }}</text>
          </view>
          <text class="chevron">›</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">词汇 ({{ detail.words.length }})</view>
        <view v-for="w in detail.words" :key="w.id" class="word-row">
          <text class="word-en">{{ w.word }}</text>
          <text v-if="w.phonetic" class="word-ph">{{ w.phonetic }}</text>
          <text class="word-cn">{{ definitionText(w.definitions) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getUnitDetail } from '@/api/curriculum'
import type { UnitDetailOut, WordOut } from '@/types/api'

const detail = ref<UnitDetailOut | null>(null)
const loading = ref(true)

onLoad(async (q: any) => {
  try {
    detail.value = await getUnitDetail(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
  } finally {
    loading.value = false
  }
})

function goKp(id: string) {
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${id}` })
}
function catLabel(c: string): string {
  return ({ grammar: '语法', vocabulary: '词汇', reading: '阅读', writing: '写作', listening: '听力' } as any)[c] || c
}
function definitionText(defs: WordOut['definitions']): string {
  return defs.map(d => (d.pos ? `${d.pos} ${d.meaning}` : d.meaning)).join('；')
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.header { display: flex; align-items: center; gap: 16rpx; padding: 12rpx 0 24rpx; }
.badge { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-md); padding: 6rpx 14rpx; font-size: 26rpx; font-weight: 800; }
.title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); flex: 1; }
.meta { font-size: 22rpx; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 16rpx; color: var(--c-ink); }
.kp-row { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.kp-row:last-child { border-bottom: none; }
.kp-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.kp-name { font-size: 28rpx; color: var(--c-ink); font-weight: 600; }
.kp-cat { font-size: 22rpx; color: var(--c-text-second); }
.chevron { color: var(--c-text-hint); font-size: 32rpx; }
.word-row { display: flex; align-items: baseline; gap: 12rpx; padding: 12rpx 0; border-bottom: 1rpx dashed var(--c-border); }
.word-row:last-child { border-bottom: none; }
.word-en { font-size: 28rpx; font-weight: 700; color: var(--c-ink); min-width: 160rpx; }
.word-ph { font-size: 22rpx; color: var(--c-text-hint); }
.word-cn { flex: 1; font-size: 24rpx; color: var(--c-text-body); }
</style>

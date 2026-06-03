<template>
  <view class="page">
    <view v-if="!essay" class="tip">加载中…</view>
    <view v-else>
      <view class="card">
        <view class="card-title">总分 {{ essay.total }}</view>
        <view v-for="s in essay.scores" :key="s.dimension" class="score-row">
          <text class="dim">{{ s.dimension }}</text>
          <text class="sc">{{ s.score }} / {{ s.full }}</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">原文</view>
        <text class="para">{{ essay.original_text }}</text>
      </view>

      <view class="card">
        <view class="card-title">AI 优化版</view>
        <text class="para">{{ essay.polished_text }}</text>
      </view>

      <view v-if="essay.issues.length" class="card">
        <view class="card-title">逐处建议</view>
        <view v-for="(it, i) in essay.issues" :key="i" class="issue" :class="it.color">
          <text class="issue-head">{{ it.original }} → {{ it.suggestion }}（{{ it.type }}）</text>
          <text class="issue-exp">{{ it.explanation }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getEssay } from '@/api/essay'
import type { EssayDetail } from '@/types/api'

const essay = ref<EssayDetail | null>(null)

onLoad((q) => {
  const id = (q as { id?: string })?.id
  if (id) getEssay(id).then((e) => { essay.value = e }).catch((e) => {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  })
})
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.score-row { display: flex; justify-content: space-between; padding: 8rpx 0; font-size: 28rpx; color: var(--c-text-body); }
.sc { font-weight: 700; color: var(--c-gold); }
.para { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; white-space: pre-wrap; }
.issue { padding: 12rpx; border-radius: 12rpx; margin-bottom: 12rpx; background: var(--c-bg-page); border-left: 6rpx solid var(--c-border); }
.issue.red { border-left-color: #e54d42; }
.issue.yellow { border-left-color: #f0ad4e; }
.issue.blue { border-left-color: #3b82f6; }
.issue-head { display: block; font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.issue-exp { display: block; font-size: 24rpx; color: var(--c-text-second); margin-top: 6rpx; line-height: 1.6; }
</style>

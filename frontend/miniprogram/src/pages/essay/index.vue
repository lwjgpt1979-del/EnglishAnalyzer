<template>
  <view class="page">
    <view class="card">
      <view class="card-title">作文 AI 精修</view>
      <textarea v-model="text" class="essay-input" placeholder="粘贴或输入你的英文作文…" :maxlength="-1" />
      <input v-model="essayType" class="type-input" placeholder="作文题型（选填，如 话题作文）" />
      <button class="btn-primary" :disabled="loading || !text.trim()" @tap="onSubmit">
        {{ loading ? 'AI 批改中…' : 'AI 精修' }}
      </button>
      <view class="tip">Pro/ProMax 专属 · Pro 每月 3 次</view>
    </view>

    <view class="card">
      <view class="card-title">历史精修</view>
      <view v-if="!list.length" class="empty">还没有精修记录</view>
      <view v-for="it in list" :key="it.id" class="row" @tap="goDetail(it.id)">
        <text class="row-title">{{ it.title || it.essay_type || '作文' }}</text>
        <text class="row-score">{{ it.total }} 分</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { createEssay, getEssays } from '@/api/essay'
import type { EssayListItem } from '@/types/api'

const text = ref('')
const essayType = ref('')
const loading = ref(false)
const list = ref<EssayListItem[]>([])

async function loadList() {
  try { list.value = (await getEssays()).items } catch { /* 忽略 */ }
}
onShow(loadList)

async function onSubmit() {
  loading.value = true
  try {
    const r = await createEssay({ original_text: text.value, essay_type: essayType.value || undefined })
    text.value = ''
    uni.navigateTo({ url: `/pages/essay/detail?id=${r.id}` })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}
function goDetail(id: string) { uni.navigateTo({ url: `/pages/essay/detail?id=${id}` }) }
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.essay-input { width: 100%; height: 320rpx; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; }
.type-input { width: 100%; height: 72rpx; font-size: 26rpx; border-top: 1rpx solid var(--c-border); margin-top: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.tip { font-size: 22rpx; color: var(--c-text-hint); margin-top: 12rpx; text-align: center; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.row { display: flex; justify-content: space-between; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row-title { font-size: 28rpx; color: var(--c-text-body); }
.row-score { font-size: 28rpx; font-weight: 700; color: var(--c-gold); }
</style>

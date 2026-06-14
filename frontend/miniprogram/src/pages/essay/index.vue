<template>
  <view class="page">
    <view class="card train-entry" @tap="goTrain">
      <view class="te-l"><text class="te-t">✍️ 应试写作训练</text><text class="te-s">审题 · 限时写 · 按档诊断 · 漏点检测</text></view>
      <text class="te-arrow">›</text>
    </view>
    <view v-if="progress && progress.total_essays > 0" class="card">
      <view class="card-title">我的进步</view>
      <view class="prog-row">
        <text>已精修 {{ progress.total_essays }} 篇</text>
        <text class="prog-avg">平均 {{ progress.avg_total }} 分</text>
      </view>
      <view v-for="d in progress.dimension_avg" :key="d.dimension" class="prog-dim">
        <text>{{ d.dimension }}</text><text class="prog-avg">{{ d.avg }}</text>
      </view>
    </view>

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
import { createEssay, getEssays, getEssayProgress } from '@/api/essay'
import type { EssayListItem, EssayProgress } from '@/types/api'

const text = ref('')
const essayType = ref('')
const loading = ref(false)
const list = ref<EssayListItem[]>([])
const progress = ref<EssayProgress | null>(null)

async function loadList() {
  try { list.value = (await getEssays()).items } catch { /* 忽略 */ }
}
async function loadProgress() {
  try { progress.value = await getEssayProgress() } catch { /* 忽略 */ }
}
onShow(() => { loadList(); loadProgress() })

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
function goTrain() { uni.navigateTo({ url: '/pages/essay/train' }) }
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.train-entry { display: flex; align-items: center; justify-content: space-between; background: linear-gradient(135deg, var(--c-primary), var(--c-primary-deep)); }
.te-l { display: flex; flex-direction: column; gap: 6rpx; }
.te-t { font-size: 32rpx; font-weight: 800; color: #fff; }
.te-s { font-size: 22rpx; color: rgba(255,255,255,.85); }
.te-arrow { font-size: 44rpx; color: #fff; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.essay-input { width: 100%; height: 320rpx; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; }
.type-input { width: 100%; height: 72rpx; font-size: 26rpx; border-top: 1rpx solid var(--c-border); margin-top: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; margin-top: 16rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.tip { font-size: 22rpx; color: var(--c-text-hint); margin-top: 12rpx; text-align: center; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.row { display: flex; justify-content: space-between; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row-title { font-size: 28rpx; color: var(--c-text-body); }
.row-score { font-size: 28rpx; font-weight: 700; color: var(--c-gold); }
.prog-row { display: flex; justify-content: space-between; font-size: 28rpx; color: var(--c-text-body); margin-bottom: 8rpx; }
.prog-avg { font-weight: 700; color: var(--c-gold); }
.prog-dim { display: flex; justify-content: space-between; font-size: 26rpx; color: var(--c-text-second); padding: 4rpx 0; }
</style>

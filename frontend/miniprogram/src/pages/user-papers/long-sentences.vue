<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">本卷长难句</text>
      <text class="hd-sub">原文里的长难句,点「解析」拆结构、看意思;可加入待学习。</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!sentences.length" class="tip">本卷没有识别到长难句</view>

    <template v-else>
      <view v-for="(s, i) in sentences" :key="i" class="card ls-item">
        <text class="ls-text">{{ s }}</text>
        <view class="ls-row">
          <view class="ls-btn" @tap="openAnalysis(i)"><text>解析 ›</text></view>
          <view class="ls-btn ls-add" :class="{ done: saved.has(i) }" @tap="save(i)">
            <text>{{ saved.has(i) ? '已加入' : '加入待学习' }}</text>
          </view>
        </view>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getPaperLongSentences, savePaperSentence } from '@/api/userPapers'

const paperId = ref('')
const sentences = ref<string[]>([])
const loading = ref(true)
const saved = ref<Set<number>>(new Set())

function openAnalysis(i: number) {
  const s = saved.value.has(i) ? '1' : '0'
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(sentences.value[i])}&saved=${s}` })
}
async function save(i: number) {
  if (saved.value.has(i)) return
  try {
    await savePaperSentence(sentences.value[i])
    saved.value = new Set([...saved.value, i])
    uni.showToast({ title: '已加入待学习', icon: 'success' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

onLoad(async (q: any) => {
  paperId.value = q.paperId || ''
  if (!paperId.value) { loading.value = false; return }
  try { sentences.value = (await getPaperLongSentences(paperId.value)).sentences } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx 24rpx 60rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 0; }
.card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 18rpx; }
.ls-text { font-size: 27rpx; line-height: 1.7; color: var(--c-ink); }
.ls-row { display: flex; justify-content: flex-end; gap: 12rpx; margin-top: 14rpx; }
.ls-btn { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 24rpx; }
.ls-add.done { color: #2ecc71; border-color: #2ecc71; }
</style>

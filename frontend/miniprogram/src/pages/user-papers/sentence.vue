<template>
  <view class="page">
    <view class="card src-card">
      <text class="src-label">长难句</text>
      <text class="src-text">{{ text }}</text>
      <view class="src-add" :class="{ done: saved }" @tap="save">
        <text>{{ saved ? '已加入待学习' : '加入待学习' }}</text>
      </view>
    </view>

    <view v-if="loading" class="tip">解析中…</view>

    <template v-else-if="a">
      <view v-if="a.translation" class="card">
        <text class="sec-t">意思</text>
        <text class="trans">{{ a.translation }}</text>
        <text v-if="a.sentence_type" class="stype">{{ a.sentence_type }}</text>
      </view>

      <!-- 成分拆分(按原文顺序,彩色) -->
      <view v-if="a.segments && a.segments.length" class="card">
        <text class="sec-t">结构拆分</text>
        <view v-for="(s, i) in a.segments" :key="i" class="seg" :style="{ background: s.tint || 'var(--c-bg-soft)' }">
          <text class="seg-type" :style="{ color: s.color || 'var(--c-primary)' }">{{ s.type }}</text>
          <text class="seg-text">{{ s.text }}</text>
        </view>
      </view>

      <!-- 逐条解析 -->
      <view v-if="a.explanations && a.explanations.length" class="card">
        <text class="sec-t">逐句解析</text>
        <view v-for="(e, i) in a.explanations" :key="i" class="expl">
          <text class="expl-idx">{{ e.idx }}</text>
          <text class="expl-text">{{ e.text }}</text>
        </view>
      </view>

      <!-- 语法点 -->
      <view v-if="a.grammar_points && a.grammar_points.length" class="card">
        <text class="sec-t">涉及语法</text>
        <view v-for="(g, i) in a.grammar_points" :key="i" class="gp">
          <text class="gp-name">{{ g.name }}</text>
          <text v-if="g.explanation" class="gp-x">{{ g.explanation }}</text>
        </view>
      </view>

      <!-- 重点词 -->
      <view v-if="a.key_words && a.key_words.length" class="card">
        <text class="sec-t">重点词汇</text>
        <view class="kw-wrap">
          <view v-for="(k, i) in a.key_words" :key="i" class="kw">
            <text class="kw-w">{{ k.word }}</text>
            <text v-if="k.pos" class="kw-pos">{{ k.pos }}</text>
            <text v-if="k.meaning" class="kw-m">{{ k.meaning }}</text>
          </view>
        </view>
      </view>
    </template>

    <view v-else class="tip">解析失败,返回重试</view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { analyzePaperSentence, savePaperSentence } from '@/api/userPapers'

const text = ref('')
const a = ref<any>(null)
const loading = ref(true)
const saved = ref(false)
const paperId = ref('')

async function save() {
  if (saved.value || !text.value) return
  try {
    await savePaperSentence(text.value, paperId.value || undefined)
    saved.value = true
    uni.showToast({ title: '已加入待学习', icon: 'success' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

onLoad(async (q: any) => {
  text.value = decodeURIComponent(q.text || '')
  saved.value = q.saved === '1'
  paperId.value = q.paperId || ''
  if (!text.value) { loading.value = false; return }
  try { a.value = await analyzePaperSentence(text.value) } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx 24rpx 60rpx; box-sizing: border-box; }
.card { background: #fff; border-radius: 20rpx; padding: 26rpx 24rpx; margin-bottom: 20rpx; }
.tip { text-align: center; color: var(--c-text-hint); padding: 60rpx 0; }
.src-card { display: flex; flex-direction: column; gap: 14rpx; }
.src-label { font-size: 22rpx; color: var(--c-primary); }
.src-text { font-size: 30rpx; line-height: 1.7; color: var(--c-ink); }
.src-add { align-self: flex-start; font-size: 24rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 8rpx 28rpx; }
.src-add.done { color: #2ecc71; border-color: #2ecc71; }
.sec-t { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-text-second); margin-bottom: 14rpx; }
.trans { font-size: 28rpx; line-height: 1.7; color: var(--c-ink); }
.stype { display: inline-block; margin-top: 12rpx; font-size: 22rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 8rpx; padding: 4rpx 16rpx; }
.seg { display: flex; align-items: baseline; gap: 14rpx; padding: 14rpx 16rpx; border-radius: 12rpx; margin-bottom: 10rpx; }
.seg-type { flex-shrink: 0; font-size: 22rpx; font-weight: 700; }
.seg-text { font-size: 26rpx; line-height: 1.5; color: var(--c-ink); }
.expl { display: flex; gap: 12rpx; padding: 8rpx 0; }
.expl-idx { flex-shrink: 0; width: 34rpx; height: 34rpx; text-align: center; line-height: 34rpx; font-size: 20rpx; color: #fff; background: var(--c-primary); border-radius: 50%; }
.expl-text { flex: 1; font-size: 25rpx; line-height: 1.6; color: var(--c-text-sub); }
.gp { padding: 10rpx 0; border-top: 2rpx solid var(--c-line, #eef1f5); }
.gp:first-of-type { border-top: none; }
.gp-name { font-size: 26rpx; font-weight: 600; color: var(--c-ink); }
.gp-x { display: block; font-size: 23rpx; color: var(--c-text-sub); line-height: 1.5; margin-top: 4rpx; }
.kw-wrap { display: flex; flex-direction: column; gap: 10rpx; }
.kw { display: flex; align-items: baseline; gap: 12rpx; }
.kw-w { font-size: 26rpx; font-weight: 600; color: var(--c-primary); }
.kw-pos { font-size: 20rpx; color: var(--c-text-hint); }
.kw-m { font-size: 24rpx; color: var(--c-text-sub); }
</style>

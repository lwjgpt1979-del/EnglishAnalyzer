<!-- src/pages/listening/wrong.vue 听力错题库（§6.4）-->
<template>
  <view class="wb-page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="locked" class="tip">
      听力错题库为会员专享 🎧
      <button class="btn-go" @tap="goMembership">去开通会员</button>
    </view>
    <view v-else-if="!items.length" class="tip">暂无听力错题，继续加油 🎧</view>

    <view v-else>
      <view class="wb-head">
        <view class="wb-title" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-book" style="width:34rpx;height:34rpx"/><text>听力错题库</text></view>
        <text class="wb-sub">共 {{ items.length }} 题 · 按易错优先排序</text>
      </view>
      <view v-for="w in items" :key="w.id" class="card">
        <view class="w-top">
          <text class="w-src">{{ w.exercise_title || '听力' }}</text>
          <text class="w-cnt">错 {{ w.wrong_count }} 次</text>
        </view>
        <text class="w-prompt">{{ w.prompt }}</text>
        <view class="w-opts">
          <view v-for="(o, i) in w.options" :key="i" class="w-opt" :class="{ correct: i === w.correct_index }" style="display:flex;align-items:center;gap:8rpx">
            <text>{{ letter(i) }}. {{ o }}</text><view v-if="i === w.correct_index" class="ic ic-check-circle" style="width:26rpx;height:26rpx;flex-shrink:0"/>
          </view>
        </view>
        <view v-if="w.explanation" class="w-exp" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-idea" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ w.explanation }}</text></view>
        <button class="w-redo" @tap="redo(w.exercise_id)">重练此篇</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getListeningWrong, type ListeningWrong } from '@/api/listening'

const loading = ref(true)
const locked = ref(false)
const items = ref<ListeningWrong[]>([])

function letter(i: number) { return ['A', 'B', 'C', 'D'][i] ?? '' }
function goMembership() { uni.navigateTo({ url: '/pages/membership/buy' }) }
function redo() { uni.navigateBack() }   // 返回听力列表重新进入该篇精听

async function load() {
  loading.value = true
  try {
    items.value = await getListeningWrong()
  } catch (e) {
    if ((e as { code?: number }).code === 402) locked.value = true
    else uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally { loading.value = false }
}

onMounted(load)
</script>

<style scoped>
.wb-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 40rpx; color: var(--c-text-hint); font-size: 28rpx; display: flex; flex-direction: column; align-items: center; gap: 24rpx; }
.btn-go { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 28rpx; padding: 16rpx 48rpx; }
.wb-head { margin-bottom: 16rpx; }
.wb-title { font-size: 36rpx; font-weight: 800; color: var(--c-ink); display: block; }
.wb-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 4rpx; display: block; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.w-top { display: flex; justify-content: space-between; margin-bottom: 10rpx; }
.w-src { font-size: 24rpx; color: var(--c-text-hint); }
.w-cnt { font-size: 24rpx; color: var(--c-danger); font-weight: 700; }
.w-prompt { font-size: 30rpx; font-weight: 700; color: var(--c-ink); line-height: 1.5; display: block; }
.w-opts { display: flex; flex-direction: column; gap: 8rpx; margin: 12rpx 0; }
.w-opt { font-size: 26rpx; color: var(--c-text-body); }
.w-opt.correct { color: #18a058; font-weight: 700; }
.w-exp { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; display: block; }
.w-redo { margin-top: 14rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-pill); font-size: 26rpx; padding: 14rpx 0; }
</style>

<template>
  <view class="page">
    <view class="tabs">
      <view
        v-for="d in dims" :key="d.key"
        class="tab" :class="{ active: activeDim === d.key }"
        @tap="activeDim = d.key"
      >{{ d.label }}</view>
    </view>

    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!currentContent" class="empty">该维度暂无内容</view>
    <scroll-view v-else scroll-y class="content">
      <text class="md">{{ currentContent.content_md }}</text>
    </scroll-view>
    <view class="practice-bar">
      <button class="btn-secondary" @tap="goPractice">练习（5 题）</button>
      <button class="btn-primary" @tap="goExam">模拟考（10 题）</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getKpContents } from '@/api/curriculum'
import type { KPContentOut } from '@/types/api'

const dims = [
  { key: 'listening', label: '听力' },
  { key: 'dictation', label: '听写' },
  { key: 'grammar', label: '语法' },
  { key: 'writing', label: '写作' },
]
const contents = ref<KPContentOut[]>([])
const activeDim = ref('grammar')
const loading = ref(true)
const kpId = ref('')

const currentContent = computed(
  () => contents.value.find(c => c.dimension === activeDim.value) || null,
)

onLoad(async (q: any) => {
  kpId.value = q.id || ''
  try {
    contents.value = await getKpContents(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function goPractice() {
  uni.navigateTo({ url: `/pages/practice/v2-session?kp=${kpId.value}&dim=${activeDim.value}` })
}

function goExam() {
  uni.navigateTo({ url: `/pages/practice/v2-exam?kp=${kpId.value}&count=10&dim=${activeDim.value}` })
}
</script>

<style scoped>
.page { padding: 0; background: var(--c-bg-page); min-height: 100vh; display: flex; flex-direction: column; }
.tabs { display: flex; background: var(--c-bg-card); border-bottom: 1rpx solid var(--c-border); }
.tab {
  flex: 1; text-align: center; padding: 24rpx 0; font-size: 28rpx;
  color: var(--c-text-second); position: relative;
}
.tab.active { color: var(--c-ink); font-weight: 700; }
.tab.active::after {
  content: ''; position: absolute; left: 30%; right: 30%; bottom: 0;
  height: 4rpx; background: var(--c-primary);
}
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.content { flex: 1; padding: 24rpx; }
.md { font-size: 28rpx; line-height: 1.7; color: var(--c-text-body); white-space: pre-wrap; }
.practice-bar { padding: 24rpx; background: var(--c-bg-card); border-top: 1rpx solid var(--c-border); display: flex; gap: 16rpx; }
.btn-primary, .btn-secondary { flex: 1; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; text-align: center; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); }
.btn-secondary { background: var(--c-bg-soft); color: var(--c-text-body); border: 2rpx solid var(--c-border); }
</style>

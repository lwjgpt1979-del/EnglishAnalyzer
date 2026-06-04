<!-- src/pages/wrong-questions/list.vue -->
<template>
  <view class="list-page">
    <!-- 来源筛选 -->
    <view class="src-tabs">
      <text v-for="t in SRC_TABS" :key="t.value" class="src-tab" :class="{ active: source === t.value }" @tap="switchSource(t.value)">{{ t.label }}</text>
    </view>

    <!-- 加载态 -->
    <view v-if="loading && items.length === 0" class="center-tip">加载中…</view>

    <!-- 空状态 -->
    <view v-else-if="!loading && items.length === 0" class="center-tip">
      <text>还没有错题，去上传一题吧 📷</text>
      <button
        class="btn-sm"
        @tap="() => uni.navigateTo({ url: '/pages/upload/index' })"
      >
        上传错题
      </button>
    </view>

    <!-- 列表 -->
    <view v-else>
      <view
        v-for="wq in items"
        :key="wq.id"
        class="wq-card"
        @tap="goDetail(wq.id)"
      >
        <view v-if="fromAssignment(wq)" class="wq-img wq-assign">
          <text class="wq-assign-icon">📋</text>
          <text class="wq-assign-text">{{ (wq.question_text || '作业错题').slice(0, 24) }}</text>
        </view>
        <image
          v-else
          class="wq-img"
          :src="wq.source_image_url"
          mode="aspectFill"
          lazy-load
        />
        <view class="wq-info">
          <view class="wq-meta">
            <text v-if="fromAssignment(wq)" class="tag tag-blue">来自作业</text>
            <text v-if="wq.question_type" class="tag">{{ wq.question_type }}</text>
            <text v-if="wq.difficulty" class="tag">{{ '★'.repeat(wq.difficulty) }}</text>
            <text v-if="wq.is_mastered" class="tag tag-green">已掌握</text>
          </view>
          <text class="wq-date">{{ wq.created_at.slice(0, 10) }}</text>
        </view>
      </view>

      <!-- 加载更多 -->
      <view v-if="hasMore" class="load-more" @tap="loadMore">
        {{ loading ? '加载中…' : '加载更多' }}
      </view>
      <view v-else-if="items.length > 0" class="load-more gray">已加载全部</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { listWrongQuestions } from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'
import type { WrongQuestionOut } from '@/types/api'

const auth = useAuthStore()
const items = ref<WrongQuestionOut[]>([])
function fromAssignment(wq: WrongQuestionOut): boolean {
  return (wq.source_image_url || '').startsWith('assignment://')
}
const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const LIMIT = 20
const hasMore = ref(true)
const source = ref('')
const SRC_TABS = [
  { label: '全部', value: '' },
  { label: '作业', value: 'assignment' },
  { label: '上传', value: 'upload' },
]
function switchSource(v: string) {
  if (source.value === v) return
  source.value = v
  items.value = []
  skip.value = 0
  hasMore.value = true
  loadItems()
}

onMounted(async () => {
  if (!auth.isLoggedIn()) {
    await auth.login()
  }
  await loadItems()
})

async function loadItems() {
  if (loading.value) return
  loading.value = true
  try {
    const res = await listWrongQuestions(skip.value, LIMIT, source.value)
    items.value.push(...res.items)
    total.value = res.total
    hasMore.value = items.value.length < res.total
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loading.value || !hasMore.value) return
  // Advance skip only after confirming success inside loadItems
  const nextSkip = skip.value + LIMIT
  skip.value = nextSkip
  try {
    await loadItems()
  } catch {
    // Roll back skip on failure so the same page can be retried
    skip.value = nextSkip - LIMIT
  }
}

function goDetail(id: string) {
  uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${id}` })
}
</script>

<style scoped>
.list-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }
.btn-sm {
  margin-top: 32rpx;
  background: var(--c-primary);
  color: var(--c-ink);
  font-size: 28rpx;
  font-weight: 700;
  border-radius: var(--r-btn);
}
.wq-card {
  display: flex;
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  margin-bottom: 20rpx;
  overflow: hidden;
  box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04);
}
.wq-img { width: 180rpx; height: 140rpx; flex-shrink: 0; }
.wq-info {
  flex: 1;
  padding: 20rpx;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.wq-meta { display: flex; flex-wrap: wrap; gap: 8rpx; }
.tag {
  background: var(--c-primary-soft);
  color: #8a7212;
  font-size: 22rpx;
  font-weight: 600;
  padding: 4rpx 14rpx;
  border-radius: var(--r-pill);
}
.tag-green { background: var(--c-success-bg); color: var(--c-success-dark); }
.tag-blue { background: var(--c-primary-faint); color: var(--c-primary); }
.src-tabs { display: flex; gap: 16rpx; padding: 16rpx 0; }
.src-tab { padding: 10rpx 28rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.src-tab.active { background: var(--c-primary); color: var(--c-ink); font-weight: 700; }
.wq-assign { display: flex; flex-direction: column; align-items: center; justify-content: center; background: var(--c-bg-page); border-radius: 8rpx; padding: 8rpx; }
.wq-assign-icon { font-size: 40rpx; }
.wq-assign-text { font-size: 20rpx; color: var(--c-text-hint); text-align: center; line-height: 1.3; margin-top: 4rpx; }
.wq-date { color: var(--c-text-hint); font-size: 24rpx; }
.load-more { text-align: center; padding: 32rpx; color: var(--c-text-second); font-size: 28rpx; }
.gray { color: var(--c-text-hint); }
</style>

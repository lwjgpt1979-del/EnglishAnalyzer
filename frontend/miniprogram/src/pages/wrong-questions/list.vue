<!-- src/pages/wrong-questions/list.vue -->
<template>
  <view class="list-page">
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
        <image
          class="wq-img"
          :src="wq.source_image_url"
          mode="aspectFill"
          lazy-load
        />
        <view class="wq-info">
          <view class="wq-meta">
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
const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const LIMIT = 20
const hasMore = ref(true)

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
    const res = await listWrongQuestions(skip.value, LIMIT)
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
  skip.value += LIMIT
  await loadItems()
}

function goDetail(id: string) {
  uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${id}` })
}
</script>

<style scoped>
.list-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx 0; color: #999; font-size: 28rpx; }
.btn-sm {
  margin-top: 32rpx;
  background: #1677ff;
  color: #fff;
  font-size: 28rpx;
  border-radius: 10rpx;
}
.wq-card {
  display: flex;
  background: #fff;
  border-radius: 16rpx;
  margin-bottom: 20rpx;
  overflow: hidden;
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
  background: #e6f0ff;
  color: #1677ff;
  font-size: 22rpx;
  padding: 4rpx 12rpx;
  border-radius: 6rpx;
}
.tag-green { background: #f0fff4; color: #52c41a; }
.wq-date { color: #999; font-size: 24rpx; }
.load-more { text-align: center; padding: 32rpx; color: #1677ff; font-size: 28rpx; }
.gray { color: #ccc; }
</style>

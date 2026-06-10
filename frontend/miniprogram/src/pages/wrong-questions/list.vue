<!-- src/pages/wrong-questions/list.vue -->
<template>
  <view class="list-page">
    <!-- 今日错题复习（M12 遗忘曲线）-->
    <view v-if="reviewDue > 0" class="review-banner" @tap="goReview">
      <view class="rb-left">
        <text class="rb-icon">🧠</text>
        <view class="rb-text">
          <text class="rb-title">今日错题复习</text>
          <text class="rb-sub">{{ reviewDue }} 道到期 · 遗忘曲线智能安排</text>
        </view>
      </view>
      <text class="rb-arrow">开始 ›</text>
    </view>

    <!-- 来源筛选 -->
    <view class="src-tabs">
      <text v-for="t in SRC_TABS" :key="t.value" class="src-tab" :class="{ active: source === t.value }" @tap="switchSource(t.value)">{{ t.label }}</text>
    </view>

    <!-- 知识点标签筛选栏（M38） -->
    <scroll-view v-if="allTags.length > 0" class="tag-scroll" scroll-x enhanced>
      <view class="tag-bar">
        <text class="tag-chip" :class="{ active: !activeTag }" @tap="switchTag('')">全部</text>
        <text
          v-for="t in allTags"
          :key="t"
          class="tag-chip"
          :class="{ active: activeTag === t }"
          @tap="switchTag(t)"
        >{{ t }}</text>
      </view>
    </scroll-view>

    <!-- 一键自动打标按钮 -->
    <view v-if="source !== 'paper'" class="auto-tag-row">
      <button class="btn-auto-tag" :disabled="autoTagging" @tap="doAutoTag">
        {{ autoTagging ? '打标中…' : '✨ 一键自动打标' }}
      </button>
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
        @tap="source === 'paper' ? null : goDetail(wq.id)"
      >
        <!-- 整卷错题（source_label='整卷'，有 stem 字段） -->
        <view v-if="wq.source_label === '整卷'" class="wq-img wq-assign">
          <text class="wq-assign-icon">📄</text>
          <text class="wq-assign-text">{{ (wq.stem || '整卷错题').slice(0, 28) }}</text>
        </view>
        <!-- 作业错题 -->
        <view v-else-if="fromAssignment(wq)" class="wq-img wq-assign">
          <text class="wq-assign-icon">📋</text>
          <text class="wq-assign-text">{{ (wq.question_text || '作业错题').slice(0, 24) }}</text>
        </view>
        <!-- 普通单题上传 -->
        <image
          v-else
          class="wq-img"
          :src="wq.source_image_url"
          mode="aspectFill"
          lazy-load
        />
        <view class="wq-info">
          <view class="wq-meta">
            <text v-if="wq.source_label === '整卷'" class="tag tag-paper">整卷</text>
            <text v-else-if="fromAssignment(wq)" class="tag tag-blue">来自作业</text>
            <text v-if="wq.question_type" class="tag">{{ wq.question_type }}</text>
            <text v-if="wq.difficulty" class="tag">{{ '★'.repeat(wq.difficulty) }}</text>
            <text v-if="wq.is_mastered" class="tag tag-green">已掌握</text>
          </view>
          <!-- 知识点标签 chips（M38） -->
          <view v-if="wq.tags && wq.tags.length > 0" class="kp-tags">
            <text
              v-for="t in wq.tags.slice(0, 3)"
              :key="t"
              class="kp-tag"
              @tap.stop="switchTag(t)"
            >{{ t }}</text>
            <text v-if="wq.tags.length > 3" class="kp-tag kp-more">+{{ wq.tags.length - 3 }}</text>
          </view>
          <text v-if="wq.created_at" class="wq-date">{{ wq.created_at.slice(0, 10) }}</text>
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
import { computed, onMounted, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listWrongQuestions, listPaperWrongs, autoTagWrongQuestions, getReviewQueue } from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'
import type { WrongQuestionOut } from '@/types/api'

const auth = useAuthStore()

// 今日复习到期数（SM-2 遗忘曲线，M12）
const reviewDue = ref(0)
async function loadReviewDue() {
  try {
    const r = await getReviewQueue()
    reviewDue.value = (r.stats?.due_today || 0) + (r.stats?.new_unscheduled || 0)
  } catch { reviewDue.value = 0 }
}
function goReview() {
  uni.navigateTo({ url: '/pages/wrong-questions/review' })
}
onShow(loadReviewDue)
const items = ref<any[]>([])
function fromAssignment(wq: WrongQuestionOut): boolean {
  return (wq.source_image_url || '').startsWith('assignment://')
}
const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const LIMIT = 20
const hasMore = ref(true)
const source = ref('')
const activeTag = ref('')
const autoTagging = ref(false)
const SRC_TABS = [
  { label: '全部', value: '' },
  { label: '作业', value: 'assignment' },
  { label: '上传', value: 'upload' },
  { label: '整卷', value: 'paper' },
]

// 从已加载的错题中提取所有唯一 tags，用于筛选栏
const allTags = computed<string[]>(() => {
  const set = new Set<string>()
  for (const wq of items.value) {
    if (Array.isArray(wq.tags)) wq.tags.forEach((t: string) => set.add(t))
  }
  return Array.from(set)
})

function resetList() {
  items.value = []
  skip.value = 0
  hasMore.value = true
}

function switchSource(v: string) {
  if (source.value === v) return
  source.value = v
  activeTag.value = ''
  resetList()
  loadItems()
}

function switchTag(t: string) {
  if (activeTag.value === t) return
  activeTag.value = t
  resetList()
  loadItems()
}

async function doAutoTag() {
  if (autoTagging.value) return
  autoTagging.value = true
  try {
    const res = await autoTagWrongQuestions()
    uni.showToast({
      title: res.processed > 0 ? `已打标 ${res.processed} 道题` : '所有错题已有标签',
      icon: 'none',
    })
    if (res.processed > 0) {
      resetList()
      await loadItems()
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '打标失败', icon: 'none' })
  } finally {
    autoTagging.value = false
  }
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
    let res: { items: any[]; total: number }
    if (source.value === 'paper') {
      res = await listPaperWrongs(skip.value, LIMIT)
    } else {
      res = await listWrongQuestions(skip.value, LIMIT, source.value, activeTag.value)
    }
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
/* 今日复习横幅（M12）*/
.review-banner {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--g-hero); border-radius: var(--r-lg); padding: 28rpx 32rpx;
  margin-bottom: 24rpx; box-shadow: var(--shadow-primary);
}
.rb-left { display: flex; align-items: center; gap: 20rpx; }
.rb-icon { font-size: 52rpx; }
.rb-text { display: flex; flex-direction: column; gap: 4rpx; }
.rb-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-on-primary); }
.rb-sub { font-size: 22rpx; color: var(--c-on-primary); opacity: 0.9; }
.rb-arrow { font-size: 28rpx; font-weight: 700; color: var(--c-on-primary); white-space: nowrap; }
.center-tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }
.btn-sm {
  margin-top: 32rpx;
  background: var(--c-primary);
  color: var(--c-on-primary);
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
  color: var(--c-primary-deep);
  font-size: 22rpx;
  font-weight: 600;
  padding: 4rpx 14rpx;
  border-radius: var(--r-pill);
}
.tag-green { background: var(--c-success-bg); color: var(--c-success-dark); }
.tag-blue { background: var(--c-primary-faint); color: var(--c-primary); }
.tag-paper { background: #EDE9FE; color: #6D28D9; }
.src-tabs { display: flex; gap: 16rpx; padding: 16rpx 0; }
.src-tab { padding: 10rpx 28rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.src-tab.active { background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; }
.wq-assign { display: flex; flex-direction: column; align-items: center; justify-content: center; background: var(--c-bg-page); border-radius: 8rpx; padding: 8rpx; }
.wq-assign-icon { font-size: 40rpx; }
.wq-assign-text { font-size: 20rpx; color: var(--c-text-hint); text-align: center; line-height: 1.3; margin-top: 4rpx; }
.wq-date { color: var(--c-text-hint); font-size: 24rpx; }
.load-more { text-align: center; padding: 32rpx; color: var(--c-text-second); font-size: 28rpx; }
.gray { color: var(--c-text-hint); }

/* M38 知识点标签筛选栏 */
.tag-scroll { width: 100%; margin-bottom: 16rpx; }
.tag-bar { display: flex; flex-direction: row; gap: 12rpx; padding: 4rpx 0 8rpx 2rpx; white-space: nowrap; }
.tag-chip { font-size: 22rpx; padding: 6rpx 16rpx; border-radius: 999rpx; background: #f0f0f0; color: var(--c-text-second); border: 2rpx solid transparent; flex-shrink: 0; }
.tag-chip.active { background: var(--c-primary-faint); color: var(--c-primary-deep); border-color: var(--c-primary); font-weight: 700; }

/* 一键打标按钮 */
.auto-tag-row { margin-bottom: 20rpx; display: flex; justify-content: flex-end; }
.btn-auto-tag { font-size: 22rpx; padding: 10rpx 20rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border: 2rpx solid var(--c-primary); border-radius: 999rpx; line-height: 1.4; }
.btn-auto-tag[disabled] { opacity: 0.5; }

/* 知识点 chips on card */
.kp-tags { display: flex; flex-wrap: wrap; gap: 8rpx; margin-top: 8rpx; }
.kp-tag { font-size: 18rpx; padding: 2rpx 10rpx; border-radius: 999rpx; background: var(--c-primary-soft); color: var(--c-primary-deep); border: 1rpx solid var(--c-primary); }
.kp-more { background: #f0f0f0; color: var(--c-text-hint); border-color: #ddd; }
</style>

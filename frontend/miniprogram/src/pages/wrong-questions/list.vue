<!-- src/pages/wrong-questions/list.vue —— 我的错题(统一:一份错题 wrong_record) -->
<template>
  <view class="list-page">
    <!-- 今日错题复习（遗忘曲线）-->
    <view v-if="reviewDue > 0" class="review-banner" @tap="goReview">
      <view class="rb-left">
        <view class="ic ic-brain rb-icon" />
        <view class="rb-text">
          <text class="rb-title">今日错题复习</text>
          <text class="rb-sub">{{ reviewDue }} 道到期 · 遗忘曲线智能安排</text>
        </view>
      </view>
      <text class="rb-arrow">开始 ›</text>
    </view>

    <!-- 语法 / 词汇 筛选 -->
    <view class="src-tabs">
      <text v-for="t in KIND_TABS" :key="t.value" class="src-tab" :class="{ active: kind === t.value }" @tap="switchKind(t.value)">{{ t.label }}</text>
    </view>

    <!-- 加载态 -->
    <view v-if="loading && items.length === 0" class="center-tip">加载中…</view>

    <!-- 空状态 -->
    <view v-else-if="!loading && items.length === 0" class="center-tip">
      <text>还没有错题，去上传作业吧 📄</text>
      <button
        class="btn-sm"
        @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })"
      >
        上传作业
      </button>
    </view>

    <!-- 列表 -->
    <view v-else>
      <view v-for="wq in items" :key="wq.id" class="wq-card">
        <view class="wq-icon">
          <view class="ic wq-icon-emoji" :class="wq.kp_kind === 'grammar' ? 'ic-edit' : wq.kp_kind === 'vocab' ? 'ic-book' : 'ic-file'" />
        </view>
        <view class="wq-info">
          <text class="wq-stem">{{ cardText(wq) }}</text>
          <view class="wq-meta">
            <text v-if="wq.kp_kind === 'grammar'" class="tag tag-gram">语法</text>
            <text v-else-if="wq.kp_kind === 'vocab'" class="tag tag-vocab">词汇</text>
            <!-- 来源标签:有可跳目标 → 点击回到错题来源(卷/作业),原生返回即可回来 -->
            <text
              class="tag tag-src"
              :class="{ 'tag-link': wq.source_route }"
              @tap.stop="wq.source_route && goSource(wq)"
            >{{ wq.source_label }}{{ wq.source_route ? ' ›' : '' }}</text>
            <text v-if="wq.question_type" class="tag">{{ wq.question_type }}</text>
            <text v-if="wq.kp_name" class="tag tag-kp">{{ wq.kp_name }}</text>
            <text v-if="wq.is_mastered" class="tag tag-green">已掌握</text>
          </view>
          <!-- 练同类仿真题 -->
          <view class="pw-prac" @tap.stop="practiceWrong(wq)">
            <text>{{ pracLoading === wq.id ? '出题中…' : '练同类仿真题' }}</text>
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

    <!-- 练同类仿真题 弹层 -->
    <view v-if="pracOpen" class="modal" @tap.self="pracOpen = false">
      <view class="modal-card">
        <text class="modal-title">同类练习 · {{ pracKp }}</text>
        <scroll-view scroll-y class="modal-body">
          <view v-for="(q, i) in pracList" :key="q.id || i" class="sq">
            <text class="sq-stem">{{ i + 1 }}. {{ q.stem }}</text>
            <view v-if="q.options" class="sq-opts">
              <text v-for="(v, kk) in q.options" :key="kk" class="sq-opt">{{ kk }}. {{ v }}</text>
            </view>
          </view>
          <text v-if="!pracList.length" class="muted">未生成题目</text>
        </scroll-view>
        <view class="modal-close" @tap="pracOpen = false"><text>关闭</text></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getReviewQueue, listWrongCenter, practiceWrongCenter, type WrongCenterItem } from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

// 练同类仿真题
const pracOpen = ref(false)
const pracLoading = ref('')
const pracKp = ref('')
const pracList = ref<any[]>([])
async function practiceWrong(wq: WrongCenterItem) {
  if (pracLoading.value) return
  pracLoading.value = wq.id
  try {
    const r = await practiceWrongCenter(wq.id)
    pracKp.value = r.knowledge_point; pracList.value = r.questions; pracOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '出题失败', icon: 'none' }) }
  finally { pracLoading.value = '' }
}

// 点击错题来源 → 回到来源(整卷详情/作业详情);navigateTo 入栈,原生返回即「立即回来」
function goSource(wq: WrongCenterItem) {
  if (!wq.source_route) return
  uni.navigateTo({
    url: wq.source_route,
    fail: () => uni.showToast({ title: '来源已不可用', icon: 'none' }),
  })
}

// 今日复习到期数
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
onShow(() => { loadReviewDue(); if (items.value.length) reload() })

const items = ref<WrongCenterItem[]>([])
function cardText(wq: WrongCenterItem): string {
  return wq.stem || '错题（点击查看）'
}
const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const LIMIT = 20
const hasMore = ref(true)
const kind = ref('')
const KIND_TABS = [
  { label: '全部', value: '' },
  { label: '语法', value: 'grammar' },
  { label: '词汇', value: 'vocab' },
]

function reload() {
  items.value = []
  skip.value = 0
  hasMore.value = true
  loadItems()
}

function switchKind(v: string) {
  if (kind.value === v) return
  kind.value = v
  reload()
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
    const res = await listWrongCenter(kind.value, skip.value, LIMIT)
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
  const nextSkip = skip.value + LIMIT
  skip.value = nextSkip
  try {
    await loadItems()
  } catch {
    skip.value = nextSkip - LIMIT
  }
}
</script>

<style scoped>
.list-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
/* 今日复习横幅 */
.review-banner {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--g-hero); border-radius: var(--r-lg); padding: 28rpx 32rpx;
  margin-bottom: 24rpx; box-shadow: var(--shadow-primary);
}
.rb-left { display: flex; align-items: center; gap: 20rpx; }
.rb-icon { width: 52rpx; height: 52rpx; }
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
.wq-icon { width: 120rpx; flex-shrink: 0; align-self: stretch; min-height: 120rpx; display: flex; align-items: center; justify-content: center; background: var(--c-bg-soft); }
.wq-icon-emoji { width: 48rpx; height: 48rpx; }
.wq-info {
  flex: 1;
  padding: 20rpx;
  display: flex;
  flex-direction: column;
  gap: 10rpx;
  min-width: 0;
}
.wq-stem {
  font-size: 28rpx; color: var(--c-ink); font-weight: 600; line-height: 1.45;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  overflow: hidden; text-overflow: ellipsis;
}
.wq-meta { display: flex; flex-wrap: wrap; gap: 8rpx; align-items: center; }
.tag {
  background: var(--c-primary-soft);
  color: var(--c-primary-deep);
  font-size: 22rpx;
  font-weight: 600;
  padding: 4rpx 14rpx;
  border-radius: var(--r-pill);
}
.tag-green { background: var(--c-success-bg); color: var(--c-success-dark); }
.tag-src { background: #EDE9FE; color: #6D28D9; }
.tag-link { border: 2rpx solid #6D28D9; font-weight: 700; }
.tag-gram { background: #e6f0ff; color: #3d8bf5; }
.tag-vocab { background: #fff1e6; color: #ff8a3d; }
.tag-kp { background: var(--c-bg-soft); color: var(--c-text-second); font-weight: 500; }
.pw-prac { display: inline-block; margin-top: 12rpx; font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 60; padding: 40rpx; }
.modal-card { width: 100%; max-width: 640rpx; max-height: 80vh; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-body { flex: 1; margin: 16rpx 0; }
.sq { padding: 14rpx 0; border-top: 2rpx solid #eef1f5; }
.sq:first-child { border-top: none; }
.sq-stem { display: block; font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.sq-opts { display: flex; flex-direction: column; gap: 4rpx; margin-top: 8rpx; }
.sq-opt { font-size: 24rpx; color: var(--c-text-sub); }
.muted { color: var(--c-text-hint); font-size: 24rpx; }
.modal-close { text-align: center; font-size: 26rpx; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 14rpx; }
.src-tabs { display: flex; gap: 16rpx; padding: 16rpx 0; }
.src-tab { padding: 10rpx 28rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.src-tab.active { background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; }
.wq-date { color: var(--c-text-hint); font-size: 24rpx; }
.load-more { text-align: center; padding: 32rpx; color: var(--c-text-second); font-size: 28rpx; }
.gray { color: var(--c-text-hint); }
</style>

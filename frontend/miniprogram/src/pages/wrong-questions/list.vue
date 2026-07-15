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
    <view v-else class="wq-list">
      <view v-for="wq in items" :key="wq.id" class="wq-card">
        <!-- 顶部:考点类型徽章 + 来源 -->
        <view class="wq-top">
          <view class="kind-badge" :class="kindClass(wq)">
            <view class="ic kind-ic" :class="kindIcon(wq)" />
            <text>{{ kindLabel(wq) }}</text>
          </view>
          <text
            v-if="wq.source_route"
            class="src-chip src-link"
            @tap.stop="goSource(wq)"
          >{{ sourceText(wq) }} ›</text>
          <text v-else class="src-chip">{{ sourceText(wq) }}</text>
        </view>

        <!-- 题干 -->
        <text class="wq-stem">{{ cardText(wq) }}</text>

        <!-- 标签行 -->
        <view v-if="wq.question_type || wq.kp_name || wq.is_mastered" class="wq-tags">
          <text v-if="wq.kp_name" class="mini-tag mini-kp">{{ wq.kp_name }}</text>
          <text v-if="wq.question_type" class="mini-tag">{{ wq.question_type }}</text>
          <text v-if="wq.is_mastered" class="mini-tag mini-done">✓ 已掌握</text>
        </view>

        <!-- 底部:日期 + 练同类 -->
        <view class="wq-foot">
          <text class="wq-date">{{ wq.created_at ? wq.created_at.slice(0, 10) : '' }}</text>
          <view class="prac-btn" :class="{ loading: pracLoading === wq.id }" @tap.stop="practiceWrong(wq)">
            <view class="ic ic-sparkle prac-ic" />
            <text>{{ pracLoading === wq.id ? '出题中…' : '练同类' }}</text>
          </view>
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
function kindLabel(wq: WrongCenterItem): string {
  return wq.kp_kind === 'grammar' ? '语法' : wq.kp_kind === 'vocab' ? '词汇' : '错题'
}
function kindClass(wq: WrongCenterItem): string {
  return wq.kp_kind === 'grammar' ? 'k-gram' : wq.kp_kind === 'vocab' ? 'k-vocab' : 'k-none'
}
function kindIcon(wq: WrongCenterItem): string {
  return wq.kp_kind === 'grammar' ? 'ic-edit' : wq.kp_kind === 'vocab' ? 'ic-book' : 'ic-file'
}
// 来源展示名:整卷 → 我的作业
function sourceText(wq: WrongCenterItem): string {
  return wq.source_label === '整卷' ? '我的作业' : (wq.source_label || '错题')
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
.wq-list { display: flex; flex-direction: column; gap: 20rpx; }
.wq-card {
  background: var(--c-bg-card);
  border-radius: 24rpx;
  padding: 24rpx 26rpx;
  box-shadow: 0 6rpx 28rpx rgba(17, 24, 39, 0.05);
  display: flex; flex-direction: column; gap: 16rpx;
}
/* 顶部:类型徽章 + 来源 */
.wq-top { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.kind-badge {
  display: inline-flex; align-items: center; gap: 8rpx;
  height: 44rpx; padding: 0 18rpx; border-radius: 999rpx;
  font-size: 24rpx; font-weight: 700;
}
.kind-ic { width: 28rpx; height: 28rpx; }
.k-gram { background: #e8f1ff; color: #2f77e6; }
.k-vocab { background: #fff0e4; color: #f0821e; }
.k-none { background: var(--c-bg-soft); color: var(--c-text-second); }
.src-chip {
  font-size: 23rpx; color: var(--c-text-second);
  background: var(--c-bg-soft); padding: 7rpx 18rpx; border-radius: 999rpx;
  white-space: nowrap; flex-shrink: 0;
}
.src-link { background: #f0ecff; color: #6D28D9; font-weight: 600; }
/* 题干 */
.wq-stem {
  font-size: 30rpx; color: var(--c-ink); font-weight: 600; line-height: 1.5;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  overflow: hidden; text-overflow: ellipsis;
}
/* 标签行 */
.wq-tags { display: flex; flex-wrap: wrap; gap: 10rpx; }
.mini-tag {
  font-size: 22rpx; color: var(--c-text-second); background: var(--c-bg-soft);
  padding: 5rpx 16rpx; border-radius: 999rpx;
}
.mini-kp { background: var(--c-primary-faint); color: var(--c-primary-deep); font-weight: 600; }
.mini-done { background: #e6f8ee; color: #18a058; font-weight: 600; }
/* 底部 */
.wq-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 2rpx; }
.prac-btn {
  display: inline-flex; align-items: center; gap: 8rpx;
  height: 58rpx; padding: 0 26rpx; border-radius: 999rpx;
  background: var(--c-primary-faint); color: var(--c-primary-deep);
  border: 2rpx solid var(--c-primary); font-size: 24rpx; font-weight: 700;
}
.prac-btn.loading { opacity: 0.6; }
.prac-ic { width: 26rpx; height: 26rpx; }
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

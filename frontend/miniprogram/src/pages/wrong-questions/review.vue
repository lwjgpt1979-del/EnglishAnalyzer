<!-- 错题智能复习（V2 M36）— SM-2 间隔重复 -->
<template>
  <view class="page">

    <!-- 加载中 -->
    <view v-if="loading" class="center-tip">正在加载今日复习…</view>

    <!-- 全部复习完 / 无待复习 -->
    <view v-else-if="!current && !finished" class="done-card">
      <view class="ic ic-check-circle done-emoji" />
      <text class="done-title">今日复习已完成</text>
      <text class="done-sub">共 {{ stats.due_today }} 道，明天继续保持！</text>
      <view class="done-stats">
        <view class="stat-box">
          <text class="stat-n">{{ stats.total_unmastered }}</text>
          <text class="stat-l">待掌握</text>
        </view>
        <view class="stat-box">
          <text class="stat-n">{{ stats.new_unscheduled }}</text>
          <text class="stat-l">新错题</text>
        </view>
      </view>
      <button class="btn-primary" @tap="goBack">返回错题本</button>
    </view>

    <!-- 复习完成结算页 -->
    <view v-else-if="finished" class="done-card">
      <view class="ic ic-sparkle done-emoji" />
      <text class="done-title">本轮复习完成！</text>
      <text class="done-sub">
        {{ reviewedCount }} 道题，
        掌握 {{ masteredCount }} 道，
        需加强 {{ needRetryCount }} 道
      </text>
      <button class="btn-primary" @tap="goBack">返回错题本</button>
    </view>

    <!-- 复习中 -->
    <view v-else>
      <!-- 进度条 -->
      <view class="progress-wrap">
        <view class="progress-bar">
          <view class="progress-fill" :style="{ width: progressPct + '%' }" />
        </view>
        <text class="progress-text">{{ currentIdx + 1 }} / {{ queue.length }}</text>
      </view>

      <view class="card">
        <!-- 题目信息 -->
        <view class="meta-row">
          <text class="meta-tag">{{ current!.question_type || '题目' }}</text>
          <text class="meta-review">第 {{ (current!.review_count || 0) + 1 }} 次复习</text>
        </view>

        <!-- 题干 -->
        <text class="question-text">{{ current!.question_text || '（无题干，请查看原图）' }}</text>

        <!-- 答案区（默认遮盖，点击揭示） -->
        <view v-if="!revealed" class="reveal-wrap" @tap="revealed = true">
          <text class="reveal-hint">点击查看正确答案</text>
        </view>
        <view v-else class="answer-wrap">
          <view class="ans-item">
            <text class="ans-k">你的作答</text>
            <text class="ans-v ans-wrong">{{ current!.student_answer || '未作答' }}</text>
          </view>
          <view class="ans-divider" />
          <view class="ans-item">
            <text class="ans-k">正确答案</text>
            <text class="ans-v ans-right">{{ current!.correct_answer || '—' }}</text>
          </view>
        </view>

        <!-- 评分按钮（揭示后才显示）-->
        <view v-if="revealed" class="quality-wrap">
          <text class="quality-label">这道题你掌握得怎么样？</text>
          <view class="quality-btns">
            <view
              v-for="(btn, i) in qualityBtns"
              :key="btn.q"
              class="q-btn"
              :class="[`q-lv-${i}`, selectedQuality === btn.q ? 'selected' : '']"
              @tap="selectedQuality = btn.q"
            >
              <view class="q-icon" />
              <text class="q-label">{{ btn.label }}</text>
            </view>
          </view>
          <button
            class="btn-primary submit-btn"
            :disabled="selectedQuality === null || submitting"
            @tap="submitQuality"
          >
            {{ submitting ? '提交中…' : '确认' }}
          </button>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { getReviewQueue, submitReview } from '@/api/wrongQuestions'
import type { WrongQuestionReviewItem, ReviewStats } from '@/api/wrongQuestions'

const loading = ref(true)
const finished = ref(false)
const queue = ref<WrongQuestionReviewItem[]>([])
const currentIdx = ref(0)
const revealed = ref(false)
const selectedQuality = ref<number | null>(null)
const submitting = ref(false)
const stats = ref<ReviewStats>({ total_unmastered: 0, due_today: 0, new_unscheduled: 0 })

// 结算统计
const reviewedCount = ref(0)
const masteredCount = ref(0)
const needRetryCount = ref(0)

const current = computed(() =>
  queue.value.length > 0 && currentIdx.value < queue.value.length
    ? queue.value[currentIdx.value]
    : null
)
const progressPct = computed(() =>
  queue.value.length > 0 ? Math.round(currentIdx.value / queue.value.length * 100) : 0
)

const qualityBtns = [
  { q: 0, icon: '😰', label: '完全忘了' },
  { q: 2, icon: '😕', label: '模糊' },
  { q: 3, icon: '🤔', label: '想起来了' },
  { q: 4, icon: '😊', label: '基本掌握' },
  { q: 5, icon: '🎯', label: '完全掌握' },
]

async function load() {
  loading.value = true
  try {
    const res = await getReviewQueue()
    queue.value = res.due_items
    stats.value = res.stats
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
load()

async function submitQuality() {
  if (selectedQuality.value === null || !current.value) return
  submitting.value = true
  try {
    const updated = await submitReview(current.value.id, selectedQuality.value)
    reviewedCount.value++
    if (updated.is_mastered) masteredCount.value++
    if (selectedQuality.value < 3) needRetryCount.value++

    // 下一题
    if (currentIdx.value + 1 >= queue.value.length) {
      finished.value = true
    } else {
      currentIdx.value++
      revealed.value = false
      selectedQuality.value = null
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }

/* 完成页 */
.done-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 60rpx 40rpx; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.done-emoji { width: 96rpx; height: 96rpx; }
.done-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); }
.done-sub { font-size: 28rpx; color: var(--c-text-second); }
.done-stats { display: flex; gap: 48rpx; margin: 8rpx 0; }
.stat-box { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.stat-n { font-size: 48rpx; font-weight: 900; color: var(--c-gold); }
.stat-l { font-size: 22rpx; color: var(--c-text-hint); }

/* 进度条 */
.progress-wrap { display: flex; align-items: center; gap: 16rpx; margin-bottom: 20rpx; }
.progress-bar { flex: 1; height: 14rpx; background: #e3edf5; border-radius: 999rpx; overflow: hidden; }
.progress-fill { height: 100%; background: #7bbde8; border-radius: 999rpx; transition: width 0.3s; }
.progress-text { font-size: 24rpx; font-weight: 800; color: #3f87b8; white-space: nowrap; }

/* 题目卡片 */
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.meta-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18rpx; }
.meta-tag { font-size: 22rpx; font-weight: 700; color: #3f87b8; background: #e9f4fb; padding: 5rpx 18rpx; border-radius: 999rpx; }
.meta-review { font-size: 22rpx; color: var(--c-text-hint); }
.question-text { display: block; font-size: 32rpx; color: var(--c-ink); line-height: 1.6; font-weight: 700; margin-bottom: 28rpx; }

/* 揭示区 */
.reveal-wrap { background: #eef5fb; border: 2rpx dashed #b6d8ee; border-radius: var(--r-md); padding: 40rpx; text-align: center; margin-bottom: 28rpx; }
.reveal-wrap:active { background: #e2eff9; }
.reveal-hint { font-size: 28rpx; color: #5e93ba; font-weight: 600; }

/* 答案卡 */
.answer-wrap { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 8rpx 24rpx; margin-bottom: 28rpx; }
.ans-item { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; padding: 20rpx 0; }
.ans-divider { height: 1rpx; background: var(--c-border); }
.ans-k { font-size: 24rpx; color: var(--c-text-second); flex-shrink: 0; }
.ans-v { font-size: 30rpx; font-weight: 800; text-align: right; }
.ans-v.ans-wrong { color: #e0512c; }
.ans-v.ans-right { color: #18a058; }

/* 评分区 */
.quality-wrap { border-top: 1rpx solid var(--c-border); padding-top: 28rpx; }
.quality-label { font-size: 28rpx; font-weight: 700; color: var(--c-ink); display: block; margin-bottom: 22rpx; }
.quality-btns { display: flex; justify-content: space-between; gap: 12rpx; margin-bottom: 28rpx; }
.q-btn { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 10rpx; padding: 20rpx 4rpx; border-radius: var(--r-md); background: #f6f8fa; border: 2rpx solid transparent; transition: all 0.15s; }
.q-btn:active { transform: scale(0.96); }
.q-label { font-size: 19rpx; color: var(--c-text-hint); }
/* 线性表情图标（难过→开心 渐变，按掌握程度配色）*/
.q-icon {
  width: 48rpx; height: 48rpx;
  background-repeat: no-repeat; background-position: center; background-size: contain;
}
.q-lv-0 .q-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23f08a6a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Ccircle cx='9' cy='10' r='1' fill='%23f08a6a' stroke='none'/%3E%3Ccircle cx='15' cy='10' r='1' fill='%23f08a6a' stroke='none'/%3E%3Cpath d='M7.8 16.2 Q12 12.8 16.2 16.2'/%3E%3C/svg%3E"); }
.q-lv-1 .q-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23f5a623' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Ccircle cx='9' cy='10' r='1' fill='%23f5a623' stroke='none'/%3E%3Ccircle cx='15' cy='10' r='1' fill='%23f5a623' stroke='none'/%3E%3Cpath d='M8.2 15.8 Q12 14 15.8 15.8'/%3E%3C/svg%3E"); }
.q-lv-2 .q-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23e0a116' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Ccircle cx='9' cy='10' r='1' fill='%23e0a116' stroke='none'/%3E%3Ccircle cx='15' cy='10' r='1' fill='%23e0a116' stroke='none'/%3E%3Cpath d='M8.5 15 L15.5 15'/%3E%3C/svg%3E"); }
.q-lv-3 .q-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%235fa9dd' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Ccircle cx='9' cy='10' r='1' fill='%235fa9dd' stroke='none'/%3E%3Ccircle cx='15' cy='10' r='1' fill='%235fa9dd' stroke='none'/%3E%3Cpath d='M8.2 14.6 Q12 16.4 15.8 14.6'/%3E%3C/svg%3E"); }
.q-lv-4 .q-icon { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%232ecc71' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Ccircle cx='9' cy='10' r='1' fill='%232ecc71' stroke='none'/%3E%3Ccircle cx='15' cy='10' r='1' fill='%232ecc71' stroke='none'/%3E%3Cpath d='M7.8 14.2 Q12 17.8 16.2 14.2'/%3E%3C/svg%3E"); }
/* 选中态：按掌握程度梯度着色（忘→掌握 暖到冷）*/
.q-btn.selected { border-width: 2rpx; }
.q-btn.q-lv-0.selected { border-color: #f08a6a; background: #fff0eb; }
.q-btn.q-lv-1.selected { border-color: #f5a623; background: #fff5e3; }
.q-btn.q-lv-2.selected { border-color: #e0a116; background: #fdf6da; }
.q-btn.q-lv-3.selected { border-color: #7bbde8; background: #eaf4fb; }
.q-btn.q-lv-4.selected { border-color: #2ecc71; background: #eafaf1; }
.q-btn.selected .q-label { font-weight: 800; color: var(--c-ink); }
.submit-btn { margin-top: 0; }

.btn-primary { background: #7bbde8; color: #fff; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; width: 100%; }
.btn-primary[disabled] { background: #d4e7f5; color: #97b8cf; }
</style>

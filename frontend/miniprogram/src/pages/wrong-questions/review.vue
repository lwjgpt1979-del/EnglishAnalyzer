<!-- 错题智能复习（V2 M36）— SM-2 间隔重复 -->
<template>
  <view class="page">

    <!-- 加载中 -->
    <view v-if="loading" class="center-tip">正在加载今日复习…</view>

    <!-- 全部复习完 / 无待复习 -->
    <view v-else-if="!current && !finished" class="done-card">
      <text class="done-emoji">✅</text>
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
      <text class="done-emoji">🎉</text>
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
          <view class="answer-row">
            <text class="answer-label">你的作答：</text>
            <text class="answer-val student">{{ current!.student_answer || '（未记录）' }}</text>
          </view>
          <view class="answer-row">
            <text class="answer-label">正确答案：</text>
            <text class="answer-val correct">{{ current!.correct_answer || '（未记录）' }}</text>
          </view>
        </view>

        <!-- 评分按钮（揭示后才显示）-->
        <view v-if="revealed" class="quality-wrap">
          <text class="quality-label">这道题你掌握得怎么样？</text>
          <view class="quality-btns">
            <view
              v-for="btn in qualityBtns"
              :key="btn.q"
              class="q-btn"
              :class="selectedQuality === btn.q ? 'selected' : ''"
              @tap="selectedQuality = btn.q"
            >
              <text class="q-icon">{{ btn.icon }}</text>
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
.done-emoji { font-size: 96rpx; }
.done-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); }
.done-sub { font-size: 28rpx; color: var(--c-text-second); }
.done-stats { display: flex; gap: 48rpx; margin: 8rpx 0; }
.stat-box { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.stat-n { font-size: 48rpx; font-weight: 900; color: var(--c-gold); }
.stat-l { font-size: 22rpx; color: var(--c-text-hint); }

/* 进度条 */
.progress-wrap { display: flex; align-items: center; gap: 16rpx; margin-bottom: 20rpx; }
.progress-bar { flex: 1; height: 12rpx; background: #f0f0f0; border-radius: 999rpx; overflow: hidden; }
.progress-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; transition: width 0.3s; }
.progress-text { font-size: 22rpx; color: var(--c-text-hint); white-space: nowrap; }

/* 题目卡片 */
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.meta-row { display: flex; justify-content: space-between; margin-bottom: 16rpx; }
.meta-tag { font-size: 22rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 12rpx; border-radius: 999rpx; }
.meta-review { font-size: 22rpx; color: var(--c-text-hint); }
.question-text { display: block; font-size: 30rpx; color: var(--c-ink); line-height: 1.6; font-weight: 600; margin-bottom: 28rpx; }

/* 揭示区 */
.reveal-wrap { background: #f5f5f5; border-radius: var(--r-md); padding: 36rpx; text-align: center; margin-bottom: 24rpx; cursor: pointer; }
.reveal-hint { font-size: 28rpx; color: var(--c-text-hint); }
.answer-wrap { display: flex; flex-direction: column; gap: 16rpx; margin-bottom: 28rpx; }
.answer-row { display: flex; align-items: flex-start; gap: 8rpx; }
.answer-label { font-size: 24rpx; color: var(--c-text-hint); white-space: nowrap; }
.answer-val { font-size: 28rpx; font-weight: 600; }
.answer-val.student { color: var(--c-danger); }
.answer-val.correct { color: #22c55e; }

/* 评分区 */
.quality-wrap { border-top: 1rpx solid var(--c-border); padding-top: 24rpx; }
.quality-label { font-size: 26rpx; color: var(--c-text-second); display: block; margin-bottom: 20rpx; }
.quality-btns { display: flex; justify-content: space-between; gap: 8rpx; margin-bottom: 24rpx; }
.q-btn { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6rpx; padding: 16rpx 4rpx; border-radius: var(--r-md); background: #f8f8f8; border: 2rpx solid transparent; transition: all 0.15s; }
.q-btn.selected { border-color: var(--c-primary); background: var(--c-primary-faint); }
.q-icon { font-size: 36rpx; }
.q-label { font-size: 18rpx; color: var(--c-text-hint); }
.q-btn.selected .q-label { color: var(--c-primary-deep); font-weight: 700; }
.submit-btn { margin-top: 0; }

.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; width: 100%; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
</style>

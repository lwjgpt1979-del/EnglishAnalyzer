<template>
  <view class="se-page">
    <view v-if="loading" class="center-tip">加载中…</view>

    <view v-else>
      <!-- 头部 -->
      <view class="hero">
        <text class="hero-title">📝 自助出卷</text>
        <text class="hero-sub">ProMax 专属 · 按你的薄弱点智能组卷、限时作答</text>
      </view>

      <!-- 非 ProMax -->
      <view v-if="!quota.is_promax" class="card lock-card">
        <text class="lock-icon">🔒</text>
        <text class="lock-title">ProMax 会员专属功能</text>
        <text class="lock-desc">升级 ProMax 后，可按薄弱点自助生成模拟卷、限时实战。</text>
      </view>

      <!-- ProMax -->
      <view v-else>
        <view class="card quota-card">
          <view class="quota-row">
            <text class="quota-label">本周剩余次数</text>
            <text class="quota-val">{{ quota.remaining }} / {{ quota.limit }}</text>
          </view>
          <button
            class="btn-primary"
            :disabled="quota.remaining <= 0 || generating"
            @tap="onGenerate"
          >
            {{ generating ? '出卷中…' : (quota.remaining > 0 ? '开始出卷（约10题·15分钟）' : '本周次数已用完') }}
          </button>
          <text class="quota-tip">每周 {{ quota.limit }} 份，自然周一 0:00 重置</text>
        </view>

        <!-- 历史记录 -->
        <view class="card">
          <view class="card-title">历史记录</view>
          <view v-if="history.length === 0" class="empty">还没有出过卷，点上方开始吧</view>
          <view
            v-for="h in history" :key="h.id"
            class="hist-row" @tap="goExam(h)"
          >
            <view class="hist-left">
              <text class="hist-date">{{ h.created_at.slice(5, 16).replace('T', ' ') }}</text>
              <text class="hist-status" :class="h.status">{{ h.status === 'done' ? '已完成' : '答题中' }}</text>
            </view>
            <view class="hist-right">
              <text v-if="h.status === 'done'" class="hist-score">{{ h.correct_count }}/{{ h.total }}</text>
              <text v-else class="hist-continue">继续 ›</text>
            </view>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import {
  getSelfExamQuota, generateSelfExam, getSelfExamHistory,
  type SelfExamBrief,
} from '@/api/selfExam'

const loading = ref(true)
const generating = ref(false)
const quota = reactive({ is_promax: false, used: 0, limit: 3, remaining: 3 })
const history = ref<SelfExamBrief[]>([])

async function load() {
  try {
    const [q, h] = await Promise.all([getSelfExamQuota(), getSelfExamHistory().catch(() => [])])
    Object.assign(quota, q)
    history.value = h
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

async function onGenerate() {
  generating.value = true
  try {
    const exam = await generateSelfExam()
    uni.navigateTo({ url: `/pages/self-exam/answer?id=${exam.id}` })
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '出卷失败', icon: 'none' })
  } finally {
    generating.value = false
  }
}

function goExam(h: SelfExamBrief) {
  // 答题中→继续作答；已完成→查看结果（答题页据 status 展示）
  uni.navigateTo({ url: `/pages/self-exam/answer?id=${h.id}` })
}

onMounted(load)
</script>

<style scoped>
.se-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 0; color: var(--c-text-hint); }
.hero { padding: 8rpx 4rpx 20rpx; }
.hero-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hero-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.lock-card { display: flex; flex-direction: column; align-items: center; gap: 12rpx; padding: 56rpx 40rpx; text-align: center; }
.lock-icon { font-size: 72rpx; }
.lock-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.lock-desc { font-size: 26rpx; color: var(--c-text-second); line-height: 1.6; }
.quota-card { display: flex; flex-direction: column; gap: 16rpx; }
.quota-row { display: flex; align-items: baseline; justify-content: space-between; }
.quota-label { font-size: 28rpx; color: var(--c-text-second); }
.quota-val { font-size: 44rpx; font-weight: 900; color: var(--c-primary); }
.quota-tip { font-size: 22rpx; color: var(--c-text-hint); text-align: center; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 24rpx; font-size: 30rpx; font-weight: 700; text-align: center; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.empty { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 24rpx 0; }
.hist-row { display: flex; align-items: center; justify-content: space-between; padding: 18rpx 0; border-bottom: 1rpx solid var(--c-border); }
.hist-row:last-child { border-bottom: none; }
.hist-left { display: flex; align-items: center; gap: 14rpx; }
.hist-date { font-size: 26rpx; color: var(--c-ink); font-weight: 600; }
.hist-status { font-size: 20rpx; padding: 2rpx 12rpx; border-radius: var(--r-pill); }
.hist-status.done { background: #e6f8ee; color: #18a058; }
.hist-status.answering { background: var(--c-primary-faint); color: var(--c-primary-deep); }
.hist-score { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.hist-continue { font-size: 26rpx; color: var(--c-primary); }
</style>

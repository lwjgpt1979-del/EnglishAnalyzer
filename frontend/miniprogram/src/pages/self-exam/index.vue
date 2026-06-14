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
          <view v-if="quota.addon_left > 0" class="quota-row">
            <text class="quota-label">加量包余额</text>
            <text class="quota-val">{{ quota.addon_left }} 次</text>
          </view>
          <button
            class="btn-primary"
            :disabled="(quota.remaining <= 0 && quota.addon_left <= 0 && !quota.can_buy_addon) || generating"
            @tap="onGenerate"
          >
            {{ generating ? '出卷中…' : (quota.remaining > 0 || quota.addon_left > 0 ? '开始出卷（约10题·15分钟）' : (quota.can_buy_addon ? '本周已用完 · 购买加量包' : '本周次数已用完')) }}
          </button>
          <text class="quota-tip">每周 {{ quota.limit }} 份，自然周一 0:00 重置{{ quota.addon_left > 0 ? '；超额用加量包' : '' }}</text>
        </view>

        <!-- 成绩趋势 -->
        <view v-if="doneExams.length >= 2" class="card">
          <view class="card-title">成绩趋势</view>
          <view class="trend-stats">
            <view class="ts-item">
              <text class="ts-num">{{ doneExams.length }}</text>
              <text class="ts-label">已完成</text>
            </view>
            <view class="ts-item">
              <text class="ts-num">{{ avgAcc }}%</text>
              <text class="ts-label">平均正确率</text>
            </view>
            <view class="ts-item">
              <text class="ts-num">{{ bestAcc }}%</text>
              <text class="ts-label">最高正确率</text>
            </view>
          </view>
          <view class="bars">
            <view v-for="(b, i) in bars" :key="i" class="bar-col">
              <view class="bar-track">
                <view class="bar-fill" :class="b.cls" :style="{ height: b.pct + '%' }" />
              </view>
              <text class="bar-acc">{{ b.acc }}</text>
            </view>
          </view>
          <text class="trend-hint">最近 {{ bars.length }} 次正确率（越高越好）</text>
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

    <Paywall :open="showPaywall" :feature="ent.feature('exam.generate')" emoji="📝"
      title="自助出卷" @close="showPaywall = false" @purchased="onPurchased" />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import {
  getSelfExamQuota, generateSelfExam, getSelfExamHistory,
  type SelfExamBrief,
} from '@/api/selfExam'
import { useEntitlementsStore } from '@/stores/entitlements'
import Paywall from '@/components/Paywall.vue'

const ent = useEntitlementsStore()
const showPaywall = ref(false)
const loading = ref(true)
const generating = ref(false)
const quota = reactive({ is_promax: false, used: 0, limit: 3, remaining: 3,
  addon_left: 0, can_buy_addon: false, addon_pack: null as { pack_size: number; price_fen: number } | null })
const history = ref<SelfExamBrief[]>([])

// 已完成的卷（按时间正序，用于趋势）
const doneExams = computed(() =>
  history.value.filter(h => h.status === 'done' && h.total)
    .slice().reverse(),
)
function accPct(h: SelfExamBrief) {
  return Math.round(((h.accuracy ?? (h.correct_count || 0) / (h.total || 1))) * 100)
}
const avgAcc = computed(() => {
  const xs = doneExams.value.map(accPct)
  return xs.length ? Math.round(xs.reduce((a, b) => a + b, 0) / xs.length) : 0
})
const bestAcc = computed(() => {
  const xs = doneExams.value.map(accPct)
  return xs.length ? Math.max(...xs) : 0
})
const bars = computed(() =>
  doneExams.value.slice(-10).map(h => {
    const acc = accPct(h)
    const cls = acc >= 85 ? 'good' : acc >= 60 ? 'mid' : 'low'
    return { acc, pct: Math.max(6, acc), cls }
  }),
)

async function load() {
  ent.fetch()
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
  // 配额+加量余额都没了：顶档→买加量包，否则→升级
  if (quota.remaining <= 0 && quota.addon_left <= 0) { showPaywall.value = true; return }
  generating.value = true
  try {
    const exam = await generateSelfExam()
    uni.navigateTo({ url: `/pages/self-exam/answer?id=${exam.id}` })
  } catch (e) {
    if ((e as { code?: number }).code === 403) { showPaywall.value = true }
    else uni.showToast({ title: (e as Error).message || '出卷失败', icon: 'none' })
  } finally {
    generating.value = false
  }
}
async function onPurchased() { await load() }

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

/* 成绩趋势 */
.trend-stats { display: flex; justify-content: space-around; margin-bottom: 20rpx; }
.ts-item { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.ts-num { font-size: 40rpx; font-weight: 900; color: var(--c-primary); }
.ts-label { font-size: 22rpx; color: var(--c-text-hint); }
.bars { display: flex; align-items: flex-end; gap: 12rpx; height: 200rpx; padding: 8rpx 4rpx 0; }
.bar-col { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8rpx; height: 100%; justify-content: flex-end; }
.bar-track { width: 100%; flex: 1; display: flex; align-items: flex-end; background: var(--c-bg-soft); border-radius: 8rpx; overflow: hidden; }
.bar-fill { width: 100%; border-radius: 8rpx 8rpx 0 0; transition: height .3s; }
.bar-fill.good { background: #18a058; }
.bar-fill.mid { background: var(--c-primary); }
.bar-fill.low { background: #f0a020; }
.bar-acc { font-size: 20rpx; color: var(--c-text-second); font-weight: 600; }
.trend-hint { display: block; text-align: center; font-size: 22rpx; color: var(--c-text-hint); margin-top: 12rpx; }
</style>

<!-- src/pages/vocabulary/report.vue 词力通学情报表 -->
<template>
  <view class="rp-page">
    <view v-if="loading" class="center-tip">加载学情…</view>
    <view v-else-if="ov" class="rp-body">
      <!-- 词数分布 -->
      <view class="rp-card">
        <text class="rp-title">📚 单词进度</text>
        <view class="stat-grid">
          <view class="stat"><text class="stat-n mastered">{{ ov.mastered }}</text><text class="stat-l">已掌握</text></view>
          <view class="stat"><text class="stat-n learning">{{ ov.learning + ov.new_learned }}</text><text class="stat-l">在学</text></view>
          <view class="stat"><text class="stat-n review">{{ ov.due_total }}</text><text class="stat-l">待复习</text></view>
          <view class="stat"><text class="stat-n remain">{{ ov.remaining_new }}</text><text class="stat-l">待学</text></view>
        </view>
        <view v-if="ov.learned_total" class="bar">
          <view class="bar-seg mastered" :style="{ width: pct(ov.mastered) }" />
          <view class="bar-seg learning" :style="{ width: pct(ov.learning + ov.new_learned) }" />
          <view class="bar-seg review" :style="{ width: pct(ov.review) }" />
        </view>
        <text class="rp-sub">已学 {{ ov.learned_total }} 词</text>
      </view>

      <!-- 坚持 + 错词 -->
      <view class="rp-row">
        <view class="rp-card half">
          <text class="rp-title">🔥 坚持</text>
          <text class="big">{{ ov.current_streak }}<text class="big-u"> 天</text></text>
          <text class="rp-sub">最高连续 {{ ov.longest_streak }} 天</text>
        </view>
        <view class="rp-card half" @tap="goWrongBook">
          <text class="rp-title">📕 错词本</text>
          <text class="big wrong">{{ ov.wrong_total }}<text class="big-u"> 词</text></text>
          <text class="rp-sub link">查看错词本 ›</text>
        </view>
      </view>

      <!-- 发音报告 -->
      <view v-if="ov.pron" class="rp-card">
        <view class="vrep-hd">
          <text class="rp-title">🎤 发音报告</text>
          <text class="vrep-trend" :class="ov.pron.trend">{{ trendText(ov.pron.trend) }}</text>
        </view>
        <view class="vrep-top">
          <view class="vrep-avg">
            <text class="vrep-avg-n">{{ ov.pron.avg ?? '-' }}</text>
            <text class="vrep-avg-u">平均分</text>
          </view>
          <view class="vrep-dims">
            <text class="vrep-dim">跟读 {{ ov.pron.count }} 次</text>
            <text v-if="ov.pron.accuracy != null" class="vrep-dim">准确 {{ ov.pron.accuracy }} · 流利 {{ ov.pron.fluency }} · 完整 {{ ov.pron.completion }}</text>
          </view>
        </view>
        <view v-if="ov.pron.bars.length" class="vrep-bars">
          <view v-for="(b, i) in ov.pron.bars" :key="i" class="vrep-bar" :class="barLevel(b)"
            :style="{ height: Math.max(8, b * 0.6) + 'rpx' }" />
        </view>
        <view v-if="ov.pron.weak_words.length" class="vrep-weak">
          <text class="vrep-weak-t">需加强：</text>
          <text v-for="(w, i) in ov.pron.weak_words" :key="i" class="vrep-weak-w">{{ w }}</text>
        </view>
      </view>
      <view v-else class="rp-card">
        <text class="rp-title">🎤 发音报告</text>
        <text class="rp-sub">还没有跟读记录，去词力通点 🎤 跟读试试吧（会员功能）。</text>
      </view>

      <button class="btn-primary" @tap="goStudy">去学习 →</button>
    </view>
    <view v-else class="center-tip">暂无学情数据</view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getVocabOverview, type VocabOverview } from '@/api/vocabulary'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const loading = ref(true)
const ov = ref<VocabOverview | null>(null)

function pct(n: number): string {
  const total = ov.value?.learned_total || 1
  return `${Math.round((n / total) * 100)}%`
}
function trendText(t: string) {
  return t === 'up' ? '📈 越练越好' : t === 'down' ? '📉 略有起伏' : '➡️ 稳定发挥'
}
function barLevel(b: number) {
  return b >= 90 ? 'excellent' : b >= 80 ? 'good' : b >= 60 ? 'fair' : 'poor'
}
function goWrongBook() { uni.navigateTo({ url: '/pages/vocabulary/wrong-book' }) }
function goStudy() { uni.navigateTo({ url: '/pages/vocabulary/index' }) }

async function load() {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try { ov.value = await getVocabOverview() } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally { loading.value = false }
}
onMounted(load)
</script>

<style scoped>
.rp-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); line-height: 1.8; }
.rp-body { display: flex; flex-direction: column; gap: 20rpx; }
.rp-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx 26rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); display: flex; flex-direction: column; gap: 14rpx; }
.rp-row { display: flex; gap: 20rpx; }
.rp-card.half { flex: 1; }
.rp-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.rp-sub { font-size: 24rpx; color: var(--c-text-hint); }
.rp-sub.link { color: var(--c-primary-deep); font-weight: 700; }
.stat-grid { display: flex; justify-content: space-between; }
.stat { display: flex; flex-direction: column; align-items: center; gap: 6rpx; flex: 1; }
.stat-n { font-size: 44rpx; font-weight: 900; }
.stat-n.mastered { color: #34c759; }
.stat-n.learning { color: #5aa9f8; }
.stat-n.review { color: #ffab40; }
.stat-n.remain { color: var(--c-text-hint); }
.stat-l { font-size: 22rpx; color: var(--c-text-second); }
.bar { display: flex; height: 18rpx; border-radius: 10rpx; overflow: hidden; background: var(--c-bg-soft); }
.bar-seg.mastered { background: #34c759; }
.bar-seg.learning { background: #5aa9f8; }
.bar-seg.review { background: #ffab40; }
.big { font-size: 56rpx; font-weight: 900; color: var(--c-ink); }
.big-u { font-size: 26rpx; font-weight: 600; color: var(--c-text-hint); }
.big.wrong { color: #ff6b6b; }
/* 发音报告（复用样式） */
.vrep-hd { display: flex; align-items: center; justify-content: space-between; }
.vrep-trend { font-size: 22rpx; font-weight: 700; padding: 3rpx 14rpx; border-radius: var(--r-pill); background: var(--c-bg-soft); }
.vrep-trend.up { color: #34c759; }
.vrep-trend.down { color: #ff9500; }
.vrep-trend.flat { color: #5aa9f8; }
.vrep-top { display: flex; align-items: center; gap: 18rpx; }
.vrep-avg { flex-shrink: 0; display: flex; flex-direction: column; align-items: center; background: var(--c-bg-soft); border-radius: 14rpx; padding: 10rpx 22rpx; }
.vrep-avg-n { font-size: 48rpx; font-weight: 900; color: #2f6fd6; line-height: 1.1; }
.vrep-avg-u { font-size: 20rpx; color: var(--c-text-hint); }
.vrep-dims { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.vrep-dim { font-size: 23rpx; color: var(--c-text-body); }
.vrep-bars { display: flex; align-items: flex-end; gap: 6rpx; height: 64rpx; padding: 4rpx 0; }
.vrep-bar { flex: 1; min-width: 8rpx; border-radius: 4rpx; background: #5aa9f8; }
.vrep-bar.excellent { background: #34c759; }
.vrep-bar.good { background: #5aa9f8; }
.vrep-bar.fair { background: #ffab40; }
.vrep-bar.poor { background: #ff6b6b; }
.vrep-weak { display: flex; flex-wrap: wrap; align-items: center; gap: 8rpx; }
.vrep-weak-t { font-size: 23rpx; color: var(--c-text-hint); }
.vrep-weak-w { font-size: 22rpx; font-weight: 700; color: #d6457e; background: #fff0f5; border-radius: var(--r-pill); padding: 3rpx 14rpx; }
.btn-primary { margin-top: 8rpx; }
</style>

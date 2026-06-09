<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="detail">
      <view class="header">
        <text class="badge">U{{ detail.unit_no }}</text>
        <text class="title">{{ detail.unit_title }}</text>
        <text class="meta">{{ detail.knowledge_points.length }} 知识点 · {{ detail.words.length }} 词</text>
        <text class="meta accent" v-if="overallAccuracy !== null">综合正确率 {{ overallAccuracy }}%</text>
      </view>

      <view class="card">
        <view class="card-title">知识点</view>
        <view
          v-for="kp in detail.knowledge_points"
          :key="kp.id"
          class="kp-row"
          @tap="goKp(kp.id)"
        >
          <view class="kp-body">
            <text class="kp-name">{{ kp.name }}</text>
            <text class="kp-cat">{{ catLabel(kp.category) }}</text>
            <view class="kp-progress-wrap" v-if="masteryMap[kp.id]?.total > 0">
              <view class="kp-progress-bar">
                <view class="kp-progress-fill" :style="{ width: Math.round((masteryMap[kp.id]?.accuracy ?? 0) * 100) + '%' }" />
              </view>
              <text class="kp-acc">{{ Math.round((masteryMap[kp.id]?.accuracy ?? 0) * 100) }}%</text>
            </view>
            <text class="kp-no-data" v-else>未练习</text>
          </view>
          <text class="chevron">›</text>
        </view>
      </view>

      <!-- 智能推题入口 -->
      <view class="adaptive-bar">
        <button class="btn-adaptive" @tap="goAdaptive">🧠 智能推题（针对本单元弱项）</button>
      </view>

      <view class="card">
        <view class="card-title">词汇 ({{ detail.words.length }})</view>
        <view v-for="w in detail.words" :key="w.id" class="word-row">
          <text class="word-en">{{ w.word }}</text>
          <text v-if="w.phonetic" class="word-ph">{{ w.phonetic }}</text>
          <text class="word-cn">{{ definitionText(w.definitions) }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { getUnitDetail, getUnitMasterySummary } from '@/api/curriculum'
import type { UnitDetailOut, WordOut, KpMasterySummaryItem } from '@/types/api'

const detail = ref<UnitDetailOut | null>(null)
const loading = ref(true)
const mastery = ref<KpMasterySummaryItem[]>([])
const unitId = ref('')

const masteryMap = computed(() => {
  const m: Record<string, KpMasterySummaryItem> = {}
  for (const item of mastery.value) m[item.kp_id] = item
  return m
})

const overallAccuracy = computed(() => {
  const practiced = mastery.value.filter(m => m.total > 0)
  if (!practiced.length) return null
  const totalCorrect = practiced.reduce((s, m) => s + m.correct_count, 0)
  const totalAttempts = practiced.reduce((s, m) => s + m.total, 0)
  return totalAttempts > 0 ? Math.round(totalCorrect / totalAttempts * 100) : null
})

async function loadMastery() {
  if (!unitId.value) return
  try {
    mastery.value = await getUnitMasterySummary(unitId.value)
  } catch { /* 静默失败 */ }
}

onLoad(async (q: any) => {
  unitId.value = q.id || ''
  try {
    detail.value = await getUnitDetail(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
  } finally {
    loading.value = false
  }
  loadMastery()
})

onShow(() => {
  loadMastery()
})

function goKp(id: string) {
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${id}` })
}

function goAdaptive() {
  if (!detail.value) return
  const title = encodeURIComponent(detail.value.unit_title)
  uni.navigateTo({
    url: `/pages/practice/adaptive?unit_id=${unitId.value}&unit_title=${title}`,
  })
}
function catLabel(c: string): string {
  return ({ grammar: '语法', vocabulary: '词汇', reading: '阅读', writing: '写作', listening: '听力' } as any)[c] || c
}
function definitionText(defs: WordOut['definitions']): string {
  return defs.map(d => (d.pos ? `${d.pos} ${d.meaning}` : d.meaning)).join('；')
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.header { display: flex; align-items: center; gap: 16rpx; padding: 12rpx 0 24rpx; }
.badge { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-md); padding: 6rpx 14rpx; font-size: 26rpx; font-weight: 800; }
.title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); flex: 1; }
.meta { font-size: 22rpx; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 16rpx; color: var(--c-ink); }
.kp-row { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.kp-row:last-child { border-bottom: none; }
.kp-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.kp-name { font-size: 28rpx; color: var(--c-ink); font-weight: 600; }
.kp-cat { font-size: 22rpx; color: var(--c-text-second); }
.chevron { color: var(--c-text-hint); font-size: 32rpx; }
.word-row { display: flex; align-items: baseline; gap: 12rpx; padding: 12rpx 0; border-bottom: 1rpx dashed var(--c-border); }
.word-row:last-child { border-bottom: none; }
.word-en { font-size: 28rpx; font-weight: 700; color: var(--c-ink); min-width: 160rpx; }
.word-ph { font-size: 22rpx; color: var(--c-text-hint); }
.word-cn { flex: 1; font-size: 24rpx; color: var(--c-text-body); }
.meta.accent { color: var(--c-primary); font-weight: 700; }
.kp-progress-wrap { display: flex; align-items: center; gap: 10rpx; margin-top: 6rpx; }
.kp-progress-bar { flex: 1; height: 8rpx; background: var(--c-bg-soft); border-radius: 999rpx; overflow: hidden; }
.kp-progress-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; }
.kp-acc { font-size: 22rpx; color: var(--c-primary); font-weight: 700; min-width: 60rpx; }
.kp-no-data { font-size: 22rpx; color: var(--c-text-hint); margin-top: 4rpx; }
.adaptive-bar { padding: 0 0 20rpx; }
.btn-adaptive {
  width: 100%; background: var(--c-gold, #f5c518); color: #333;
  border-radius: var(--r-btn); padding: 22rpx; font-weight: 700;
  font-size: 28rpx; text-align: center;
  box-shadow: 0 4rpx 16rpx rgba(245,197,24,.3);
}
</style>

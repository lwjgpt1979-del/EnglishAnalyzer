<!-- V2 M3c: 练习调度页 — 搜索知识点或使用 AI 智能推荐 -->
<template>
  <view class="page">
    <!-- 练习统计 -->
    <view v-if="stats && stats.total_practiced > 0" class="card stat-card">
      <view class="card-title">我的练习统计</view>
      <view class="stat-row">
        <view class="stat"><text class="num">{{ stats.total_practiced }}</text><text class="lbl">累计练习</text></view>
        <view class="stat"><text class="num">{{ stats.total_correct }}</text><text class="lbl">答对题数</text></view>
        <view class="stat"><text class="num">{{ Math.round(stats.correct_rate * 100) }}%</text><text class="lbl">正确率</text></view>
      </view>
    </view>

    <!-- 搜索区 -->
    <view class="card search-card">
      <view class="card-title">选择知识点练习</view>
      <view class="search-row">
        <input
          v-model="query"
          class="search-input"
          placeholder="搜索知识点，如：现在完成时"
          @input="onInput"
          @confirm="doSearch"
        />
        <button class="btn-search" @tap="doSearch">搜索</button>
      </view>

      <!-- 搜索结果 -->
      <view v-if="searching" class="hint">搜索中…</view>
      <view v-else-if="results.length" class="result-list">
        <view
          v-for="kp in results"
          :key="kp.id"
          class="result-item"
          @tap="goSession(kp)"
        >
          <view class="result-main">
            <text class="result-name">{{ kp.name }}</text>
            <text class="result-cat">{{ kp.category }}</text>
          </view>
          <text class="result-arrow">›</text>
        </view>
      </view>
      <view v-else-if="searched && !results.length" class="hint">
        未找到匹配知识点，换个关键词试试
      </view>
    </view>

    <!-- 分割线 -->
    <view class="divider">
      <view class="divider-line" /><text class="divider-text">或</text><view class="divider-line" />
    </view>

    <!-- AI 智能推荐 -->
    <view class="card ai-card" @tap="goAdaptive">
      <view class="ai-left">
        <view class="ic ic-robot ai-icon" />
        <view>
          <text class="ai-title">AI 帮我选</text>
          <text class="ai-desc">基于薄弱点智能推荐题目</text>
        </view>
      </view>
      <text class="ai-arrow">›</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { searchKPs } from '@/api/curriculum_kps'
import { getPracticeStats } from '@/api/practice'
import type { KPSearchItem, PracticeStatsOut } from '@/types/api'

const stats = ref<PracticeStatsOut | null>(null)
const query = ref('')
const results = ref<KPSearchItem[]>([])
const searching = ref(false)
const searched = ref(false)

let debounceTimer: ReturnType<typeof setTimeout> | null = null

function onInput() {
  if (debounceTimer) clearTimeout(debounceTimer)
  if (!query.value.trim()) {
    results.value = []
    searched.value = false
    return
  }
  debounceTimer = setTimeout(doSearch, 400)
}

async function doSearch() {
  if (!query.value.trim()) return
  searching.value = true
  searched.value = false
  try {
    results.value = await searchKPs(query.value.trim(), 10)
    searched.value = true
  } catch {
    uni.showToast({ title: '搜索失败，请重试', icon: 'none' })
  } finally {
    searching.value = false
  }
}

function goSession(kp: KPSearchItem) {
  uni.navigateTo({
    url: `/pages/practice/v2-session?kp=${kp.id}&dim=grammar`,
  })
}

function goAdaptive() {
  uni.navigateTo({ url: '/pages/practice/adaptive' })
}

onMounted(async () => {
  try { stats.value = await getPracticeStats() } catch { /* 静默忽略 */ }
})
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }

.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4);
        box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 24rpx; }
.card-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 20rpx; display: block; }

.search-row { display: flex; gap: 12rpx; margin-bottom: 16rpx; }
.search-input { flex: 1; border: 2rpx solid var(--c-border); border-radius: var(--r-md);
                height: 72rpx; line-height: 72rpx; padding: 0 20rpx; font-size: 28rpx; }
.btn-search { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-md);
              padding: 0 28rpx; font-size: 26rpx; font-weight: 600; height: 72rpx;
              line-height: 72rpx; white-space: nowrap; }

.hint { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 16rpx 0; }

.result-list { display: flex; flex-direction: column; gap: 2rpx; }
.result-item { display: flex; align-items: center; justify-content: space-between;
               padding: 20rpx 12rpx; border-bottom: 1rpx solid var(--c-border); }
.result-item:last-child { border-bottom: none; }
.result-main { display: flex; flex-direction: column; gap: 4rpx; }
.result-name { font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.result-cat { font-size: 22rpx; color: var(--c-text-hint); }
.result-arrow { font-size: 36rpx; color: var(--c-text-hint); }

.divider { display: flex; align-items: center; gap: 16rpx; margin: 8rpx 0 24rpx; }
.divider-line { flex: 1; height: 1rpx; background: var(--c-border); }
.divider-text { font-size: 24rpx; color: var(--c-text-hint); white-space: nowrap; }

.ai-card { display: flex; align-items: center; justify-content: space-between; cursor: pointer; }
.ai-left { display: flex; align-items: center; gap: 20rpx; }
.ai-icon { width: 56rpx; height: 56rpx; }
.ai-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); display: block; }
.ai-desc { font-size: 24rpx; color: var(--c-text-second); display: block; margin-top: 4rpx; }
.ai-arrow { font-size: 40rpx; color: var(--c-text-hint); }

.stat-card .stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 48rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 22rpx; color: var(--c-text-hint); }
</style>

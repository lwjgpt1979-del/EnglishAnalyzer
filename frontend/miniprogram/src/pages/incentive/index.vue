<!-- 学习激励中心（M10）：等级/经验值 + 连续打卡 + 成就墙 -->
<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>

    <view v-else-if="s">
      <!-- 等级 + 经验值 -->
      <view class="card level-card">
        <view class="level-badge">Lv.{{ s.level }}</view>
        <view class="level-info">
          <view class="level-row">
            <text class="level-xp">{{ s.xp }} XP</text>
            <text class="level-next">距下一级 {{ s.xp_to_next }} XP</text>
          </view>
          <view class="xp-track">
            <view class="xp-fill" :style="{ width: Math.round(s.xp_in_level) + '%' }" />
          </view>
        </view>
      </view>

      <!-- 连续打卡 -->
      <view class="card streak-card">
        <view class="streak-main">
          <view class="ic ic-flame streak-flame" />
          <view class="streak-text">
            <text class="streak-num">{{ s.current_streak }}</text>
            <text class="streak-label">天连续打卡</text>
          </view>
        </view>
        <view class="streak-sub">
          <text>历史最高 {{ s.longest_streak }} 天</text>
          <view class="today-status" :class="s.checked_in_today ? 'today-ok' : 'today-no'">
            <text>{{ s.checked_in_today ? '今日已打卡' : '今日未打卡' }}</text>
            <view v-if="s.checked_in_today" class="ic ic-check today-check" />
          </view>
        </view>
        <!-- 打卡勋章 -->
        <view class="badge-row">
          <view
            v-for="b in s.badges"
            :key="b.level"
            class="badge-chip"
            :class="[b.level, { locked: !b.unlocked }]"
          >
            <text class="badge-name">{{ b.name }}</text>
            <text class="badge-th">{{ b.threshold }}天</text>
          </view>
        </view>
      </view>

      <!-- 成就墙 -->
      <view class="card">
        <view class="card-head">
          <view class="card-title-wrap">
            <view class="ic ic-trophy card-title-ic" />
            <text class="card-title">成就墙</text>
          </view>
          <text class="card-sub">{{ s.stats.unlocked_achievements }}/{{ s.stats.total_achievements }} 已解锁</text>
        </view>
        <view class="ach-grid">
          <view
            v-for="a in s.achievements"
            :key="a.key"
            class="ach-item"
            :class="{ locked: !a.unlocked }"
          >
            <text class="ach-icon">{{ a.icon }}</text>
            <text class="ach-name">{{ a.name }}</text>
            <text class="ach-desc">{{ a.desc }}</text>
            <view v-if="!a.unlocked" class="ach-prog-track">
              <view class="ach-prog-fill" :style="{ width: Math.round(a.progress * 100) + '%' }" />
            </view>
            <text class="ach-meta">{{ a.unlocked ? '已达成' : a.current + ' / ' + a.target }}</text>
          </view>
        </view>
      </view>

      <!-- 数据小结 -->
      <view class="card stats-card">
        <view class="stat"><text class="stat-num">{{ s.stats.total_practice }}</text><text class="stat-lbl">累计练习</text></view>
        <view class="stat"><text class="stat-num">{{ s.stats.mastered_kp }}</text><text class="stat-lbl">掌握知识点</text></view>
        <view class="stat"><text class="stat-num">{{ s.stats.wrong_mastered }}</text><text class="stat-lbl">攻克错题</text></view>
        <view class="stat"><text class="stat-num">{{ s.stats.checkin_days }}</text><text class="stat-lbl">打卡天数</text></view>
      </view>
    </view>

    <view v-else class="tip">暂无数据，先去练习几题吧</view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getIncentiveSummary } from '@/api/incentive'
import type { IncentiveSummary } from '@/types/api'

const s = ref<IncentiveSummary | null>(null)
const loading = ref(true)

async function load() {
  try { s.value = await getIncentiveSummary() }
  catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
onShow(load)
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }

/* 等级 */
.level-card { display: flex; align-items: center; gap: 28rpx; background: linear-gradient(135deg, #fff7e0, #ffeec0); }
.level-badge { width: 110rpx; height: 110rpx; border-radius: 50%; background: var(--c-primary); color: var(--c-on-primary); font-size: 34rpx; font-weight: 800; display: flex; align-items: center; justify-content: center; flex-shrink: 0; box-shadow: 0 4rpx 16rpx rgba(0,0,0,.12); }
.level-info { flex: 1; }
.level-row { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12rpx; }
.level-xp { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.level-next { font-size: 22rpx; color: var(--c-text-second); }
.xp-track { height: 16rpx; background: rgba(0,0,0,.08); border-radius: 999rpx; overflow: hidden; }
.xp-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; transition: width .4s; }

/* 连续打卡 */
.streak-main { display: flex; align-items: center; gap: 16rpx; }
.streak-flame { width: 64rpx; height: 64rpx; flex-shrink: 0; }
.streak-text { display: flex; align-items: baseline; gap: 8rpx; }
.streak-num { font-size: 64rpx; font-weight: 800; color: #ff7a00; }
.streak-label { font-size: 26rpx; color: var(--c-text-body); }
.streak-sub { display: flex; justify-content: space-between; font-size: 24rpx; color: var(--c-text-hint); margin: 12rpx 0 16rpx; }
.today-status { display: inline-flex; align-items: center; gap: 6rpx; }
.today-check { width: 26rpx; height: 26rpx; flex-shrink: 0; }
.today-ok { color: #2ecc71; font-weight: 700; }
.today-no { color: var(--c-text-hint); }
.badge-row { display: flex; gap: 12rpx; }
.badge-chip { flex: 1; text-align: center; padding: 12rpx 0; border-radius: 12rpx; display: flex; flex-direction: column; gap: 4rpx; }
.badge-chip.bronze { background: #fbe7d2; }
.badge-chip.silver { background: #e9edf2; }
.badge-chip.gold { background: #fdf1c4; }
.badge-chip.locked { background: var(--c-bg-soft); opacity: .5; filter: grayscale(1); }
.badge-name { font-size: 24rpx; font-weight: 700; color: var(--c-ink); }
.badge-th { font-size: 20rpx; color: var(--c-text-hint); }

/* 成就墙 */
.card-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20rpx; }
.card-title-wrap { display: flex; align-items: center; gap: 10rpx; }
.card-title-ic { width: 34rpx; height: 34rpx; flex-shrink: 0; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); }
.card-sub { font-size: 24rpx; color: var(--c-primary); font-weight: 700; }
.ach-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16rpx; }
.ach-item { background: var(--c-bg-soft); border-radius: 16rpx; padding: 24rpx 16rpx; display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6rpx; }
.ach-item.locked { opacity: .55; filter: grayscale(.8); }
.ach-icon { font-size: 56rpx; }
.ach-name { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.ach-desc { font-size: 20rpx; color: var(--c-text-hint); line-height: 1.4; }
.ach-prog-track { width: 100%; height: 8rpx; background: rgba(0,0,0,.08); border-radius: 999rpx; overflow: hidden; margin-top: 6rpx; }
.ach-prog-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; }
.ach-meta { font-size: 20rpx; color: var(--c-text-second); margin-top: 2rpx; }

/* 数据小结 */
.stats-card { display: flex; justify-content: space-around; }
.stat { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.stat-num { font-size: 40rpx; font-weight: 800; color: var(--c-ink); }
.stat-lbl { font-size: 22rpx; color: var(--c-text-hint); }
</style>

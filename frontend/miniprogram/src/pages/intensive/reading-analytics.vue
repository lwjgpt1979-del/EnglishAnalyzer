<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">阅读学情</text>
      <text class="hd-sub">近一段时间的作业阅读汇总,找出真薄弱,针对性补。</text>
    </view>

    <!-- 时间窗切换 -->
    <view class="seg">
      <text v-for="w in windows" :key="w.days" class="seg-i" :class="{ on: days === w.days }"
            @tap="switchWin(w.days)">{{ w.label }}</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!data || !data.papers" class="tip">这段时间还没有阅读作业。</view>

    <template v-else>
      <!-- 诊断 -->
      <view class="diag">
        <view class="ic-stethoscope diag-ic"></view>
        <text class="diag-t">{{ data.diagnosis }}</text>
      </view>
      <text class="meta">近 {{ data.papers }} 卷</text>

      <!-- 高频薄弱考纲词 -->
      <view v-if="data.weak_words.length" class="card">
        <view class="card-hd">
          <text class="card-t">高频薄弱考纲词</text>
          <text class="card-cta" @tap="go('/pages/vocabulary/index')">去词力通补 ›</text>
        </view>
        <view class="chips">
          <text v-for="(w, i) in data.weak_words" :key="i" class="chip chip-v">{{ w.word }}<text class="chip-x"> {{ w.tag }} · {{ w.papers }}卷</text></text>
        </view>
      </view>

      <!-- 反复卡的句法结构 -->
      <view v-if="data.weak_structures.length" class="card">
        <view class="card-hd">
          <text class="card-t">反复卡的句法结构</text>
          <text class="card-cta" @tap="go('/pages/intensive/sentence')">去长难句 ›</text>
        </view>
        <view class="chips">
          <text v-for="(s, i) in data.weak_structures" :key="i" class="chip chip-s">{{ s.name }} · 卡 {{ s.count }}</text>
        </view>
      </view>

      <!-- 各题型正确率(进度即底色;弱项标红) -->
      <view v-if="data.skills.length" class="card">
        <view class="card-hd"><text class="card-t">各题型正确率</text></view>
        <view v-for="(s, i) in data.skills" :key="i" class="rate-row">
          <view class="rate-fill" :class="rateCls(s)" :style="{ width: s.rate + '%' }"></view>
          <text class="rate-sk">{{ s.skill }}</text>
          <text class="rate-n" :class="rateTxt(s)">{{ s.total - s.wrong }}/{{ s.total }} · {{ s.rate }}%</text>
        </view>
        <text v-if="!data.weak_skills.length" class="rate-hint">暂无低于阈值的弱题型(或样本不足)。</text>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getReadingAnalytics, type ReadingAnalytics, type ReadingAnalyticsSkill } from '@/api/userPapers'

const windows = [{ days: 14, label: '近2周' }, { days: 30, label: '近1月' }, { days: 0, label: '全部' }]
const days = ref(14)
const loading = ref(true)
const data = ref<ReadingAnalytics | null>(null)

const weakSet = () => new Set((data.value?.weak_skills || []).map(s => s.skill))
function rateCls(s: ReadingAnalyticsSkill): string { return weakSet().has(s.skill) ? 'rf-weak' : s.rate >= 80 ? 'rf-good' : 'rf-mid' }
function rateTxt(s: ReadingAnalyticsSkill): string { return weakSet().has(s.skill) ? 'rt-weak' : s.rate >= 80 ? 'rt-good' : 'rt-mid' }

function go(url: string) { uni.navigateTo({ url }) }

async function load() {
  loading.value = true
  try { data.value = await getReadingAnalytics(days.value) }
  catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
function switchWin(d: number) { if (d === days.value) return; days.value = d; load() }

onLoad(load)
</script>

<style scoped>
.page { min-height: 100vh; background: #f4f6fa; padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 16rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: #1f2733; display: block; }
.hd-sub { font-size: 24rpx; color: #93a0b3; margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: #93a0b3; padding: 60rpx 0; }

.seg { display: flex; gap: 10rpx; background: #e8edf4; border-radius: 16rpx; padding: 6rpx; margin-bottom: 18rpx; }
.seg-i { flex: 1; text-align: center; font-size: 26rpx; color: #6b7688; padding: 14rpx 0; border-radius: 12rpx; }
.seg-i.on { color: #3d8bf5; font-weight: 700; background: #fff; box-shadow: 0 3rpx 10rpx rgba(45, 80, 150, .12); }

.diag { display: flex; align-items: flex-start; gap: 12rpx; background: #eef4ff; border-radius: 16rpx; padding: 18rpx 20rpx; }
.diag-ic { width: 34rpx; height: 34rpx; flex: none; margin-top: 2rpx; background-size: contain; background-repeat: no-repeat; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='22 12 18 12 15 21 9 3 6 12 2 12'/%3E%3C/svg%3E"); }
.diag-t { flex: 1; font-size: 26rpx; font-weight: 600; color: #2f74d6; line-height: 1.6; }
.meta { display: block; font-size: 22rpx; color: #93a0b3; margin: 12rpx 4rpx; }

.card { background: #fff; border: 2rpx solid #e6ebf2; border-radius: 18rpx; padding: 20rpx 22rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 18rpx rgba(45, 80, 150, .05); }
.card-hd { display: flex; align-items: center; margin-bottom: 14rpx; }
.card-t { font-size: 28rpx; font-weight: 800; color: #1f2733; }
.card-cta { margin-left: auto; font-size: 23rpx; font-weight: 600; color: #3d8bf5; }

.chips { display: flex; flex-wrap: wrap; gap: 10rpx; }
.chip { font-size: 23rpx; font-weight: 600; border-radius: 8rpx; padding: 6rpx 14rpx; }
.chip-v { color: #c0662a; background: #fdf1e7; }
.chip-x { font-size: 19rpx; color: #d89a6a; }
.chip-s { color: #7057c0; background: #f2eefb; }

.rate-row { position: relative; overflow: hidden; display: flex; align-items: center; gap: 12rpx; background: #f6f8fb; border-radius: 12rpx; padding: 14rpx 16rpx; margin-bottom: 10rpx; }
.rate-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; transition: width .3s; }
.rf-good { background: linear-gradient(90deg, #e9f6f1, #f4fbf8); }
.rf-mid { background: linear-gradient(90deg, #e8f2ff, #f4f9ff); }
.rf-weak { background: linear-gradient(90deg, #fdecec, #fef5f5); }
.rate-sk { position: relative; font-size: 25rpx; font-weight: 700; color: #2b3546; }
.rate-n { position: relative; margin-left: auto; font-size: 23rpx; font-weight: 700; }
.rt-good { color: #2fa98a; }
.rt-mid { color: #3d8bf5; }
.rt-weak { color: #dc4c4c; }
.rate-hint { display: block; font-size: 21rpx; color: #93a0b3; margin-top: 6rpx; }
</style>

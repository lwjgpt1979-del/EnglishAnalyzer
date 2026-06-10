<template>
  <view class="page">
    <!-- 顶部筛选 -->
    <view class="filter-bar">
      <picker :range="VERSIONS" :value="vIdx" @change="vIdx = +($event as any).detail.value; load()">
        <view class="chip" :class="vIdx >= 0 ? 'chip-active' : ''">
          {{ vIdx >= 0 ? VERSIONS[vIdx] : '教材版本' }} ▾
        </view>
      </picker>
      <picker :range="GRADES" :value="gIdx" @change="gIdx = +($event as any).detail.value; load()">
        <view class="chip" :class="gIdx >= 0 ? 'chip-active' : ''">
          {{ gIdx >= 0 ? GRADES[gIdx] : '年级' }} ▾
        </view>
      </picker>
      <picker :range="SEMS" :value="sIdx" @change="sIdx = +($event as any).detail.value; load()">
        <view class="chip" :class="sIdx >= 0 ? 'chip-active' : ''">
          {{ sIdx >= 0 ? SEMS[sIdx] + '学期' : '学期' }} ▾
        </view>
      </picker>
      <view class="chip chip-ghost" @tap="resetFilter">重置</view>
    </view>

    <!-- 统计概览 -->
    <view v-if="filtered.length" class="overview-row">
      <view class="ov-item">
        <text class="ov-num">{{ filtered.length }}</text>
        <text class="ov-label">单元</text>
      </view>
      <view class="ov-item">
        <text class="ov-num">{{ totalKp }}</text>
        <text class="ov-label">知识点</text>
      </view>
      <view class="ov-item">
        <text class="ov-num">{{ avgRate }}%</text>
        <text class="ov-label">内容完成率</text>
      </view>
    </view>

    <!-- 单元列表 -->
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!filtered.length" class="empty">
      {{ allUnits.length ? '暂无符合条件的单元' : '暂无课程内容，请上传教材 PDF' }}
    </view>
    <view v-else class="unit-list">
      <view v-for="u in filtered" :key="u.unit_id" class="unit-card">
        <view class="unit-meta">
          <text class="unit-badge">{{ u.textbook_version }} · {{ u.grade }} · {{ u.semester }}学期</text>
        </view>
        <view class="unit-title">Unit {{ u.unit_no }}  {{ u.unit_title }}</view>
        <view class="unit-stats">
          <text class="stat-item">🧠 {{ u.kp_count }} 知识点</text>
          <view class="rate-bar-wrap">
            <view class="rate-bar" :style="{ width: rateWidth(u.content_rate) }"></view>
          </view>
          <text class="rate-txt">{{ ratePct(u.content_rate) }}</text>
        </view>
      </view>
    </view>

    <!-- 底部操作区 -->
    <view class="fab-area">
      <view class="fab-btn fab-secondary" @tap="goGenerateSemester">🤖 AI 生成学期</view>
      <view class="fab-btn fab-primary" @tap="goUploadPdf">📄 上传教材 PDF</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { listCurriculumUnits, type CurriculumUnitStat } from '@/api/adminCurriculum'

const VERSIONS = ['译林版', '人教版', '外研版', '北师大版']
const GRADES   = ['小学5年级', '小学6年级', '七年级', '八年级', '九年级']
const SEMS     = ['上', '下']

const loading  = ref(true)
const allUnits = ref<CurriculumUnitStat[]>([])
const vIdx     = ref(-1)
const gIdx     = ref(-1)
const sIdx     = ref(-1)

const filtered = computed(() => {
  return allUnits.value.filter(u => {
    if (vIdx.value >= 0 && u.textbook_version !== VERSIONS[vIdx.value]) return false
    if (gIdx.value >= 0 && u.grade !== GRADES[gIdx.value]) return false
    if (sIdx.value >= 0 && u.semester !== SEMS[sIdx.value]) return false
    return true
  })
})

const totalKp  = computed(() => filtered.value.reduce((s, u) => s + u.kp_count, 0))
const avgRate  = computed(() => {
  if (!filtered.value.length) return '0'
  const avg = filtered.value.reduce((s, u) => s + u.content_rate, 0) / filtered.value.length
  return (avg * 100).toFixed(0)
})

function rateWidth(r: number) { return `${Math.max(4, r * 100).toFixed(0)}%` }
function ratePct(r: number)   { return `${(r * 100).toFixed(0)}%` }

async function load() {
  loading.value = true
  try { allUnits.value = await listCurriculumUnits() } catch { /* ignore */ }
  finally { loading.value = false }
}

function resetFilter() { vIdx.value = -1; gIdx.value = -1; sIdx.value = -1 }

function goUploadPdf() {
  uni.navigateTo({ url: '/pages/admin/pdf-upload' })
}

function goGenerateSemester() {
  // 从当前筛选条件预填参数
  const v = vIdx.value >= 0 ? VERSIONS[vIdx.value] : '译林版'
  const g = gIdx.value >= 0 ? GRADES[gIdx.value]   : '小学5年级'
  const s = sIdx.value >= 0 ? SEMS[sIdx.value]     : '上'
  uni.navigateTo({ url: `/pages/admin/pdf-upload?mode=direct&v=${encodeURIComponent(v)}&g=${encodeURIComponent(g)}&s=${s}` })
}

onShow(load)
</script>

<style scoped>
.page { padding: 24rpx; padding-bottom: 160rpx; background: var(--c-bg-page); min-height: 100vh; }

/* 筛选栏 */
.filter-bar { display: flex; flex-wrap: wrap; gap: 12rpx; margin-bottom: 20rpx; }
.chip {
  padding: 10rpx 20rpx; border-radius: 32rpx;
  font-size: 24rpx; color: var(--c-text-body);
  background: var(--c-bg-card); border: 1rpx solid var(--c-border);
}
.chip-active { background: var(--c-primary); border-color: var(--c-primary); font-weight: 600; }
.chip-ghost  { color: var(--c-text-hint); }

/* 概览 */
.overview-row { display: flex; gap: 0; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 20rpx 0; margin-bottom: 20rpx; }
.ov-item { flex: 1; display: flex; flex-direction: column; align-items: center; }
.ov-num  { font-size: 40rpx; font-weight: 800; color: var(--c-primary); }
.ov-label{ font-size: 22rpx; color: var(--c-text-hint); margin-top: 4rpx; }

/* 单元列表 */
.unit-list { display: flex; flex-direction: column; gap: 16rpx; }
.unit-card {
  background: var(--c-bg-card); border-radius: var(--r-lg);
  padding: 24rpx; border: 1rpx solid var(--c-border);
}
.unit-meta  { margin-bottom: 8rpx; }
.unit-badge { font-size: 20rpx; color: var(--c-text-hint); background: var(--c-bg-page); padding: 4rpx 10rpx; border-radius: 8rpx; }
.unit-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 14rpx; }
.unit-stats { display: flex; align-items: center; gap: 12rpx; }
.stat-item  { font-size: 22rpx; color: var(--c-text-second); white-space: nowrap; }
.rate-bar-wrap { flex: 1; height: 8rpx; background: var(--c-border); border-radius: 4rpx; overflow: hidden; }
.rate-bar  { height: 100%; background: var(--c-primary); border-radius: 4rpx; transition: width 0.3s; }
.rate-txt  { font-size: 22rpx; color: var(--c-text-second); white-space: nowrap; }

/* empty */
.empty { text-align: center; color: var(--c-text-hint); font-size: 28rpx; padding: 80rpx 0; }

/* 底部浮动按钮 */
.fab-area {
  position: fixed; bottom: 0; left: 0; right: 0;
  display: flex; gap: 20rpx; padding: 20rpx 32rpx 40rpx;
  background: var(--c-bg-card); border-top: 1rpx solid var(--c-border);
}
.fab-btn { flex: 1; text-align: center; padding: 20rpx 0; border-radius: var(--r-btn); font-size: 28rpx; font-weight: 700; }
.fab-primary   { background: var(--c-primary); color: var(--c-on-primary); }
.fab-secondary { background: var(--c-bg-page); color: var(--c-ink); border: 1rpx solid var(--c-border); }
</style>

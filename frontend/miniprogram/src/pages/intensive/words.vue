<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 单词</text>
      <text class="hd-sub">{{ groupOpen ? groupTitle : (mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元') }}</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>

    <!-- 一级:批次 / 单元 -->
    <template v-else-if="!groupOpen">
      <view v-if="!groups.length" class="tip">{{ mode === 'homework' ? '还没有加入待学习的单词——去上传的试卷里挑生词加入' : '未设教材或该教材暂无单元词' }}</view>
      <template v-for="sec in sections" :key="sec.key">
        <text v-if="sec.header" class="sec-h">{{ sec.header }}</text>
        <view v-for="g in sec.items" :key="g.id" class="card grp" @tap="openGroup(g)">
          <view class="grp-main">
            <text class="grp-title">{{ g.title }}</text>
            <text class="grp-sub">{{ g.sub }}</text>
          </view>
          <text class="grp-cnt">{{ g.count }} 词 ›</text>
        </view>
      </template>
    </template>

    <!-- 二级:词表 -->
    <template v-else>
      <view class="back" @tap="groupOpen = null"><text>‹ 返回{{ mode === 'homework' ? '批次' : '单元' }}</text></view>
      <view v-if="!wordsLoading && words.length" class="start-btn" @tap="startStudy">
        <text>▶ 开始学习(配图·发音·例句·检测)</text>
      </view>
      <view v-if="wordsLoading" class="tip">加载中…</view>
      <view v-else-if="!words.length" class="tip">该{{ mode === 'homework' ? '批次' : '单元' }}没有单词</view>
      <text v-else class="list-hint">共 {{ words.length }} 词 · 下方为词表预览,点上方按钮进入卡片学习</text>
      <view v-for="w in words" :key="w.word_id" class="card word">
        <view class="word-top">
          <text class="word-w">{{ w.word }}</text>
          <text v-if="w.phonetic" class="word-ph">/{{ w.phonetic }}/</text>
        </view>
        <text class="word-def">{{ defText(w.definitions) }}</text>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getHwWordBatches, getHwWords, getCourseWordUnits, getCourseWords,
         type IntensiveWord, type HwWordBatch, type CourseWordUnit } from '@/api/vocabulary'

const mode = ref('homework')
const loading = ref(true)
const groups = ref<any[]>([])          // {id, title, sub, count}
const groupOpen = ref<any>(null)
const groupTitle = computed(() => groupOpen.value?.title || '')
const words = ref<IntensiveWord[]>([])
const wordsLoading = ref(false)
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))

// 课程侧按「年级 学期」分节;作业侧不分节
const sections = computed(() => {
  if (mode.value === 'homework') return [{ key: 'all', header: '', items: groups.value }]
  const map: Record<string, any[]> = {}
  for (const g of groups.value) {
    const k = g.header || ''
    ;(map[k] = map[k] || []).push(g)
  }
  return Object.keys(map).map(k => ({ key: k, header: k, items: map[k] }))
})

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

async function openGroup(g: any) {
  groupOpen.value = g
  wordsLoading.value = true
  words.value = []
  try {
    words.value = mode.value === 'homework'
      ? (await getHwWords(g.id)).words
      : (await getCourseWords(g.id)).words
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { wordsLoading.value = false }
}

// 进入完整词力通学习流(限定在该单元/批次词范围)
function startStudy() {
  const g = groupOpen.value
  if (!g) return
  const src = mode.value === 'homework' ? 'homework' : 'course'
  const key = mode.value === 'homework' ? 'paper_id' : 'unit_id'
  uni.navigateTo({ url: `/pages/vocabulary/index?source=${src}&${key}=${g.id}` })
}

async function load() {
  loading.value = true
  try {
    if (mode.value === 'homework') {
      const bs: HwWordBatch[] = (await getHwWordBatches()).batches
      groups.value = bs.map(b => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.word_count }))
    } else {
      const r = await getCourseWordUnits()
      groups.value = (r.units as CourseWordUnit[]).map(u => ({
        id: u.unit_id, title: `${u.unit_title}`, sub: `第${u.unit_no}单元`, count: u.word_count,
        header: `${u.grade} ${u.semester}册`,
      }))
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => { mode.value = q.mode || 'homework'; load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 16rpx; }
.hd-title { font-size: 38rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 23rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
.sec-h { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-text-second); margin: 18rpx 6rpx 10rpx; }
.card { background: #fff; border-radius: 18rpx; padding: 24rpx; margin-bottom: 16rpx; }
.grp { display: flex; align-items: center; gap: 14rpx; }
.grp-main { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.grp-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.grp-sub { font-size: 22rpx; color: var(--c-text-hint); }
.grp-cnt { font-size: 24rpx; color: var(--c-primary); flex-shrink: 0; }
.back { padding: 8rpx 4rpx 16rpx; font-size: 26rpx; color: var(--c-primary); }
.start-btn { background: var(--c-primary); color: #fff; text-align: center; padding: 24rpx; border-radius: 16rpx; font-size: 30rpx; font-weight: 600; margin-bottom: 16rpx; }
.list-hint { display: block; color: var(--c-text-hint, #999); font-size: 24rpx; margin-bottom: 12rpx; }
.word-top { display: flex; align-items: baseline; gap: 16rpx; }
.word-w { font-size: 32rpx; font-weight: 700; color: var(--c-ink); }
.word-ph { font-size: 24rpx; color: var(--c-text-hint); }
.word-def { display: block; font-size: 26rpx; color: var(--c-text-sub); margin-top: 8rpx; line-height: 1.6; }
</style>

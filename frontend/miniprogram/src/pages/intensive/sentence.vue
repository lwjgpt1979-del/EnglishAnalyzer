<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 长难句</text>
      <text class="hd-sub">{{ groupOpen ? groupOpen.title : (mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元') }}</text>
    </view>
    <view v-if="loading" class="tip">加载中…</view>

    <template v-else-if="!groupOpen">
      <view v-if="!groups.length" class="tip">{{ mode === 'homework' ? '还没有加入待学习的长难句——去试卷「加入待学习」' : '未设教材或该教材暂无长难句' }}</view>
      <IntensiveBatchList v-else-if="mode === 'homework'" :batches="hwItems" unit="句" @open="openById" />
      <template v-else>
        <template v-for="sec in sections" :key="sec.key">
          <text v-if="sec.header" class="sec-h">{{ sec.header }}</text>
          <view v-for="g in sec.items" :key="g.id" class="card grp" @tap="openGroup(g)">
            <view class="grp-main"><text class="grp-title">{{ g.title }}</text><text class="grp-sub">{{ g.sub }}</text></view>
            <text class="grp-cnt">{{ g.count }} 句 ›</text>
          </view>
        </template>
      </template>
    </template>

    <template v-else>
      <view class="back" @tap="groupOpen = null"><text>‹ 返回{{ mode === 'homework' ? '批次' : '单元' }}</text></view>
      <view v-if="itemsLoading" class="tip">加载中…</view>
      <view v-else-if="!sentences.length" class="tip">该{{ mode === 'homework' ? '批次' : '单元' }}没有长难句</view>
      <view v-for="(s, i) in sentences" :key="i" class="card se" @tap="goAnalyze(s.text)">
        <text class="se-text">{{ s.text }}</text>
        <text class="se-go">解析 ›</text>
      </view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { seHwBatches, seHwSentences, seCourseUnits, seCourseSentences,
         type SentenceItem, type IntensiveBatch, type IntensiveUnit } from '@/api/curriculum'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'

const mode = ref('homework')
const loading = ref(true)
const groups = ref<any[]>([])
const groupOpen = ref<any>(null)
const hwItems = computed<BatchItem[]>(() => groups.value.map(g => ({
  id: g.id, title: g.title, date: g.sub, count: g.count, studied: g.studied,
})))
function openById(id: string) { const g = groups.value.find(x => x.id === id); if (g) openGroup(g) }
const sentences = ref<SentenceItem[]>([])
const itemsLoading = ref(false)
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))

const sections = computed(() => {
  if (mode.value === 'homework') return [{ key: 'all', header: '', items: groups.value }]
  const map: Record<string, any[]> = {}
  for (const g of groups.value) { const k = g.header || ''; (map[k] = map[k] || []).push(g) }
  return Object.keys(map).map(k => ({ key: k, header: k, items: map[k] }))
})

async function openGroup(g: any) {
  groupOpen.value = g; itemsLoading.value = true; sentences.value = []
  try {
    sentences.value = mode.value === 'homework' ? (await seHwSentences(g.id)).sentences : (await seCourseSentences(g.id)).sentences
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { itemsLoading.value = false }
}
function goAnalyze(text: string) {
  // 作业模式带上批次卷号,学习页里加入的语法/单词才能归到同一作业批次
  const pid = mode.value === 'homework' && groupOpen.value ? `&paperId=${groupOpen.value.id}` : ''
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(text)}${pid}` })
}
async function load() {
  loading.value = true
  try {
    if (mode.value === 'homework') {
      groups.value = (await seHwBatches()).batches.map((b: IntensiveBatch) => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.count }))
    } else {
      groups.value = ((await seCourseUnits()).units as IntensiveUnit[]).map(u => ({
        id: u.unit_id, title: u.unit_title, sub: `第${u.unit_no}单元`, count: u.count, header: `${u.grade} ${u.semester}册` }))
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
.se { }
.se-text { font-size: 27rpx; line-height: 1.6; color: var(--c-ink); }
.se-go { display: block; text-align: right; font-size: 23rpx; color: var(--c-primary); margin-top: 8rpx; }
</style>

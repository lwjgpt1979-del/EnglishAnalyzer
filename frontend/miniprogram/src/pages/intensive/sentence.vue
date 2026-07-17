<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 长难句</text>
      <text class="hd-sub">{{ groupOpen ? groupOpen.title : (mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元') }}</text>
    </view>
    <view v-if="loading" class="tip">加载中…</view>

    <template v-else-if="!groupOpen">
      <template v-if="mode === 'homework'">
        <view v-if="!groups.length" class="tip">还没有加入待学习的长难句——去试卷「加入待学习」</view>
        <IntensiveBatchList v-else :batches="hwItems" unit="句" @open="openById" />
      </template>
      <UnitLevelMap v-else :units="courseUnits" unit="句" :title="semLabel" :next-hint="nextHint" @open="openCourseUnit" />
    </template>

    <template v-else>
      <view class="back" @tap="groupOpen = null"><text>‹ 返回{{ mode === 'homework' ? '批次' : '单元' }}</text></view>
      <view v-if="itemsLoading" class="tip">加载中…</view>
      <!-- 卷学习页(卷头进度即底色 + 待学清单);点句进逐句解析(看过即算学过),作业/课程同一套 -->
      <PaperChecklist v-else :items="sentences" :date="groupOpen && groupOpen.sub" unit="句"
          @open="(s) => goAnalyze(s.text)" @start="(i) => goAnalyze(sentences[i] && sentences[i].text)">
        <template #item="{ item }"><text class="se-text">{{ item.text }}</text></template>
        <template #empty>该{{ mode === 'homework' ? '批次' : '单元' }}没有长难句</template>
      </PaperChecklist>
    </template>

    <!-- 学完当前学期:庆祝弹层 -->
    <SemesterDoneModal :visible="showDone" :semester-label="semLabel" unit-label="长难句"
      :unit-total="courseUnits.length" :content-total="courseSeTotal" :next-semester="nextSemester"
      @quiz="onSemesterQuiz" @preview="onPreviewNext" @review="showDone = false" @close="showDone = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import PaperChecklist from '@/components/PaperChecklist.vue'
import { seHwBatches, seHwSentences, seCourseUnits, seCourseSentences,
         type SentenceItem, type IntensiveBatch, type IntensiveUnit } from '@/api/curriculum'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'
import UnitLevelMap from '@/components/UnitLevelMap.vue'
import SemesterDoneModal from '@/components/SemesterDoneModal.vue'

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

// 课程精讲·闯关地图 + 学完庆祝弹层
const courseUnits = ref<IntensiveUnit[]>([])
const courseGrade = ref<string | undefined>(undefined)
const courseSem = ref<string | undefined>(undefined)
const semLabel = ref('课程')
const nextSemester = ref<{ grade: string; semester: string } | null>(null)
const showDone = ref(false)
const courseSeTotal = computed(() => courseUnits.value.reduce((a, u) => a + (u.count || 0), 0))
const nextHint = computed(() => nextSemester.value
  ? `闯完本册接入 ${nextSemester.value.grade}${nextSemester.value.semester}册` : '')
function openCourseUnit(unitId: string) {
  const u = courseUnits.value.find(x => x.unit_id === unitId)
  if (u) openGroup({ id: u.unit_id, title: u.unit_title, sub: `第${u.unit_no}单元`, count: u.count })
}
function onPreviewNext() {
  if (!nextSemester.value) return
  courseGrade.value = nextSemester.value.grade
  courseSem.value = nextSemester.value.semester
  showDone.value = false
  load()
}
function onSemesterQuiz() { uni.showToast({ title: '学期测验即将上线', icon: 'none' }) }

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
      groups.value = (await seHwBatches()).batches.map((b: IntensiveBatch) => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.count, studied: b.studied }))
    } else {
      const r = await seCourseUnits(courseGrade.value, courseSem.value)
      courseUnits.value = r.units
      semLabel.value = r.grade && r.semester ? `${r.grade}${r.semester}册` : '课程'
      nextSemester.value = r.next_semester
      showDone.value = r.semester_done
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
onLoad((q: any) => { mode.value = q.mode || 'homework'; load() })
// 从逐句解析返回 → 刷新进度与打勾(跳过 onLoad 后首次)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load(); if (groupOpen.value) openGroup(groupOpen.value) })
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

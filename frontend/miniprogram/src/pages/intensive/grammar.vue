<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 语法精讲</text>
      <text class="hd-sub">{{ groupOpen ? groupOpen.title : (mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元') }}</text>
    </view>
    <view v-if="loading" class="tip">加载中…</view>

    <template v-else-if="!groupOpen">
      <view v-if="!groups.length" class="tip">{{ mode === 'homework' ? '还没有加入待学习的语法点——去试卷「加入学习计划」' : '未设教材或该教材暂无语法点' }}</view>
      <IntensiveBatchList v-else-if="mode === 'homework'" :batches="hwItems" unit="点" @open="openById" />
      <template v-else>
        <template v-for="sec in sections" :key="sec.key">
          <text v-if="sec.header" class="sec-h">{{ sec.header }}</text>
          <view v-for="g in sec.items" :key="g.id" class="card grp" @tap="openGroup(g)">
            <view class="grp-main"><text class="grp-title">{{ g.title }}</text><text class="grp-sub">{{ g.sub }}</text></view>
            <text class="grp-cnt">{{ g.count }} 点 ›</text>
          </view>
        </template>
      </template>
    </template>

    <template v-else>
      <view class="back" @tap="groupOpen = null"><text>‹ 返回{{ mode === 'homework' ? '批次' : '单元' }}</text></view>
      <view v-if="itemsLoading" class="tip">加载中…</view>
      <view v-else-if="!points.length" class="tip">该{{ mode === 'homework' ? '批次' : '单元' }}没有语法点</view>
      <view v-for="(p, pi) in points" :key="p.node_id || p.sgn_id || pi" class="card pt" @tap="goLearn(p)">
        <view class="pt-main">
          <text class="pt-name">{{ p.name }}</text>
          <text v-if="p.personal" class="pt-tag">自建</text>
        </view>
        <text class="pt-go">{{ p.personal ? '练习 ›' : '看讲解 ›' }}</text>
      </view>
    </template>

    <!-- 个人语法点(未入图谱):AI 讲解(缓存)+ 按语法名出题练习 -->
    <view v-if="practiceOpen" class="modal" @tap.self="practiceOpen = false">
      <view class="modal-card">
        <text class="modal-title">{{ practiceKp }}<text class="modal-tag">自建语法</text></text>
        <scroll-view scroll-y class="modal-body">
          <!-- 讲解 -->
          <view v-if="lectureLoading" class="tip">AI 讲解生成中…</view>
          <view v-for="s in lectureSections" :key="s.section_key" class="lec">
            <text class="lec-title">{{ s.title }}</text>
            <rich-text :nodes="md2html(s.content_md)" class="lec-md" />
          </view>
          <!-- 练习:逐题作答判分统一走 PracticeQuiz -->
          <view class="prac-hd">
            <text class="prac-t">练一练</text>
          </view>
          <view class="prac-start" :class="{ busy: practiceLoading }" @tap="startPractice">
            <text>{{ practiceLoading ? '出题中…' : '开始练习（5 题）' }}</text>
          </view>
        </scroll-view>
        <view class="modal-close" @tap="practiceOpen = false"><text>关闭</text></view>
      </view>
    </view>

    <!-- 练习作答(与我的错题练同类同一套组件) -->
    <PracticeQuiz
      v-if="quizOpen"
      :kp="practiceKp"
      :questions="quizQuestions"
      :judge="quizJudge"
      @close="quizOpen = false"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { grHwBatches, grHwPoints, grCourseUnits, grCoursePoints,
         type GrammarPoint, type IntensiveBatch, type IntensiveUnit } from '@/api/curriculum'
import { generateQuestions, submitAnswer } from '@/api/practice'
import { namedGrammarLecture, type GrammarLectureSection } from '@/api/curriculum'
import PracticeQuiz, { type ChosenAnswer } from '@/components/PracticeQuiz.vue'
import type { PracticeQuestion } from '@/api/wrongQuestions'
import { md2html } from '@/utils/md'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'

const mode = ref('homework')
const loading = ref(true)
const groups = ref<any[]>([])
const groupOpen = ref<any>(null)
const hwItems = computed<BatchItem[]>(() => groups.value.map(g => ({
  id: g.id, title: g.title, date: g.sub, count: g.count, studied: g.studied,
})))
function openById(id: string) { const g = groups.value.find(x => x.id === id); if (g) openGroup(g) }
const points = ref<GrammarPoint[]>([])
const itemsLoading = ref(false)
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))

const sections = computed(() => {
  if (mode.value === 'homework') return [{ key: 'all', header: '', items: groups.value }]
  const map: Record<string, any[]> = {}
  for (const g of groups.value) { const k = g.header || ''; (map[k] = map[k] || []).push(g) }
  return Object.keys(map).map(k => ({ key: k, header: k, items: map[k] }))
})

async function openGroup(g: any) {
  groupOpen.value = g; itemsLoading.value = true; points.value = []
  try {
    points.value = mode.value === 'homework' ? (await grHwPoints(g.id)).points : (await grCoursePoints(g.id)).points
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { itemsLoading.value = false }
}
const practiceOpen = ref(false)
const practiceLoading = ref(false)
const practiceKp = ref('')
const lectureLoading = ref(false)
const lectureSections = ref<GrammarLectureSection[]>([])
async function goLearn(p: GrammarPoint) {
  if (p.personal || !p.node_id) {   // 个人语法(未入图谱)→ AI 讲解(缓存)+ 按名出题
    practiceKp.value = p.name; quizQuestions.value = []; lectureSections.value = []
    practiceOpen.value = true; lectureLoading.value = true
    try { lectureSections.value = (await namedGrammarLecture(p.name)).sections }
    catch { /* 讲解失败静默 */ }
    finally { lectureLoading.value = false }
    return
  }
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${p.node_id}&name=${encodeURIComponent(p.name)}&cat=grammar` })
}
// 练一练 → 生成题 → PracticeQuiz(服务端判分,题不含答案)
const quizOpen = ref(false)
const quizQuestions = ref<PracticeQuestion[]>([])
async function startPractice() {
  if (practiceLoading.value) return
  practiceLoading.value = true
  try {
    const qs = await generateQuestions(practiceKp.value, 5, 3)
    if (!qs.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    quizQuestions.value = qs.map(q => ({ id: q.id, stem: q.stem, options: q.options, answer: null, explanation: null }))
    quizOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '出题失败', icon: 'none' }) }
  finally { practiceLoading.value = false }
}
async function quizJudge(q: PracticeQuestion, ans: ChosenAnswer) {
  const r = await submitAnswer(q.id, ans.letter || ans.input)   // 语法练习为单选,用字母
  return { correct: r.is_correct, correct_answer: r.correct_answer, explanation: r.explanation }
}
async function load() {
  loading.value = true
  try {
    if (mode.value === 'homework') {
      groups.value = (await grHwBatches()).batches.map((b: IntensiveBatch) => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.count, studied: b.studied }))
    } else {
      groups.value = ((await grCourseUnits()).units as IntensiveUnit[]).map(u => ({
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
.pt { display: flex; align-items: center; justify-content: space-between; }
.pt-main { display: flex; align-items: center; gap: 10rpx; flex: 1; min-width: 0; }
.pt-name { font-size: 28rpx; color: var(--c-ink); }
.pt-tag { flex-shrink: 0; font-size: 19rpx; color: #ff8a3d; border: 2rpx solid #ffd8bd; border-radius: 6rpx; padding: 1rpx 8rpx; }
.pt-go { font-size: 23rpx; color: var(--c-primary); flex-shrink: 0; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 40rpx; }
.modal-card { width: 100%; max-width: 640rpx; max-height: 80vh; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-tag { font-size: 19rpx; color: #ff8a3d; border: 2rpx solid #ffd8bd; border-radius: 6rpx; padding: 1rpx 8rpx; margin-left: 10rpx; font-weight: 400; }
.modal-body { flex: 1; margin: 16rpx 0; }
.lec { padding: 8rpx 0 16rpx; }
.lec-title { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-primary); margin-bottom: 8rpx; }
.lec-md { font-size: 25rpx; line-height: 1.7; color: var(--c-ink); }
.prac-hd { display: flex; align-items: center; justify-content: space-between; border-top: 2rpx solid var(--c-line, #eef1f5); padding-top: 14rpx; margin-top: 6rpx; }
.prac-t { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.prac-btn { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.prac-start { margin-top: 14rpx; text-align: center; background: var(--c-primary); color: #fff; font-size: 27rpx; font-weight: 700; border-radius: 999rpx; padding: 16rpx; }
.prac-start.busy { opacity: .6; }
.sq { padding: 14rpx 0; border-top: 2rpx solid var(--c-line, #eef1f5); }
.sq:first-child { border-top: none; }
.sq-stem { display: block; font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.sq-opts { display: flex; flex-direction: column; gap: 4rpx; margin-top: 8rpx; }
.sq-opt { font-size: 24rpx; color: var(--c-text-sub); }
.modal-close { text-align: center; font-size: 26rpx; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 14rpx; }
</style>

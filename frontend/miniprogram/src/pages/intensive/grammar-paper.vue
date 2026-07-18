<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <!-- 卷学习页(卷头进度即底色 + 待学清单);点点看讲解/练习(学过即算),作业/课程同一套 -->
    <PaperChecklist v-else :items="points" :date="sub" unit="点" flat
        @open="(p) => goLearn(p)" @start="(i) => goLearn(points[i])">
      <template #item="{ item }">
        <view class="pt-main"><text class="pt-name">{{ item.name }}</text><text v-if="item.personal" class="pt-tag">自建</text></view>
        <!-- 四维掌握度:识别/纠错/产出(0–1 填充)+ 迁移(满/空);未学=空条 -->
        <view class="mst">
          <text class="mst-cap">掌握</text>
          <view class="mst-bars">
            <view v-for="(seg, i) in masteryBars(item)" :key="i" class="mst-seg">
              <view class="mst-fill" :class="seg.cls" :style="{ width: seg.w }"></view>
            </view>
          </view>
          <text class="mst-word" :class="masteryStatus(item).cls">{{ masteryStatus(item).label }}</text>
        </view>
      </template>
      <template #empty>该{{ mode === 'homework' ? '批次' : '单元' }}没有语法点</template>
    </PaperChecklist>

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
import { ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import PaperChecklist from '@/components/PaperChecklist.vue'
import { grHwPoints, grCoursePoints, namedGrammarLecture,
         type GrammarPoint, type GrammarLectureSection } from '@/api/curriculum'
import { generateQuestions, submitAnswer } from '@/api/practice'
import PracticeQuiz, { type ChosenAnswer } from '@/components/PracticeQuiz.vue'
import type { PracticeQuestion } from '@/api/wrongQuestions'
import { md2html } from '@/utils/md'

const mode = ref('homework')
const groupId = ref('')
const sub = ref('')
const points = ref<GrammarPoint[]>([])
const loading = ref(true)

// 四维掌握度条:识别/纠错/产出(0–1 填充,≥.85 转绿)+ 迁移(满/空);未学=空条
const DIM_KEYS = ['recognize', 'detect', 'produce'] as const
function masteryBars(p: GrammarPoint): { w: string; cls: string }[] {
  const m = p.mastery
  const segs = DIM_KEYS.map((k) => {
    const v = m ? Number((m as any)[k] || 0) : 0
    const cv = Math.min(1, Math.max(0, v))
    return { w: Math.round(cv * 100) + '%', cls: v >= 0.85 ? 'ok' : (v > 0 ? 'on' : '') }
  })
  segs.push({ w: m && m.transfer ? '100%' : '0%', cls: m && m.transfer ? 'ok' : '' })
  return segs
}
function masteryStatus(p: GrammarPoint): { label: string; cls: string } {
  const m = p.mastery
  if (!m) return { label: '未学', cls: 'st-todo' }
  const done = m.recognize >= 0.85 && m.detect >= 0.85 && m.produce >= 0.85 && m.transfer
  return done ? { label: '已掌握', cls: 'st-done' } : { label: '学习中', cls: 'st-doing' }
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
  points.value = []
  try {
    points.value = mode.value === 'homework'
      ? (await grHwPoints(groupId.value)).points
      : (await grCoursePoints(groupId.value)).points
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => {
  mode.value = q.mode || 'homework'
  groupId.value = q.id || ''
  sub.value = q.sub ? decodeURIComponent(q.sub) : ''
  if (q.title) uni.setNavigationBarTitle({ title: decodeURIComponent(q.title) })
  load()
})
// 从讲解/练习返回 → 刷新进度与打勾(跳过 onLoad 后首次)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
.pt-main { display: flex; align-items: center; gap: 10rpx; flex: 1; min-width: 0; }
.pt-name { font-size: 28rpx; color: var(--c-ink); }
.pt-tag { flex-shrink: 0; font-size: 19rpx; color: #ff8a3d; border: 2rpx solid #ffd8bd; border-radius: 6rpx; padding: 1rpx 8rpx; }
/* 四维掌握度条(识别/纠错/产出/迁移) */
.mst { display: flex; align-items: center; gap: 12rpx; margin-top: 12rpx; }
.mst-cap { font-size: 19rpx; color: #94a3b8; flex: none; }
.mst-bars { display: flex; gap: 6rpx; flex: none; }
.mst-seg { width: 52rpx; height: 10rpx; border-radius: 5rpx; background: #e6ebf2; overflow: hidden; }
.mst-fill { height: 100%; width: 0; border-radius: 5rpx; background: #3d8bf5; transition: width .3s; }
.mst-fill.ok { background: #2fa98a; }
.mst-word { font-size: 19rpx; flex: none; }
.mst-word.st-todo { color: #b7c2d4; }
.mst-word.st-doing { color: #3d8bf5; }
.mst-word.st-done { color: #2fa98a; }
.modal { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 40rpx; }
.modal-card { width: 100%; max-width: 640rpx; max-height: 80vh; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-tag { font-size: 19rpx; color: #ff8a3d; border: 2rpx solid #ffd8bd; border-radius: 6rpx; padding: 1rpx 8rpx; margin-left: 10rpx; font-weight: 400; }
.modal-body { flex: 1; margin: 16rpx 0; }
.lec { padding: 8rpx 0 16rpx; }
.lec-title { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-primary); margin-bottom: 8rpx; }
.lec-md { font-size: 25rpx; line-height: 1.7; color: var(--c-ink); }
.prac-hd { display: flex; align-items: center; justify-content: space-between; border-top: 2rpx solid var(--c-line, #eef1f5); padding-top: 14rpx; margin-top: 6rpx; }
.prac-t { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.prac-start { margin-top: 14rpx; text-align: center; background: var(--c-primary); color: #fff; font-size: 27rpx; font-weight: 700; border-radius: 999rpx; padding: 16rpx; }
.prac-start.busy { opacity: .6; }
.modal-close { text-align: center; font-size: 26rpx; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 14rpx; }
</style>

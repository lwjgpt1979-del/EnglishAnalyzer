<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <!-- 卷学习页(卷头进度即底色 + 待学清单);点点看讲解/练习(学过即算),作业/课程同一套 -->
    <PaperChecklist v-else :items="points" :date="sub" unit="点" flat
        @open="(p) => goLearn(p)" @start="(i) => goLearn(points[i])">
      <template #item="{ item }">
        <view class="pt-main"><text class="pt-name">{{ item.name }}</text><text v-if="item.personal" class="pt-tag">自建</text></view>
        <!-- 图谱语法点:四维掌握度(识别/纠错/产出 0–1 + 迁移满/空);未学=空条 -->
        <view v-if="!item.personal" class="mst">
          <text class="mst-cap">掌握</text>
          <view class="mst-bars">
            <view v-for="(seg, i) in masteryBars(item)" :key="i" class="mst-seg">
              <view class="mst-fill" :class="seg.cls" :style="{ width: seg.w }"></view>
            </view>
          </view>
          <text class="mst-word" :class="masteryStatus(item).cls">{{ masteryStatus(item).label }}</text>
        </view>
        <!-- 自建语法:无图谱四维,用「练一练」痕迹反馈 -->
        <view v-else class="mst">
          <text class="mst-cap">练习</text>
          <text class="mst-word" :class="item.practice ? 'st-doing' : 'st-todo'">{{ item.practice ? item.practice.correct + ' / ' + item.practice.total + ' 正确' : '未练习' }}</text>
        </view>
      </template>
      <template #empty>该{{ mode === 'homework' ? '批次' : '单元' }}没有语法点</template>
    </PaperChecklist>

    <!-- 个人语法点(未入图谱):AI 讲解(缓存)+ 按语法名出题练习 -->
    <view v-if="practiceOpen" class="modal" @tap="practiceOpen = false">
      <view class="modal-card" @tap.stop>
        <text class="modal-title">{{ practiceKp }}<text class="modal-tag">自建语法</text></text>
        <scroll-view scroll-y class="modal-body">
          <!-- 讲解:折叠手风琴(图标 header + 展开正文),按 section 映射图标/配色 -->
          <view v-if="lectureLoading" class="tip">AI 讲解生成中…</view>
          <view v-for="(s, i) in lectureSections" :key="s.section_key" class="acc">
            <view class="acc-hd" :class="'acc-' + secMeta(s.section_key).kind" @tap="toggle(i)">
              <view class="ic acc-ic" :class="secMeta(s.section_key).icon"></view>
              <text class="acc-title">{{ s.title }}</text>
              <view class="ic acc-chev" :class="openSet.has(i) ? 'ic-chevron-up' : 'ic-chevron-down'"></view>
            </view>
            <view v-if="openSet.has(i)" class="acc-body">
              <rich-text :nodes="md2html(s.content_md)" class="lec-md" />
            </view>
          </view>
        </scroll-view>
        <!-- 开始练习:主按钮(关闭走底部次级) -->
        <view class="prac-start" :class="{ busy: practiceLoading }" @tap="startPractice">
          <text>{{ practiceLoading ? '出题中…' : '开始练习 · 5 题' }}</text>
        </view>
        <view class="modal-close" @tap="practiceOpen = false"><text>关闭</text></view>
      </view>
    </view>

    <!-- 练习作答(与我的错题练同类同一套组件) -->
    <PracticeQuiz
      v-if="quizOpen"
      :kp="practiceKp"
      :questions="quizQuestions"
      :judge="quizJudge"
      :recorder="quizRecorder"
      @close="onQuizClose"
    />
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import PaperChecklist from '@/components/PaperChecklist.vue'
import { grHwPoints, grCoursePoints, namedGrammarLecture, markPersonalGrammarPracticed,
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
const practiceSgnId = ref('')   // 当前练习的自建语法节点 id(做完标记已学 + 记成绩)
const lectureLoading = ref(false)
const lectureSections = ref<GrammarLectureSection[]>([])
// 讲解手风琴:按 section_key 映射图标/配色(idea 一句话搞懂 / examples 看例句 / pitfall 别踩坑),未知走默认
const SEC_META: Record<string, { icon: string; kind: string }> = {
  idea: { icon: 'ic-idea', kind: 'idea' },
  examples: { icon: 'ic-quote', kind: 'examples' },
  pitfall: { icon: 'ic-warning', kind: 'pitfall' },
}
function secMeta(k: string) { return SEC_META[k] || { icon: 'ic-idea', kind: 'idea' } }
const openSet = ref<Set<number>>(new Set())
function toggle(i: number) {
  const s = new Set(openSet.value)
  s.has(i) ? s.delete(i) : s.add(i)
  openSet.value = s
}
async function goLearn(p: GrammarPoint) {
  if (p.personal || !p.node_id) {   // 个人语法(未入图谱)→ AI 讲解(缓存)+ 按名出题
    practiceKp.value = p.name; practiceSgnId.value = p.sgn_id || ''
    quizQuestions.value = []; lectureSections.value = []
    openSet.value = new Set()
    practiceOpen.value = true; lectureLoading.value = true
    try {
      lectureSections.value = (await namedGrammarLecture(p.name)).sections
      openSet.value = new Set(lectureSections.value.length ? [0] : [])   // 默认展开第一段
    }
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
  const r = await submitAnswer(q.id, ans.text || ans.input)   // 后端按「选项完整文本」判分(见 practice_service),传文本非字母
  return { correct: r.is_correct, correct_answer: r.correct_answer, explanation: r.explanation }
}
// 自建语法练完:标记该节点已学 + 记最近成绩(无图谱 node、无四维)
async function quizRecorder(total: number, correct: number): Promise<string> {
  if (practiceSgnId.value) {
    try { await markPersonalGrammarPracticed(practiceSgnId.value, correct, total) } catch { /* 静默,不阻断结算 */ }
  }
  return `本轮 ${correct}/${total} 正确`
}
function onQuizClose() { quizOpen.value = false; load() }   // 关练习 → 重载 points,反映已学/练习分

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
.modal-card { width: 100%; max-width: 640rpx; max-height: 84vh; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; display: flex; flex-direction: column; overflow: hidden; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); flex: none; }
.modal-tag { font-size: 19rpx; color: #ff8a3d; border: 2rpx solid #ffd8bd; border-radius: 6rpx; padding: 1rpx 8rpx; margin-left: 10rpx; font-weight: 400; }
/* scroll-view 在 mp-weixin 需明确 max-height 才滚动;上限内滚,底部按钮常驻卡内 */
.modal-body { flex: 1; min-height: 0; max-height: 56vh; margin: 16rpx 0; }
.lec-md { font-size: 25rpx; line-height: 1.7; color: var(--c-ink); }
/* 讲解手风琴:图标 header(按 section 染色)+ 展开正文 */
.acc { border: 2rpx solid #e3e8f0; border-radius: 14rpx; overflow: hidden; margin-bottom: 14rpx; }
.acc-hd { display: flex; align-items: center; gap: 12rpx; padding: 18rpx 18rpx; }
.acc-idea { background: #f3f8fe; }
.acc-examples { background: #f1faf5; }
.acc-pitfall { background: #fdf6ef; }
.acc-ic { width: 30rpx; height: 30rpx; flex: none; }
.acc-title { flex: 1; min-width: 0; font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.acc-idea .acc-title { color: #2f74d6; }
.acc-examples .acc-title { color: #1a9059; }
.acc-pitfall .acc-title { color: #c06a2a; }
.acc-chev { width: 28rpx; height: 28rpx; flex: none; }
.acc-body { padding: 16rpx 18rpx 20rpx; }
.acc-body .lec-md { display: block; }
.prac-start { margin-top: 4rpx; text-align: center; background: linear-gradient(135deg, #4c97f7, #3d7bf0); color: #fff; font-size: 28rpx; font-weight: 700; border-radius: 16rpx; padding: 22rpx 0; box-shadow: 0 6rpx 16rpx rgba(61,123,240,.28); }
.prac-start.busy { opacity: .6; }
.modal-close { text-align: center; font-size: 26rpx; color: #93a0b3; padding: 18rpx 0 6rpx; margin-top: 4rpx; }
</style>

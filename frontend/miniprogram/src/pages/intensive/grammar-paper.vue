<template>
  <view class="page" :class="{ 'page-detail': mode === 'homework' && hwView === 'detail' }">
    <view v-if="loading" class="tip">加载中…</view>

    <!-- 课程模式:卷清单 → 跳讲解页 -->
    <PaperChecklist v-else-if="mode === 'course'" :items="points" :date="sub" unit="点" flat
        @open="(p) => goCourse(p)" @start="(i) => goCourse(points[i])">
      <template #item="{ item }">
        <view class="pt-main"><text class="pt-name">{{ item.name }}</text></view>
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
      <template #empty>该单元没有语法点</template>
    </PaperChecklist>

    <view v-else-if="!points.length" class="tip">该批次没有语法点</view>

    <!-- 作业 A·清单为家:默认本卷清单 -->
    <PaperChecklist
      v-else-if="hwView === 'list'"
      :items="points" :date="sub" unit="题" flat
      @open="onListOpen" @start="openDetail"
    >
      <template #item="{ item }">
        <view class="qrow">
          <view class="qrow-meta">
            <text v-if="item.question?.is_wrong" class="badge bad">错</text>
            <text v-else-if="item.question" class="badge ok">对</text>
            <text class="badge kp">{{ listTypeLabel(item) }}</text>
            <text v-if="item.question?.question_no" class="badge kp">第 {{ item.question.question_no }} 题</text>
          </view>
          <text class="qrow-stem">{{ stemBrief(item.question?.stem) || item.name || '—' }}</text>
          <text v-if="item.name" class="qrow-kp">{{ item.name }}</text>
        </view>
      </template>
      <template #empty>该批次没有语法点</template>
    </PaperChecklist>

    <!-- 作业详情:原题→解释→本题巩固→关系网 + 上下题 -->
    <view v-else class="d1">
      <view class="d1-top">
        <view class="list-btn" @tap="backToList"><text>清单</text></view>
        <text class="qswitch-lab">本题 {{ qi + 1 }}/{{ points.length }}</text>
        <view class="dots">
          <view
            v-for="(p, i) in points" :key="itemKey(p, i)"
            class="dot" :class="{ on: i === qi, done: !!p.studied && i !== qi }"
            @tap="switchQ(i)"
          />
        </view>
      </view>

      <view class="card" :class="{ bad: curQ?.is_wrong }">
        <view v-if="curQ" class="row">
          <text v-if="curQ.is_wrong" class="badge bad">错</text>
          <text v-else class="badge ok">对</text>
          <text class="badge kp">{{ typeLabel }}</text>
          <text class="qno">第 {{ curQ.question_no || '—' }} 题</text>
        </view>
        <text v-if="curQ" class="stem">{{ curQ.stem }}</text>
        <view v-if="curQ?.options?.length" class="opts">
          <view
            v-for="(opt, i) in curQ.options" :key="i"
            class="opt"
            :class="optCls(opt, i)"
          >
            <text class="lab">{{ letter(i) }}</text>
            <text class="ot">{{ stripOpt(opt) }}{{ optHint(opt, i) }}</text>
          </view>
        </view>
        <view v-if="curQ" class="ansline">
          <text class="x" :class="{ ok: !curQ.is_wrong }">{{ ansYouLabel }} {{ curQ.student_answer || '—' }}</text>
          <text class="o">正确 {{ curQ.correct_answer || '—' }}</text>
        </view>
        <view v-if="!curQ" class="tip soft">暂无原题详情</view>
      </view>

      <view class="explain">
        <view class="row tags"><text class="badge kp">{{ cur?.name || '语法点' }}</text></view>
        <text v-if="explainLoading" class="tip soft">解析生成中…</text>
        <text v-else-if="explainBody" class="body">{{ explainBody }}</text>
        <text v-else class="tip soft">暂无解析</text>
      </view>

      <view class="drill" :class="{ busy: practiceLoading }" @tap="startPractice">
        <view class="drill-main">
          <text class="drill-t">本题巩固</text>
          <text class="drill-d">围绕「{{ cur?.name }}」练同类单选</text>
        </view>
        <text class="drill-go">{{ practiceLoading ? '…' : '›' }}</text>
      </view>

      <WrongRelationNet
        v-if="wrnId"
        :wrong-record-id="wrnId"
      />
      <WrongRelationNet
        v-else-if="wrnSeedCorrect.length"
        :seed-correct="wrnSeedCorrect"
        :seed-wrong="wrnSeedWrong"
        :seed-other="wrnSeedOther"
      />

      <view class="foot">
        <view class="btn ghost" :class="{ dis: qi <= 0 }" @tap="prevQ"><text>‹ 上一题</text></view>
        <view class="btn pri" @tap="nextQ"><text>{{ qi < points.length - 1 ? '下一题 ›' : '回清单' }}</text></view>
      </view>
    </view>

    <PracticeQuiz
      v-if="quizOpen"
      :kp="cur?.name || ''"
      :questions="quizQuestions"
      :judge="quizJudge"
      :recorder="quizRecorder"
      :continue-label="qi < points.length - 1 ? '下一题 ›' : '回清单'"
      @continue="onQuizContinue"
      @close="onQuizClose"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { onLoad, onShow, onBackPress } from '@dcloudio/uni-app'
import PaperChecklist from '@/components/PaperChecklist.vue'
import WrongRelationNet from '@/components/WrongRelationNet.vue'
import {
  grHwPoints, grCoursePoints, markPersonalGrammarPracticed, ensureGrammarExplanation,
  type GrammarPoint, type GrammarSourceQuestion,
} from '@/api/curriculum'
import { generateQuestions, submitAnswer } from '@/api/practice'
import PracticeQuiz, { type ChosenAnswer } from '@/components/PracticeQuiz.vue'
import type { PracticeQuestion } from '@/api/wrongQuestions'

const mode = ref('homework')
const groupId = ref('')
const sub = ref('')
const pageTitle = ref('语法精讲')
const points = ref<GrammarPoint[]>([])
const loading = ref(true)

/** 作业:list=本卷清单(默认) · detail=本题详情 */
const hwView = ref<'list' | 'detail'>('list')
const qi = ref(0)
const cur = computed(() => points.value[qi.value] || null)
const curQ = computed<GrammarSourceQuestion | null>(() => cur.value?.question || null)
const wrnId = computed(() => curQ.value?.wrong_record_id || '')

/**
 * 无错题记录时(全对):用正确答案词作关系网种子;字母答案先还原成选项文本
 */
function resolveAnsText(raw: string | null | undefined): string {
  const ans = (raw || '').trim()
  if (!ans) return ''
  const opts = curQ.value?.options || []
  if (opts.length && /^[A-Da-d]$/.test(ans)) {
    const i = ans.toUpperCase().charCodeAt(0) - 65
    if (i >= 0 && i < opts.length) return stripOpt(opts[i])
  }
  for (let i = 0; i < opts.length; i++) {
    if (ans === opts[i] || ans === stripOpt(opts[i])) return stripOpt(opts[i])
  }
  return ans
}
/**
 * 关系网种子须为「完整英文单词/词组」——拒纯数字(35)、纯符号、过长句。
 * 每段至少含一个英文字母;最多 4 词、总长 ≤40。
 */
function isSeedable(t: string): boolean {
  if (!t || t.length > 40) return false
  const parts = t.trim().split(/\s+/).filter(Boolean)
  if (!parts.length || parts.length > 4) return false
  return parts.every((p) => /[a-zA-Z]/.test(p))
}

/**
 * 本题是否适合出关系网:有选项则全部选项须是词/词组;填空则正确项须是。
 * 数字题(19/35/54…)整题不出网,避免「35≈however」胡说。
 */
const wrnSeedsAllowed = computed(() => {
  if (wrnId.value) return false
  const opts = curQ.value?.options || []
  if (opts.length) return opts.every((o) => isSeedable(stripOpt(o)))
  return isSeedable(resolveAnsText(curQ.value?.correct_answer))
})
const wrnSeedCorrect = computed(() => {
  if (!wrnSeedsAllowed.value) return [] as string[]
  const t = resolveAnsText(curQ.value?.correct_answer)
  return isSeedable(t) ? [t] : []
})
const wrnSeedWrong = computed(() => {
  if (!wrnSeedsAllowed.value || !curQ.value?.is_wrong) return [] as string[]
  const t = resolveAnsText(curQ.value?.student_answer)
  return isSeedable(t) ? [t] : []
})
/** 其余选项(灰 chip):单选干扰项,排除正确与学生错选 */
const wrnSeedOther = computed(() => {
  if (!wrnSeedsAllowed.value) return [] as string[]
  const opts = curQ.value?.options || []
  if (!opts.length) return [] as string[]
  const ca = (wrnSeedCorrect.value[0] || '').toLowerCase()
  const wr = (wrnSeedWrong.value[0] || '').toLowerCase()
  const out: string[] = []
  const seen = new Set<string>()
  for (const o of opts) {
    const t = stripOpt(o)
    if (!isSeedable(t)) continue
    const k = t.toLowerCase()
    if (k === ca || k === wr || seen.has(k)) continue
    seen.add(k)
    out.push(t)
  }
  return out
})

const hasOpts = computed(() => !!(curQ.value?.options && curQ.value.options.length))
const typeLabel = computed(() => {
  const t = (curQ.value?.question_type || '').trim()
  if (t) return t
  return hasOpts.value ? '单选' : '填空'
})
const ansYouLabel = computed(() => (hasOpts.value ? '你选' : '你填'))
const explainLoading = ref(false)
/** 详情页展示用解析(本地态,避免嵌套字段不刷新) */
const explainText = ref('')
const explainBody = computed(() => (explainText.value || curQ.value?.explanation || '').trim())

function listTypeLabel(item: GrammarPoint) {
  const q = item.question
  const t = (q?.question_type || '').trim()
  if (t) return t
  if (q?.options?.length) return '单选'
  return q ? '填空' : '语法点'
}

/**
 * 无解析时查看即生成——全对(填空/单选/多空)与答错同等
 */
async function ensureExplain() {
  if (hwView.value !== 'detail') return
  const q = curQ.value
  const p = cur.value
  if (!q?.id) return
  const existing = (q.explanation || explainText.value || '').trim()
  if (existing) {
    explainText.value = existing
    return
  }
  if (explainLoading.value) return
  explainLoading.value = true
  try {
    const r = await ensureGrammarExplanation(q.id, p?.name)
    const text = (r?.explanation || '').trim()
    if (text) {
      explainText.value = text
      // 写回列表数据,回清单再进仍有
      const idx = qi.value
      const pt = points.value[idx]
      if (pt?.question?.id === q.id) {
        points.value[idx] = {
          ...pt,
          question: { ...pt.question, explanation: text },
        }
      }
    }
  } catch (e: any) {
    uni.showToast({ title: e?.message || '解析生成失败', icon: 'none' })
  } finally { explainLoading.value = false }
}

watch([qi, hwView], () => {
  explainText.value = (curQ.value?.explanation || '').trim()
  ensureExplain()
}, { flush: 'post' })

function itemKey(p: GrammarPoint, i: number) {
  return p.source_question_id || p.sgn_id || p.node_id || `i${i}`
}
function stemBrief(s: string | null | undefined) {
  const t = (s || '').trim().replace(/\s+/g, ' ')
  return t.length > 36 ? t.slice(0, 36) + '…' : t
}
function letter(i: number) {
  return String.fromCharCode(65 + i)
}
function stripOpt(opt: string) {
  return String(opt || '').replace(/^[A-Da-d][.、)．]\s*/, '').trim()
}
function isCorrectOpt(opt: string, i: number): boolean {
  const ans = (curQ.value?.correct_answer || '').trim()
  if (!ans) return false
  if (ans === opt || ans === stripOpt(opt)) return true
  return ans.toUpperCase() === letter(i)
}
function isStudentOpt(opt: string, i: number): boolean {
  const stu = (curQ.value?.student_answer || '').trim()
  if (!stu) return false
  if (stu === opt || stu === stripOpt(opt)) return true
  return stu.toUpperCase() === letter(i)
}
function optCls(opt: string, i: number) {
  if (isCorrectOpt(opt, i)) return 'ok'
  if (isStudentOpt(opt, i) && curQ.value?.is_wrong) return 'bad'
  return ''
}
function optHint(opt: string, i: number) {
  if (isCorrectOpt(opt, i)) return '　正确'
  if (isStudentOpt(opt, i) && curQ.value?.is_wrong) return '　你选'
  return ''
}

/** PaperChecklist @open(item, index) */
function onListOpen(_item: GrammarPoint, index: number) {
  openDetail(typeof index === 'number' ? index : points.value.indexOf(_item))
}

/**
 * 进入详情(CTA / 点行)
 */
function openDetail(index: number) {
  const i = index >= 0 ? index : 0
  qi.value = Math.min(i, Math.max(0, points.value.length - 1))
  quizOpen.value = false
  quizQuestions.value = []
  explainText.value = (points.value[qi.value]?.question?.explanation || '').trim()
  hwView.value = 'detail'
  uni.setNavigationBarTitle({ title: '本题详情' })
  // 进详情立刻兜底(全对/单选/填空同等)
  ensureExplain()
}

/**
 * 回本卷清单
 */
async function backToList() {
  hwView.value = 'list'
  quizOpen.value = false
  quizQuestions.value = []
  uni.setNavigationBarTitle({ title: pageTitle.value })
  await load()
}

function switchQ(i: number) {
  if (i === qi.value) return
  qi.value = i
  quizOpen.value = false
  quizQuestions.value = []
}
function prevQ() {
  if (qi.value <= 0) return
  switchQ(qi.value - 1)
}
function nextQ() {
  if (qi.value < points.value.length - 1) {
    switchQ(qi.value + 1)
  } else {
    uni.showToast({ title: '本卷已学完', icon: 'success' })
    backToList()
  }
}

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

function goCourse(p: GrammarPoint) {
  if (!p.node_id) return
  uni.navigateTo({
    url: `/pages/curriculum/kp-content?id=${p.node_id}&name=${encodeURIComponent(p.name)}&cat=grammar`,
  })
}

const practiceLoading = ref(false)
const quizOpen = ref(false)
const quizQuestions = ref<PracticeQuestion[]>([])

async function startPractice() {
  const p = cur.value
  if (!p || practiceLoading.value) return
  practiceLoading.value = true
  try {
    const qs = await generateQuestions(p.name, 5, 3)
    if (!qs.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    quizQuestions.value = qs.map(q => ({
      id: q.id, stem: q.stem, options: q.options, answer: null, explanation: null,
    }))
    quizOpen.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '出题失败', icon: 'none' })
  } finally { practiceLoading.value = false }
}

async function quizJudge(q: PracticeQuestion, ans: ChosenAnswer) {
  const r = await submitAnswer(q.id, ans.text || ans.input)
  return { correct: r.is_correct, correct_answer: r.correct_answer, explanation: r.explanation }
}

async function quizRecorder(total: number, correct: number): Promise<string> {
  const p = cur.value
  if (p?.personal && p.sgn_id) {
    try { await markPersonalGrammarPracticed(p.sgn_id, correct, total) } catch { /* 静默 */ }
  }
  return `本轮 ${correct}/${total} 正确 · 已计入本题练习`
}

function onQuizClose() {
  quizOpen.value = false
  load()
}

function onQuizContinue() {
  quizOpen.value = false
  if (qi.value < points.value.length - 1) {
    qi.value += 1
    quizQuestions.value = []
    load()
  } else {
    uni.showToast({ title: '本卷已学完', icon: 'success' })
    backToList()
  }
}

async function load() {
  loading.value = true
  try {
    points.value = mode.value === 'homework'
      ? (await grHwPoints(groupId.value)).points
      : (await grCoursePoints(groupId.value)).points
    if (qi.value >= points.value.length) qi.value = Math.max(0, points.value.length - 1)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally { loading.value = false }
}

onLoad((q: any) => {
  mode.value = q.mode || 'homework'
  groupId.value = q.id || ''
  sub.value = q.sub ? decodeURIComponent(q.sub) : ''
  pageTitle.value = q.title ? decodeURIComponent(q.title) : '语法精讲'
  uni.setNavigationBarTitle({ title: pageTitle.value })
  hwView.value = 'list'
  load()
})

/** 详情态系统返回键 → 先回清单 */
onBackPress(() => {
  if (mode.value === 'homework' && hwView.value === 'detail') {
    backToList()
    return true
  }
  return false
})

let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load() })
</script>

<style scoped>
.page { min-height: 100vh; background: #f0f6fc; padding: 24rpx; box-sizing: border-box; }
.page-detail { padding-bottom: 160rpx; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
.tip.soft { padding: 28rpx 8rpx; font-size: 24rpx; }
.pt-main { display: flex; align-items: center; gap: 10rpx; flex: 1; min-width: 0; }
.pt-name { font-size: 28rpx; color: var(--c-ink); }
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

.qrow { min-width: 0; }
.qrow-meta { display: flex; flex-wrap: wrap; gap: 8rpx; margin-bottom: 8rpx; }
.qrow-stem {
  display: block; font-size: 26rpx; font-weight: 650; color: var(--c-ink);
  line-height: 1.4; overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.qrow-kp { display: block; font-size: 20rpx; color: #94a3b8; margin-top: 6rpx; }

.d1-top {
  display: flex; align-items: center; gap: 12rpx; margin-bottom: 16rpx; flex-wrap: wrap;
}
.list-btn {
  font-size: 22rpx; font-weight: 700; color: #185fa5;
  background: #eaf2ff; border: 2rpx solid #bcd8ff;
  padding: 8rpx 18rpx; border-radius: 999rpx; flex: none;
}
.qswitch-lab { font-size: 24rpx; font-weight: 800; color: var(--c-ink); }
.dots { display: flex; gap: 12rpx; flex-wrap: wrap; }
.dot { width: 16rpx; height: 16rpx; border-radius: 50%; background: #c5d4e8; }
.dot.on { width: 36rpx; border-radius: 8rpx; background: var(--c-primary, #3d8bf5); }
.dot.done { background: #2fa98a; }

.card {
  background: #fff; border: 2rpx solid #d5e4f5; border-radius: 24rpx;
  padding: 24rpx; margin-bottom: 16rpx;
}
.card.bad { background: #f7f3e6; border-color: #e0d6b8; }
.row { display: flex; align-items: center; gap: 12rpx; flex-wrap: wrap; }
.tags { margin-bottom: 12rpx; }
.qno { font-size: 24rpx; font-weight: 700; color: #64748b; }
.badge { font-size: 20rpx; font-weight: 700; padding: 2rpx 12rpx; border-radius: 8rpx; }
.badge.bad { background: #f0e8d4; color: #b54a3a; }
.badge.ok { background: #e9f6f1; color: #2fa98a; }
.badge.kp { background: #e8f2ff; color: var(--c-primary, #3d8bf5); }
.stem { display: block; font-size: 28rpx; font-weight: 650; line-height: 1.55; margin: 14rpx 0; color: var(--c-ink); }
.opts { margin-top: 4rpx; }
.opt {
  display: flex; gap: 12rpx; align-items: flex-start; padding: 14rpx 18rpx; margin-top: 10rpx;
  border-radius: 16rpx; background: #eef4fb; font-size: 26rpx; line-height: 1.45;
}
.opt.ok { background: #e9f6f1; border: 2rpx solid #b7e0cf; }
.opt.bad { background: #fdeeee; border: 2rpx solid #f3c7c7; }
.opt .lab { font-weight: 800; color: #64748b; min-width: 28rpx; }
.opt.ok .lab { color: #2fa98a; }
.opt.bad .lab { color: #e35d5d; }
.opt .ot { flex: 1; color: var(--c-ink); }
.ansline {
  margin-top: 14rpx; font-size: 24rpx; line-height: 1.55;
  display: flex; flex-wrap: wrap; gap: 20rpx;
}
.ansline .x { color: #e35d5d; font-weight: 700; }
.ansline .x.ok { color: #2fa98a; }
.ansline .o { color: #2fa98a; font-weight: 700; }

.explain {
  background: #fff; border: 2rpx solid #d5e4f5; border-radius: 24rpx;
  padding: 24rpx; margin-bottom: 16rpx;
}
.explain .body { display: block; font-size: 28rpx; line-height: 1.65; color: var(--c-ink); }

.drill {
  display: flex; align-items: center; gap: 16rpx;
  border-radius: 20rpx; padding: 22rpx 24rpx; margin-bottom: 16rpx;
  border: 3rpx solid #bcd8ff; background: #eaf2ff;
}
.drill.busy { opacity: .65; }
.drill-t { display: block; font-size: 28rpx; font-weight: 800; color: #185fa5; }
.drill-d { display: block; font-size: 22rpx; color: #64748b; margin-top: 4rpx; }
.drill-go { margin-left: auto; color: #185fa5; font-weight: 800; font-size: 32rpx; }

.foot {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 10;
  display: flex; gap: 16rpx; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff; border-top: 2rpx solid #d5e4f5;
}
.btn {
  flex: 1; text-align: center; font-size: 26rpx; font-weight: 700; color: var(--c-primary, #3d8bf5);
  border: 2rpx solid #c5daf5; background: #eaf2ff; border-radius: 16rpx; padding: 22rpx 0;
}
.btn.pri { color: #fff; background: linear-gradient(135deg, #4c97f7, #3d7bf0); border: none; }
.btn.ghost { background: #fff; color: #64748b; border-color: #e6ebf2; }
.btn.dis { opacity: .4; }
</style>

<template>
  <view class="page">
    <view v-if="loadingList" class="tip">加载题目…</view>
    <view v-else-if="!questions.length" class="empty">
      <view class="ic ic-edit empty-ic" />
      <text>题库暂无可练的书面表达题。</text>
    </view>

    <template v-else>
      <view class="qmeta">第 {{ qIdx + 1 }} / {{ questions.length }} 题<text v-if="curQ.genre" class="genre">{{ curQ.genre }}</text></view>

      <!-- 题目(全程可见) -->
      <view class="card">
        <view class="stem"><text>{{ curQ.stem }}</text></view>
      </view>

      <!-- ── S0 审题小测(前置强制门:先想清楚再动笔)── -->
      <view v-if="stage === 'quiz'" class="card">
        <view class="box-head"><view class="ic ic-target head-ic" /><text class="box-title">审题小测 · 答对才能开写</text></view>
        <view class="tip">先判断这道题的体裁、主时态和要点条数——审题是提分第一步。</view>

        <view class="quiz-q">
          <text class="quiz-label">1. 本题体裁?</text>
          <view class="opts">
            <text v-for="g in GENRES" :key="g" class="opt" :class="optClass('genre', g)" @tap="pick('genre', g)">{{ g }}</text>
          </view>
        </view>
        <view class="quiz-q">
          <text class="quiz-label">2. 主要时态?</text>
          <view class="opts">
            <text v-for="t in TENSES" :key="t" class="opt" :class="optClass('tense', t)" @tap="pick('tense', t)">{{ t }}</text>
          </view>
        </view>
        <view class="quiz-q">
          <text class="quiz-label">3. 必写要点有几条?</text>
          <view class="opts">
            <text v-for="n in [2,3,4,5]" :key="n" class="opt" :class="optClass('count', n)" @tap="pick('count', n)">{{ n }} 条</text>
          </view>
        </view>

        <view v-if="quizChecked && !quizPass" class="quiz-fail">
          <view class="ic ic-x-circle qf-ic" /><text>还有判断不对(标红项),对照题目再想想,改完重新提交。</text>
        </view>
        <button class="btn-primary" :disabled="!quizComplete" @tap="checkQuiz">
          {{ quizChecked && !quizPass ? '重新提交' : '提交审题,开始写作' }}
        </button>
      </view>

      <!-- ── 写作阶段(审题过关后解锁)── -->
      <template v-else>
        <!-- 要点清单(客观锚) -->
        <view class="card">
          <view class="box-head"><view class="ic ic-target head-ic" /><text class="box-title">必写要点({{ curQ.points.length }})· 一条都别漏</text></view>
          <view class="points-box">
            <view v-for="(p, i) in curQ.points" :key="i" class="point-line"><text class="dot">{{ i + 1 }}</text><text>{{ p.point }}</text></view>
          </view>
        </view>

        <!-- S1 结构脚手架 -->
        <view v-if="curQ.structure.length" class="card scaffold">
          <view class="box-head tap" @tap="showScaffold = !showScaffold">
            <view class="ic ic-book head-ic" />
            <text class="box-title">结构套路{{ curQ.strategy ? '：' + curQ.strategy : '' }}</text>
            <view class="ic ic-arrow-right head-ic flip" :class="{ open: showScaffold }" />
          </view>
          <view v-if="showScaffold" class="scaffold-body">
            <view v-for="(b, i) in curQ.structure" :key="i" class="scaf-block">
              <text class="scaf-role">{{ b.role || ('第' + (i + 1) + '段') }}</text>
              <text class="scaf-guide">{{ b.guide }}</text>
            </view>
          </view>
        </view>

        <!-- S2 写作 -->
        <view class="card">
          <view class="box-head"><view class="ic ic-pen head-ic" /><text class="box-title">我的作文</text><text class="wc">{{ wordCount }} 词</text></view>
          <textarea v-model="essay" class="ta" :maxlength="-1" :disabled="graded"
            placeholder="用英文写出你的短文,尽量覆盖全部要点、套用上面的结构与句式…" auto-height />
          <button class="btn-primary" :disabled="(!graded && !essay.trim()) || loading"
            @tap="graded ? nextQ() : submit()">
            {{ loading ? 'AI 批改中…' : (graded ? (qIdx < questions.length - 1 ? '下一题' : '再来一组') : '提交批改') }}
          </button>
        </view>

        <!-- S3 诊断 -->
        <view v-if="result" class="card result">
          <view class="score-line">
            <view class="band" :class="'band-' + bandKey">{{ result.band || 'C' }}</view>
            <text class="score-num">{{ result.total }}</text><text class="score-full"> / {{ result.full }}</text>
            <text v-if="result.is_ai_graded" class="ai-tag">AI 评分 · 供参考</text>
          </view>

          <view class="dim">
            <text class="dim-title">① 内容 · 要点覆盖 {{ result.content_score }}/{{ result.content_full }}</text>
            <view v-for="(p, i) in result.points" :key="i" class="pt">
              <view class="ic pt-ic" :class="p.hit ? 'ic-check-circle' : 'ic-x-circle'" />
              <view class="pt-body">
                <text class="pt-name" :class="{ miss: !p.hit }">{{ p.point }}</text>
                <text v-if="p.comment" class="pt-comment">{{ p.comment }}</text>
              </view>
            </view>
          </view>

          <view class="dim">
            <text class="dim-title">② 语言准确 {{ result.accuracy.score }}/{{ result.accuracy.full }}</text>
            <view v-if="!result.accuracy.errors.length" class="ok-line">未发现明显语法错误</view>
            <view v-for="(e, i) in result.accuracy.errors" :key="i" class="err">
              <text class="err-span">{{ e.span }}</text>
              <text class="err-type">{{ e.type }}</text>
              <text class="err-fix">→ {{ e.fix }}</text>
            </view>
          </view>

          <view class="dim">
            <text class="dim-title">③ 语言丰富 {{ result.richness.score }}/{{ result.richness.full }}</text>
            <view class="tags">
              <text v-if="!result.richness.used_targets.length" class="tag tag-warn">未用高级句型</text>
              <text v-for="(t, i) in result.richness.used_targets" :key="i" class="tag tag-ok">{{ t }}</text>
            </view>
            <view v-for="(s, i) in result.richness.suggestions" :key="'s' + i" class="upgrade">
              <view class="ic ic-trend-up up-ic" /><text>{{ s }}</text>
            </view>
          </view>

          <view class="dim">
            <text class="dim-title">④ 结构连贯 {{ result.organization.score }}/{{ result.organization.full }}</text>
            <text class="dim-body">{{ result.organization.comment }}</text>
          </view>

          <view class="fb"><text>{{ result.feedback }}</text></view>

          <!-- ── 错因定向微练:把批改抓到的错句改对 ── -->
          <view v-if="result.accuracy.errors.length" class="drill">
            <view class="box-head"><view class="ic ic-edit head-ic" /><text class="box-title">订正微练 · 把错句改对({{ result.accuracy.errors.length }})</text></view>
            <view v-for="(e, i) in result.accuracy.errors" :key="i" class="drill-item">
              <view class="drill-q"><text class="err-type">{{ e.type }}</text><text class="drill-span">{{ e.span }}</text></view>
              <input v-model="drillInputs[i]" class="drill-input" placeholder="在这里写出正确的说法" />
              <view class="drill-foot">
                <text class="drill-show" @tap="toggleDrill(i)">{{ drillOpen[i] ? '收起' : '看订正' }}</text>
                <text v-if="drillOpen[i]" class="drill-ans">{{ e.fix }}</text>
              </view>
            </view>
          </view>

          <!-- 下一步:按未达标维度给方向 -->
          <view v-if="weakDims.length" class="nextstep">
            <text class="ns-title">下一步重点练:</text>
            <text v-for="(d, i) in weakDims" :key="i" class="tag tag-warn">{{ d }}</text>
          </view>

          <!-- ── S4 范文对照 + 要点↔句高亮 ── -->
          <view v-if="result.model_essay" class="model-toggle" @tap="showModel = !showModel">
            <view class="ic ic-file head-ic" /><text class="box-title">对照范文 · 看每个要点怎么落成句</text>
            <view class="ic ic-arrow-right head-ic flip" :class="{ open: showModel }" />
          </view>
          <view v-if="showModel && result.model_essay" class="model-essay">
            <text v-for="(seg, i) in essaySegments" :key="i" :class="seg.pid ? 'hl' : ''">{{ seg.text }}<text
              v-if="seg.pid" class="hl-tag">要点{{ seg.pid }}</text></text>
          </view>
        </view>
      </template>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  listWritingQuestions, gradeWritingByQuestion,
  type WritingQuestion, type WritingGradeResult,
} from '@/api/writing'

const GENRES = ['记叙文', '议论文', '说明文', '应用文']
const TENSES = ['一般现在时', '一般过去时', '一般将来时', '混合时态']

const loadingList = ref(false)
const loading = ref(false)
const questions = ref<WritingQuestion[]>([])
const qIdx = ref(0)
const essay = ref('')
const graded = ref(false)
const result = ref<WritingGradeResult | null>(null)
const showScaffold = ref(true)
const showModel = ref(false)
const nodeId = ref('')

// 审题小测
const stage = ref<'quiz' | 'write'>('quiz')
const ans = ref<{ genre: string; tense: string; count: number | null }>({ genre: '', tense: '', count: null })
const quizChecked = ref(false)
const quizPass = ref(false)

// 错因微练
const drillInputs = ref<string[]>([])
const drillOpen = ref<boolean[]>([])

const curQ = computed(() => questions.value[qIdx.value])
const wordCount = computed(() => (essay.value.trim() ? essay.value.trim().split(/\s+/).length : 0))
const bandKey = computed(() => (result.value?.band || 'C').charAt(0).toUpperCase())
const quizComplete = computed(() => !!ans.value.genre && !!ans.value.tense && ans.value.count != null)

const weakDims = computed(() => {
  const p = result.value?.dim_passes || {}
  const label: Record<string, string> = { content: '要点覆盖', accuracy: '语法准确', richness: '高级句型', organization: '结构连贯' }
  return Object.keys(label).filter(k => p[k] === false).map(k => label[k])
})

// 正确判定(体裁允许"应用文（活动方案）"含"应用文")
function isCorrect(kind: 'genre' | 'tense' | 'count', v: string | number): boolean {
  if (kind === 'genre') return !!curQ.value?.genre && String(curQ.value.genre).includes(String(v))
  if (kind === 'tense') return curQ.value?.main_tense === v
  return curQ.value?.points_count === v
}
function pick(kind: 'genre' | 'tense' | 'count', v: string | number) {
  if (quizPass.value) return
  if (kind === 'count') ans.value.count = v as number
  else ans.value[kind] = v as string
}
function optClass(kind: 'genre' | 'tense' | 'count', v: string | number) {
  const sel = kind === 'count' ? ans.value.count === v : ans.value[kind] === v
  if (!sel) return ''
  if (!quizChecked.value) return 'sel'
  return isCorrect(kind, v) ? 'right' : 'wrong'
}
function checkQuiz() {
  quizChecked.value = true
  quizPass.value = isCorrect('genre', ans.value.genre) && isCorrect('tense', ans.value.tense)
    && isCorrect('count', ans.value.count!)
  if (quizPass.value) stage.value = 'write'
}

// 范文要点↔句高亮:按 point_map 把范文切成 [普通段, 要点句(带 pid)] 片段
const essaySegments = computed(() => {
  const essay = result.value?.model_essay || ''
  const pmap = result.value?.point_map || {}
  const marks: { pid: string; start: number; end: number }[] = []
  for (const [pid, sent] of Object.entries(pmap)) {
    const s = (sent || '').trim()
    if (!s) continue
    const idx = essay.indexOf(s)
    if (idx >= 0) marks.push({ pid, start: idx, end: idx + s.length })
  }
  marks.sort((a, b) => a.start - b.start)
  const segs: { text: string; pid?: string }[] = []
  let cur = 0
  for (const m of marks) {
    if (m.start < cur) continue          // 重叠跳过
    if (m.start > cur) segs.push({ text: essay.slice(cur, m.start) })
    segs.push({ text: essay.slice(m.start, m.end), pid: m.pid })
    cur = m.end
  }
  if (cur < essay.length) segs.push({ text: essay.slice(cur) })
  return segs.length ? segs : [{ text: essay }]
})

onLoad((q: any) => {
  nodeId.value = q?.node || q?.kp || ''
  loadQuestions()
})

async function loadQuestions() {
  loadingList.value = true
  try {
    questions.value = await listWritingQuestions(10, nodeId.value || undefined)
    qIdx.value = 0
    resetForQuestion()
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loadingList.value = false
  }
}

function resetForQuestion() {
  essay.value = ''; graded.value = false; result.value = null
  showScaffold.value = true; showModel.value = false
  stage.value = 'quiz'; quizChecked.value = false; quizPass.value = false
  ans.value = { genre: '', tense: '', count: null }
  drillInputs.value = []; drillOpen.value = []
}

async function submit() {
  if (!curQ.value || !essay.value.trim()) return
  loading.value = true
  try {
    result.value = await gradeWritingByQuestion({
      question_id: curQ.value.id,
      student_essay: essay.value.trim(),
      full_score: curQ.value.full_score || 20,
    })
    graded.value = true
    drillInputs.value = new Array(result.value.accuracy?.errors?.length || 0).fill('')
    drillOpen.value = new Array(result.value.accuracy?.errors?.length || 0).fill(false)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '批改失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function toggleDrill(i: number) { drillOpen.value[i] = !drillOpen.value[i] }

function nextQ() {
  if (qIdx.value < questions.value.length - 1) { qIdx.value++; resetForQuestion() }
  else loadQuestions()
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-bottom: 16rpx; }
.empty { display: flex; flex-direction: column; align-items: center; gap: 16rpx; padding: 80rpx 0; color: var(--c-text-hint); font-size: 26rpx; }
.empty-ic { width: 72rpx; height: 72rpx; opacity: .5; }
.qmeta { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 12rpx; display: flex; align-items: center; }
.genre { margin-left: auto; background: var(--c-primary-soft); color: var(--c-primary); border-radius: var(--r-sm); padding: 2rpx 14rpx; font-weight: 600; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 24rpx; }
.stem { display: block; font-size: 30rpx; font-weight: 600; color: var(--c-ink); line-height: 1.6; white-space: pre-wrap; }
.box-head { display: flex; align-items: center; gap: 10rpx; margin-bottom: 14rpx; }
.box-head.tap { margin-bottom: 0; }
.head-ic { width: 34rpx; height: 34rpx; }
.box-title { font-size: 27rpx; font-weight: 700; color: var(--c-text-body); }
.wc { margin-left: auto; font-size: 22rpx; color: var(--c-text-hint); }
/* 审题小测 */
.quiz-q { margin-bottom: 20rpx; }
.quiz-label { display: block; font-size: 27rpx; font-weight: 600; color: var(--c-ink); margin-bottom: 12rpx; }
.opts { display: flex; flex-wrap: wrap; gap: 12rpx; }
.opt { font-size: 26rpx; color: var(--c-text-body); background: var(--c-bg-soft); border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 12rpx 24rpx; }
.opt.sel { border-color: var(--c-primary); color: var(--c-primary); background: var(--c-primary-soft); font-weight: 600; }
.opt.right { border-color: #22c55e; color: #22c55e; background: rgba(34,197,94,.1); font-weight: 700; }
.opt.wrong { border-color: #ef4444; color: #ef4444; background: rgba(239,68,68,.1); font-weight: 700; }
.quiz-fail { display: flex; align-items: center; gap: 10rpx; font-size: 24rpx; color: #ef4444; margin-bottom: 14rpx; }
.qf-ic { width: 32rpx; height: 32rpx; flex-shrink: 0; }
.points-box { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 18rpx 20rpx; }
.point-line { display: flex; gap: 12rpx; align-items: flex-start; font-size: 26rpx; color: var(--c-text-body); line-height: 1.6; padding: 4rpx 0; }
.dot { flex-shrink: 0; width: 32rpx; height: 32rpx; line-height: 32rpx; text-align: center; background: var(--c-primary); color: var(--c-on-primary); border-radius: 50%; font-size: 20rpx; }
.scaffold .scaffold-body { margin-top: 16rpx; display: flex; flex-direction: column; gap: 12rpx; }
.scaf-block { background: var(--c-bg-soft); border-left: 4rpx solid var(--c-primary); border-radius: var(--r-sm); padding: 12rpx 16rpx; }
.scaf-role { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-primary); margin-bottom: 4rpx; }
.scaf-guide { font-size: 25rpx; color: var(--c-text-body); line-height: 1.6; }
.flip { transition: transform .2s; margin-left: auto; }
.flip.open { transform: rotate(90deg); }
.ta { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 18rpx; font-size: 28rpx; min-height: 240rpx; box-sizing: border-box; width: 100%; margin-bottom: 18rpx; line-height: 1.7; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.result .score-line { display: flex; align-items: center; gap: 16rpx; margin-bottom: 20rpx; }
.band { width: 60rpx; height: 60rpx; line-height: 60rpx; text-align: center; border-radius: var(--r-md); font-size: 34rpx; font-weight: 800; color: #fff; }
.band-A { background: #22c55e; } .band-B { background: #3d8bf5; } .band-C { background: #ff8a3d; } .band-D { background: #ef4444; }
.score-num { font-size: 52rpx; font-weight: 800; color: var(--c-primary); }
.score-full { font-size: 28rpx; color: var(--c-text-hint); }
.ai-tag { margin-left: auto; font-size: 22rpx; color: var(--c-text-hint); }
.dim { border-top: 2rpx solid var(--c-border); padding: 18rpx 0; }
.dim-title { display: block; font-size: 26rpx; font-weight: 700; color: var(--c-text-body); margin-bottom: 12rpx; }
.dim-body { font-size: 25rpx; color: var(--c-text-body); line-height: 1.6; }
.pt { display: flex; gap: 12rpx; align-items: flex-start; padding: 6rpx 0; }
.pt-ic { width: 34rpx; height: 34rpx; flex-shrink: 0; margin-top: 2rpx; }
.pt-body { display: flex; flex-direction: column; }
.pt-name { font-size: 26rpx; color: var(--c-text-body); }
.pt-name.miss { color: #ef4444; }
.pt-comment { font-size: 23rpx; color: var(--c-text-hint); line-height: 1.5; }
.ok-line { font-size: 24rpx; color: #22c55e; }
.err { display: flex; flex-wrap: wrap; align-items: center; gap: 10rpx; padding: 6rpx 0; }
.err-span { font-size: 25rpx; color: #ef4444; text-decoration: line-through; }
.err-type { font-size: 20rpx; color: #ff8a3d; background: rgba(255,138,61,.12); border-radius: var(--r-sm); padding: 2rpx 10rpx; }
.err-fix { font-size: 25rpx; color: #22c55e; }
.tags { display: flex; flex-wrap: wrap; gap: 10rpx; margin-bottom: 8rpx; }
.tag { font-size: 22rpx; border-radius: var(--r-sm); padding: 4rpx 14rpx; }
.tag-ok { color: var(--c-primary); background: var(--c-primary-soft); }
.tag-warn { color: #ff8a3d; background: rgba(255,138,61,.12); }
.upgrade { display: flex; gap: 10rpx; align-items: flex-start; font-size: 24rpx; color: var(--c-text-body); line-height: 1.6; padding: 6rpx 0; }
.up-ic { width: 30rpx; height: 30rpx; flex-shrink: 0; margin-top: 2rpx; }
.fb { margin-top: 12rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx 20rpx; font-size: 25rpx; color: var(--c-text-body); line-height: 1.7; }
/* 错因微练 */
.drill { border-top: 2rpx solid var(--c-border); padding-top: 18rpx; margin-top: 6rpx; }
.drill-item { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; margin-bottom: 12rpx; }
.drill-q { display: flex; align-items: center; gap: 10rpx; margin-bottom: 10rpx; }
.drill-span { font-size: 25rpx; color: #ef4444; text-decoration: line-through; }
.drill-input { border: 2rpx solid var(--c-border); border-radius: var(--r-sm); padding: 12rpx 16rpx; font-size: 26rpx; background: var(--c-bg-card); }
.drill-foot { margin-top: 8rpx; display: flex; align-items: center; gap: 12rpx; }
.drill-show { font-size: 24rpx; color: var(--c-primary); }
.drill-ans { font-size: 25rpx; color: #22c55e; }
.nextstep { margin-top: 14rpx; display: flex; flex-wrap: wrap; align-items: center; gap: 10rpx; }
.ns-title { font-size: 25rpx; font-weight: 600; color: var(--c-text-body); }
.model-toggle { display: flex; align-items: center; gap: 10rpx; margin-top: 18rpx; padding-top: 16rpx; border-top: 2rpx solid var(--c-border); }
.model-essay { margin-top: 12rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 18rpx 20rpx; font-size: 26rpx; color: var(--c-text-body); line-height: 1.9; white-space: pre-wrap; }
.hl { background: rgba(61,139,245,.14); color: var(--c-primary); border-radius: 4rpx; }
.hl-tag { font-size: 18rpx; color: var(--c-on-primary); background: var(--c-primary); border-radius: 4rpx; padding: 0 6rpx; margin: 0 4rpx; vertical-align: super; }
</style>

<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>

    <!-- 已完成（历史复看）-->
    <view v-else-if="reviewOnly" class="list">
      <view class="score-card card">
        <text class="score-num">{{ exam.correct_count }} / {{ exam.total }}</text>
        <text class="score-meta">本卷已完成 · 错题已加入「我的错题」可复盘</text>
      </view>
      <button class="btn-primary" style="margin-top:16rpx" @tap="goBack">返回</button>
    </view>

    <!-- 答题中 -->
    <scroll-view v-else-if="!result" scroll-y class="list">
      <view class="exam-head">
        <view class="eh-top">
          <text class="exam-title">自助模拟卷</text>
          <view class="timer" :class="{ urgent: remain <= 60 }"><view class="ic ic-clock timer-ic" /><text>{{ mmss }}</text></view>
        </view>
        <text class="exam-sub">薄弱点：{{ (exam.weak_kps || []).join(' · ') || '综合' }}</text>
      </view>

      <view v-for="sec in sections" :key="sec.key" class="section">
        <view class="sec-head">
          <view class="sec-title"><view class="ic sec-ic" :class="sec.icon" /><text>{{ sec.label }}</text></view>
          <view
            v-if="sec.key === 'listening' && sec.audioText"
            class="play-btn" :class="{ playing }" @tap="playListening(sec.audioText)"
          >{{ playing ? '暂停' : '播放听力' }}</view>
        </view>

        <view v-for="(q, idx) in sec.items" :key="q.id" class="card">
          <view class="qtype">{{ q.question_type }}</view>
          <text class="stem">{{ q.stem }}</text>

          <view v-if="hasOptions(q)" class="options">
            <view
              v-for="(opt, i) in q.options" :key="i"
              class="option" :class="{ selected: answers[q.id] === letter(i) }"
              @tap="answers[q.id] = letter(i)"
            >
              <text class="opt-letter">{{ letter(i) }}</text>
              <text class="opt-text">{{ optText(opt) }}</text>
            </view>
          </view>
          <view v-else-if="q.question_type === '判断'" class="options">
            <view
              v-for="opt in ['对', '错']" :key="opt"
              class="option" :class="{ selected: answers[q.id] === opt }"
              @tap="answers[q.id] = opt"
            >{{ opt }}</view>
          </view>
          <textarea
            v-else-if="q.section === 'writing'"
            v-model="answers[q.id]" class="essay-input" placeholder="请在此作答（40 词左右）"
          />
          <input v-else v-model="answers[q.id]" class="fill-input" placeholder="请输入答案" />
        </view>
      </view>
      <view style="height: 150rpx;" />
    </scroll-view>

    <!-- 结果 -->
    <scroll-view v-else scroll-y class="list">
      <view class="score-card card">
        <text class="score-num">{{ result.correct_count }} / {{ result.total }}</text>
        <text class="score-meta">客观+听力得分 · 错题已入错题本{{ result.writing_submitted ? '；写作另计' : '' }}</text>
      </view>
      <view
        v-for="(it, idx) in result.items" :key="it.id"
        class="card result-card"
        :class="{ ok: it.correct === true, neutral: it.correct === null }"
      >
        <view class="res-head">
          <text class="res-idx">{{ secLabel(it.section) }}</text>
          <view class="res-flag" :class="{ ok: it.correct === true, neutral: it.correct === null }">
            <view v-if="it.correct === true" class="ic ic-check-circle res-flag-ic" />
            <view v-else-if="it.correct === false" class="ic ic-x-circle res-flag-ic" />
            <text>{{ it.correct === null ? '参考' : (it.correct ? '正确' : '错误') }}</text>
          </view>
        </view>
        <text class="res-stem">{{ it.stem }}</text>
        <text class="res-line">你的答案：{{ it.user_answer || '（未作答）' }}</text>
        <text v-if="it.correct !== null" class="res-line right">正确答案：{{ it.correct_answer }}</text>
        <view v-if="it.section === 'writing' && it.score != null" class="essay-box">
          <text class="essay-score">作文得分 {{ it.score }}<text class="essay-full"> / {{ it.full_score }}</text></text>
          <text v-if="it.essay_id" class="essay-link" @tap="() => goEssay(it.essay_id)">查看 AI 精修详情 ›</text>
        </view>
        <text v-if="it.explanation" class="res-exp">{{ it.explanation }}</text>
      </view>
      <view class="practice-bar fixed result-bar">
        <button v-if="hasWrong" class="btn-secondary" @tap="goWrongBook"><view class="ic ic-book btn-ic" /><text>错题回看</text></button>
        <button class="btn-primary" @tap="goBack">返回</button>
      </view>
    </scroll-view>

    <view v-if="!loading && !reviewOnly && !result" class="practice-bar fixed">
      <button class="btn-primary" :disabled="submitting" @tap="() => submit(false)">
        {{ submitting ? '批改中…' : '提交考试' }}
      </button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getSelfExam, submitSelfExam, type SelfExamOut, type SelfExamQuestion, type SelfExamResult } from '@/api/selfExam'
import { resolveSpeakUrl, gradeToStage } from '@/utils/tts'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

const loading = ref(true)
const reviewOnly = ref(false)
const submitting = ref(false)
const examId = ref('')
const exam = reactive<Partial<SelfExamOut>>({})
const questions = ref<SelfExamQuestion[]>([])
const answers = reactive<Record<string, string>>({})
const result = ref<SelfExamResult | null>(null)

const SEC_META: Record<string, { label: string; icon: string }> = {
  listening: { label: '听力理解', icon: 'ic-headphone' },
  objective: { label: '客观题', icon: 'ic-pen' },
  writing: { label: '书面表达', icon: 'ic-edit' },
}
function secLabel(s: string) { return SEC_META[s]?.label || s }

// 是否有归库的错题（客观区答错才进错题本）
const hasWrong = computed(() =>
  (result.value?.items || []).some(it => it.section === 'objective' && it.correct === false),
)
function goWrongBook() {
  uni.navigateTo({ url: '/pages/wrong-questions/list' })
}

const sections = computed(() => {
  const order = ['listening', 'objective', 'writing']
  return order
    .map((key) => {
      const items = questions.value.filter(q => q.section === key)
      const audioText = items.find(q => q.audio_text)?.audio_text || ''
      return { key, label: SEC_META[key].label, icon: SEC_META[key].icon, items, audioText }
    })
    .filter(s => s.items.length > 0)
})

const remain = ref(0)
let timer: number | undefined
const mmss = computed(() => {
  const m = Math.floor(remain.value / 60), s = remain.value % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function letter(i: number) { return ['A', 'B', 'C', 'D', 'E', 'F'][i] ?? '' }
function hasOptions(q: SelfExamQuestion) { return Array.isArray(q.options) && q.options.length > 0 && q.question_type !== '判断' }
function optText(opt: string) { return String(opt).replace(/^\s*[A-Fa-f]\s*[.．、，)）:：]\s*/, '').trim() }

onLoad(async (q: any) => {
  examId.value = q?.id || ''
  try {
    const e = await getSelfExam(examId.value)
    Object.assign(exam, e)
    if (e.status === 'done') {
      reviewOnly.value = true
    } else {
      questions.value = e.questions || []
      remain.value = e.time_limit_sec || 1200
      startTimer()
    }
  } catch (err) {
    uni.showToast({ title: (err as Error).message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function startTimer() {
  timer = setInterval(() => {
    remain.value -= 1
    if (remain.value <= 0) { clearTimer(); uni.showToast({ title: '时间到，自动交卷', icon: 'none' }); submit(true) }
  }, 1000) as unknown as number
}
function clearTimer() { if (timer) { clearInterval(timer); timer = undefined } }
onUnmounted(() => { clearTimer(); stopAudio() })

// 听力音频
let _ctx: UniApp.InnerAudioContext | null = null
const playing = ref(false)
function stopAudio() { if (_ctx) { try { _ctx.stop() } catch { /* ignore */ } } playing.value = false }
async function playListening(text: string) {
  if (!_ctx) {
    _ctx = uni.createInnerAudioContext()
    _ctx.onPlay(() => { playing.value = true })
    _ctx.onEnded(() => { playing.value = false })
    _ctx.onStop(() => { playing.value = false })
    _ctx.onError(() => { playing.value = false })
  }
  if (playing.value) { _ctx.pause(); playing.value = false; return }
  _ctx.src = await resolveSpeakUrl(text, gradeToStage((auth.user as any)?.preferred_grade))
  _ctx.play()
}

async function submit(auto: boolean) {
  if (submitting.value || result.value) return
  if (!auto) {
    const need = questions.value.filter(q => !(answers[q.id] || '').trim()).length
    if (need > 0) {
      const go = await new Promise<boolean>((res) => {
        uni.showModal({ title: '还有未作答', content: `还有 ${need} 题未作答，确认提交？`, success: (r) => res(r.confirm) })
      })
      if (!go) return
    }
  }
  submitting.value = true
  clearTimer()
  stopAudio()
  try {
    const items = questions.value.map(q => ({ question_id: q.id, user_answer: (answers[q.id] || '').trim() || '未作答' }))
    const r = await submitSelfExam(examId.value, items)
    result.value = r.result
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function goBack() { uni.navigateBack() }
function goEssay(id?: string | null) {
  if (id) uni.navigateTo({ url: `/pages/essay/detail?id=${id}` })
}
</script>

<style scoped>
.page { background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 160rpx 0; color: var(--c-text-hint); }
.list { height: 100vh; padding: 24rpx; box-sizing: border-box; }
.exam-head { padding: 8rpx 0 12rpx; }
.eh-top { display: flex; align-items: center; justify-content: space-between; }
.exam-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.timer { display: inline-flex; align-items: center; gap: 6rpx; font-size: 30rpx; font-weight: 800; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 18rpx; border-radius: var(--r-pill); }
.timer-ic { width: 30rpx; height: 30rpx; }
.timer.urgent { color: #fff; background: var(--c-danger); }
.exam-sub { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; }
.section { margin-top: 8rpx; }
.sec-head { display: flex; align-items: center; justify-content: space-between; margin: 18rpx 4rpx 10rpx; }
.sec-title { display: flex; align-items: center; gap: 8rpx; font-size: 28rpx; font-weight: 800; color: var(--c-ink); }
.sec-ic { width: 32rpx; height: 32rpx; }
.play-btn { font-size: 24rpx; font-weight: 700; color: var(--c-on-primary); background: var(--c-primary); padding: 8rpx 22rpx; border-radius: var(--r-pill); }
.play-btn.playing { background: var(--c-primary-deep); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qtype { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.stem { display: block; font-size: 30rpx; font-weight: 700; color: var(--c-ink); line-height: 1.5; margin-bottom: 20rpx; }
.options { display: flex; flex-direction: column; gap: 12rpx; }
.option { display: flex; align-items: center; gap: 16rpx; padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); background: #fff; font-size: 28rpx; color: var(--c-text-body); }
.option.selected { border-color: var(--c-primary); background: var(--c-primary-faint); }
.opt-letter { width: 44rpx; height: 44rpx; flex-shrink: 0; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--c-bg-soft); color: var(--c-text-second); font-size: 24rpx; font-weight: 800; }
.option.selected .opt-letter { background: var(--c-primary); color: var(--c-on-primary); }
.opt-text { flex: 1; }
.fill-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 18rpx; font-size: 28rpx; width: 100%; box-sizing: border-box; }
.essay-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 18rpx; font-size: 28rpx; width: 100%; min-height: 200rpx; box-sizing: border-box; }
.score-card { display: flex; flex-direction: column; align-items: center; gap: 8rpx; padding: 40rpx; }
.score-num { font-size: 64rpx; font-weight: 900; color: var(--c-primary); }
.score-meta { font-size: 24rpx; color: var(--c-text-second); text-align: center; }
.result-card { border-left: 6rpx solid var(--c-danger); }
.result-card.ok { border-left-color: #2ecc71; }
.result-card.neutral { border-left-color: var(--c-gold); }
.res-head { display: flex; justify-content: space-between; margin-bottom: 6rpx; }
.res-idx { font-size: 22rpx; color: var(--c-text-hint); }
.res-flag { display: inline-flex; align-items: center; gap: 4rpx; font-size: 24rpx; font-weight: 700; color: var(--c-danger); }
.res-flag-ic { width: 28rpx; height: 28rpx; }
.res-flag.ok { color: #18a058; }
.res-flag.neutral { color: var(--c-gold); }
.res-stem { display: block; font-size: 26rpx; color: var(--c-ink); font-weight: 600; line-height: 1.5; margin-bottom: 8rpx; }
.res-line { display: block; font-size: 26rpx; color: var(--c-text-body); line-height: 1.6; }
.res-line.right { color: #18a058; }
.res-exp { display: block; font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-top: 6rpx; }
.essay-box { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; margin: 10rpx 0; padding: 14rpx 18rpx; background: var(--c-primary-faint); border-radius: var(--r-md); }
.essay-score { font-size: 28rpx; font-weight: 800; color: var(--c-primary-deep); }
.essay-full { font-size: 22rpx; font-weight: 600; color: var(--c-text-hint); }
.essay-link { font-size: 24rpx; font-weight: 600; color: var(--c-primary); }
.practice-bar.fixed { position: fixed; left: 0; right: 0; bottom: 0; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: var(--c-bg-card); box-shadow: 0 -2rpx 16rpx rgba(0,0,0,.06); }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; flex: 1; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.result-bar { display: flex; gap: 16rpx; }
.btn-secondary { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border: 2rpx solid var(--c-primary-soft); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; }
.btn-ic { width: 32rpx; height: 32rpx; }
</style>

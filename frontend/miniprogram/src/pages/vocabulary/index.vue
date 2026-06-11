<!-- src/pages/vocabulary/index.vue 词力通背词 -->
<template>
  <view class="vocab-page">
    <view v-if="loading" class="center-tip">加载今日任务…</view>

    <view v-else-if="phase === 'empty'">
      <view v-if="cal" class="checkin-panel">
        <view class="cp-summary">连续 {{ cal.current_streak }} 天 · 最高 {{ cal.longest_streak }} 天</view>
        <view class="cp-badges">
          <text v-for="b in cal.badges" :key="b.level" class="cp-badge" :class="{ on: b.unlocked }">
            {{ b.level === 'bronze' ? '🥉' : b.level === 'silver' ? '🥈' : '🥇' }}{{ b.name }}
          </text>
        </view>
        <view class="cp-grid">
          <view v-for="(c, i) in calCells" :key="i" class="cp-cell"
                :class="{ checked: c.checked, missable: c.missable, blank: !c.day }"
                @tap="c.missable ? onMakeUp(c.date) : null">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
          </view>
        </view>
        <view class="cp-hint">点亮灰色日期可补签</view>
      </view>
      <view class="center-tip">🎉 今日没有待学/待复习的单词，明天再来吧！</view>
    </view>

    <!-- 学习阶段：词卡 -->
    <view v-else-if="phase === 'study'" class="card">
      <view class="progress-hint">学新词 {{ studyIndex + 1 }} / {{ newCards.length }}</view>
      <view class="word">{{ curStudy.word }}</view>
      <view class="phonetic" v-if="curStudy.phonetic">/{{ curStudy.phonetic }}/</view>
      <view class="defs">
        <text v-for="(d, i) in defList(curStudy)" :key="i" class="def-line">{{ d }}</text>
      </view>
      <view class="examples" v-if="exampleList(curStudy).length">
        <text class="ex-title">例句</text>
        <view v-for="(e, i) in exampleList(curStudy)" :key="i" class="ex-row">
          <text class="ex-line">{{ e }}</text>
          <text class="ex-shadow-btn" @tap="openShadow(e)">🎤 跟读</text>
        </view>
      </view>

      <!-- 图背单词：配图 -->
      <scroll-view v-if="curStudy.image_urls && curStudy.image_urls.length" scroll-x class="img-row">
        <image v-for="(u, i) in curStudy.image_urls" :key="i" :src="u" mode="aspectFill" class="word-img" />
      </scroll-view>
      <!-- 英文可理解性描述 -->
      <view v-if="curStudy.en_description" class="en-desc">
        <text class="en-desc-text">{{ curStudy.en_description }}</text>
      </view>
      <!-- 双音频播放（火山 TTS 实时合成）-->
      <view class="audio-row" v-if="curStudy.word">
        <text class="audio-btn" @tap="playTTS(curStudy.word)">🔊 单词</text>
        <text v-if="curStudy.en_description" class="audio-btn" @tap="playTTS(curStudy.en_description)">🔊 英文描述</text>
      </view>

      <button class="btn-primary" @tap="nextStudy">记住了，下一个</button>
    </view>

    <!-- 测试阶段：4 选 1 -->
    <view v-else-if="phase === 'quiz'" class="card">
      <view class="progress-hint">测试 {{ quizIndex + 1 }} / {{ quizQueue.length }} · 正确 {{ correctCount }}</view>
      <view class="quiz-type">{{ quizTypeLabel }}</view>
      <view class="quiz-prompt">{{ curQuiz.prompt }}</view>

      <!-- 看图选词：4 张图选 1 -->
      <view v-if="curQuiz.mode === 'pic'" class="pic-grid">
        <view
          v-for="(opt, i) in curQuiz.options"
          :key="i"
          class="pic-option"
          :class="optionClass(i)"
          @tap="choose(i)"
        >
          <image :src="opt" mode="aspectFill" class="pic-option-img" />
        </view>
      </view>
      <!-- 文本选项 -->
      <view
        v-else
        v-for="(opt, i) in curQuiz.options"
        :key="i"
        class="option"
        :class="optionClass(i)"
        @tap="choose(i)"
      >
        {{ opt }}
      </view>

      <button v-if="answered" class="btn-primary" @tap="nextQuiz">下一题</button>
    </view>

    <!-- 完成 -->
    <view v-else-if="phase === 'done'" class="card done">
      <view class="done-emoji">✅</view>
      <view class="done-title">今日完成！</view>
      <view class="done-stat">新学 {{ newCards.length }} 词 · 复习 {{ reviewCards.length }} 词</view>
      <view class="done-stat">答对率 {{ quizQueue.length ? Math.round((correctCount / quizQueue.length) * 100) : 0 }}%</view>
      <view v-if="checkinDone" class="done-streak">已连续打卡 {{ streakDays }} 天 🔥</view>
      <view v-else class="done-gap">{{ gapHint }}</view>
      <view v-if="cal" class="checkin-panel">
        <view class="cp-badges">
          <text v-for="b in cal.badges" :key="b.level" class="cp-badge" :class="{ on: b.unlocked }">
            {{ b.level === 'bronze' ? '🥉' : b.level === 'silver' ? '🥈' : '🥇' }}{{ b.name }}
          </text>
        </view>
        <view class="cp-grid">
          <view v-for="(c, i) in calCells" :key="i" class="cp-cell"
                :class="{ checked: c.checked, missable: c.missable, blank: !c.day }"
                @tap="c.missable ? onMakeUp(c.date) : null">
            <text v-if="c.day">{{ c.checked ? '🔥' : c.day }}</text>
          </view>
        </view>
        <view class="cp-hint">点亮灰色日期可补签</view>
      </view>
      <button class="btn-primary" @tap="reload">再来一组</button>
      <button class="btn-ghost" @tap="() => uni.navigateTo({ url: '/pages/vocabulary/wrong-book' })">查看错词本</button>
    </view>

    <!-- 跟读评分弹窗 -->
    <view v-if="shadow.open" class="shadow-modal" @tap.self="closeShadow">
      <view class="shadow-card">
        <view class="shadow-title">🎤 跟读练习</view>
        <text class="shadow-sentence">{{ shadow.text }}</text>

        <view class="shadow-tools">
          <text class="shadow-demo" @tap="playShadowDemo">🔊 示范</text>
        </view>

        <!-- 录音 / 评分态 -->
        <view v-if="!shadow.result" class="shadow-rec-area">
          <button
            class="shadow-rec-btn"
            :class="{ recording: shadow.recording }"
            :disabled="shadow.scoring"
            @tap="shadow.recording ? stopAndScore() : startShadowRecord()"
          >
            {{ shadow.scoring ? '评分中…' : (shadow.recording ? '● 录音中，点击结束' : '开始跟读') }}
          </button>
          <text class="shadow-hint">点击开始，朗读上面的句子</text>
        </view>

        <!-- 评分结果 -->
        <view v-else class="shadow-result">
          <view class="shadow-score" :class="`lv-${shadow.result.level}`">
            <text class="ss-num">{{ shadow.result.overall }}</text>
            <text class="ss-unit">分 · {{ levelLabel(shadow.result.level) }}</text>
          </view>
          <view class="shadow-words">
            <text
              v-for="(w, i) in shadow.result.words" :key="i"
              class="sw-chip" :class="{ weak: w.score < 80 }"
            >{{ w.word }} <text class="sw-score">{{ w.score }}</text></text>
          </view>
          <view class="shadow-tip">💡 {{ shadow.result.tip }}</view>
          <view class="shadow-actions">
            <button v-if="shadow.recordPath" class="btn-ghost half" @tap="playMyRecord">▶ 我的录音</button>
            <button class="btn-primary half" @tap="retryShadow">🔁 重跟</button>
          </view>
        </view>

        <text class="shadow-close" @tap="closeShadow">关闭</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { getDailyTask, submitVocabAnswer, checkin, getCheckinCalendar, makeUpCheckin, shadowScore } from '@/api/vocabulary'
import type { ShadowScoreResult } from '@/api/vocabulary'
import type { VocabStudentCalendar } from '@/types/api'
import { useAuthStore } from '@/stores/auth'
import type { VocabWordCard } from '@/types/api'

interface Quiz {
  word_id: string
  mode: 'w2m' | 'm2w' | 'pic'   // 看词选义 / 看义选词 / 看图选词
  prompt: string
  options: string[]   // 文本选项；mode==='pic' 时为图片 URL
  answerIndex: number
}

const auth = useAuthStore()
const loading = ref(true)
const phase = ref<'empty' | 'study' | 'quiz' | 'done'>('study')

const newCards = ref<VocabWordCard[]>([])
const reviewCards = ref<VocabWordCard[]>([])
const pool = ref<VocabWordCard[]>([])   // 全部词，用于生成干扰项

const studyIndex = ref(0)
const quizIndex = ref(0)
const correctCount = ref(0)
const answered = ref(false)
const chosenIndex = ref(-1)
const quizQueue = ref<Quiz[]>([])
const streakDays = ref(0)
const checkinDone = ref(false)
const gapHint = ref('')
const cal = ref<VocabStudentCalendar | null>(null)
const calCells = computed(() => {
  if (!cal.value) return [] as { day: number; date: string; checked: boolean; missable: boolean }[]
  const { year, month } = cal.value
  const checkedSet = new Set(cal.value.days.map(d => d.date))
  const first = new Date(year, month - 1, 1).getDay()
  const daysIn = new Date(year, month, 0).getDate()
  const todayStr = new Date().toISOString().slice(0, 10)
  const arr: { day: number; date: string; checked: boolean; missable: boolean }[] = []
  for (let i = 0; i < first; i++) arr.push({ day: 0, date: '', checked: false, missable: false })
  for (let d = 1; d <= daysIn; d++) {
    const date = `${year}-${String(month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    const checked = checkedSet.has(date)
    arr.push({ day: d, date, checked, missable: !checked && date < todayStr })
  }
  return arr
})
async function loadCalendar() {
  try { cal.value = await getCheckinCalendar() } catch { /* 不阻塞 */ }
}
async function onMakeUp(date: string) {
  try {
    await makeUpCheckin(date)
    await loadCalendar()
    uni.showToast({ title: '补签成功', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}

const curStudy = computed(() => newCards.value[studyIndex.value] || ({} as VocabWordCard))
const curQuiz = computed(() => quizQueue.value[quizIndex.value] || ({} as Quiz))
const quizTypeLabel = computed(() => {
  const m = curQuiz.value.mode
  return m === 'w2m' ? '看词选义' : m === 'm2w' ? '看义选词' : '看图选词'
})

function defList(card: VocabWordCard): string[] {
  const d = card.definitions
  if (Array.isArray(d)) return d.map((x: any) => `${x.pos ? x.pos + ' ' : ''}${x.meaning}`)
  return []
}
function primaryMeaning(card: VocabWordCard): string {
  const d = card.definitions
  if (Array.isArray(d) && d.length) return (d[0] as any).meaning
  return ''
}
function exampleList(card: VocabWordCard): string[] {
  const e = card.examples
  if (Array.isArray(e)) return e.map((x) => String(x))
  return []
}

function shuffle<T>(arr: T[]): T[] {
  const a = arr.slice()
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1))
    ;[a[i], a[j]] = [a[j], a[i]]
  }
  return a
}

function firstImage(w: VocabWordCard): string | null {
  return w.image_urls && w.image_urls.length ? w.image_urls[0] : null
}

function buildQuiz(card: VocabWordCard, mode: 'w2m' | 'm2w' | 'pic'): Quiz {
  const others = pool.value.filter((w) => w.word_id !== card.word_id)
  if (mode === 'pic') {
    // 看图选词：本词图 + 3 干扰词图，4 选 1（需本词有图 + ≥3 个有图干扰词，否则回退看词选义）
    const correctImg = firstImage(card)
    const imgOthers = shuffle(others.filter((w) => firstImage(w)))
    if (correctImg && imgOthers.length >= 3) {
      const opts = shuffle([correctImg, ...imgOthers.slice(0, 3).map((w) => firstImage(w) as string)])
      return { word_id: card.word_id, mode: 'pic', prompt: card.word, options: opts, answerIndex: opts.indexOf(correctImg) }
    }
    mode = 'w2m'
  }
  const distractors = shuffle(others).slice(0, 3)
  if (mode === 'w2m') {
    const correct = primaryMeaning(card)
    const opts = shuffle([correct, ...distractors.map((w) => primaryMeaning(w))])
    return { word_id: card.word_id, mode: 'w2m', prompt: card.word, options: opts, answerIndex: opts.indexOf(correct) }
  }
  const correct = card.word
  const opts = shuffle([correct, ...distractors.map((w) => w.word)])
  return { word_id: card.word_id, mode: 'm2w', prompt: primaryMeaning(card), options: opts, answerIndex: opts.indexOf(correct) }
}

function startQuiz() {
  const all = [...newCards.value, ...reviewCards.value]
  const modes: Array<'w2m' | 'm2w' | 'pic'> = ['w2m', 'm2w', 'pic']
  quizQueue.value = all.map((card, i) => buildQuiz(card, modes[i % 3]))
  quizIndex.value = 0
  correctCount.value = 0
  answered.value = false
  chosenIndex.value = -1
  if (quizQueue.value.length) {
    phase.value = 'quiz'
  } else {
    finishSession()
  }
}

async function finishSession() {
  phase.value = 'done'
  try {
    const r = await checkin()
    checkinDone.value = r.completed
    if (r.completed) {
      streakDays.value = r.streak_days
      // 打卡成功后请求订阅消息授权（一次性，用户点允许后后端 cron 才能推送提醒）
      requestCheckinSubscribe()
    } else {
      const newGap = Math.max(0, r.new_target - r.new_learned_today)
      gapHint.value = `还差 ${r.review_due} 个复习 / ${newGap} 个新词，完成后才能打卡`
    }
  } catch {
    // 打卡失败不阻塞完成页展示
  }
  await loadCalendar()
}

/**
 * 请求微信订阅消息授权（打卡提醒）。
 * template_id 通过环境变量 VITE_WX_SUBSCRIBE_TEMPLATE_CHECKIN 注入；
 * dev 模式（空字符串）时静默跳过，不弹授权框。
 */
function requestCheckinSubscribe() {
  const tmplId = import.meta.env.VITE_WX_SUBSCRIBE_TEMPLATE_CHECKIN as string | undefined
  if (!tmplId) return  // dev 模式或未配置，跳过

  uni.requestSubscribeMessage({
    tmplIds: [tmplId],
    success() {
      // 用户选择（accept/reject/ban），结果记录在微信侧
      // 后端 cron 下次发送时微信会自动过滤未授权用户
    },
    fail() {
      // 用户拒绝或环境不支持（如开发工具），静默忽略
    },
  })
}

function nextStudy() {
  if (studyIndex.value < newCards.value.length - 1) {
    studyIndex.value++
  } else {
    startQuiz()
  }
}

async function choose(i: number) {
  if (answered.value) return
  answered.value = true
  chosenIndex.value = i
  const correct = i === curQuiz.value.answerIndex
  if (correct) correctCount.value++
  try {
    await submitVocabAnswer(curQuiz.value.word_id, correct, false)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}

function nextQuiz() {
  if (quizIndex.value < quizQueue.value.length - 1) {
    quizIndex.value++
    answered.value = false
    chosenIndex.value = -1
  } else {
    finishSession()
  }
}

function optionClass(i: number): string {
  if (!answered.value) return ''
  if (i === curQuiz.value.answerIndex) return 'opt-correct'
  if (i === chosenIndex.value) return 'opt-wrong'
  return ''
}

async function load() {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try {
    const task = await getDailyTask()
    newCards.value = task.new_words
    reviewCards.value = task.review_words
    pool.value = [...task.new_words, ...task.review_words]
    studyIndex.value = 0
    if (newCards.value.length === 0 && reviewCards.value.length === 0) {
      phase.value = 'empty'
      loadCalendar()
    } else if (newCards.value.length > 0) {
      phase.value = 'study'
    } else {
      startQuiz()
    }
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    loading.value = false
  }
}

let _audioCtx: UniApp.InnerAudioContext | null = null
function playAudio(src?: string | null) {
  if (!src) return
  if (!_audioCtx) _audioCtx = uni.createInnerAudioContext()
  _audioCtx.src = src
  _audioCtx.play()
}

const _ttsBase = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'
/** 用火山 TTS 接口实时合成并播放一段文本（dev 无凭据时接口 204，静默无声）。 */
function playTTS(text?: string | null) {
  if (!text) return
  playAudio(`${_ttsBase}/api/v1/tts/speak?text=${encodeURIComponent(text)}`)
}

function reload() {
  load()
}

// ── 跟读评分（听力跟读·嵌入例句）──────────────────────────────────────────
const shadow = reactive({
  open: false,
  text: '',
  recording: false,
  scoring: false,
  result: null as ShadowScoreResult | null,
  recordPath: '',
})

function levelLabel(lv: string) {
  return ({ excellent: '优秀', good: '良好', fair: '及格', poor: '待加强' } as Record<string, string>)[lv] || lv
}

function openShadow(text: string) {
  Object.assign(shadow, { open: true, text, recording: false, scoring: false, result: null, recordPath: '' })
}

function closeShadow() {
  // #ifdef MP-WEIXIN
  if (shadow.recording) { try { _recorder?.stop() } catch { /* ignore */ } }
  // #endif
  shadow.open = false
  shadow.recording = false
}

function playShadowDemo() {
  // 火山 TTS 实时合成整句示范音频
  playTTS(shadow.text)
}

let _recorder: UniApp.RecorderManager | null = null
function startShadowRecord() {
  shadow.result = null
  // #ifdef MP-WEIXIN
  try {
    if (!_recorder) _recorder = uni.getRecorderManager()
    _recorder.onStop((res) => { shadow.recordPath = (res as { tempFilePath?: string }).tempFilePath || '' })
    _recorder.start({ format: 'mp3', duration: 60000 })
    shadow.recording = true
    return
  } catch { /* 不支持则退回直接评分 */ }
  // #endif
  // H5 / 不支持录音：直接进入「录音中」态，结束即评分（演示用）
  shadow.recording = true
}

async function stopAndScore() {
  // #ifdef MP-WEIXIN
  try { _recorder?.stop() } catch { /* ignore */ }
  // #endif
  shadow.recording = false
  shadow.scoring = true
  try {
    shadow.result = await shadowScore(shadow.text)
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '评分失败', icon: 'none' })
  } finally {
    shadow.scoring = false
  }
}

function retryShadow() {
  shadow.result = null
  shadow.recordPath = ''
}

function playMyRecord() {
  if (shadow.recordPath) playAudio(shadow.recordPath)
}

onMounted(load)
</script>

<style scoped>
.vocab-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); line-height: 1.8; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 40rpx 32rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,0.04); }
.progress-hint { font-size: 24rpx; color: var(--c-text-hint); margin-bottom: 24rpx; }
.word { font-size: 60rpx; font-weight: 800; color: var(--c-ink); text-align: center; }
.phonetic { font-size: 30rpx; color: var(--c-text-second); text-align: center; margin-top: 8rpx; }
.defs { margin-top: 32rpx; }
.def-line { display: block; font-size: 32rpx; color: var(--c-text-body); line-height: 1.8; }
.img-row { white-space: nowrap; margin: 20rpx 0; }
.word-img { width: 220rpx; height: 160rpx; border-radius: var(--r-md); margin-right: 16rpx; display: inline-block; background: var(--c-bg-soft); }
.en-desc { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; margin: 16rpx 0; }
.en-desc-text { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }
.audio-row { display: flex; gap: 24rpx; margin-bottom: 8rpx; }
.audio-btn { font-size: 28rpx; color: var(--c-gold); font-weight: 600; }
.examples { margin-top: 24rpx; padding-top: 20rpx; border-top: 1rpx solid var(--c-bg-soft); }
.ex-title { font-size: 24rpx; color: var(--c-text-hint); display: block; margin-bottom: 8rpx; }
.ex-row { display: flex; align-items: center; gap: 12rpx; margin-bottom: 6rpx; }
.ex-line { flex: 1; font-size: 28rpx; color: var(--c-text-second); line-height: 1.7; }
.ex-shadow-btn { flex-shrink: 0; font-size: 22rpx; font-weight: 600; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 6rpx 16rpx; border-radius: var(--r-pill); }
.quiz-type { font-size: 24rpx; color: var(--c-gold); font-weight: 600; }
.quiz-prompt { font-size: 44rpx; font-weight: 700; color: var(--c-ink); text-align: center; margin: 32rpx 0 40rpx; }
.option { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 28rpx 24rpx; font-size: 30rpx; color: var(--c-text-body); margin-bottom: 20rpx; }
.opt-correct { background: #d8f3dc; color: #1b7a3d; }
.opt-wrong { background: #fdecea; color: var(--c-danger); }
/* 看图选词 2×2 */
.pic-grid { display: flex; flex-wrap: wrap; justify-content: space-between; }
.pic-option { width: 48%; height: 220rpx; border-radius: var(--r-md); overflow: hidden; margin-bottom: 16rpx; border: 4rpx solid transparent; background: var(--c-bg-soft); }
.pic-option.opt-correct { border-color: #1b7a3d; }
.pic-option.opt-wrong { border-color: var(--c-danger); }
.pic-option-img { width: 100%; height: 100%; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; margin-top: 24rpx; }
.done { text-align: center; }
.done-emoji { font-size: 80rpx; }
.done-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); margin: 16rpx 0; }
.done-stat { font-size: 30rpx; color: var(--c-text-second); line-height: 1.9; }
.done-streak { margin-top: 20rpx; font-size: 34rpx; font-weight: 700; color: var(--c-primary); }
.done-gap { margin-top: 20rpx; font-size: 28rpx; color: var(--c-text-second); }
.checkin-panel { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin: 20rpx 0; }
.cp-summary { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.cp-badges { display: flex; gap: 12rpx; margin: 12rpx 0; flex-wrap: wrap; }
.cp-badge { font-size: 22rpx; color: var(--c-text-hint); opacity: .45; }
.cp-badge.on { color: var(--c-gold); opacity: 1; font-weight: 700; }
.cp-grid { display: flex; flex-wrap: wrap; }
.cp-cell { width: 14.28%; height: 60rpx; display: flex; align-items: center; justify-content: center; font-size: 22rpx; color: var(--c-text-body); }
.cp-cell.checked { color: var(--c-gold); font-weight: 700; }
.cp-cell.missable { color: var(--c-text-hint); border: 1rpx dashed var(--c-border); border-radius: 8rpx; }
.cp-cell.blank { visibility: hidden; }
.cp-hint { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.btn-ghost { background: var(--c-bg-soft); color: var(--c-text-body); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; margin-top: 16rpx; text-align: center; }

/* ── 跟读评分弹窗 ── */
.shadow-modal { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
.shadow-card { background: var(--c-bg-card); border-radius: var(--r-xl); padding: 40rpx 36rpx; width: 84%; max-width: 640rpx; display: flex; flex-direction: column; align-items: center; }
.shadow-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); margin-bottom: 20rpx; }
.shadow-sentence { font-size: 32rpx; font-weight: 600; color: var(--c-ink); line-height: 1.6; text-align: center; }
.shadow-tools { margin: 20rpx 0; }
.shadow-demo { font-size: 26rpx; font-weight: 600; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 10rpx 28rpx; border-radius: var(--r-pill); }
.shadow-rec-area { display: flex; flex-direction: column; align-items: center; gap: 12rpx; margin-top: 12rpx; width: 100%; }
.shadow-rec-btn { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); font-size: 30rpx; font-weight: 700; padding: 22rpx 0; width: 100%; }
.shadow-rec-btn.recording { background: var(--c-danger); }
.shadow-rec-btn[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.shadow-hint { font-size: 22rpx; color: var(--c-text-hint); }
.shadow-result { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 18rpx; margin-top: 8rpx; }
.shadow-score { display: flex; align-items: baseline; gap: 10rpx; }
.ss-num { font-size: 80rpx; font-weight: 900; line-height: 1; }
.ss-unit { font-size: 26rpx; color: var(--c-text-second); }
.shadow-score.lv-excellent .ss-num, .shadow-score.lv-good .ss-num { color: #18a058; }
.shadow-score.lv-fair .ss-num { color: var(--c-gold); }
.shadow-score.lv-poor .ss-num { color: var(--c-danger); }
.shadow-words { display: flex; flex-wrap: wrap; gap: 12rpx; justify-content: center; }
.sw-chip { font-size: 24rpx; color: var(--c-text-body); background: var(--c-bg-soft); padding: 6rpx 16rpx; border-radius: var(--r-pill); }
.sw-chip.weak { background: var(--c-danger-bg); color: var(--c-danger); font-weight: 600; }
.sw-score { font-size: 20rpx; opacity: .8; }
.shadow-tip { font-size: 26rpx; color: var(--c-text-second); line-height: 1.6; text-align: center; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx 20rpx; width: 100%; box-sizing: border-box; }
.shadow-actions { display: flex; gap: 16rpx; width: 100%; }
.shadow-actions .half { flex: 1; margin-top: 0; }
.shadow-close { margin-top: 24rpx; font-size: 26rpx; color: var(--c-text-hint); }
</style>

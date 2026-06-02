<!-- src/pages/vocabulary/index.vue 词力通背词 -->
<template>
  <view class="vocab-page">
    <view v-if="loading" class="center-tip">加载今日任务…</view>

    <view v-else-if="phase === 'empty'" class="center-tip">
      🎉 今日没有待学/待复习的单词，明天再来吧！
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
        <text v-for="(e, i) in exampleList(curStudy)" :key="i" class="ex-line">{{ e }}</text>
      </view>
      <button class="btn-primary" @tap="nextStudy">记住了，下一个</button>
    </view>

    <!-- 测试阶段：4 选 1 -->
    <view v-else-if="phase === 'quiz'" class="card">
      <view class="progress-hint">测试 {{ quizIndex + 1 }} / {{ quizQueue.length }} · 正确 {{ correctCount }}</view>
      <view class="quiz-type">{{ curQuiz.mode === 'w2m' ? '看词选义' : '看义选词' }}</view>
      <view class="quiz-prompt">{{ curQuiz.prompt }}</view>
      <view
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
      <button class="btn-primary" @tap="reload">再来一组</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getDailyTask, submitVocabAnswer } from '@/api/vocabulary'
import { useAuthStore } from '@/stores/auth'
import type { VocabWordCard } from '@/types/api'

interface Quiz {
  word_id: string
  mode: 'w2m' | 'm2w'   // 看词选义 / 看义选词
  prompt: string
  options: string[]
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

const curStudy = computed(() => newCards.value[studyIndex.value] || ({} as VocabWordCard))
const curQuiz = computed(() => quizQueue.value[quizIndex.value] || ({} as Quiz))

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

function buildQuiz(card: VocabWordCard, mode: 'w2m' | 'm2w'): Quiz {
  const others = pool.value.filter((w) => w.word_id !== card.word_id)
  const distractors = shuffle(others).slice(0, 3)
  if (mode === 'w2m') {
    const correct = primaryMeaning(card)
    const opts = shuffle([correct, ...distractors.map((w) => primaryMeaning(w))])
    return { word_id: card.word_id, mode, prompt: card.word, options: opts, answerIndex: opts.indexOf(correct) }
  }
  const correct = card.word
  const opts = shuffle([correct, ...distractors.map((w) => w.word)])
  return { word_id: card.word_id, mode, prompt: primaryMeaning(card), options: opts, answerIndex: opts.indexOf(correct) }
}

function startQuiz() {
  const all = [...newCards.value, ...reviewCards.value]
  quizQueue.value = all.map((card, i) =>
    buildQuiz(card, i % 2 === 0 ? 'w2m' : 'm2w'),
  )
  quizIndex.value = 0
  correctCount.value = 0
  answered.value = false
  chosenIndex.value = -1
  phase.value = quizQueue.value.length ? 'quiz' : 'done'
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
    phase.value = 'done'
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

function reload() {
  load()
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
.examples { margin-top: 24rpx; padding-top: 20rpx; border-top: 1rpx solid var(--c-bg-soft); }
.ex-title { font-size: 24rpx; color: var(--c-text-hint); display: block; margin-bottom: 8rpx; }
.ex-line { display: block; font-size: 28rpx; color: var(--c-text-second); line-height: 1.7; }
.quiz-type { font-size: 24rpx; color: var(--c-gold); font-weight: 600; }
.quiz-prompt { font-size: 44rpx; font-weight: 700; color: var(--c-ink); text-align: center; margin: 32rpx 0 40rpx; }
.option { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 28rpx 24rpx; font-size: 30rpx; color: var(--c-text-body); margin-bottom: 20rpx; }
.opt-correct { background: #d8f3dc; color: #1b7a3d; }
.opt-wrong { background: #fdecea; color: var(--c-danger); }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; margin-top: 24rpx; }
.done { text-align: center; }
.done-emoji { font-size: 80rpx; }
.done-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); margin: 16rpx 0; }
.done-stat { font-size: 30rpx; color: var(--c-text-second); line-height: 1.9; }
</style>

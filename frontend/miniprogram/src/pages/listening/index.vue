<template>
  <view class="lst-page">
    <view v-if="loading" class="center-tip">加载中…</view>

    <!-- 素材列表 -->
    <view v-else-if="phase === 'list'">
      <view class="list-head">
        <text class="lh-title">🎧 听力练习</text>
        <text class="lh-sub">先看题 → 听音作答 → 对答案 → 回听原文</text>
      </view>
      <view
        v-for="ex in exercises" :key="ex.id"
        class="ex-card" @tap="openExercise(ex.id)"
      >
        <view class="ex-badge" :class="`bd-${ex.type}`">{{ ex.type === 'dialogue' ? '对话' : '短文' }}</view>
        <view class="ex-body">
          <text class="ex-title">{{ ex.title }}</text>
          <text class="ex-meta">{{ ex.question_count }} 题 · 难度 {{ ex.difficulty }}</text>
        </view>
        <text class="ex-arrow">›</text>
      </view>
    </view>

    <!-- 答题 / 结果 -->
    <view v-else>
      <view class="card audio-card">
        <text class="ac-title">{{ detail.title }}</text>
        <button class="play-btn" :class="{ playing }" @tap="playAudio">
          {{ playing ? '⏸ 暂停' : (audioLoaded ? '▶ 重听' : '▶ 播放音频') }}
        </button>
        <text class="ac-hint">{{ phase === 'doing' ? '听音频，选出每题答案' : '可回听音频，对照下方原文' }}</text>
      </view>

      <!-- 题目 -->
      <view v-for="(q, qi) in detail.questions" :key="qi" class="card q-card">
        <text class="q-prompt">{{ qi + 1 }}. {{ q.prompt }}</text>
        <view
          v-for="(opt, oi) in q.options" :key="oi"
          class="q-option"
          :class="optionClass(qi, oi)"
          @tap="phase === 'doing' ? selectOption(qi, oi) : null"
        >
          <text class="qo-letter">{{ letter(oi) }}</text>
          <text class="qo-text">{{ opt }}</text>
        </view>
        <view v-if="phase === 'result'" class="q-exp">
          <text class="qe-tag" :class="answers[qi] === q.answer_index ? 'ok' : 'no'">
            {{ answers[qi] === q.answer_index ? '✓ 答对' : '✗ 答错' }}
          </text>
          <text class="qe-text">{{ q.explanation }}</text>
        </view>
      </view>

      <!-- 提交 -->
      <button
        v-if="phase === 'doing'"
        class="btn-primary"
        :disabled="!allAnswered"
        @tap="submit"
      >{{ allAnswered ? '提交答案' : `还有 ${unanswered} 题未作答` }}</button>

      <!-- 结果区 -->
      <view v-else>
        <view class="card score-card">
          <text class="sc-num">{{ correctCount }}/{{ detail.questions.length }}</text>
          <text class="sc-label">答对题数</text>
        </view>
        <view class="card transcript-card">
          <text class="tc-title">📄 听力原文</text>
          <text class="tc-text">{{ detail.transcript }}</text>
        </view>
        <button class="btn-secondary" @tap="retry">🔁 再做一次</button>
        <button class="btn-ghost" @tap="backToList">返回列表</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getListeningExercises, getListeningExercise } from '@/api/listening'
import type { ListeningBrief, ListeningDetail } from '@/api/listening'
import { resolveSpeakUrl } from '@/utils/tts'

const loading = ref(true)
const phase = ref<'list' | 'doing' | 'result'>('list')
const exercises = ref<ListeningBrief[]>([])
const detail = ref<ListeningDetail>({} as ListeningDetail)
const answers = ref<number[]>([])

onMounted(async () => {
  try {
    exercises.value = await getListeningExercises()
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

async function openExercise(id: string) {
  loading.value = true
  try {
    detail.value = await getListeningExercise(id)
    answers.value = new Array(detail.value.questions.length).fill(-1)
    phase.value = 'doing'
    audioLoaded.value = false
    resetAudio()
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function letter(i: number) { return ['A', 'B', 'C', 'D'][i] ?? '' }

function selectOption(qi: number, oi: number) {
  answers.value[qi] = oi
}

const unanswered = computed(() => answers.value.filter(a => a < 0).length)
const allAnswered = computed(() => unanswered.value === 0)
const correctCount = computed(() =>
  detail.value.questions?.reduce((n, q, i) => n + (answers.value[i] === q.answer_index ? 1 : 0), 0) || 0,
)

function optionClass(qi: number, oi: number) {
  if (phase.value === 'doing') {
    return answers.value[qi] === oi ? 'selected' : ''
  }
  // result：标出正确答案 + 标错选项
  const q = detail.value.questions[qi]
  if (oi === q.answer_index) return 'correct'
  if (answers.value[qi] === oi) return 'wrong'
  return ''
}

function submit() {
  phase.value = 'result'
  uni.pageScrollTo({ scrollTop: 0, duration: 200 })
}

function retry() {
  answers.value = new Array(detail.value.questions.length).fill(-1)
  phase.value = 'doing'
  uni.pageScrollTo({ scrollTop: 0, duration: 200 })
}

function backToList() {
  resetAudio()
  phase.value = 'list'
}

// ── 音频 ──
let _ctx: UniApp.InnerAudioContext | null = null
const playing = ref(false)
const audioLoaded = ref(false)

function resetAudio() {
  if (_ctx) { try { _ctx.stop() } catch { /* ignore */ } }
  playing.value = false
}

async function playAudio() {
  if (!detail.value.transcript) return
  if (!_ctx) {
    _ctx = uni.createInnerAudioContext()
    _ctx.onPlay(() => { playing.value = true; audioLoaded.value = true })
    _ctx.onEnded(() => { playing.value = false })
    _ctx.onStop(() => { playing.value = false })
    _ctx.onError(() => { playing.value = false })
  }
  if (playing.value) { _ctx.pause(); playing.value = false; return }
  _ctx.src = await resolveSpeakUrl(detail.value.transcript)
  _ctx.play()
}
</script>

<style scoped>
.lst-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 0; color: var(--c-text-hint); font-size: 28rpx; }

.list-head { margin-bottom: 20rpx; }
.lh-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lh-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }

.ex-card { display: flex; align-items: center; gap: 18rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx 24rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.ex-badge { flex-shrink: 0; font-size: 24rpx; font-weight: 700; padding: 8rpx 18rpx; border-radius: var(--r-pill); }
.bd-dialogue { background: var(--c-primary-faint); color: var(--c-primary-deep); }
.bd-monologue { background: #fff0e0; color: #c98314; }
.ex-body { flex: 1; display: flex; flex-direction: column; gap: 6rpx; min-width: 0; }
.ex-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.ex-meta { font-size: 22rpx; color: var(--c-text-hint); }
.ex-arrow { font-size: 40rpx; color: var(--c-text-disabled, #c4ccd6); }

.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.audio-card { display: flex; flex-direction: column; align-items: center; gap: 16rpx; }
.ac-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.play-btn { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); font-size: 30rpx; font-weight: 700; padding: 20rpx 0; width: 100%; }
.play-btn.playing { background: var(--c-primary-deep); }
.ac-hint { font-size: 22rpx; color: var(--c-text-hint); }

.q-card { display: flex; flex-direction: column; gap: 14rpx; }
.q-prompt { font-size: 30rpx; font-weight: 700; color: var(--c-ink); line-height: 1.5; }
.q-option { display: flex; align-items: center; gap: 16rpx; padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); background: #fff; }
.qo-letter { width: 44rpx; height: 44rpx; flex-shrink: 0; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--c-bg-soft); color: var(--c-text-second); font-size: 24rpx; font-weight: 800; }
.qo-text { flex: 1; font-size: 28rpx; color: var(--c-text-body); }
.q-option.selected { border-color: var(--c-primary); background: var(--c-primary-faint); }
.q-option.selected .qo-letter { background: var(--c-primary); color: var(--c-on-primary); }
.q-option.correct { border-color: #2ecc71; background: #eafaf1; }
.q-option.correct .qo-letter { background: #2ecc71; color: #fff; }
.q-option.wrong { border-color: var(--c-danger); background: var(--c-danger-bg); }
.q-option.wrong .qo-letter { background: var(--c-danger); color: #fff; }
.q-exp { display: flex; flex-direction: column; gap: 6rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; }
.qe-tag { font-size: 24rpx; font-weight: 700; }
.qe-tag.ok { color: #18a058; }
.qe-tag.no { color: var(--c-danger); }
.qe-text { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; }

.score-card { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.sc-num { font-size: 64rpx; font-weight: 900; color: var(--c-primary); }
.sc-label { font-size: 24rpx; color: var(--c-text-hint); }
.transcript-card { }
.tc-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); display: block; margin-bottom: 12rpx; }
.tc-text { font-size: 28rpx; color: var(--c-text-body); line-height: 1.9; }

.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.btn-secondary { background: var(--c-primary-faint); color: var(--c-primary-deep); border: 2rpx solid var(--c-primary-soft); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; margin-bottom: 12rpx; }
.btn-ghost { background: var(--c-bg-soft); color: var(--c-text-body); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; text-align: center; }
</style>

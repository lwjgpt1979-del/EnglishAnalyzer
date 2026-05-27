<!-- src/pages/practice/index.vue -->
<template>
  <view class="practice-page">

    <!-- 开始界面 -->
    <view v-if="phase === 'start'" class="card">
      <view class="card-title">AI 仿真题练习</view>
      <text class="hint">针对你的薄弱知识点生成练习题。留空则自动选取最薄弱知识点。</text>
      <input
        v-model="kpInput"
        class="input"
        placeholder="目标知识点（选填，如：一般现在时）"
      />
      <view class="row">
        <text class="row-label">题量</text>
        <view class="seg">
          <text
            v-for="n in [3, 5, 8]"
            :key="n"
            class="seg-item"
            :class="{ active: count === n }"
            @tap="count = n"
          >{{ n }}</text>
        </view>
      </view>
      <view class="row">
        <text class="row-label">难度</text>
        <view class="seg">
          <text
            v-for="d in [1, 2, 3, 4, 5]"
            :key="d"
            class="seg-item"
            :class="{ active: difficulty === d }"
            @tap="difficulty = d"
          >{{ d }}</text>
        </view>
      </view>
      <button class="btn-primary" :disabled="loading" @tap="startPractice">
        {{ loading ? '出题中（约3-8秒）…' : '开始练习' }}
      </button>
    </view>

    <!-- 答题界面 -->
    <view v-else-if="phase === 'doing'" class="card">
      <view class="progress">第 {{ currentIndex + 1 }} / {{ questions.length }} 题 · {{ current.knowledge_point_name }}</view>
      <view class="stem">{{ current.stem }}</view>
      <view
        v-for="opt in current.options"
        :key="opt"
        class="option"
        :class="optionClass(opt)"
        @tap="selectOption(opt)"
      >{{ opt }}</view>

      <view v-if="result" class="result-box" :class="result.is_correct ? 'ok' : 'bad'">
        <text class="result-title">{{ result.is_correct ? '✅ 回答正确' : '❌ 回答错误' }}</text>
        <text v-if="!result.is_correct" class="result-answer">正确答案：{{ result.correct_answer }}</text>
        <text class="result-explain">{{ result.explanation }}</text>
      </view>

      <button
        v-if="!result"
        class="btn-primary"
        :disabled="!selected || submitting"
        @tap="submitCurrent"
      >{{ submitting ? '提交中…' : '提交答案' }}</button>
      <button v-else class="btn-primary" @tap="nextQuestion">
        {{ currentIndex + 1 < questions.length ? '下一题' : '查看小结' }}
      </button>
    </view>

    <!-- 小结界面 -->
    <view v-else class="card">
      <view class="card-title">练习小结</view>
      <view class="summary-score">{{ correctCount }} / {{ questions.length }}</view>
      <text class="summary-rate">正确率 {{ Math.round((correctCount / questions.length) * 100) }}%</text>
      <button class="btn-primary" @tap="restart">再练一组</button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { generateQuestions, submitAnswer } from '@/api/practice'
import type { PracticeQuestionOut, SubmitAnswerResult } from '@/types/api'

type Phase = 'start' | 'doing' | 'summary'

const phase = ref<Phase>('start')
const kpInput = ref('')
const count = ref(5)
const difficulty = ref(3)
const loading = ref(false)

const questions = ref<PracticeQuestionOut[]>([])
const currentIndex = ref(0)
const selected = ref('')
const submitting = ref(false)
const result = ref<SubmitAnswerResult | null>(null)
const correctCount = ref(0)
let questionStart = 0

const current = computed(() => questions.value[currentIndex.value])

async function startPractice() {
  loading.value = true
  try {
    const data = await generateQuestions(kpInput.value || null, count.value, difficulty.value)
    if (data.length === 0) {
      uni.showToast({ title: '未生成题目，请重试', icon: 'none' })
      return
    }
    questions.value = data
    currentIndex.value = 0
    correctCount.value = 0
    result.value = null
    selected.value = ''
    questionStart = Date.now()
    phase.value = 'doing'
  } catch (e: any) {
    uni.showToast({ title: e?.message || '出题失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function selectOption(opt: string) {
  if (result.value) return
  selected.value = opt
}

function optionClass(opt: string) {
  if (!result.value) return { selected: selected.value === opt }
  if (opt === result.value.correct_answer) return { correct: true }
  if (opt === selected.value) return { wrong: true }
  return {}
}

async function submitCurrent() {
  if (!selected.value) return
  submitting.value = true
  try {
    const timeSpent = Math.round((Date.now() - questionStart) / 1000)
    const res = await submitAnswer(current.value.id, selected.value, timeSpent)
    result.value = res
    if (res.is_correct) correctCount.value++
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function nextQuestion() {
  if (currentIndex.value + 1 < questions.value.length) {
    currentIndex.value++
    selected.value = ''
    result.value = null
    questionStart = Date.now()
  } else {
    phase.value = 'summary'
  }
}

function restart() {
  phase.value = 'start'
}
</script>

<style scoped>
.practice-page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.hint { font-size: 24rpx; color: var(--c-text-second); display: block; margin-bottom: 16rpx; line-height: 1.5; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin-bottom: 16rpx; width: 100%; box-sizing: border-box; }
.row { display: flex; align-items: center; margin-bottom: 16rpx; }
.row-label { width: 80rpx; font-size: 26rpx; color: var(--c-text-second); }
.seg { display: flex; gap: 12rpx; flex: 1; }
.seg-item { flex: 1; text-align: center; padding: 12rpx 0; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 26rpx; color: var(--c-text-second); }
.seg-item.active { border-color: var(--c-gold); color: var(--c-ink); background: var(--c-primary-faint); font-weight: 600; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; font-weight: 700; text-align: center; margin-top: 8rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.progress { font-size: 24rpx; color: var(--c-text-second); margin-bottom: 16rpx; }
.stem { font-size: 30rpx; color: var(--c-ink); line-height: 1.6; margin-bottom: 20rpx; }
.option { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 18rpx 20rpx; font-size: 28rpx; color: var(--c-text-body); margin-bottom: 12rpx; }
.option.selected { border-color: var(--c-gold); background: var(--c-primary-faint); }
.option.correct { border-color: var(--c-success); background: var(--c-success-bg); color: var(--c-success-dark); }
.option.wrong { border-color: var(--c-danger); background: var(--c-danger-bg); color: var(--c-danger-dark); }
.result-box { border-radius: var(--r-md); padding: 16rpx; margin: 16rpx 0; display: flex; flex-direction: column; gap: 6rpx; }
.result-box.ok { background: var(--c-success-bg); }
.result-box.bad { background: var(--c-danger-bg); }
.result-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.result-answer { font-size: 26rpx; color: var(--c-danger-dark); }
.result-explain { font-size: 26rpx; color: var(--c-text-second); line-height: 1.5; }
.summary-score { font-size: 64rpx; font-weight: 800; color: var(--c-ink); text-align: center; margin: 24rpx 0 8rpx; }
.summary-rate { font-size: 28rpx; color: var(--c-text-second); text-align: center; display: block; margin-bottom: 24rpx; }
</style>

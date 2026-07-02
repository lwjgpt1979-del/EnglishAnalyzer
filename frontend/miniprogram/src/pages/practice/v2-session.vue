<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!questions.length" class="empty">该知识点暂无题目</view>

    <view v-else-if="!finished">
      <view class="progress">
        <text>{{ currentIdx + 1 }} / {{ questions.length }}</text>
      </view>

      <view class="card">
        <view class="qtype">{{ current.question_type }} · 难度 {{ current.difficulty }}</view>
        <view v-if="current.passage" class="passage"><text>{{ current.passage }}</text></view>
        <text class="stem">{{ current.stem }}</text>

        <view v-if="hasOptions(current)" class="options">
          <view
            v-for="(opt, i) in current.options" :key="i"
            class="option"
            :class="{
              selected: userAnswer === letter(i),
              correct: feedback && letter(i) === feedback.correct_answer,
              wrong: feedback && userAnswer === letter(i) && !feedback.correct,
            }"
            @tap="feedback ? null : (userAnswer = letter(i))"
          >{{ opt }}</view>
        </view>

        <view v-else-if="current.question_type === '填空'" class="fill">
          <input
            v-model="userAnswer"
            class="fill-input"
            placeholder="请输入答案"
            :disabled="!!feedback"
          />
        </view>

        <view v-else-if="current.question_type === '判断'" class="judge">
          <view
            v-for="opt in ['对', '错']" :key="opt"
            class="option"
            :class="{
              selected: userAnswer === opt,
              correct: feedback && opt === feedback.correct_answer,
              wrong: feedback && userAnswer === opt && !feedback.correct,
            }"
            @tap="feedback ? null : (userAnswer = opt)"
          >{{ opt }}</view>
        </view>

        <view v-if="feedback" class="feedback" :class="{ ok: feedback.correct }">
          <view class="fb-title"><view class="ic fb-ic" :class="feedback.correct ? 'ic-check-circle' : 'ic-x-circle'" /><text>{{ feedback.correct ? '答对了' : '答错了' }}</text></view>
          <text class="fb-ans">正确答案：{{ feedback.correct_answer }}</text>
          <text class="fb-exp">{{ feedback.explanation }}</text>
        </view>

        <button
          class="btn-primary"
          :disabled="!canSubmit"
          @tap="feedback ? next() : submit()"
        >
          {{ feedback ? (isLast ? '完成' : '下一题') : '提交答案' }}
        </button>
      </view>
    </view>

    <view v-else class="finish-card card">
      <text class="finish-title">练习完成</text>
      <text class="finish-meta">共 {{ questions.length }} 题，对 {{ correctCount }} 道</text>
      <button class="btn-primary" @tap="goBack">返回</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listPracticeQuestions, submitAttempt } from '@/api/questions'
import type { SimQuestionOut, PracticeResultOut } from '@/types/api'

const kpId = ref('')
const dim = ref('')
const questions = ref<SimQuestionOut[]>([])
const currentIdx = ref(0)
const userAnswer = ref('')
const feedback = ref<PracticeResultOut | null>(null)
const correctCount = ref(0)
const loading = ref(true)
const finished = ref(false)

const current = computed(() => questions.value[currentIdx.value])
const isLast = computed(() => currentIdx.value === questions.value.length - 1)
const canSubmit = computed(() => !!feedback.value || (userAnswer.value && userAnswer.value.trim()))

function letter(i: number): string {
  return ['A', 'B', 'C', 'D'][i] || ''
}

// 单选/完型/阅读 皆为 A-D 选项作答(物化后如实继承题型,不再只认单选)
function hasOptions(q: SimQuestionOut): boolean {
  return ['单选', '完型', '阅读'].includes(q.question_type) && !!q.options
}

onLoad(async (q: any) => {
  kpId.value = q.kp || ''
  dim.value = q.dim || ''
  if (!kpId.value) {
    uni.showToast({ title: '缺少 kp 参数', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  try {
    questions.value = await listPracticeQuestions(kpId.value, 5, dim.value)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

async function submit() {
  if (!current.value) return
  try {
    const r = await submitAttempt({
      question_id: current.value.id,
      user_answer: userAnswer.value.trim(),
    })
    feedback.value = r
    if (r.correct) correctCount.value++
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  }
}

function next() {
  if (isLast.value) {
    finished.value = true
    return
  }
  currentIdx.value++
  userAnswer.value = ''
  feedback.value = null
}

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.progress { text-align: center; padding: 16rpx 0; font-size: 24rpx; color: var(--c-text-second); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qtype { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.passage { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx 20rpx; margin-bottom: 16rpx; font-size: 26rpx; color: var(--c-text-body); line-height: 1.7; white-space: pre-wrap; max-height: 480rpx; overflow-y: auto; }
.stem { display: block; font-size: 30rpx; font-weight: 600; color: var(--c-ink); line-height: 1.5; margin-bottom: 24rpx; }
.options, .judge { display: flex; flex-direction: column; gap: 12rpx; margin-bottom: 24rpx; }
.option { padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 28rpx; color: var(--c-text-body); }
.option.selected { border-color: var(--c-gold); background: var(--c-primary-faint); font-weight: 600; }
.option.correct { border-color: #2ecc71; background: #eafaf1; }
.option.wrong { border-color: var(--c-danger); background: var(--c-danger-bg); }
.fill-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); height: 72rpx; line-height: 72rpx; padding: 0 20rpx; font-size: 28rpx; margin-bottom: 24rpx; box-sizing: border-box; width: 100%; }
.feedback { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 8rpx; }
.feedback.ok { background: #eafaf1; }
.fb-title { display: flex; align-items: center; gap: 8rpx; font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.fb-ic { width: 32rpx; height: 32rpx; }
.fb-ans { font-size: 24rpx; color: var(--c-text-body); }
.fb-exp { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.finish-card { display: flex; flex-direction: column; gap: 16rpx; align-items: center; text-align: center; padding: 48rpx; }
.finish-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); }
.finish-meta { font-size: 28rpx; color: var(--c-text-second); }
</style>

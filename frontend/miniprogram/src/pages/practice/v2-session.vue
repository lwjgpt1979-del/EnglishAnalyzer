<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!questions.length" class="empty">该知识点暂无题目</view>
    <PracticeQuiz
      v-else
      kp=""
      :questions="quizQuestions"
      :judge="judge"
      last-label="完成"
      @close="goBack"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listPracticeQuestions, submitAttempt } from '@/api/questions'
import PracticeQuiz, { type ChosenAnswer } from '@/components/PracticeQuiz.vue'
import type { SimQuestionOut } from '@/types/api'
import type { PracticeQuestion } from '@/api/wrongQuestions'

const kpId = ref('')
const dim = ref('')
const questions = ref<SimQuestionOut[]>([])
const loading = ref(true)

// 题目 → PracticeQuestion(有语篇则并进题干;答案由服务端判分)
const quizQuestions = computed<PracticeQuestion[]>(() => questions.value.map(q => ({
  id: q.id,
  stem: (q.passage ? q.passage + '\n\n' : '') + q.stem,
  options: q.options || null,
  answer: null,
  explanation: null,
})))
function isJudge(q: PracticeQuestion): boolean {
  return !!(q.options && q.options.length === 2 && q.options.every(o => o === '对' || o === '错'))
}
async function judge(q: PracticeQuestion, ans: ChosenAnswer) {
  // 单选/完型/阅读传字母;判断传对/错;填空传输入
  const ua = q.options && q.options.length ? (isJudge(q) ? ans.text : ans.letter) : ans.input
  const r = await submitAttempt({ question_id: q.id, user_answer: ua })
  return { correct: r.correct, correct_answer: r.correct_answer, explanation: r.explanation }
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

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
</style>

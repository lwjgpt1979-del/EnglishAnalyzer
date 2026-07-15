<template>
  <view class="page">
    <view v-if="loading" class="empty">正在为你智能组卷…</view>

    <view v-else-if="!questions.length" class="empty-card card">
      <view class="ic ic-edit empty-icon" />
      <text class="empty-title">暂无推荐题目</text>
      <text class="empty-hint">先完成一些练习或上传作业，AI 就能为你精准出题了</text>
      <button class="btn-primary" @tap="goBack">返回</button>
    </view>

    <!-- 答题:统一走 PracticeQuiz(逐题作答判分);结果页由本页自渲染(按 KP 统计) -->
    <PracticeQuiz
      v-else-if="!finished"
      :kp="unitTitle || (weakKpNames[0] || '智能练习')"
      :questions="quizQuestions"
      :judge="judge"
      hide-result
      @finish="onFinish"
      @close="onClose"
    />

    <!-- 完成:按 KP 统计 -->
    <view v-else class="finish-card card">
      <view class="ic ic-sparkle finish-icon" />
      <text class="finish-title">智能练习完成</text>
      <text class="finish-meta">共 {{ questions.length }} 题，答对 {{ correctCount }} 道</text>
      <text class="finish-rate">正确率 {{ Math.round(correctCount / questions.length * 100) }}%</text>

      <view v-if="kpStats.length" class="kp-breakdown">
        <text class="kp-breakdown-title">各知识点表现</text>
        <view v-for="stat in kpStats" :key="stat.name" class="kp-stat-row">
          <text class="kp-stat-name">{{ stat.name }}</text>
          <view class="kp-stat-bar-wrap">
            <view
              class="kp-stat-bar"
              :style="{ width: (stat.total > 0 ? stat.correct / stat.total * 100 : 0) + '%' }"
              :class="stat.correct === stat.total ? 'full' : stat.correct > 0 ? 'partial' : 'none'"
            />
          </view>
          <text class="kp-stat-num">{{ stat.correct }}/{{ stat.total }}</text>
        </view>
      </view>

      <view class="finish-actions">
        <button class="btn-primary" @tap="retryAdaptive">再练一组 →</button>
        <button class="btn-secondary" @tap="goDiagnosis">查看学情报告</button>
        <button class="btn-ghost" @tap="goBack">返回</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getAdaptiveSet, submitAttempt } from '@/api/questions'
import PracticeQuiz, { type ChosenAnswer } from '@/components/PracticeQuiz.vue'
import type { SimQuestionOut } from '@/types/api'
import type { PracticeQuestion } from '@/api/wrongQuestions'

const loading = ref(true)
const questions = ref<SimQuestionOut[]>([])
const weakKpNames = ref<string[]>([])
const correctCount = ref(0)
const finished = ref(false)
const unitId = ref<string | undefined>(undefined)
const unitTitle = ref('')

interface AnswerRecord { kp_name: string; correct: boolean }
const answerRecords = ref<AnswerRecord[]>([])
const byId = computed(() => Object.fromEntries(questions.value.map(q => [q.id, q])))

const quizQuestions = computed<PracticeQuestion[]>(() => questions.value.map(q => ({
  id: q.id,
  stem: (q.passage ? q.passage + '\n\n' : '') + q.stem,
  options: q.options || null,
  answer: null,
  explanation: null,
})))

const kpStats = computed(() => {
  const map = new Map<string, { correct: number; total: number }>()
  for (const r of answerRecords.value) {
    const name = r.kp_name || '其他'
    const slot = map.get(name) || { correct: 0, total: 0 }
    slot.total++
    if (r.correct) slot.correct++
    map.set(name, slot)
  }
  return Array.from(map.entries()).map(([name, s]) => ({ name, ...s }))
})

function isJudge(q: PracticeQuestion): boolean {
  return !!(q.options && q.options.length === 2 && q.options.every(o => o === '对' || o === '错'))
}
async function judge(q: PracticeQuestion, ans: ChosenAnswer) {
  const ua = q.options && q.options.length ? (isJudge(q) ? ans.text : ans.letter) : ans.input
  const r = await submitAttempt({ question_id: q.id, user_answer: ua })
  answerRecords.value.push({ kp_name: byId.value[q.id]?.kp_name || '其他', correct: r.correct })
  return { correct: r.correct, correct_answer: r.correct_answer, explanation: r.explanation }
}
function onFinish(_total: number, correct: number) {
  correctCount.value = correct
  finished.value = true
}
function onClose() {
  if (!finished.value) goBack()
}

async function loadAdaptiveSet() {
  loading.value = true
  try {
    const result = await getAdaptiveSet(5, unitId.value)
    questions.value = result.questions
    weakKpNames.value = result.weak_kp_names
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onLoad((q: any) => {
  unitId.value = q?.unit_id || undefined
  unitTitle.value = q?.unit_title ? decodeURIComponent(q.unit_title) : ''
  loadAdaptiveSet()
})

function goBack() { uni.navigateBack() }
function retryAdaptive() {
  questions.value = []
  weakKpNames.value = []
  correctCount.value = 0
  finished.value = false
  answerRecords.value = []
  loading.value = true
  loadAdaptiveSet()
}
function goDiagnosis() { uni.switchTab({ url: '/pages/diagnosis/index' }) }
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.btn-primary { background: #7ba6c9; color: #fff; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.empty-card { display: flex; flex-direction: column; align-items: center; gap: 16rpx; padding: 60rpx 40rpx; text-align: center; }
.empty-icon { width: 80rpx; height: 80rpx; }
.empty-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-ink); }
.empty-hint { font-size: 26rpx; color: var(--c-text-second); line-height: 1.6; }
.finish-card { display: flex; flex-direction: column; gap: 16rpx; align-items: center; text-align: center; padding: 48rpx; }
.finish-icon { width: 80rpx; height: 80rpx; }
.finish-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); }
.finish-meta { font-size: 28rpx; color: var(--c-text-second); }
.finish-rate { font-size: 40rpx; font-weight: 800; color: var(--c-gold); }
.kp-breakdown { width: 100%; margin-top: 8rpx; margin-bottom: 8rpx; }
.kp-breakdown-title { font-size: 24rpx; color: var(--c-text-hint); display: block; text-align: left; margin-bottom: 12rpx; }
.kp-stat-row { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; }
.kp-stat-name { font-size: 24rpx; color: var(--c-text-body); width: 160rpx; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; flex-shrink: 0; text-align: left; }
.kp-stat-bar-wrap { flex: 1; height: 12rpx; background: #f0f0f0; border-radius: 999rpx; overflow: hidden; }
.kp-stat-bar { height: 100%; border-radius: 999rpx; transition: width 0.4s; }
.kp-stat-bar.full { background: #22c55e; }
.kp-stat-bar.partial { background: #ffb020; }
.kp-stat-bar.none { background: #ef4444; width: 4rpx !important; }
.kp-stat-num { font-size: 22rpx; color: var(--c-text-hint); width: 60rpx; text-align: right; flex-shrink: 0; }
.finish-actions { width: 100%; display: flex; flex-direction: column; gap: 16rpx; margin-top: 8rpx; }
.btn-secondary { background: #fff; color: var(--c-ink); border: 2rpx solid var(--c-border); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-ghost { background: transparent; color: var(--c-text-hint); border: none; font-size: 26rpx; padding: 8rpx; }
</style>

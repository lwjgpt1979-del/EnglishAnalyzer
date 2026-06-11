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
          <text class="exam-title">自助模拟卷 · {{ questions.length }} 题</text>
          <text class="timer" :class="{ urgent: remain <= 60 }">⏱ {{ mmss }}</text>
        </view>
        <text class="exam-sub">薄弱点：{{ (exam.weak_kps || []).join(' · ') || '综合' }}</text>
      </view>

      <view v-for="(q, idx) in questions" :key="q.id" class="card">
        <view class="qtype">第 {{ idx + 1 }} 题 · {{ q.question_type }}</view>
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
        <view v-else class="fill">
          <input v-model="answers[q.id]" class="fill-input" placeholder="请输入答案" />
        </view>
      </view>
      <view style="height: 150rpx;" />
    </scroll-view>

    <!-- 结果 -->
    <scroll-view v-else scroll-y class="list">
      <view class="score-card card">
        <text class="score-num">{{ result.correct_count }} / {{ result.total }}</text>
        <text class="score-meta">答对 {{ result.correct_count }}，答错 {{ result.total - result.correct_count }}（错题已入错题本）</text>
      </view>
      <view
        v-for="(it, idx) in result.items" :key="it.question_id"
        class="card result-card" :class="{ ok: it.correct }"
      >
        <view class="res-head">
          <text class="res-idx">第 {{ idx + 1 }} 题</text>
          <text class="res-flag" :class="{ ok: it.correct }">{{ it.correct ? '✓ 正确' : '✗ 错误' }}</text>
        </view>
        <text class="res-line">你的答案：{{ it.user_answer || '（未作答）' }}</text>
        <text class="res-line right">正确答案：{{ it.correct_answer }}</text>
        <text v-if="it.explanation" class="res-exp">{{ it.explanation }}</text>
      </view>
      <view class="practice-bar fixed"><button class="btn-primary" @tap="goBack">返回</button></view>
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
import { getSelfExam, submitSelfExam, type SelfExamOut, type SelfExamQuestion } from '@/api/selfExam'
import type { ExamResultOut } from '@/types/api'

const loading = ref(true)
const reviewOnly = ref(false)
const submitting = ref(false)
const examId = ref('')
const exam = reactive<Partial<SelfExamOut>>({})
const questions = ref<SelfExamQuestion[]>([])
const answers = reactive<Record<string, string>>({})
const result = ref<ExamResultOut | null>(null)

// 倒计时
const remain = ref(0)
let timer: number | undefined
const mmss = computed(() => {
  const m = Math.floor(remain.value / 60), s = remain.value % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})

function letter(i: number) { return ['A', 'B', 'C', 'D', 'E', 'F'][i] ?? '' }
function hasOptions(q: SelfExamQuestion) {
  return Array.isArray(q.options) && q.options.length > 0
}
function optText(opt: string) {
  return String(opt).replace(/^\s*[A-Fa-f]\s*[.．、，)）:：]\s*/, '').trim()
}

onLoad(async (q: any) => {
  examId.value = q?.id || ''
  try {
    const e = await getSelfExam(examId.value)
    Object.assign(exam, e)
    if (e.status === 'done') {
      reviewOnly.value = true
    } else {
      questions.value = e.questions || []
      remain.value = e.time_limit_sec || 900
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
    if (remain.value <= 0) {
      clearTimer()
      uni.showToast({ title: '时间到，自动交卷', icon: 'none' })
      submit(true)
    }
  }, 1000) as unknown as number
}
function clearTimer() { if (timer) { clearInterval(timer); timer = undefined } }
onUnmounted(clearTimer)

async function submit(auto: boolean) {
  if (submitting.value || result.value) return
  if (!auto) {
    const unanswered = questions.value.filter(q => !answers[q.id]).length
    if (unanswered > 0) {
      const go = await new Promise<boolean>((res) => {
        uni.showModal({
          title: '还有未作答', content: `还有 ${unanswered} 题未作答，确认提交？`,
          success: (r) => res(r.confirm),
        })
      })
      if (!go) return
    }
  }
  submitting.value = true
  clearTimer()
  try {
    // 未作答以占位提交（计为错，后端要求非空）
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
</script>

<style scoped>
.page { background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 160rpx 0; color: var(--c-text-hint); }
.list { height: 100vh; padding: 24rpx; box-sizing: border-box; }
.exam-head { padding: 8rpx 0 16rpx; }
.eh-top { display: flex; align-items: center; justify-content: space-between; }
.exam-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.timer { font-size: 30rpx; font-weight: 800; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 18rpx; border-radius: var(--r-pill); }
.timer.urgent { color: #fff; background: var(--c-danger); }
.exam-sub { font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 18rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qtype { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.stem { display: block; font-size: 30rpx; font-weight: 700; color: var(--c-ink); line-height: 1.5; margin-bottom: 20rpx; }
.options { display: flex; flex-direction: column; gap: 12rpx; }
.option { display: flex; align-items: center; gap: 16rpx; padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); background: #fff; font-size: 28rpx; color: var(--c-text-body); }
.option.selected { border-color: var(--c-primary); background: var(--c-primary-faint); }
.opt-letter { width: 44rpx; height: 44rpx; flex-shrink: 0; display: flex; align-items: center; justify-content: center; border-radius: 50%; background: var(--c-bg-soft); color: var(--c-text-second); font-size: 24rpx; font-weight: 800; }
.option.selected .opt-letter { background: var(--c-primary); color: var(--c-on-primary); }
.opt-text { flex: 1; }
.fill-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 18rpx; font-size: 28rpx; width: 100%; box-sizing: border-box; }
.score-card { display: flex; flex-direction: column; align-items: center; gap: 8rpx; padding: 40rpx; }
.score-num { font-size: 64rpx; font-weight: 900; color: var(--c-primary); }
.score-meta { font-size: 24rpx; color: var(--c-text-second); text-align: center; }
.result-card.ok { border-left: 6rpx solid #2ecc71; }
.result-card { border-left: 6rpx solid var(--c-danger); }
.res-head { display: flex; justify-content: space-between; margin-bottom: 8rpx; }
.res-idx { font-size: 24rpx; color: var(--c-text-hint); }
.res-flag { font-size: 24rpx; font-weight: 700; color: var(--c-danger); }
.res-flag.ok { color: #18a058; }
.res-line { display: block; font-size: 26rpx; color: var(--c-text-body); line-height: 1.6; }
.res-line.right { color: #18a058; }
.res-exp { display: block; font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-top: 6rpx; }
.practice-bar.fixed { position: fixed; left: 0; right: 0; bottom: 0; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: var(--c-bg-card); box-shadow: 0 -2rpx 16rpx rgba(0,0,0,.06); }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; text-align: center; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
</style>

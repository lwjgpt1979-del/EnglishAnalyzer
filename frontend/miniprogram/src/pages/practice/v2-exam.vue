<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!questions.length" class="empty">该知识点暂无题目</view>

    <!-- 答题阶段：滚动列表，所有题一次性显示，无即时反馈 -->
    <scroll-view v-else-if="!result" scroll-y class="list">
      <view class="exam-head">
        <text class="exam-title">模拟考 · 共 {{ questions.length }} 题</text>
        <text class="exam-sub">作答完成后点击底部「提交考试」一次性批改</text>
      </view>

      <view v-for="(q, idx) in questions" :key="q.id" class="card">
        <view class="qtype">第 {{ idx + 1 }} 题 · {{ q.question_type }} · 难度 {{ q.difficulty }}</view>
        <text class="stem">{{ q.stem }}</text>

        <!-- 单选 / 完型 / 阅读：A-D 选项 -->
        <view v-if="hasOptions(q)" class="options">
          <view
            v-for="(opt, i) in q.options" :key="i"
            class="option"
            :class="{ selected: answers[q.id] === letter(i) }"
            @tap="answers[q.id] = letter(i)"
          >{{ opt }}</view>
        </view>

        <!-- 判断：对/错 -->
        <view v-else-if="q.question_type === '判断'" class="judge">
          <view
            v-for="opt in ['对', '错']" :key="opt"
            class="option"
            :class="{ selected: answers[q.id] === opt }"
            @tap="answers[q.id] = opt"
          >{{ opt }}</view>
        </view>

        <!-- 写作：多行文本 -->
        <view v-else-if="q.question_type === '写作'" class="fill">
          <textarea
            v-model="answers[q.id]"
            class="essay-input"
            placeholder="请输入你的作文（参考答案仅供对照，不计入正误）"
            maxlength="-1"
          />
        </view>

        <!-- 连线：文本，格式 1-A|2-B|3-C -->
        <view v-else-if="q.question_type === '连线'" class="fill">
          <input
            v-model="answers[q.id]"
            class="fill-input"
            placeholder="按格式作答，如 1-A|2-B|3-C"
          />
        </view>

        <!-- 填空及其它：单行文本 -->
        <view v-else class="fill">
          <input v-model="answers[q.id]" class="fill-input" placeholder="请输入答案" />
        </view>
      </view>

      <view style="height: 140rpx;" />
    </scroll-view>

    <!-- 结果阶段：总分 + 每题解析 -->
    <scroll-view v-else scroll-y class="list">
      <view class="score-card card">
        <text class="score-num">{{ result.correct_count }} / {{ result.total }}</text>
        <text class="score-meta">答对 {{ result.correct_count }} 题，答错 {{ result.total - result.correct_count }} 题</text>
      </view>

      <view
        v-for="(it, idx) in result.items" :key="it.question_id"
        class="card result-card"
        :class="{ ok: it.correct }"
      >
        <view class="res-head">
          <text class="res-idx">第 {{ idx + 1 }} 题</text>
          <text class="res-flag" :class="{ ok: it.correct }">{{ it.correct ? '✓ 正确' : '✗ 错误' }}</text>
        </view>
        <text class="res-line">你的答案：{{ it.user_answer || '（未作答）' }}</text>
        <text class="res-line">正确答案：{{ it.correct_answer }}</text>
        <text class="res-exp">{{ it.explanation }}</text>
      </view>

      <view class="practice-bar fixed">
        <button class="btn-primary" @tap="goBack">返回</button>
      </view>
    </scroll-view>

    <!-- 提交按钮（答题阶段固定底部） -->
    <view v-if="questions.length && !result && !loading" class="practice-bar fixed">
      <button class="btn-primary" :disabled="submitting" @tap="submit">
        {{ submitting ? '批改中…' : '提交考试' }}
      </button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listPracticeQuestions, submitExam } from '@/api/questions'
import type { SimQuestionOut, ExamResultOut } from '@/types/api'

const kpId = ref('')
const questions = ref<SimQuestionOut[]>([])
const answers = reactive<Record<string, string>>({})
const result = ref<ExamResultOut | null>(null)
const loading = ref(true)
const submitting = ref(false)

function letter(i: number): string {
  return ['A', 'B', 'C', 'D'][i] || ''
}

function hasOptions(q: SimQuestionOut): boolean {
  return ['单选', '完型', '阅读'].includes(q.question_type) && !!q.options && q.options.length > 0
}

onLoad(async (q: any) => {
  kpId.value = q.kp || ''
  const count = Number(q.count) || 10
  if (!kpId.value) {
    uni.showToast({ title: '缺少 kp 参数', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  try {
    questions.value = await listPracticeQuestions(kpId.value, count)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

async function submit() {
  const items = questions.value.map(q => ({
    question_id: q.id,
    user_answer: (answers[q.id] || '').trim() || '（未作答）',
  }))
  submitting.value = true
  try {
    result.value = await submitExam({ items })
    uni.pageScrollTo({ scrollTop: 0, duration: 200 })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function goBack() {
  uni.navigateBack()
}
</script>

<style scoped>
.page { background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.list { height: 100vh; padding: 24rpx; box-sizing: border-box; }
.exam-head { padding: 8rpx 0 20rpx; display: flex; flex-direction: column; gap: 8rpx; }
.exam-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-ink); }
.exam-sub { font-size: 24rpx; color: var(--c-text-second); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 20rpx; }
.qtype { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.stem { display: block; font-size: 30rpx; font-weight: 600; color: var(--c-ink); line-height: 1.6; margin-bottom: 24rpx; }
.options, .judge { display: flex; flex-direction: column; gap: 12rpx; }
.option { padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 28rpx; color: var(--c-text-body); }
.option.selected { border-color: var(--c-gold); background: var(--c-primary-faint); font-weight: 600; }
.fill-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); height: 72rpx; line-height: 72rpx; padding: 0 20rpx; font-size: 28rpx; box-sizing: border-box; width: 100%; }
.essay-input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx 20rpx; font-size: 28rpx; line-height: 1.5; box-sizing: border-box; width: 100%; min-height: 200rpx; }
.practice-bar { padding: 24rpx; background: var(--c-bg-card); border-top: 1rpx solid var(--c-border); }
.practice-bar.fixed { position: fixed; left: 0; right: 0; bottom: 0; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; text-align: center; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.score-card { display: flex; flex-direction: column; align-items: center; gap: 12rpx; padding: 48rpx; }
.score-num { font-size: 64rpx; font-weight: 800; color: var(--c-ink); }
.score-meta { font-size: 26rpx; color: var(--c-text-second); }
.result-card { border-left: 6rpx solid var(--c-danger); }
.result-card.ok { border-left-color: #2ecc71; }
.res-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12rpx; }
.res-idx { font-size: 24rpx; color: var(--c-text-hint); }
.res-flag { font-size: 26rpx; font-weight: 700; color: var(--c-danger); }
.res-flag.ok { color: #2ecc71; }
.res-line { display: block; font-size: 26rpx; color: var(--c-text-body); margin-bottom: 6rpx; }
.res-exp { display: block; font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-top: 6rpx; }
</style>

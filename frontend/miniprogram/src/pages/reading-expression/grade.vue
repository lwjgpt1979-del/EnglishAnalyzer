<template>
  <view class="page">
    <view class="card">
      <view class="tip">阅读表达 · AI 批改。填入短文(可选)、问题、参考答案与你的作答,得到逐要点命中与语言反馈。</view>

      <view class="field">
        <text class="label">短文(可选)</text>
        <textarea v-model="passage" class="ta" :maxlength="-1" placeholder="粘贴短文正文,便于结合上下文判分" auto-height />
      </view>
      <view class="field">
        <text class="label">问题</text>
        <textarea v-model="question" class="ta" :maxlength="-1" placeholder="如:When does Tom run?" auto-height />
      </view>
      <view class="field">
        <text class="label">参考答案</text>
        <textarea v-model="referenceAnswer" class="ta" :maxlength="-1" placeholder="标准/参考答案" auto-height />
      </view>
      <view class="field">
        <text class="label">你的作答</text>
        <textarea v-model="studentAnswer" class="ta" :maxlength="-1" placeholder="用英文写出你的答案" auto-height />
      </view>
      <view class="field-row">
        <text class="label">本题满分</text>
        <input v-model.number="fullScore" class="num" type="number" />
      </view>

      <button class="btn-primary" :disabled="!canSubmit || loading" @tap="submit">
        {{ loading ? '批改中…' : '开始批改' }}
      </button>
    </view>

    <view v-if="result" class="card result">
      <view class="score-line">
        <text class="score-num">{{ result.total }}</text><text class="score-full"> / {{ result.full }}</text>
        <text class="score-tag">内容 {{ result.content_score }}/{{ result.content_full }}</text>
      </view>

      <view class="pts">
        <view v-for="(p, i) in result.points" :key="i" class="pt">
          <view class="ic pt-ic" :class="p.hit ? 'ic-check-circle' : 'ic-x-circle'" />
          <view class="pt-body">
            <text class="pt-name">{{ p.point }}</text>
            <text v-if="p.comment" class="pt-comment">{{ p.comment }}</text>
          </view>
        </view>
      </view>

      <view class="lang">
        <text class="lang-title">语言</text>
        <text class="lang-body">{{ result.language_comment }}<text v-if="result.language_deduction"> · 扣 {{ result.language_deduction }} 分</text></text>
      </view>
      <view class="fb"><text>{{ result.feedback }}</text></view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { gradeReadingExpression, type REGradeResult } from '@/api/reading-expression'

const passage = ref('')
const question = ref('')
const referenceAnswer = ref('')
const studentAnswer = ref('')
const fullScore = ref(4)
const loading = ref(false)
const result = ref<REGradeResult | null>(null)

const canSubmit = computed(() =>
  !!question.value.trim() && !!referenceAnswer.value.trim() && !!studentAnswer.value.trim())

async function submit() {
  if (!canSubmit.value) return
  loading.value = true
  try {
    result.value = await gradeReadingExpression({
      question: question.value.trim(),
      reference_answer: referenceAnswer.value.trim(),
      student_answer: studentAnswer.value.trim(),
      passage: passage.value.trim() || undefined,
      full_score: Number(fullScore.value) || 4,
    })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '批改失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 24rpx; }
.tip { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-bottom: 16rpx; }
.field { display: flex; flex-direction: column; gap: 8rpx; margin-bottom: 16rpx; }
.field-row { display: flex; align-items: center; gap: 16rpx; margin-bottom: 20rpx; }
.label { font-size: 26rpx; color: var(--c-text-body); font-weight: 600; }
.ta { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; min-height: 88rpx; box-sizing: border-box; width: 100%; }
.num { border: 2rpx solid var(--c-border); border-radius: var(--r-md); height: 64rpx; line-height: 64rpx; padding: 0 16rpx; font-size: 28rpx; width: 140rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.result .score-line { display: flex; align-items: baseline; gap: 12rpx; margin-bottom: 16rpx; }
.score-num { font-size: 52rpx; font-weight: 800; color: var(--c-primary); }
.score-full { font-size: 28rpx; color: var(--c-text-hint); }
.score-tag { margin-left: auto; font-size: 24rpx; color: var(--c-text-second); }
.pts { display: flex; flex-direction: column; gap: 12rpx; margin-bottom: 16rpx; }
.pt { display: flex; align-items: flex-start; gap: 12rpx; }
.pt-ic { width: 36rpx; height: 36rpx; flex-shrink: 0; margin-top: 2rpx; }
.pt-body { display: flex; flex-direction: column; gap: 2rpx; }
.pt-name { font-size: 28rpx; color: var(--c-ink); }
.pt-comment { font-size: 24rpx; color: var(--c-text-second); }
.lang { margin-bottom: 12rpx; }
.lang-title { font-size: 24rpx; font-weight: 700; color: var(--c-ink); margin-right: 8rpx; }
.lang-body { font-size: 26rpx; color: var(--c-text-body); }
.fb { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; color: var(--c-text-second); line-height: 1.6; }
</style>

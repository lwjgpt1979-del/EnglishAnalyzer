<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!detail" class="tip">试卷不存在</view>
    <view v-else>
      <!-- 试卷头部 -->
      <view class="paper-header">
        <text class="paper-title">{{ detail.title }}</text>
        <view class="meta">
          <text v-if="detail.grade">{{ detail.grade }} · {{ detail.semester }}学期</text>
          <text>共 {{ detail.questions.length }} 题</text>
        </view>
        <text v-if="detail.description" class="desc">{{ detail.description }}</text>
      </view>

      <!-- 题目列表 -->
      <view
        v-for="(q, idx) in detail.questions"
        :key="q.id"
        class="question-card"
      >
        <view class="q-header">
          <text class="q-no">{{ idx + 1 }}.</text>
          <text class="q-type-tag">{{ q.question_type }}</text>
          <text class="q-diff">难度 {{ q.difficulty }}</text>
        </view>
        <text class="q-stem">{{ q.stem }}</text>

        <!-- 选择题选项 -->
        <view v-if="q.options" class="options">
          <view
            v-for="(opt, oi) in q.options"
            :key="oi"
            :class="['option', answers[q.id] === String.fromCharCode(65 + oi) ? 'selected' : '']"
            @tap="selectAnswer(q.id, String.fromCharCode(65 + oi))"
          >
            <text class="opt-letter">{{ String.fromCharCode(65 + oi) }}</text>
            <text class="opt-text">{{ opt }}</text>
          </view>
        </view>

        <!-- 填空/简答题 -->
        <view v-else class="answer-input-wrap">
          <textarea
            :value="answers[q.id] || ''"
            class="answer-input"
            placeholder="请输入答案"
            @input="(e: any) => answers[q.id] = e.detail.value"
          />
        </view>
      </view>

      <view class="footer">
        <text class="answered-tip">已作答 {{ answeredCount }} / {{ detail.questions.length }} 题</text>
        <button
          class="btn-submit"
          :disabled="submitting || detail.questions.length === 0"
          @tap="onSubmit"
        >
          {{ submitting ? '提交中…' : '提交试卷' }}
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { getStudentPaperDetail } from '@/api/examPapers'
import type { ClassPaperDetailOut } from '@/types/api'

const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as any
const paperId: string = currentPage.options?.paperId || ''

const detail = ref<ClassPaperDetailOut | null>(null)
const loading = ref(false)
const submitting = ref(false)

// 答案：questionId → answer string
const answers = reactive<Record<string, string>>({})

const answeredCount = computed(() =>
  Object.values(answers).filter(v => v && v.trim()).length
)

function selectAnswer(qId: string, letter: string) {
  answers[qId] = letter
}

async function onSubmit() {
  const total = detail.value?.questions.length || 0
  if (answeredCount.value < total) {
    const res = await uni.showModal({
      title: '确认提交',
      content: `还有 ${total - answeredCount.value} 题未作答，确认提交？`,
      confirmText: '确认提交',
    })
    if (!res.confirm) return
  }
  submitting.value = true
  try {
    // MVP: 本地记录答案，后续接入 exam-attempts API
    // 暂时只展示提交成功提示
    await new Promise(resolve => setTimeout(resolve, 600))
    uni.showToast({ title: '提交成功', icon: 'success' })
    setTimeout(() => uni.navigateBack(), 1200)
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (!paperId) return
  loading.value = true
  try {
    const r = await getStudentPaperDetail(paperId)
    detail.value = r.data || null
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; padding-bottom: 120rpx; }
.tip { text-align: center; color: #aaa; padding: 80rpx 0; font-size: 28rpx; }
.paper-header { background: #fff; border-radius: 12rpx; padding: 28rpx; margin-bottom: 20rpx; }
.paper-title { font-size: 36rpx; font-weight: 700; color: #333; display: block; margin-bottom: 12rpx; }
.meta { display: flex; gap: 20rpx; font-size: 24rpx; color: #999; margin-bottom: 8rpx; }
.desc { font-size: 26rpx; color: #666; display: block; margin-top: 8rpx; }
.question-card { background: #fff; border-radius: 12rpx; padding: 28rpx; margin-bottom: 16rpx; }
.q-header { display: flex; align-items: center; gap: 12rpx; margin-bottom: 16rpx; }
.q-no { font-size: 30rpx; font-weight: 700; color: #333; }
.q-type-tag { background: #e8f4ff; color: #4f9bff; font-size: 22rpx; padding: 4rpx 12rpx; border-radius: 20rpx; }
.q-diff { background: #fff7e6; color: #f99; font-size: 22rpx; padding: 4rpx 12rpx; border-radius: 20rpx; }
.q-stem { font-size: 30rpx; color: #333; line-height: 1.6; display: block; margin-bottom: 20rpx; }
.options { display: flex; flex-direction: column; gap: 12rpx; }
.option { display: flex; align-items: center; padding: 18rpx 20rpx; border: 2rpx solid #eee; border-radius: 10rpx; background: #fafafa; }
.option.selected { border-color: #4f9bff; background: #e8f4ff; }
.opt-letter { width: 48rpx; height: 48rpx; border-radius: 50%; background: #eee; display: flex; align-items: center; justify-content: center; font-size: 26rpx; font-weight: 700; color: #555; margin-right: 16rpx; }
.option.selected .opt-letter { background: #4f9bff; color: #fff; }
.opt-text { font-size: 28rpx; color: #333; flex: 1; }
.answer-input-wrap { margin-top: 8rpx; }
.answer-input { width: 100%; border: 1px solid #eee; border-radius: 8rpx; padding: 16rpx; font-size: 28rpx; min-height: 120rpx; box-sizing: border-box; background: #fafafa; }
.footer { position: fixed; bottom: 0; left: 0; right: 0; background: #fff; padding: 20rpx 32rpx; border-top: 1px solid #eee; display: flex; align-items: center; gap: 20rpx; }
.answered-tip { flex: 1; font-size: 26rpx; color: #999; }
.btn-submit { flex: 2; background: #4f9bff; color: #fff; font-size: 30rpx; height: 80rpx; line-height: 80rpx; border-radius: 12rpx; border: none; }
.btn-submit[disabled] { background: #aaa; }
</style>

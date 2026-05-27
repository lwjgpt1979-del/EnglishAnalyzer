<!-- src/pages/wrong-questions/detail.vue -->
<template>
  <view class="detail-page">
    <view v-if="!wq" class="center-tip">加载中…</view>
    <view v-else>
      <!-- 题目图片 -->
      <image
        class="wq-img"
        :src="wq.source_image_url"
        mode="widthFix"
        @tap="previewImg"
      />

      <!-- OCR 识别状态卡 -->
      <view class="card" v-if="wq">
        <!-- 状态条 -->
        <view class="ocr-status-bar" :class="ocrStatusClass">
          <text class="ocr-status-icon">{{ ocrStatusIcon }}</text>
          <text class="ocr-status-text">{{ ocrStatusText }}</text>
          <button
            v-if="wq.ocr_status === 'failed' || wq.ocr_status === null"
            class="btn-ocr-retry"
            @tap="onTriggerOcr"
          >重新识别</button>
        </view>

        <!-- OCR 结果确认/编辑表单（completed 状态显示） -->
        <view v-if="wq.ocr_status === 'completed'" class="ocr-form">
          <view class="card-title" style="margin-top: 20rpx">识别内容确认</view>
          <view class="ocr-field">
            <text class="label">题目内容</text>
            <textarea
              class="ocr-textarea"
              :value="editQuestion"
              @input="editQuestion = $event.detail.value"
              placeholder="AI 识别的题目文字"
              auto-height
            />
          </view>
          <view class="ocr-field">
            <text class="label">你的作答</text>
            <input
              class="ocr-input"
              :value="editAnswer"
              @input="editAnswer = $event.detail.value"
              placeholder="识别的手写答案"
            />
          </view>
          <view class="ocr-field">
            <text class="label">正确答案</text>
            <input
              class="ocr-input"
              :value="editCorrect"
              @input="editCorrect = $event.detail.value"
              placeholder="正确答案（可选）"
            />
          </view>
          <button
            class="btn-confirm"
            :disabled="confirming"
            @tap="onConfirmOcr"
          >
            {{ confirming ? '保存中…' : '确认内容' }}
          </button>
        </view>
      </view>

      <!-- 元信息卡 -->
      <view class="card">
        <view class="row">
          <text class="label">题型</text>
          <text>{{ wq.question_type || '未填写' }}</text>
        </view>
        <view class="row">
          <text class="label">难度</text>
          <text>{{ wq.difficulty ? '★'.repeat(wq.difficulty) : '未填写' }}</text>
        </view>
        <view class="row">
          <text class="label">已掌握</text>
          <switch :checked="wq.is_mastered" @change="onToggleMastered" />
        </view>
      </view>

      <!-- AI 分析 -->
      <view class="card">
        <view class="card-title">AI 诊断分析</view>
        <button class="btn-analyze" :disabled="analyzing" @tap="onAnalyze">
          {{ analyzing ? '分析中（约3-8秒）…' : '触发 AI 分析' }}
        </button>

        <view v-if="latestAnalysis" class="analysis-result">
          <view class="section-title">错误类型</view>
          <view class="tags">
            <text
              v-for="t in latestAnalysis.error_types"
              :key="t"
              class="tag-red"
            >{{ t }}</text>
          </view>

          <view class="section-title">薄弱知识点</view>
          <view class="tags">
            <text
              v-for="k in latestAnalysis.knowledge_points"
              :key="k"
              class="tag-orange"
            >{{ k }}</text>
          </view>

          <view class="section-title">诊断</view>
          <text class="analysis-text">{{ latestAnalysis.diagnosis }}</text>

          <view class="section-title">建议</view>
          <text class="analysis-text">{{ latestAnalysis.suggestions }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import {
  analyzeWrongQuestion,
  confirmOcrText,
  getWrongQuestion,
  listAnalyses,
  markMastered,
  triggerOcr,
} from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'
import type { AiAnalysisOut, ConfirmOcrTextRequest, WrongQuestionOut } from '@/types/api'

const auth = useAuthStore()

// uni-app 小程序获取路由参数方式
const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as UniApp.Page & { options: Record<string, string> }
const wqId = currentPage.options.id

const wq = ref<WrongQuestionOut | null>(null)
const latestAnalysis = ref<AiAnalysisOut | null>(null)
const analyzing = ref(false)

// OCR 编辑状态
const editQuestion = ref('')
const editAnswer = ref('')
const editCorrect = ref('')
const confirming = ref(false)
let ocrPollTimer: ReturnType<typeof setInterval> | null = null

// OCR 状态展示
const ocrStatusClass = computed(() => {
  const map: Record<string, string> = {
    pending: 'ocr-pending',
    processing: 'ocr-processing',
    completed: 'ocr-completed',
    failed: 'ocr-failed',
  }
  return map[wq.value?.ocr_status ?? ''] ?? 'ocr-unknown'
})

const ocrStatusIcon = computed(() => {
  const map: Record<string, string> = {
    pending: '⏳',
    processing: '🔄',
    completed: '✅',
    failed: '❌',
  }
  return map[wq.value?.ocr_status ?? ''] ?? '❓'
})

const ocrStatusText = computed(() => {
  const map: Record<string, string> = {
    pending: 'OCR 识别等待中…',
    processing: '正在识别题目文字（约 5-15 秒）…',
    completed: 'OCR 识别完成，请确认内容',
    failed: 'OCR 识别失败',
  }
  return map[wq.value?.ocr_status ?? ''] ?? '未触发 OCR'
})

function startOcrPolling() {
  if (ocrPollTimer) return
  ocrPollTimer = setInterval(async () => {
    if (!wq.value) return
    const status = wq.value.ocr_status
    if (status !== 'pending' && status !== 'processing') {
      stopOcrPolling()
      return
    }
    try {
      wq.value = await getWrongQuestion(wqId)
      if (wq.value.ocr_status === 'completed') {
        editQuestion.value = wq.value.question_text ?? ''
        editAnswer.value = wq.value.student_answer ?? ''
        editCorrect.value = wq.value.correct_answer ?? ''
        stopOcrPolling()
      }
    } catch (_) { /* 静默忽略轮询错误 */ }
  }, 3000)
}

function stopOcrPolling() {
  if (ocrPollTimer) {
    clearInterval(ocrPollTimer)
    ocrPollTimer = null
  }
}

async function onTriggerOcr() {
  if (!wq.value) return
  try {
    wq.value = await triggerOcr(wqId)
    startOcrPolling()
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  }
}

async function onConfirmOcr() {
  if (!wq.value) return
  confirming.value = true
  try {
    const data: ConfirmOcrTextRequest = {
      question_text: editQuestion.value || null,
      student_answer: editAnswer.value || null,
      correct_answer: editCorrect.value || null,
    }
    wq.value = await confirmOcrText(wqId, data)
    uni.showToast({ title: '已保存', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    confirming.value = false
  }
}

onUnmounted(() => stopOcrPolling())

onMounted(async () => {
  if (!auth.isLoggedIn()) {
    await auth.login()
  }
  try {
    wq.value = await getWrongQuestion(wqId)
    const analyses = await listAnalyses(wqId)
    if (analyses.length > 0) latestAnalysis.value = analyses[0]
      // OCR 预填 + 自动轮询
      if (wq.value?.ocr_status === 'completed') {
        editQuestion.value = wq.value.question_text ?? ''
        editAnswer.value = wq.value.student_answer ?? ''
        editCorrect.value = wq.value.correct_answer ?? ''
      } else if (wq.value?.ocr_status === 'pending' || wq.value?.ocr_status === 'processing') {
        startOcrPolling()
      }
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  }
})

async function onToggleMastered(e: { detail: { value: boolean } }) {
  if (!wq.value) return
  try {
    wq.value = await markMastered(wqId, e.detail.value)
  } catch (err) {
    uni.showToast({ title: (err as Error).message, icon: 'error' })
  }
}

async function onAnalyze() {
  analyzing.value = true
  try {
    latestAnalysis.value = await analyzeWrongQuestion(wqId)
    uni.showToast({ title: 'AI 分析完成', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    analyzing.value = false
  }
}

function previewImg() {
  if (wq.value) {
    uni.previewImage({ urls: [wq.value.source_image_url] })
  }
}
</script>

<style scoped>
.detail-page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.center-tip { text-align: center; padding: 100rpx; color: #999; }
.wq-img { width: 100%; border-radius: 16rpx; margin-bottom: 20rpx; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 20rpx; }
.card-title { font-size: 30rpx; font-weight: bold; margin-bottom: 20rpx; color: #222; }
.row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid #f5f5f5;
}
.label { width: 140rpx; color: #666; font-size: 28rpx; }
.btn-analyze {
  background: #1677ff;
  color: #fff;
  border-radius: 10rpx;
  font-size: 28rpx;
  height: 80rpx;
  line-height: 80rpx;
}
.btn-analyze[disabled] { opacity: 0.5; }
.analysis-result { margin-top: 24rpx; }
.section-title { font-size: 26rpx; color: #888; margin: 20rpx 0 8rpx; }
.tags { display: flex; flex-wrap: wrap; gap: 10rpx; }
.tag-red {
  background: #fff0f0;
  color: #ff4d4f;
  font-size: 24rpx;
  padding: 4rpx 14rpx;
  border-radius: 6rpx;
}
.tag-orange {
  background: #fff7e6;
  color: #fa8c16;
  font-size: 24rpx;
  padding: 4rpx 14rpx;
  border-radius: 6rpx;
}
.analysis-text { font-size: 28rpx; color: #333; line-height: 1.7; }

/* OCR 状态条 */
.ocr-status-bar {
  display: flex;
  align-items: center;
  padding: 16rpx;
  border-radius: 10rpx;
  gap: 12rpx;
}
.ocr-pending, .ocr-unknown { background: #f5f5f5; }
.ocr-processing { background: #e6f4ff; }
.ocr-completed { background: #f0fff4; }
.ocr-failed { background: #fff0f0; }
.ocr-status-icon { font-size: 32rpx; }
.ocr-status-text { flex: 1; font-size: 26rpx; color: #555; }
.btn-ocr-retry {
  font-size: 24rpx; height: 56rpx; line-height: 56rpx;
  background: #1677ff; color: #fff; border-radius: 8rpx; padding: 0 20rpx;
}

/* OCR 编辑表单 */
.ocr-form { margin-top: 16rpx; }
.ocr-field { margin-bottom: 20rpx; }
.ocr-textarea {
  width: 100%; min-height: 120rpx; background: #f9f9f9;
  border-radius: 8rpx; padding: 16rpx; font-size: 26rpx; color: #333;
  box-sizing: border-box;
}
.ocr-input {
  width: 100%; height: 72rpx; background: #f9f9f9;
  border-radius: 8rpx; padding: 0 16rpx; font-size: 26rpx; color: #333;
}
.btn-confirm {
  background: #52c41a; color: #fff; border-radius: 10rpx;
  font-size: 28rpx; height: 80rpx; line-height: 80rpx; width: 100%;
}
.btn-confirm[disabled] { opacity: 0.5; }
</style>

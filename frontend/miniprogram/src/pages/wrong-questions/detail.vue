<!-- src/pages/wrong-questions/detail.vue -->
<template>
  <view class="detail-page">
    <view v-if="!wq" class="center-tip">加载中…</view>
    <view v-else>
      <!-- 题目：作业来源 / 真实图片 / 文字题干 -->
      <view v-if="fromAssignment" class="assign-banner">
        <text class="assign-icon">📋</text>
        <text class="assign-label">来自老师作业的错题</text>
      </view>
      <image
        v-else-if="isRealImage"
        class="wq-img"
        :src="wq.source_image_url"
        mode="widthFix"
        @tap="previewImg"
      />
      <view v-else class="stem-card">
        <text class="stem-label">📝 题目</text>
        <text class="stem-text">{{ wq.question_text || '（无题干，本题为图片错题）' }}</text>
      </view>

      <!-- OCR 识别状态卡（仅图片错题需要 OCR；文字录入错题不显示）-->
      <view class="card" v-if="wq && isRealImage">
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

      <!-- 元信息卡：彩色标签胶囊 -->
      <view class="card meta-card">
        <view class="meta-chips">
          <text class="chip chip-type">{{ wq.question_type || '未填写' }}</text>
          <text class="chip chip-diff">{{ wq.difficulty ? '★'.repeat(wq.difficulty) : '难度未填' }}</text>
        </view>
        <view
          class="chip chip-master"
          :class="{ 'is-on': wq.is_mastered }"
          @tap="tapMastered"
        >{{ wq.is_mastered ? '✓ 已掌握' : '○ 未掌握' }}</view>
      </view>

      <!-- AI 分析 -->
      <view class="card">
        <view class="card-title">AI 诊断分析</view>
        <button class="btn-analyze" :disabled="analyzing" @tap="onAnalyze">
          {{ analyzing ? '分析中（约3-8秒）…' : '触发 AI 分析' }}
        </button>

        <view v-if="latestAnalysis" class="analysis-result">
          <view class="ana-sec" v-if="latestAnalysis.error_types && latestAnalysis.error_types.length">
            <text class="ana-label">🏷️ 错误类型</text>
            <view class="tags">
              <text v-for="t in latestAnalysis.error_types" :key="t" class="tag-red">{{ t }}</text>
            </view>
          </view>

          <view class="ana-sec" v-if="latestAnalysis.knowledge_points && latestAnalysis.knowledge_points.length">
            <text class="ana-label">⚠️ 薄弱知识点</text>
            <view class="tags">
              <text v-for="k in latestAnalysis.knowledge_points" :key="k" class="tag-orange">{{ k }}</text>
            </view>
          </view>

          <view class="ana-sec" v-if="latestAnalysis.diagnosis">
            <text class="ana-label">🔍 诊断</text>
            <text class="ana-box">{{ latestAnalysis.diagnosis }}</text>
          </view>

          <view class="ana-sec" v-if="latestAnalysis.suggestions">
            <text class="ana-label">💡 建议</text>
            <text class="ana-box ana-box-tip">{{ latestAnalysis.suggestions }}</text>
          </view>
          <text class="report-err" @tap="onReportError">🚩 诊断有误？反馈</text>
        </view>
      </view>

      <!-- 老师批注 -->
      <view v-if="teacherComments.length > 0" class="card">
        <view class="card-title">老师批注</view>
        <view
          v-for="c in teacherComments"
          :key="c.id"
          class="teacher-comment-item"
        >
          <text class="tc-text">{{ c.comment_text }}</text>
          <text class="tc-time">{{ c.created_at.slice(0, 16).replace('T', ' ') }}</text>
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
  reportContentFeedback,
} from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'
import { getComments } from '@/api/teacher'
import type { AiAnalysisOut, ConfirmOcrTextRequest, TeacherCommentOut, WrongQuestionOut } from '@/types/api'

const auth = useAuthStore()

// uni-app 小程序获取路由参数方式
// 防御：DevTools 可能直接打开 detail 页而无 ?id= 参数 → 不再让 setup 崩溃
const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as (UniApp.Page & { options?: Record<string, string> }) | undefined
const wqId = currentPage?.options?.id || ''
if (!wqId) {
  console.warn('[detail] 缺 ?id= 参数，将仅显示错误提示')
  uni.showToast({ title: '错题 ID 缺失', icon: 'none' })
}

const wq = ref<WrongQuestionOut | null>(null)
const fromAssignment = computed(() => (wq.value?.source_image_url || '').startsWith('assignment://'))
const isRealImage = computed(() => {
  const u = wq.value?.source_image_url || ''
  return /^https?:\/\//.test(u) || u.startsWith('/') || u.startsWith('data:') || u.startsWith('wxfile://')
})
const latestAnalysis = ref<AiAnalysisOut | null>(null)
const analyzing = ref(false)
const teacherComments = ref<TeacherCommentOut[]>([])

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
    try {
      teacherComments.value = await getComments(wqId)
    } catch { /* 无批注也不报错 */ }
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

async function tapMastered() {
  if (!wq.value) return
  const next = !wq.value.is_mastered
  try {
    wq.value = await markMastered(wqId, next)
    uni.showToast({ title: next ? '已标记掌握' : '已取消', icon: 'none' })
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
  if (wq.value && !fromAssignment.value) {
    uni.previewImage({ urls: [wq.value.source_image_url] })
  }
}

function onReportError() {
  uni.showModal({
    title: '反馈诊断有误', editable: true, placeholderText: '请简述哪里有误（选填）',
    success: async (r) => {
      if (!r.confirm) return
      try {
        await reportContentFeedback({
          target_type: 'diagnosis', target_id: wqId,
          snippet: (wq.value?.question_text || '').slice(0, 80), reason: r.content || '',
        })
        uni.showToast({ title: '已提交，感谢反馈', icon: 'success' })
      } catch (e) {
        uni.showToast({ title: (e as Error).message || '提交失败', icon: 'none' })
      }
    },
  })
}
</script>

<style scoped>
.detail-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 100rpx; color: var(--c-text-hint); }
.wq-img { width: 100%; border-radius: var(--r-lg); margin-bottom: 20rpx; }
.assign-banner { display: flex; align-items: center; gap: 12rpx; background: var(--c-primary-faint); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 20rpx; }
/* 文字题干卡（无真实图片时）*/
.stem-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; margin-bottom: 20rpx; box-shadow: var(--shadow-sm); }
.stem-label { font-size: 22rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 14rpx; border-radius: var(--r-pill); }
.stem-text { display: block; margin-top: 16rpx; font-size: 32rpx; color: var(--c-ink); font-weight: 600; line-height: 1.6; }
.assign-icon { font-size: 40rpx; }
.assign-label { font-size: 28rpx; font-weight: 700; color: var(--c-primary); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 20rpx; color: var(--c-ink); }
.row {
  display: flex;
  align-items: center;
  padding: 16rpx 0;
  border-bottom: 1rpx solid var(--c-border);
}
.label { width: 140rpx; color: var(--c-text-second); font-size: 28rpx; }

/* 元信息卡：彩色标签胶囊 */
.meta-card { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 24rpx; }
.meta-chips { display: flex; flex-wrap: wrap; gap: 12rpx; }
.chip {
  display: inline-flex; align-items: center;
  height: 52rpx; padding: 0 22rpx;
  border-radius: var(--r-pill);
  font-size: 26rpx; font-weight: 600;
  white-space: nowrap;
}
.chip-type { background: var(--c-primary-faint); color: var(--c-primary-deep); }
.chip-diff { background: #fff4e0; color: #c98314; }
.chip-master {
  background: var(--c-bg-soft); color: var(--c-text-second);
  border: 1rpx solid var(--c-border);
}
.chip-master.is-on {
  background: #e6f8ee; color: #18a058; border-color: #b8ebcf;
}
.btn-analyze {
  background: var(--c-primary);
  color: var(--c-on-primary);
  border-radius: var(--r-btn);
  font-size: 28rpx;
  font-weight: 700;
  height: 80rpx;
  line-height: 80rpx;
}
.btn-analyze[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.analysis-result { margin-top: 24rpx; }
.ana-sec { margin-top: 24rpx; }
.ana-sec:first-child { margin-top: 0; }
.ana-label { display: block; font-size: 27rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 12rpx; }
.ana-box { display: block; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx 24rpx; font-size: 27rpx; color: var(--c-text-body); line-height: 1.7; }
.ana-box-tip { background: var(--c-primary-faint); border-left: 6rpx solid var(--c-primary); }
.report-err { display: inline-block; margin-top: 16rpx; font-size: 24rpx; color: var(--c-text-hint); }
.tags { display: flex; flex-wrap: wrap; gap: 10rpx; }
.tag-red {
  background: var(--c-danger-bg);
  color: var(--c-danger);
  font-size: 24rpx;
  font-weight: 600;
  padding: 4rpx 14rpx;
  border-radius: var(--r-pill);
}
.tag-orange {
  background: #ffeee9;
  color: #d9603f;
  font-size: 24rpx;
  font-weight: 600;
  padding: 4rpx 14rpx;
  border-radius: var(--r-pill);
}
.analysis-text { font-size: 28rpx; color: var(--c-text-body); line-height: 1.7; }

/* OCR 状态条 */
.ocr-status-bar {
  display: flex;
  align-items: center;
  padding: 16rpx;
  border-radius: var(--r-md);
  gap: 12rpx;
}
.ocr-pending, .ocr-unknown { background: var(--c-bg-soft); }
.ocr-processing { background: var(--c-primary-faint); }
.ocr-completed { background: var(--c-success-bg); }
.ocr-failed { background: var(--c-danger-bg); }
.ocr-status-icon { font-size: 32rpx; }
.ocr-status-text { flex: 1; font-size: 26rpx; color: var(--c-text-second); }
.btn-ocr-retry {
  font-size: 24rpx; height: 56rpx; line-height: 56rpx;
  background: var(--c-primary); color: var(--c-on-primary); font-weight: 600; border-radius: var(--r-sm); padding: 0 20rpx;
}

/* OCR 编辑表单 */
.ocr-form { margin-top: 16rpx; }
.ocr-field { margin-bottom: 20rpx; }
.ocr-textarea {
  width: 100%; min-height: 120rpx; background: var(--c-bg-soft);
  border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; color: var(--c-text-body);
  box-sizing: border-box;
}
.ocr-input {
  width: 100%; height: 72rpx; background: var(--c-bg-soft);
  border-radius: var(--r-md); padding: 0 16rpx; font-size: 26rpx; color: var(--c-text-body);
}
.btn-confirm {
  background: var(--c-success); color: #fff; border-radius: var(--r-btn);
  font-size: 28rpx; font-weight: 700; height: 80rpx; line-height: 80rpx; width: 100%;
}
.btn-confirm[disabled] { opacity: 0.5; }
.teacher-comment-item { background: var(--c-primary-faint); border-radius: var(--r-md); padding: 14rpx 18rpx; margin-bottom: 8rpx; border-left: 4rpx solid var(--c-gold); }
.tc-text { font-size: 28rpx; color: var(--c-text-body); display: block; margin-bottom: 4rpx; }
.tc-time { font-size: 22rpx; color: var(--c-text-hint); }
</style>

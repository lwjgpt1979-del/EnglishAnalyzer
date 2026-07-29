<!-- src/pages/wrong-questions/detail.vue —— 错题详情(统一 wrong_record:重做订正 + 掌握标记) -->
<template>
  <view class="detail-page">
    <view v-if="!wq" class="center-tip">加载中…</view>
    <view v-else>
      <!-- 题干 -->
      <view class="stem-card">
        <view class="stem-label"><view class="ic ic-edit" style="width:26rpx;height:26rpx" /><text>题目</text></view>
        <view v-if="sourceBadgeText" class="src-badge" :class="sourceBadgeCls">{{ sourceBadgeText }}</view>
        <text class="stem-text">{{ wq.question_text || wq.stem || '（本题无题干）' }}</text>
      </view>

      <!-- 重做订正（有选项时客观判分；答对即订正）-->
      <view v-if="wq.options && wq.options.length" class="card">
        <view class="card-title">{{ revealed ? '订正详情' : '重做订正' }}</view>
        <view class="opt-list">
          <view
            v-for="(opt, i) in wq.options"
            :key="i"
            class="opt-item"
            :class="optClass(i, opt)"
            @tap="onPick(i)"
          >
            <text class="opt-text">{{ opt }}</text>
            <view v-if="revealed && isCorrectOption(opt)" class="ic ic-check-circle opt-ok" />
          </view>
        </view>

        <button
          v-if="!revealed"
          class="btn-redo"
          :disabled="selectedIdx === null || redoing"
          @tap="onRedo"
        >{{ redoing ? '判分中…' : '提交订正' }}</button>

        <view v-if="revealed" class="redo-feedback">
          <text class="fb-line" :class="feedbackCorrect ? 'fb-ok' : 'fb-no'">
            {{ feedbackCorrect ? '✓ 答对，已订正' : '✗ 答错，本题已排入复习' }}
          </text>
          <view class="answer-row">
            <text class="answer-label">正确答案</text>
            <text class="answer-val">{{ wq.correct_answer || '—' }}</text>
          </view>
          <view v-if="wq.explanation" class="expl-box">
            <view class="stem-label"><view class="ic ic-idea" style="width:26rpx;height:26rpx" /><text>解析</text></view>
            <text class="expl-text">{{ wq.explanation }}</text>
          </view>
        </view>
      </view>

      <!-- 无选项错题：直接展示正确答案 + 解析 -->
      <view v-else-if="wq.correct_answer || wq.explanation" class="card">
        <view class="answer-row">
          <text class="answer-label">正确答案</text>
          <text class="answer-val">{{ wq.correct_answer || '—' }}</text>
        </view>
        <view v-if="wq.explanation" class="expl-box">
          <view class="stem-label"><view class="ic ic-idea" style="width:26rpx;height:26rpx" /><text>解析</text></view>
          <text class="expl-text">{{ wq.explanation }}</text>
        </view>
      </view>

      <!-- 错题关系网(以词为中心:答案词居中 + 主/次错题 + 考点维度) -->
      <WrongRelationNet v-if="wqId" :wrong-record-id="wqId" />

      <!-- 元信息卡 -->
      <view class="card meta-card">
        <view class="meta-chips">
          <text class="chip chip-type">{{ wq.question_type || '未填写' }}</text>
        </view>
        <view
          class="chip chip-master"
          :class="{ 'is-on': wq.is_mastered }"
          @tap="tapMastered"
        >{{ wq.is_mastered ? '✓ 已掌握' : '○ 未掌握' }}</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getWrongQuestion, markMastered, redoWrong } from '@/api/wrongQuestions'
import type { RedoResult } from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'
import type { WrongQuestionOut } from '@/types/api'
import WrongRelationNet from '@/components/WrongRelationNet.vue'

const auth = useAuthStore()

// 路由参数：onLoad(options) 读取（真机可靠）。
let wqId = ''
const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as (UniApp.Page & { options?: Record<string, string> }) | undefined
wqId = currentPage?.options?.id || ''
onLoad((opts?: Record<string, string>) => {
  if (opts?.id) wqId = opts.id
})

const wq = ref<WrongQuestionOut | null>(null)
const letter = (i: number) => String.fromCharCode(65 + i)

/** 平台族题级来源徽章 */
const sourceBadgeText = computed(() => {
  const s = wq.value?.source_label || ''
  if (s === '课程精讲' || s === '语法精讲' || s === '课程练习' || s === '模拟考' || s === '课程闯关') return s
  if (s === '平台') return '平台练习'
  return ''
})
const sourceBadgeCls = computed(() => {
  const s = wq.value?.source_label || ''
  if (s === '课程精讲') return 'src-course'
  if (s === '语法精讲') return 'src-gram'
  if (s === '课程练习') return 'src-prac'
  if (s === '模拟考') return 'src-exam'
  if (s === '课程闯关' || s === '平台') return 'src-chal'
  return ''
})

function isCorrectOption(opt: string): boolean {
  const ans = (wq.value?.correct_answer || '').trim()
  if (!ans) return false
  const idx = wq.value?.options?.indexOf(opt) ?? -1
  return ans === opt || (idx >= 0 && ans.toUpperCase() === letter(idx))
}

// —— 重做订正（客观判分：选项字母 → /redo）——
const selectedIdx = ref<number | null>(null)
const redoing = ref(false)
const redoResult = ref<RedoResult | null>(null)
const revealed = computed(() => redoResult.value !== null || (wq.value?.is_mastered ?? false))
const feedbackCorrect = computed(() =>
  redoResult.value ? redoResult.value.is_correct : (wq.value?.is_mastered ?? false))

function onPick(i: number) {
  if (revealed.value) return
  selectedIdx.value = i
}
function optClass(i: number, opt: string): string {
  if (revealed.value) {
    if (isCorrectOption(opt)) return 'opt-correct'
    if (redoResult.value && selectedIdx.value === i) return 'opt-wrong'
    return ''
  }
  return selectedIdx.value === i ? 'opt-selected' : ''
}
async function onRedo() {
  if (selectedIdx.value === null || !wq.value) return
  redoing.value = true
  try {
    redoResult.value = await redoWrong(wqId, letter(selectedIdx.value))
    if (redoResult.value.mastered) {
      wq.value.is_mastered = true
      uni.showToast({ title: '订正成功', icon: 'success' })
    } else {
      uni.showToast({ title: '答错了，已排入复习', icon: 'none' })
    }
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    redoing.value = false
  }
}

onMounted(async () => {
  if (!wqId) {
    uni.showToast({ title: '错题 ID 缺失', icon: 'none' })
    return
  }
  if (!auth.isLoggedIn()) {
    await auth.login()
  }
  try {
    wq.value = await getWrongQuestion(wqId)
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
</script>

<style scoped>
.detail-page { padding: 24rpx; background: #f0f6fc; min-height: 100vh; }
.center-tip { text-align: center; padding: 100rpx; color: var(--c-text-hint); }
.stem-card {
  background: #f7f3e6; border: 2rpx solid #e0d6b8; border-radius: var(--r-lg);
  padding: 28rpx; margin-bottom: 20rpx;
}
.src-badge {
  display: inline-block; font-size: 22rpx; font-weight: 700;
  padding: 4rpx 14rpx; border-radius: 8rpx; margin: 8rpx 0 12rpx;
}
.src-badge.src-course { background: #eef8f3; color: #2fa98a; }
.src-badge.src-gram { background: #f3eefc; color: #7c5cbf; }
.src-badge.src-prac { background: #e8f4ff; color: #2f77e6; }
.src-badge.src-exam { background: #eef0ff; color: #4f46e5; }
.src-badge.src-chal { background: #fff4e8; color: #d97706; }
.src-badge.src-plat { background: #fff4e8; color: #d97706; }
.stem-label { display: inline-flex; align-items: center; gap: 6rpx; font-size: 22rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 14rpx; border-radius: var(--r-pill); }
.stem-text { display: block; margin-top: 16rpx; font-size: 32rpx; color: var(--c-ink); font-weight: 600; line-height: 1.6; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; margin-bottom: 20rpx; color: var(--c-ink); }

/* 选项 / 正确答案 / 解析 */
.opt-list { display: flex; flex-direction: column; gap: 12rpx; margin-bottom: 8rpx; }
.opt-item { display: flex; align-items: center; gap: 14rpx; padding: 18rpx 20rpx; border-radius: var(--r-md); background: var(--c-bg-page); border: 1rpx solid var(--c-border); }
.opt-item.opt-selected { background: var(--c-primary-faint); border-color: var(--c-primary); }
.opt-item.opt-correct { background: var(--c-primary-faint); border-color: var(--c-primary); }
.opt-item.opt-wrong { background: #fdecec; border-color: #e35b5b; }
.opt-text { flex: 1; color: var(--c-ink); font-size: 28rpx; line-height: 1.5; }
.opt-ok { width: 32rpx; height: 32rpx; flex-shrink: 0; }
.btn-redo { margin-top: 22rpx; background: var(--c-primary); color: #fff; border-radius: var(--r-pill); font-size: 30rpx; font-weight: 700; padding: 18rpx 0; }
.btn-redo[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.redo-feedback { margin-top: 20rpx; }
.fb-line { display: block; font-size: 28rpx; font-weight: 700; margin-bottom: 12rpx; }
.fb-ok { color: var(--c-primary-deep); }
.fb-no { color: #e35b5b; }
.answer-row { display: flex; align-items: center; gap: 16rpx; margin-top: 4rpx; }
.answer-label { font-size: 24rpx; color: var(--c-text-second); }
.answer-val { font-size: 30rpx; font-weight: 700; color: var(--c-primary-deep); }
.expl-box { margin-top: 20rpx; padding-top: 20rpx; border-top: 1rpx solid var(--c-border); }
.expl-text { display: block; margin-top: 12rpx; font-size: 28rpx; color: var(--c-text-second); line-height: 1.7; }

/* 元信息卡 */
.meta-card { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 24rpx; }
.meta-chips { display: flex; flex-wrap: wrap; gap: 12rpx; }
.chip { display: inline-flex; align-items: center; height: 52rpx; padding: 0 22rpx; border-radius: var(--r-pill); font-size: 26rpx; font-weight: 600; white-space: nowrap; }
.chip-type { background: var(--c-primary-faint); color: var(--c-primary-deep); }
.chip-master { background: var(--c-bg-soft); color: var(--c-text-second); border: 1rpx solid var(--c-border); }
.chip-master.is-on { background: #e6f8ee; color: #18a058; border-color: #b8ebcf; }
</style>

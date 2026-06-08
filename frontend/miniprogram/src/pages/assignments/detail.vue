<template>
  <view class="page">
    <view v-if="!detail" class="tip">加载中…</view>
    <view v-else>
      <view class="card">
        <view class="card-title">{{ detail.assignment.title }}</view>
        <view v-if="detail.submitted && detail.score != null" class="score">得分：{{ detail.score }}</view>
        <view v-for="(q, i) in detail.assignment.questions" :key="i" class="q">
          <text class="q-stem">{{ i + 1 }}. {{ q.stem }}</text>
          <input v-model="answers[i]" class="ans-ipt" :disabled="detail.submitted" placeholder="你的答案" />
          <view v-if="detail.submitted && q.answer" class="ref-ans">
            <text class="ref-label">参考答案：</text>
            <text class="ref-val">{{ q.answer }}</text>
          </view>
        </view>
      </view>
      <button v-if="!detail.submitted" class="btn-primary" :disabled="submitting" @tap="onSubmit">
        {{ submitting ? '提交中…' : '提交作业' }}
      </button>
      <view v-else class="done-tip">客观题已自动判分，主观题待老师批改</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getStudentAssignment, submitAssignment } from '@/api/assignments'
import type { StudentAssignmentDetail } from '@/types/api'

const id = ref('')
const detail = ref<StudentAssignmentDetail | null>(null)
const answers = reactive<Record<number, string>>({})
const submitting = ref(false)

onLoad((q) => {
  id.value = (q as { id?: string })?.id || ''
  if (id.value) load()
})

async function load() {
  try {
    detail.value = await getStudentAssignment(id.value)
    // 回显已交答案
    const a = detail.value.answers
    if (Array.isArray(a)) a.forEach((it: any, i: number) => { answers[i] = it?.answer ?? String(it ?? '') })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
async function onSubmit() {
  if (!detail.value) return
  submitting.value = true
  try {
    const payload = detail.value.assignment.questions.map((_, i) => ({ index: i, answer: answers[i] || '' }))
    await submitAssignment(id.value, payload)
    await load()
    uni.showToast({ title: '已提交', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    submitting.value = false
  }
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 12rpx; }
.score { font-size: 30rpx; font-weight: 800; color: var(--c-gold); margin-bottom: 12rpx; }
.q { padding: 12rpx 0; border-bottom: 1rpx solid var(--c-border); }
.q-stem { display: block; font-size: 28rpx; color: var(--c-text-body); margin-bottom: 8rpx; }
.ans-ipt { width: 100%; height: 68rpx; border: 1rpx solid var(--c-border); border-radius: 8rpx; padding: 0 12rpx; font-size: 26rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.done-tip { text-align: center; font-size: 26rpx; color: var(--c-text-hint); padding: 16rpx; }
.ref-ans { display: flex; gap: 8rpx; margin-top: 8rpx; font-size: 24rpx; }
.ref-label { color: var(--c-text-hint); flex-shrink: 0; }
.ref-val { color: var(--c-gold); font-weight: 600; }
</style>

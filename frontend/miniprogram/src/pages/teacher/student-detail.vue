<!-- src/pages/teacher/student-detail.vue -->
<template>
  <view class="student-detail-page">

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="wqs.length === 0" class="tip">该学生暂无错题记录。</view>

    <view v-for="wq in wqs" :key="wq.id" class="wq-card">
      <image
        v-if="wq.source_image_url"
        :src="wq.source_image_url"
        class="wq-image"
        mode="widthFix"
      />
      <view v-if="wq.question_text" class="wq-text">{{ wq.question_text }}</view>
      <view class="wq-meta">
        <text>{{ wq.question_type || '未知题型' }}</text>
        <text v-if="wq.difficulty"> · 难度 {{ wq.difficulty }}</text>
        <text> · {{ wq.is_mastered ? '✅已掌握' : '⏳待掌握' }}</text>
      </view>

      <!-- 批注输入 -->
      <view class="comment-section">
        <textarea
          v-model="commentDraft[wq.id]"
          class="comment-input"
          placeholder="为这道题添加批注…"
          maxlength="500"
        />
        <button
          size="mini"
          class="btn-comment"
          :disabled="submitting[wq.id]"
          @tap="submitComment(wq.id)"
        >
          {{ submitting[wq.id] ? '提交中…' : '提交批注' }}
        </button>
      </view>

      <!-- 已有批注 -->
      <view v-if="existingComments[wq.id]?.length" class="existing-comments">
        <view
          v-for="c in existingComments[wq.id]"
          :key="c.id"
          class="comment-item"
        >
          <text class="comment-text">{{ c.comment_text }}</text>
          <text class="comment-time">{{ c.created_at.slice(0, 16).replace('T', ' ') }}</text>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue'
import { getStudentWrongQuestions, addComment, getComments } from '@/api/teacher'
import type { WrongQuestionOut, TeacherCommentOut } from '@/types/api'

const wqs = ref<WrongQuestionOut[]>([])
const loading = ref(true)
const commentDraft = reactive<Record<string, string>>({})
const submitting = reactive<Record<string, boolean>>({})
const existingComments = reactive<Record<string, TeacherCommentOut[]>>({})

onMounted(async () => {
  const pages = getCurrentPages()
  const page = pages[pages.length - 1] as any
  const sid = page.options?.studentId || ''
  if (!sid) {
    loading.value = false
    return
  }

  try {
    wqs.value = await getStudentWrongQuestions(sid)
    await Promise.all(
      wqs.value.map(async (wq) => {
        try {
          existingComments[wq.id] = await getComments(wq.id)
        } catch { /* 忽略 */ }
      })
    )
  } finally {
    loading.value = false
  }
})

async function submitComment(wqId: string) {
  const text = (commentDraft[wqId] || '').trim()
  if (!text) {
    uni.showToast({ title: '请输入批注内容', icon: 'none' })
    return
  }
  submitting[wqId] = true
  try {
    const newComment = await addComment(wqId, text)
    commentDraft[wqId] = ''
    if (!existingComments[wqId]) existingComments[wqId] = []
    existingComments[wqId].push(newComment)
    uni.showToast({ title: '批注成功', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  } finally {
    submitting[wqId] = false
  }
}
</script>

<style scoped>
.student-detail-page { padding: 16rpx; background: #f5f5f5; min-height: 100vh; }
.tip { text-align: center; padding: 60rpx; font-size: 26rpx; color: #aaa; }
.wq-card { background: #fff; border-radius: 12rpx; padding: 24rpx; margin-bottom: 16rpx; }
.wq-image { width: 100%; border-radius: 8rpx; margin-bottom: 12rpx; }
.wq-text { font-size: 28rpx; color: #333; line-height: 1.6; margin-bottom: 8rpx; white-space: pre-wrap; }
.wq-meta { font-size: 24rpx; color: #888; margin-bottom: 16rpx; }
.comment-section { border-top: 1rpx solid #f0f0f0; padding-top: 16rpx; }
.comment-input { width: 100%; border: 1rpx solid #e8e8e8; border-radius: 8rpx; padding: 12rpx; font-size: 26rpx; min-height: 80rpx; box-sizing: border-box; margin-bottom: 8rpx; }
.btn-comment { background: #1677ff; color: #fff; border-radius: 6rpx; font-size: 24rpx; }
.btn-comment[disabled] { opacity: 0.5; }
.existing-comments { margin-top: 16rpx; }
.comment-item { background: #fffbe6; border-radius: 8rpx; padding: 12rpx 16rpx; margin-bottom: 8rpx; }
.comment-text { font-size: 26rpx; color: #333; display: block; margin-bottom: 4rpx; }
.comment-time { font-size: 22rpx; color: #aaa; }
</style>

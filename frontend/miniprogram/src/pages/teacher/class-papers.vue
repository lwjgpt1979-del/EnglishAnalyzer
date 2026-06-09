<template>
  <view class="page">
    <view class="header">
      <text class="title">班级试卷</text>
      <button class="btn-compose" @tap="goCompose">+ 组卷</button>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="papers.length === 0" class="tip empty">
      <text>还没有试卷</text>
      <text class="sub">点击右上角「+ 组卷」从仿真题库选题出卷</text>
    </view>

    <view
      v-for="p in papers"
      :key="p.paper_id"
      class="card"
      @tap="goDetail(p.paper_id)"
    >
      <view class="card-top">
        <text class="paper-title">{{ p.title }}</text>
        <text class="q-count">{{ p.question_count }} 题</text>
      </view>
      <view class="card-meta">
        <text v-if="p.grade">{{ p.grade }} · {{ p.semester }}学期</text>
        <text class="created-at">{{ p.created_at.slice(0, 10) }}</text>
      </view>
      <view class="card-actions" @tap.stop>
        <button
          size="mini"
          class="btn-del"
          :disabled="deletingId === p.paper_id"
          @tap.stop="onDelete(p)"
        >
          {{ deletingId === p.paper_id ? '…' : '删除' }}
        </button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listClassPapers, deleteClassPaper } from '@/api/examPapers'
import type { ClassPaperItem } from '@/types/api'

const props = defineProps<{ classId: string }>()
const papers = ref<ClassPaperItem[]>([])
const loading = ref(false)
const deletingId = ref<string | null>(null)

async function load() {
  loading.value = true
  try {
    const r = await listClassPapers(props.classId)
    papers.value = r.data || []
  } finally {
    loading.value = false
  }
}

function goCompose() {
  uni.navigateTo({ url: `/pages/teacher/paper-compose?classId=${props.classId}` })
}

function goDetail(paperId: string) {
  uni.navigateTo({ url: `/pages/teacher/paper-compose?classId=${props.classId}&paperId=${paperId}&readonly=1` })
}

async function onDelete(p: ClassPaperItem) {
  const res = await uni.showModal({
    title: '删除试卷',
    content: `确认删除「${p.title}」？`,
    confirmText: '删除',
    confirmColor: '#f56c6c',
  })
  if (!res.confirm) return
  deletingId.value = p.paper_id
  try {
    await deleteClassPaper(p.paper_id)
    uni.showToast({ title: '已删除', icon: 'success' })
    await load()
  } catch (e: any) {
    uni.showToast({ title: e?.message || '删除失败', icon: 'none' })
  } finally {
    deletingId.value = null
  }
}

onMounted(load)

// 页面显示时重新加载（从 compose 返回后刷新）
defineExpose({ load })
</script>

<style scoped>
.page { padding: 16rpx; background: #f5f5f5; min-height: 100vh; }
.header { display: flex; align-items: center; padding: 16rpx 8rpx 24rpx; }
.title { flex: 1; font-size: 36rpx; font-weight: 700; color: #333; }
.btn-compose { background: #4f9bff; color: #fff; font-size: 26rpx; border-radius: 8rpx; padding: 0 24rpx; height: 64rpx; line-height: 64rpx; border: none; }
.tip { text-align: center; color: #aaa; padding: 80rpx 0; }
.empty { display: flex; flex-direction: column; gap: 12rpx; }
.sub { font-size: 24rpx; color: #ccc; }
.card { background: #fff; border-radius: 12rpx; margin-bottom: 16rpx; padding: 24rpx; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12rpx; }
.paper-title { font-size: 30rpx; font-weight: 600; color: #333; flex: 1; }
.q-count { font-size: 24rpx; color: #4f9bff; font-weight: 600; margin-left: 12rpx; }
.card-meta { display: flex; justify-content: space-between; font-size: 24rpx; color: #999; margin-bottom: 16rpx; }
.created-at { color: #ccc; }
.card-actions { display: flex; justify-content: flex-end; }
.btn-del { background: #fff; color: #f56c6c; border: 1px solid #f56c6c; font-size: 24rpx; border-radius: 6rpx; }
</style>

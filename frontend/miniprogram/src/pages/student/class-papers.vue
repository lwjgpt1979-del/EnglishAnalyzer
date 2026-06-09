<template>
  <view class="page">
    <view class="page-title">班级试卷</view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="papers.length === 0" class="tip empty">暂无试卷</view>

    <view
      v-for="p in papers"
      :key="p.paper_id"
      class="card"
      @tap="goPaper(p.paper_id)"
    >
      <view class="card-top">
        <text class="paper-title">{{ p.title }}</text>
        <text class="q-count">{{ p.question_count }} 题</text>
      </view>
      <view class="card-meta">
        <text v-if="p.grade">{{ p.grade }} · {{ p.semester }}学期</text>
        <text class="created-at">{{ p.created_at.slice(0, 10) }}</text>
      </view>
      <text v-if="p.description" class="desc">{{ p.description }}</text>
      <view class="card-footer">
        <text class="btn-view">查看试卷 ›</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listStudentClassPapers } from '@/api/examPapers'
import type { ClassPaperItem } from '@/types/api'

const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as any
const classId: string = currentPage.options?.classId || ''

const papers = ref<ClassPaperItem[]>([])
const loading = ref(false)

async function load() {
  if (!classId) return
  loading.value = true
  try {
    const r = await listStudentClassPapers(classId)
    papers.value = r.data || []
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

function goPaper(paperId: string) {
  uni.navigateTo({ url: `/pages/student/paper-view?paperId=${paperId}` })
}

onMounted(load)
</script>

<style scoped>
.page { padding: 24rpx; background: #f5f5f5; min-height: 100vh; }
.page-title { font-size: 36rpx; font-weight: 700; color: #333; margin-bottom: 24rpx; padding: 8rpx 0; }
.tip { text-align: center; color: #aaa; padding: 80rpx 0; font-size: 28rpx; }
.empty { display: block; }
.card { background: #fff; border-radius: 12rpx; padding: 28rpx; margin-bottom: 16rpx; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.card-top { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12rpx; }
.paper-title { font-size: 32rpx; font-weight: 700; color: #333; flex: 1; }
.q-count { font-size: 26rpx; color: #4f9bff; font-weight: 600; margin-left: 16rpx; }
.card-meta { display: flex; justify-content: space-between; font-size: 24rpx; color: #999; margin-bottom: 8rpx; }
.created-at { color: #ccc; }
.desc { font-size: 26rpx; color: #666; display: block; margin-bottom: 12rpx; }
.card-footer { display: flex; justify-content: flex-end; padding-top: 12rpx; border-top: 1px solid #f5f5f5; margin-top: 8rpx; }
.btn-view { font-size: 26rpx; color: #4f9bff; }
</style>

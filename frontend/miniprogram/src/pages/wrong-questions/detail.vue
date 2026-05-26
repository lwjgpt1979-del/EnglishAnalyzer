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
import { onMounted, ref } from 'vue'
import {
  analyzeWrongQuestion,
  getWrongQuestion,
  listAnalyses,
  markMastered,
} from '@/api/wrongQuestions'
import type { AiAnalysisOut, WrongQuestionOut } from '@/types/api'

// uni-app 小程序获取路由参数方式
const pages = getCurrentPages()
const currentPage = pages[pages.length - 1] as UniApp.Page & { options: Record<string, string> }
const wqId = currentPage.options.id

const wq = ref<WrongQuestionOut | null>(null)
const latestAnalysis = ref<AiAnalysisOut | null>(null)
const analyzing = ref(false)

onMounted(async () => {
  try {
    wq.value = await getWrongQuestion(wqId)
    const analyses = await listAnalyses(wqId)
    if (analyses.length > 0) latestAnalysis.value = analyses[0]
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
</style>

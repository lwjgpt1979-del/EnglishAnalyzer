<!-- src/pages/upload/index.vue -->
<template>
  <view class="upload-page">
    <view class="card">
      <view class="card-title">上传错题图片</view>

      <!-- 题型选择 -->
      <view class="form-item">
        <text class="label">题型</text>
        <picker :range="questionTypes" @change="onTypeChange">
          <view class="picker-val">{{ selectedType || '请选择（可选）' }}</view>
        </picker>
      </view>

      <!-- 难度选择 -->
      <view class="form-item">
        <text class="label">难度</text>
        <picker :range="difficulties" @change="onDiffChange">
          <view class="picker-val">
            {{ selectedDiff ? selectedDiff + ' 星' : '请选择（可选）' }}
          </view>
        </picker>
      </view>

      <!-- 上传按钮 -->
      <button class="btn-upload" :disabled="uploading" @tap="onUpload">
        {{ uploadBtnText }}
      </button>

      <!-- 错误提示 -->
      <view v-if="errorMsg" class="error-msg">{{ errorMsg }}</view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { useUpload } from '@/composables/useUpload'

const auth = useAuthStore()
const questionTypes = ['单选', '完型', '阅读', '作文', '其他']
const difficulties = ['1', '2', '3', '4', '5']

const selectedType = ref('')
const selectedDiff = ref<number | undefined>(undefined)

const { uploading, progress, errorMsg, uploadAndCreate } = useUpload()

function onTypeChange(e: { detail: { value: number } }) {
  selectedType.value = questionTypes[e.detail.value]
}

function onDiffChange(e: { detail: { value: number } }) {
  selectedDiff.value = e.detail.value + 1
}

const uploadBtnText = computed(() => {
  const map: Record<string, string> = {
    idle: '选图上传',
    choosing: '选择图片中…',
    presigning: '准备上传…',
    uploading: '上传图片中…',
    creating: '保存错题中…',
    done: '上传成功！',
    error: '重试上传',
  }
  return map[progress.value] || '选图上传'
})

async function onUpload() {
  if (!auth.isLoggedIn()) {
    await auth.login()
    return
  }
  const wq = await uploadAndCreate({
    questionType: selectedType.value || undefined,
    difficulty: selectedDiff.value,
  })
  if (wq) {
    uni.showToast({ title: '上传成功', icon: 'success' })
    setTimeout(() => {
      uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${wq.id}` })
    }, 800)
  } else {
    uni.showToast({ title: errorMsg.value || '上传失败', icon: 'error' })
  }
}
</script>

<style scoped>
.upload-page { padding: 24rpx; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 32rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: 32rpx; font-weight: 700; margin-bottom: 32rpx; color: var(--c-ink); }
.form-item {
  display: flex;
  align-items: center;
  padding: 20rpx 0;
  border-bottom: 1rpx solid var(--c-border);
}
.label { width: 120rpx; color: var(--c-text-second); font-size: 28rpx; }
.picker-val { flex: 1; color: var(--c-text-body); font-size: 28rpx; padding-left: 16rpx; }
.btn-upload {
  margin-top: 48rpx;
  background: var(--c-primary);
  color: var(--c-on-primary);
  border-radius: var(--r-btn);
  font-size: 32rpx;
  font-weight: 700;
  height: 96rpx;
  line-height: 96rpx;
}
.btn-upload[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.error-msg { margin-top: 20rpx; color: var(--c-danger); font-size: 26rpx; text-align: center; }
</style>

<template>
  <view class="page">
    <view class="card">
      <view class="card-title">拍整份作业</view>
      <view class="hint">
        一份作业可拍 1~9 张图片。多张时请<text class="em">按页码顺序</text>排列，
        系统会按此顺序拼接识别（可上移/下移调整）。
      </view>

      <!-- 标题 -->
      <view class="form-item">
        <text class="label">标题</text>
        <input v-model="title" class="title-input" placeholder="留空自动命名（名字+日期）" maxlength="100" />
      </view>

      <!-- 图片网格 -->
      <view class="grid">
        <view v-for="(it, idx) in items" :key="it.url" class="thumb">
          <image :src="it.temp" mode="aspectFill" class="thumb-img" @tap="preview(idx)" />
          <view class="order-tag">{{ idx + 1 }}</view>
          <view class="thumb-ops">
            <text class="op" :class="{ disabled: idx === 0 }" @tap="move(idx, -1)">↑</text>
            <text class="op" :class="{ disabled: idx === items.length - 1 }" @tap="move(idx, 1)">↓</text>
            <view class="op del" @tap="remove(idx)"><view class="ic ic-x-circle" style="width:30rpx;height:30rpx" /></view>
          </view>
        </view>

        <view v-if="items.length < MAX" class="thumb add" @tap="addImages">
          <view class="add-icon ic ic-plus" />
          <text class="add-text">{{ adding ? '上传中…' : '加图片' }}</text>
        </view>
      </view>

      <button
        class="btn-submit"
        :disabled="submitting || adding || !items.length"
        @tap="submit"
      >
        {{ submitBtnText }}
      </button>

      <view v-if="errorMsg" class="error-msg">{{ errorMsg }}</view>
    </view>

    <view class="card-link" @tap="goList">查看我的作业 ›</view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { uploadOneImage } from '@/composables/useUpload'
import { createUserPaper } from '@/api/userPapers'

const MAX = 9
const auth = useAuthStore()

interface Item {
  temp: string // 本地预览路径
  url: string // 上传后 COS file_url（提交用）
}

const items = ref<Item[]>([])
const title = ref('')
const adding = ref(false)
const submitting = ref(false)
const errorMsg = ref('')

const submitBtnText = computed(() => {
  if (submitting.value) return '提交中…'
  if (!items.value.length) return '请先加图片'
  return `提交识别（${items.value.length} 张）`
})

async function addImages() {
  if (adding.value) return
  if (!auth.isLoggedIn()) {
    await auth.login()
    return
  }
  adding.value = true
  errorMsg.value = ''
  try {
    const remaining = MAX - items.value.length
    const tempPaths = await new Promise<string[]>((resolve, reject) => {
      uni.chooseImage({
        count: remaining,
        sizeType: ['compressed'],
        sourceType: ['album', 'camera'],
        success: (res) => resolve(res.tempFilePaths as string[]),
        fail: (err) => {
          const msg = err.errMsg || ''
          if (msg.includes('cancel')) {
            resolve([])
          } else {
            reject(new Error(msg || '选图失败'))
          }
        },
      })
    })
    for (const temp of tempPaths) {
      const url = await uploadOneImage(temp)
      items.value.push({ temp, url })
    }
  } catch (e) {
    errorMsg.value = (e as Error).message || '加图片失败'
    uni.showToast({ title: errorMsg.value, icon: 'none' })
  } finally {
    adding.value = false
  }
}

function move(idx: number, dir: -1 | 1) {
  const target = idx + dir
  if (target < 0 || target >= items.value.length) return
  const arr = items.value
  ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
}

function remove(idx: number) {
  items.value.splice(idx, 1)
}

function preview(idx: number) {
  uni.previewImage({
    urls: items.value.map((i) => i.temp),
    current: idx,
  })
}

async function submit() {
  if (!items.value.length || submitting.value) return
  submitting.value = true
  errorMsg.value = ''
  try {
    const res = await createUserPaper(
      items.value.map((i) => i.url),
      title.value.trim() || undefined,
    )
    if (res.reused) uni.showToast({ title: '这张卷子已解析过,已为你打开', icon: 'none' })
    uni.redirectTo({ url: `/pages/user-papers/detail?id=${res.id}` })
  } catch (e) {
    errorMsg.value = (e as Error).message || '提交失败'
    uni.showToast({ title: errorMsg.value, icon: 'none' })
  } finally {
    submitting.value = false
  }
}

function goList() {
  uni.navigateTo({ url: '/pages/user-papers/list' })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 32rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: 32rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.hint { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-bottom: 24rpx; }
.hint .em { color: var(--c-danger); font-weight: 700; }
.form-item { display: flex; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); margin-bottom: 24rpx; }
.label { width: 100rpx; color: var(--c-text-second); font-size: 28rpx; }
.title-input { flex: 1; font-size: 28rpx; color: var(--c-text-body); padding-left: 16rpx; }
.grid { display: flex; flex-wrap: wrap; gap: 16rpx; }
.thumb { position: relative; width: 200rpx; height: 200rpx; border-radius: var(--r-md); overflow: hidden; background: var(--c-bg-soft); }
.thumb-img { width: 100%; height: 100%; }
.order-tag { position: absolute; top: 8rpx; left: 8rpx; min-width: 36rpx; height: 36rpx; line-height: 36rpx; text-align: center; background: rgba(0,0,0,.6); color: #fff; font-size: 22rpx; border-radius: 18rpx; padding: 0 8rpx; }
.thumb-ops { position: absolute; bottom: 0; left: 0; right: 0; display: flex; justify-content: space-around; background: rgba(0,0,0,.5); }
.op { color: #fff; font-size: 28rpx; padding: 6rpx 0; flex: 1; text-align: center; display: flex; align-items: center; justify-content: center; }
.op.disabled { color: rgba(255,255,255,.35); }
.op.del { color: #ff8a8a; }
.add { display: flex; flex-direction: column; align-items: center; justify-content: center; border: 2rpx dashed var(--c-border); }
.add-icon { width: 56rpx; height: 56rpx; }
.add-text { font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.btn-submit { margin-top: 40rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); font-size: 32rpx; font-weight: 700; height: 96rpx; line-height: 96rpx; }
.btn-submit[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.error-msg { margin-top: 20rpx; color: var(--c-danger); font-size: 26rpx; text-align: center; }
.card-link { margin-top: 24rpx; text-align: center; color: var(--c-text-second); font-size: 28rpx; padding: 16rpx; }
</style>

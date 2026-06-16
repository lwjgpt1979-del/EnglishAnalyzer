<!-- 意见反馈 / BUG 报告（§13.3）-->
<template>
  <view class="fb-page">
    <view class="card">
      <text class="label">反馈类型</text>
      <view class="kinds">
        <view class="kind" :class="{ on: kind === 'suggestion' }" @tap="kind = 'suggestion'">💡 功能建议</view>
        <view class="kind" :class="{ on: kind === 'bug' }" @tap="kind = 'bug'">🐞 BUG报告</view>
      </view>
      <text class="label">详细描述</text>
      <textarea v-model="content" class="ta" placeholder="请描述您的建议或遇到的问题…" maxlength="1000" />
      <text class="label">截图（{{ images.length }}/6，选填）</text>
      <view class="imgs">
        <image v-for="(u, i) in images" :key="i" :src="u" class="img" mode="aspectFill" @tap="removeImg(i)" />
        <view v-if="images.length < 6" class="add" @tap="addImg">{{ uploading ? '…' : '+' }}</view>
      </view>
      <text class="label">联系方式（选填）</text>
      <input v-model="contact" class="ipt" placeholder="手机号/微信，方便我们回访" maxlength="60" />
      <button class="submit" :disabled="submitting" @tap="submit">{{ submitting ? '提交中…' : '提交反馈' }}</button>
    </view>

    <view v-if="mine.length" class="card">
      <text class="card-title">我的反馈</text>
      <view v-for="f in mine" :key="f.id" class="mine-item">
        <view class="mine-row">
          <text class="mine-kind">{{ f.kind === 'bug' ? 'BUG' : '建议' }}</text>
          <text class="mine-status" :class="f.status">{{ ST[f.status] || f.status }}</text>
        </view>
        <text class="mine-content">{{ f.content }}</text>
        <text v-if="f.note" class="mine-note">官方回复：{{ f.note }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { submitFeedback, myFeedback, type MyFeedback } from '@/api/feedback'
import { uploadOneImage } from '@/composables/useUpload'

const kind = ref('suggestion')
const content = ref('')
const images = ref<string[]>([])
const contact = ref('')
const uploading = ref(false)
const submitting = ref(false)
const mine = ref<MyFeedback[]>([])
const ST: Record<string, string> = { pending: '待处理', reviewing: '处理中', done: '已处理', dismissed: '已忽略' }

function addImg() {
  if (uploading.value || images.value.length >= 6) return
  uni.chooseImage({ count: 1, sizeType: ['compressed'], success: async (res) => {
    const p = (res.tempFilePaths || [])[0]; if (!p) return
    uploading.value = true
    try { const url = await uploadOneImage(p); if (url) images.value.push(url) }
    catch (e: any) { uni.showToast({ title: e?.message || '上传失败', icon: 'none' }) }
    finally { uploading.value = false }
  } })
}
function removeImg(i: number) { images.value.splice(i, 1) }

async function submit() {
  if (!content.value.trim()) { uni.showToast({ title: '请填写反馈内容', icon: 'none' }); return }
  submitting.value = true
  try {
    await submitFeedback({ kind: kind.value, content: content.value.trim(), images: images.value, contact: contact.value.trim() || undefined })
    uni.showToast({ title: '感谢您的反馈！', icon: 'none' })
    content.value = ''; images.value = []; contact.value = ''
    await load()
  } catch (e: any) { uni.showToast({ title: e?.message || '提交失败', icon: 'none' }) }
  finally { submitting.value = false }
}
async function load() { try { mine.value = (await myFeedback()).items } catch { /* ignore */ } }

onShow(load)
</script>

<style scoped>
.fb-page { padding: 24rpx; background: #f5f6f8; min-height: 100vh; }
.card { background: #fff; border-radius: 16rpx; padding: 28rpx; margin-bottom: 24rpx; }
.card-title { font-size: 30rpx; font-weight: 600; color: #222; display: block; margin-bottom: 16rpx; }
.label { font-size: 26rpx; color: #666; display: block; margin: 20rpx 0 12rpx; }
.kinds { display: flex; gap: 16rpx; }
.kind { flex: 1; text-align: center; padding: 18rpx 0; border-radius: 12rpx; background: #f0f2f5; font-size: 28rpx; color: #555; }
.kind.on { background: #409eff; color: #fff; }
.ta { background: #f7f8fa; border-radius: 12rpx; padding: 20rpx; font-size: 28rpx; height: 200rpx; width: 100%; box-sizing: border-box; }
.ipt { background: #f7f8fa; border-radius: 12rpx; padding: 20rpx; font-size: 28rpx; }
.imgs { display: flex; flex-wrap: wrap; gap: 16rpx; }
.img, .add { width: 140rpx; height: 140rpx; border-radius: 12rpx; }
.add { background: #f0f2f5; display: flex; align-items: center; justify-content: center; font-size: 56rpx; color: #bbb; }
.submit { background: #409eff; color: #fff; border-radius: 999rpx; font-size: 30rpx; margin-top: 32rpx; }
.mine-item { border-bottom: 1rpx solid #f0f0f0; padding: 16rpx 0; }
.mine-row { display: flex; justify-content: space-between; }
.mine-kind { font-size: 24rpx; color: #409eff; }
.mine-status { font-size: 24rpx; color: #e6a23c; }
.mine-status.done { color: #67c23a; }
.mine-status.dismissed { color: #999; }
.mine-content { font-size: 28rpx; color: #333; display: block; margin: 8rpx 0; }
.mine-note { font-size: 24rpx; color: #666; display: block; }
</style>

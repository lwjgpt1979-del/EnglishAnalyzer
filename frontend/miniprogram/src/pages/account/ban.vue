<!-- src/pages/account/ban.vue 封禁说明 + 申诉（§5.3.1）-->
<template>
  <view class="ban-page">
    <view class="ban-card">
      <view class="ban-emoji ic ic-x-circle" />
      <text class="ban-title">账号已被{{ status?.ban_type === 'permanent' ? '永久' : '临时' }}封禁</text>
      <text class="ban-reason">原因：{{ status?.reason || '违反平台规则' }}</text>
      <text v-if="status?.banned_until" class="ban-until">解封时间：{{ fmt(status.banned_until) }}</text>
      <text class="ban-note">封禁期间无法使用功能，仅可查看本页与提交申诉。会员有效期在封禁期间暂停计时。</text>
    </view>

    <!-- 申诉记录 -->
    <view v-if="appeals.length" class="card">
      <text class="card-title">我的申诉</text>
      <view v-for="a in appeals" :key="a.id" class="ap-item">
        <view class="ap-row"><text class="ap-reason">{{ a.reason }}</text>
          <text class="ap-status" :class="a.status">{{ ST[a.status] || a.status }}</text></view>
        <text v-if="a.note" class="ap-note">处理备注：{{ a.note }}</text>
      </view>
    </view>

    <!-- 申诉表单 -->
    <view v-if="canAppeal" class="card">
      <text class="card-title">提交申诉</text>
      <textarea v-model="reason" class="ap-input" placeholder="请说明申诉理由（如：误判、未违规）" maxlength="500" />
      <text class="ap-label">证明截图（{{ evidence.length }}/3，选填）</text>
      <view class="ap-imgs">
        <image v-for="(u, i) in evidence" :key="i" :src="u" class="ap-img" mode="aspectFill" @tap="removeImg(i)" />
        <view v-if="evidence.length < 3" class="ap-add" @tap="addImg">{{ imgUploading ? '…' : '+' }}</view>
      </view>
      <button class="ap-submit" :disabled="submitting" @tap="submit">{{ submitting ? '提交中…' : '提交申诉' }}</button>
    </view>
    <view v-else-if="status?.banned" class="card hint-card">已有待审申诉，请耐心等待 3 个工作日内处理。</view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getBanStatus, submitBanAppeal, getMyBanAppeals, type BanStatus, type MyBanAppeal } from '@/api/ban'
import { uploadOneImage } from '@/composables/useUpload'

const status = ref<BanStatus | null>(null)
const appeals = ref<MyBanAppeal[]>([])
const reason = ref('')
const evidence = ref<string[]>([])
const imgUploading = ref(false)
const submitting = ref(false)

const ST: Record<string, string> = { pending: '审核中', approved: '已通过(已解封)', rejected: '已驳回' }
const canAppeal = computed(() => status.value?.banned && !appeals.value.some(a => a.status === 'pending'))
function fmt(s: string) { return (s || '').replace('T', ' ').slice(0, 16) }

async function load() {
  try { status.value = await getBanStatus() } catch { /* ignore */ }
  try { appeals.value = await getMyBanAppeals() } catch { /* ignore */ }
}
function addImg() {
  if (imgUploading.value || evidence.value.length >= 3) return
  uni.chooseImage({ count: 1, sizeType: ['compressed'], success: async (res) => {
    const p = (res.tempFilePaths || [])[0]; if (!p) return
    imgUploading.value = true
    try { evidence.value.push(await uploadOneImage(p)) }
    catch (e) { uni.showToast({ title: (e as Error).message || '上传失败', icon: 'none' }) }
    finally { imgUploading.value = false }
  } })
}
function removeImg(i: number) { evidence.value.splice(i, 1) }
async function submit() {
  if (!reason.value.trim()) { uni.showToast({ title: '请填写申诉理由', icon: 'none' }); return }
  submitting.value = true
  try {
    await submitBanAppeal(reason.value.trim(), evidence.value.length ? [...evidence.value] : undefined)
    uni.showToast({ title: '申诉已提交', icon: 'success' })
    reason.value = ''; evidence.value = []
    await load()
  } catch (e) { uni.showToast({ title: (e as Error).message || '提交失败', icon: 'none' }) }
  finally { submitting.value = false }
}
onMounted(load)
</script>

<style scoped>
.ban-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.ban-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 40rpx 28rpx; display: flex; flex-direction: column; align-items: center; gap: 12rpx; margin-bottom: 20rpx; }
.ban-emoji { width: 88rpx; height: 88rpx; }
.ban-title { font-size: 34rpx; font-weight: 800; color: var(--c-danger); }
.ban-reason { font-size: 28rpx; color: var(--c-text-body); text-align: center; }
.ban-until { font-size: 26rpx; color: var(--c-text-second); }
.ban-note { font-size: 24rpx; color: var(--c-text-hint); text-align: center; line-height: 1.6; margin-top: 8rpx; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 16rpx; }
.card-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); display: block; margin-bottom: 12rpx; }
.ap-item { padding: 12rpx 0; border-bottom: 1rpx solid var(--c-border); }
.ap-row { display: flex; justify-content: space-between; }
.ap-reason { flex: 1; font-size: 26rpx; color: var(--c-text-body); }
.ap-status { font-size: 24rpx; font-weight: 700; }
.ap-status.pending { color: #ffb020; } .ap-status.approved { color: #18a058; } .ap-status.rejected { color: var(--c-danger); }
.ap-note { font-size: 22rpx; color: var(--c-text-hint); }
.ap-input { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 18rpx; width: 100%; box-sizing: border-box; height: 160rpx; font-size: 26rpx; }
.ap-label { display: block; font-size: 24rpx; color: var(--c-text-second); margin: 12rpx 0 8rpx; }
.ap-imgs { display: flex; flex-wrap: wrap; gap: 14rpx; }
.ap-img { width: 140rpx; height: 140rpx; border-radius: var(--r-md); }
.ap-add { width: 140rpx; height: 140rpx; border-radius: var(--r-md); border: 2rpx dashed var(--c-border); display: flex; align-items: center; justify-content: center; font-size: 52rpx; color: var(--c-text-hint); }
.ap-submit { margin-top: 20rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); height: 84rpx; line-height: 84rpx; font-size: 30rpx; font-weight: 700; }
.hint-card { font-size: 24rpx; color: var(--c-text-hint); text-align: center; }
</style>

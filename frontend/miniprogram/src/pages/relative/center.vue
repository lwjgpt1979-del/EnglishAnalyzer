<template>
  <view class="page">
    <view class="card">
      <view class="card-title">绑定孩子账号</view>
      <view class="bind-intro">
        <text class="bind-intro-title">绑定孩子后，你可以：</text>
        <text class="bind-feat">📊 查看孩子的学情报告与学习周报</text>
        <text class="bind-feat">🧠 查看知识点掌握台账与复习建议</text>
        <text class="bind-feat">📅 关注每日打卡与练习情况</text>
      </view>
      <text class="bind-hint">向孩子索取邀请码（孩子在「我的」页生成），或用微信扫孩子分享的二维码。</text>
      <input v-model="bindCode" class="input" maxlength="6" placeholder="6位邀请码" @input="bindCode = bindCode.toUpperCase()" />
      <input v-model="relationship" class="input" placeholder="关系（如：母亲/父亲/祖父）" />
      <button class="btn-primary" :disabled="!bindCode || !relationship || binding" @tap="onBind">
        {{ binding ? '绑定中…' : '绑定' }}
      </button>
    </view>

    <view class="card">
      <view class="card-title">我的孩子（{{ children.length }}）</view>
      <view v-if="loading" class="tip">加载中…</view>
      <view v-else-if="children.length === 0" class="tip">还没有绑定的孩子。</view>
      <view v-for="c in children" :key="c.student_id" class="child-row" @tap="goView(c.student_id)">
        <view>
          <text class="cname">{{ c.nickname || ('孩子 ' + c.student_id.slice(0, 8) + '…') }}</text>
          <text class="crel">{{ c.relationship }}</text>
        </view>
        <text class="arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { bindRelative, getMyStudentsAsRelative } from '@/api/relative'
import type { BoundStudent } from '@/types/api'
const bindCode = ref('')
const relationship = ref('')
const binding = ref(false)
const children = ref<BoundStudent[]>([])
const loading = ref(false)
async function load() {
  loading.value = true
  try { children.value = (await getMyStudentsAsRelative()) || [] }
  finally { loading.value = false }
}
async function onBind() {
  binding.value = true
  try {
    await bindRelative(bindCode.value, relationship.value)
    bindCode.value = ''; relationship.value = ''
    await load()
    uni.showToast({ title: '绑定成功', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
  } finally { binding.value = false }
}
function goView(sid: string) { uni.navigateTo({ url: `/pages/relative/student-view?studentId=${sid}` }) }
onMounted(load)

// 扫码进入：scene 形如 r:CODE → prompt 关系名 → 自动调家人绑定
onLoad((options) => {
  const sceneRaw = (options as any)?.scene
  if (!sceneRaw) return
  const scene = decodeURIComponent(sceneRaw)
  if (!scene.startsWith('r:')) return
  const code = scene.slice(2)
  if (!code) return
  // 关系字段需要用户填，弹 editable modal
  uni.showModal({
    title: '请填写您与孩子的关系',
    editable: true,
    placeholderText: '如：母亲 / 父亲 / 祖父',
    success: async (res) => {
      if (!res.confirm || !res.content?.trim()) return
      uni.showLoading({ title: '绑定中…' })
      try {
        await bindRelative(code, res.content.trim())
        uni.hideLoading()
        uni.showToast({ title: '已绑定孩子', icon: 'success' })
        if (typeof load === 'function') load()
      } catch (e: any) {
        uni.hideLoading()
        uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
      }
    },
  })
})
</script>

<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin-bottom: 16rpx; width: 100%; box-sizing: border-box; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.tip { text-align: center; padding: 60rpx 0; color: var(--c-text-hint); font-size: 26rpx; }
.child-row { display: flex; justify-content: space-between; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.child-row:last-child { border-bottom: none; }
.cname { font-size: 28rpx; color: var(--c-ink); font-weight: 700; display: block; }
.crel { font-size: 24rpx; color: var(--c-text-hint); }
.arrow { font-size: 32rpx; color: var(--c-text-hint); }
.bind-intro { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 10rpx; }
.bind-intro-title { font-size: 26rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 4rpx; }
.bind-feat { font-size: 25rpx; color: var(--c-text-body); line-height: 1.5; }
.bind-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); line-height: 1.5; margin-bottom: 16rpx; }
</style>

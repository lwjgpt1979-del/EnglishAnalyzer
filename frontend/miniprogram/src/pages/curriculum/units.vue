<template>
  <view class="page">
    <view class="header">
      <text class="header-title">{{ textbookVersion }} · {{ grade }} · {{ semester }}</text>
      <text class="header-sub">共 {{ units.length }} 个单元，前 1 个免费</text>
    </view>

    <view v-if="loading" class="empty">加载中…</view>
    <view v-else-if="!units.length" class="empty">该学期暂无内容</view>

    <view v-else class="unit-list">
      <view
        v-for="u in units"
        :key="u.id"
        class="unit-card"
        :class="{ locked: u.locked }"
        @tap="onTapUnit(u)"
      >
        <view class="unit-no-badge">U{{ u.unit_no }}</view>
        <view class="unit-body">
          <text class="unit-title">{{ u.unit_title }}</text>
          <text class="unit-meta">{{ u.kp_count }} 个知识点</text>
        </view>
        <view class="unit-status">
          <view v-if="u.locked" class="ic ic-lock lock-icon" />
          <text v-else class="open-icon">›</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listUnits } from '@/api/curriculum'
import type { UnitOut } from '@/types/api'

const textbookVersion = ref('')
const grade = ref('')
const semester = ref('')
const units = ref<UnitOut[]>([])
const loading = ref(true)

function safeDecode(s: string | undefined): string {
  if (!s) return ''
  try { return decodeURIComponent(s) } catch { return s }
}

onLoad(async (q: any) => {
  // profile 页用 encodeURIComponent 编码后通过 url 传过来；
  // uni-app onLoad 不自动 decode → 必须手动 decodeURIComponent，
  // 否则会把字面 %E8%AF%91... 当 textbook_version 发给后端，
  // 后端 enum cast 失败 500。
  textbookVersion.value = safeDecode(q.textbook) || '译林版'
  grade.value = safeDecode(q.grade) || '小学5年级'
  semester.value = safeDecode(q.semester) || '上'
  try {
    units.value = await listUnits(textbookVersion.value, grade.value, semester.value)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
})

function onTapUnit(u: UnitOut) {
  if (u.locked) {
    uni.showModal({
      title: '需要解锁',
      content: `购买《${textbookVersion.value} ${grade.value} ${semester.value}》学期会员后可学习所有单元。`,
      confirmText: '去个人中心',
      success: (r) => {
        if (r.confirm) uni.switchTab({ url: '/pages/profile/index' })
      },
    })
    return
  }
  uni.navigateTo({ url: `/pages/curriculum/unit-detail?id=${u.id}` })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.header { padding: 12rpx 0 24rpx; }
.header-title { display: block; font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); }
.header-sub { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.empty { text-align: center; color: var(--c-text-hint); padding: 80rpx 0; font-size: 28rpx; }
.unit-list { display: flex; flex-direction: column; gap: 16rpx; }
.unit-card {
  background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx;
  box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04);
  display: flex; align-items: center; gap: 20rpx;
}
.unit-card.locked { opacity: .65; }
.unit-no-badge {
  background: var(--c-primary); color: var(--c-on-primary);
  border-radius: var(--r-md); padding: 8rpx 16rpx;
  font-size: 28rpx; font-weight: 800; min-width: 64rpx; text-align: center;
}
.unit-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.unit-title { font-size: 30rpx; font-weight: 600; color: var(--c-ink); }
.unit-meta { font-size: 24rpx; color: var(--c-text-second); }
.unit-status { font-size: 32rpx; color: var(--c-text-hint); }
.lock-icon { width: 36rpx; height: 36rpx; }
</style>

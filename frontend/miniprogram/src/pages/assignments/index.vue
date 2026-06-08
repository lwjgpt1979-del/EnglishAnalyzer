<template>
  <view class="page">
    <view class="card">
      <view class="card-title">老师任务</view>
      <view v-if="!list.length" class="empty">暂无作业</view>
      <view v-for="a in list" :key="a.id" class="row" @tap="goDetail(a.id)">
        <view>
          <text class="row-title">{{ a.title }}</text>
          <text class="row-sub">{{ a.submitted ? (a.score != null ? '已批改 ' + a.score + ' 分' : '已提交') : '待完成' }}{{ a.due_at ? '　截止 ' + a.due_at.slice(0, 10) : '' }}</text>
        </view>
        <text class="row-arrow">›</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getReceivedAssignments } from '@/api/assignments'
import type { StudentAssignmentItem } from '@/types/api'

const list = ref<StudentAssignmentItem[]>([])
async function load() {
  try { list.value = await getReceivedAssignments() } catch { /* 忽略 */ }
}
onShow(load)
function goDetail(id: string) { uni.navigateTo({ url: `/pages/assignments/detail?id=${id}` }) }
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row-title { font-size: 28rpx; color: var(--c-text-body); display: block; }
.row-sub { font-size: 22rpx; color: var(--c-text-hint); }
.row-arrow { color: var(--c-text-hint); font-size: 36rpx; }
</style>

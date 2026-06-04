<template>
  <view class="page">
    <view v-if="!detail" class="tip">加载中…</view>
    <view v-else>
      <view class="card">
        <view class="card-title">{{ detail.assignment.title }}</view>
        <view v-for="(q, i) in detail.assignment.questions" :key="i" class="q">
          <text class="q-stem">{{ i + 1 }}. {{ q.stem }}</text>
          <text v-if="q.answer" class="q-ans">参考答案：{{ q.answer }}</text>
        </view>
      </view>

      <view v-if="stats" class="card">
        <view class="card-title">统计</view>
        <view class="stat-row"><text>完成率</text><text class="stat-v">{{ Math.round(stats.completion_rate * 100) }}%（{{ stats.submitted_count }}/{{ stats.total_students }}）</text></view>
        <view v-if="stats.avg_score != null" class="stat-row"><text>平均分</text><text class="stat-v">{{ stats.avg_score }}（{{ stats.min_score }}~{{ stats.max_score }}）</text></view>
        <view v-for="p in stats.per_question" :key="p.index" class="stat-row">
          <text>第 {{ p.index + 1 }} 题正确率</text><text class="stat-v">{{ Math.round(p.rate * 100) }}%（{{ p.correct }}/{{ p.total }}）</text>
        </view>
      </view>

      <view class="card">
        <view class="card-title">提交（{{ detail.submissions.length }}）</view>
        <view v-if="!detail.submissions.length" class="empty">还没有学生提交</view>
        <view v-for="su in detail.submissions" :key="su.id" class="sub">
          <text class="sub-head">学生 {{ su.student_id.slice(0, 8) }}… · {{ su.score != null ? su.score + ' 分' : '未批改' }}</text>
          <text class="sub-ans">{{ JSON.stringify(su.answers) }}</text>
          <view class="grade-row">
            <input v-model="scores[su.id]" class="score-ipt" type="number" placeholder="分数" />
            <text class="op" @tap="onGrade(su.id)">打分</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getAssignmentDetail, gradeSubmission, getAssignmentStats } from '@/api/assignments'
import type { TeacherAssignmentDetail, AssignmentStats } from '@/types/api'

const id = ref('')
const detail = ref<TeacherAssignmentDetail | null>(null)
const stats = ref<AssignmentStats | null>(null)
const scores = reactive<Record<string, string>>({})

onLoad((q) => {
  id.value = (q as { id?: string })?.id || ''
  if (id.value) load()
})

async function load() {
  try {
    detail.value = await getAssignmentDetail(id.value)
    stats.value = await getAssignmentStats(id.value)
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
async function onGrade(sid: string) {
  const score = Number(scores[sid])
  if (Number.isNaN(score)) { uni.showToast({ title: '请输入分数', icon: 'none' }); return }
  try {
    await gradeSubmission(sid, score)
    await load()
    uni.showToast({ title: '已打分', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.q { padding: 8rpx 0; border-bottom: 1rpx solid var(--c-border); }
.q-stem { display: block; font-size: 28rpx; color: var(--c-text-body); }
.q-ans { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-top: 4rpx; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.sub { border-top: 1rpx solid var(--c-border); padding: 12rpx 0; }
.sub-head { display: block; font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.sub-ans { display: block; font-size: 24rpx; color: var(--c-text-second); margin: 6rpx 0; }
.grade-row { display: flex; align-items: center; gap: 16rpx; }
.score-ipt { width: 160rpx; height: 64rpx; border: 1rpx solid var(--c-border); border-radius: 8rpx; padding: 0 12rpx; font-size: 26rpx; }
.op { font-size: 26rpx; color: var(--c-primary); font-weight: 700; }
.stat-row { display: flex; justify-content: space-between; font-size: 26rpx; color: var(--c-text-body); padding: 6rpx 0; }
.stat-v { font-weight: 700; color: var(--c-gold); }
</style>

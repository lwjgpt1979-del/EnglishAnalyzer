<template>
  <view class="page">
    <view class="card">
      <view class="card-title">出卷</view>
      <input v-model="title" class="ipt" placeholder="作业标题" />
      <view v-for="(q, i) in questions" :key="i" class="q-block">
        <view class="q-head">第 {{ i + 1 }} 题 <text class="q-del" @tap="removeQ(i)">删除</text></view>
        <textarea v-model="q.stem" class="q-stem" placeholder="题干" />
        <input v-model="q.answer" class="ipt" placeholder="参考答案（选填）" />
      </view>
      <button class="btn-ghost" @tap="addQ">+ 添加题目</button>
      <button class="btn-primary" :disabled="creating || !title.trim() || !questions.length" @tap="onCreate">
        {{ creating ? '创建中…' : '创建作业（草稿）' }}
      </button>
    </view>

    <view class="card">
      <view class="card-title">作业列表</view>
      <view v-if="!list.length" class="empty">还没有作业</view>
      <view v-for="a in list" :key="a.id" class="row">
        <view class="row-main" @tap="goDetail(a.id)">
          <text class="row-title">{{ a.title }}</text>
          <text class="row-sub">{{ statusText(a.status) }} · 已交 {{ a.submission_count }}</text>
        </view>
        <view class="row-ops">
          <text v-if="a.status === 'draft'" class="op" @tap="onPublish(a.id)">发布</text>
          <text v-if="a.status === 'published'" class="op" @tap="onClose(a.id)">关闭</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { createAssignment, listAssignments, publishAssignment, closeAssignment } from '@/api/assignments'
import type { AssignmentListItem, AssignmentQuestion } from '@/types/api'

const classId = ref('')
const title = ref('')
const questions = ref<AssignmentQuestion[]>([{ stem: '', answer: '' }])
const creating = ref(false)
const list = ref<AssignmentListItem[]>([])

onLoad((q) => { classId.value = (q as { classId?: string })?.classId || '' })
onShow(load)

async function load() {
  try { list.value = await listAssignments(classId.value || undefined) } catch { /* 忽略 */ }
}
function addQ() { questions.value.push({ stem: '', answer: '' }) }
function removeQ(i: number) { questions.value.splice(i, 1) }
function statusText(s: string) { return s === 'draft' ? '草稿' : s === 'published' ? '已发布' : '已关闭' }

async function onCreate() {
  creating.value = true
  try {
    await createAssignment({
      class_id: classId.value, title: title.value,
      questions: questions.value.filter((q) => q.stem.trim()),
    })
    title.value = ''
    questions.value = [{ stem: '', answer: '' }]
    await load()
    uni.showToast({ title: '已创建', icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  } finally {
    creating.value = false
  }
}
async function onPublish(id: string) {
  try { await publishAssignment(id); await load(); uni.showToast({ title: '已发布', icon: 'success' }) }
  catch (e) { uni.showToast({ title: (e as Error).message, icon: 'none' }) }
}
async function onClose(id: string) {
  try { await closeAssignment(id); await load() }
  catch (e) { uni.showToast({ title: (e as Error).message, icon: 'none' }) }
}
function goDetail(id: string) { uni.navigateTo({ url: `/pages/teacher/assignment-detail?id=${id}` }) }
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 20rpx; }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.ipt { width: 100%; height: 72rpx; font-size: 28rpx; border: 1rpx solid var(--c-border); border-radius: 8rpx; padding: 0 16rpx; margin-bottom: 12rpx; }
.q-block { border-top: 1rpx solid var(--c-border); padding-top: 12rpx; margin-bottom: 12rpx; }
.q-head { font-size: 26rpx; color: var(--c-text-second); margin-bottom: 8rpx; }
.q-del { color: #e54d42; margin-left: 12rpx; }
.q-stem { width: 100%; height: 140rpx; font-size: 28rpx; border: 1rpx solid var(--c-border); border-radius: 8rpx; padding: 12rpx; margin-bottom: 12rpx; }
.btn-ghost { background: var(--c-bg-page); color: var(--c-text-body); border-radius: var(--r-btn); padding: 16rpx; font-size: 26rpx; margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row-title { font-size: 28rpx; color: var(--c-text-body); display: block; }
.row-sub { font-size: 22rpx; color: var(--c-text-hint); }
.op { font-size: 26rpx; color: var(--c-primary); margin-left: 16rpx; }
</style>

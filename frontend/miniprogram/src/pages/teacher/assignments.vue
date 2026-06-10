<template>
  <view class="page">
    <view class="card">
      <view class="card-title">出卷</view>
      <input v-model="title" class="ipt" placeholder="作业标题" />
      <picker mode="date" :value="dueDate" @change="dueDate = ($event as any).detail.value">
        <view class="ipt due-picker">{{ dueDate ? '截止日期：' + dueDate : '截止日期（选填）' }}</view>
      </picker>

      <!-- M47 班级弱项推荐 -->
      <view v-if="weakKps.length" class="rec-section">
        <view class="rec-title">🎯 班级弱项推荐</view>
        <view class="rec-chips">
          <view
            v-for="kp in weakKps"
            :key="kp.kp_key"
            class="kp-chip"
            :class="chipClass(kp.avg_accuracy)"
            @tap="onKpChip(kp)"
          >
            <text class="chip-name">{{ kp.kp_key }}</text>
            <text class="chip-acc">{{ pct(kp.avg_accuracy) }}</text>
            <text class="chip-weak">{{ kp.weak_count }}/{{ kp.student_count }}人弱</text>
          </view>
        </view>
        <text v-if="chipLoading" class="rec-loading">生成中…</text>
      </view>

      <!-- 原有：按学生 ID 智能选题 -->
      <view class="suggest-row">
        <input v-model="suggestSid" class="ipt suggest-ipt" placeholder="目标学生ID（智能选题）" />
        <text class="suggest-btn" @tap="onSuggest">🎯 智能选题</text>
      </view>

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
          <text class="row-sub">{{ statusText(a.status) }} · 已交 {{ a.submission_count }}{{ a.due_at ? ' · 截止 ' + a.due_at.slice(0, 10) : '' }}</text>
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
import {
  createAssignment, listAssignments, publishAssignment,
  closeAssignment, suggestAssignmentQuestions, suggestByKp,
} from '@/api/assignments'
import { getClassKpStats, type ClassKpWeakItem } from '@/api/teacher'
import type { AssignmentListItem, AssignmentQuestion } from '@/types/api'

const classId = ref('')
const title = ref('')
const dueDate = ref('')
const questions = ref<AssignmentQuestion[]>([{ stem: '', answer: '' }])
const creating = ref(false)
const list = ref<AssignmentListItem[]>([])
const suggestSid = ref('')

// M47 — 班级弱项 KP 推荐
const weakKps = ref<ClassKpWeakItem[]>([])
const chipLoading = ref(false)

// 从 KP 统计页深链跳转时携带的预选知识点
const presetKpKey = ref('')

onLoad((q) => {
  const p = q as { classId?: string; kpKey?: string }
  classId.value = p?.classId || ''
  presetKpKey.value = p?.kpKey ? decodeURIComponent(p.kpKey) : ''
})
onShow(load)

async function load() {
  try { list.value = await listAssignments(classId.value || undefined) } catch { /* 忽略 */ }
  // 加载班级弱项 KP（有 classId 时）
  if (classId.value && !weakKps.value.length) {
    try {
      const stats = await getClassKpStats(classId.value)
      weakKps.value = stats.top_weak_kps.slice(0, 5)
    } catch { /* 班级统计失败不阻断 */ }
  }
  // 深链预选：从 KP 统计页带 kpKey 进来 → 自动按该 KP 选题（仅首次）
  if (presetKpKey.value) {
    const kp = presetKpKey.value
    presetKpKey.value = ''
    await selectByKp(kp)
  }
}

/** 按知识点名生成题目并填入表单。供芯片点击与深链预选复用。 */
async function selectByKp(kpKey: string) {
  if (chipLoading.value) return
  chipLoading.value = true
  try {
    const r = await suggestByKp(kpKey, 5)
    questions.value = r.questions.map((q) => ({
      stem: q.stem, type: q.type, options: q.options, answer: q.answer,
    }))
    if (!title.value) title.value = `${kpKey} 专项练习`
    uni.showToast({ title: `已按「${kpKey}」选题`, icon: 'success' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '选题失败', icon: 'none' })
  } finally {
    chipLoading.value = false
  }
}

/** 点击弱项 KP 芯片 → 按该 KP 生成题目 */
function onKpChip(kp: ClassKpWeakItem) {
  return selectByKp(kp.kp_key)
}

async function onSuggest() {
  if (!suggestSid.value.trim()) { uni.showToast({ title: '请输入学生ID', icon: 'none' }); return }
  try {
    const r = await suggestAssignmentQuestions(suggestSid.value.trim(), 5)
    questions.value = r.questions.map((q) => ({ stem: q.stem, type: q.type, options: q.options, answer: q.answer }))
    if (!title.value) title.value = `${r.knowledge_point} 专项练习`
    uni.showToast({ title: `已按「${r.knowledge_point}」选题`, icon: 'none' })
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'none' })
  }
}

function addQ() { questions.value.push({ stem: '', answer: '' }) }
function removeQ(i: number) { questions.value.splice(i, 1) }
function statusText(s: string) { return s === 'draft' ? '草稿' : s === 'published' ? '已发布' : '已关闭' }
function pct(acc: number) { return `${(acc * 100).toFixed(0)}%` }
function chipClass(acc: number) {
  if (acc >= 0.8) return 'chip-green'
  if (acc >= 0.6) return 'chip-yellow'
  return 'chip-red'
}

async function onCreate() {
  creating.value = true
  try {
    await createAssignment({
      class_id: classId.value, title: title.value,
      questions: questions.value.filter((q) => q.stem.trim()),
      due_at: dueDate.value ? dueDate.value + 'T23:59:59Z' : undefined,
    })
    title.value = ''
    dueDate.value = ''
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
.ipt { width: 100%; height: 72rpx; font-size: 28rpx; border: 1rpx solid var(--c-border); border-radius: 8rpx; padding: 0 16rpx; margin-bottom: 12rpx; box-sizing: border-box; }

/* M47 班级弱项推荐 */
.rec-section { margin-bottom: 16rpx; padding: 16rpx; background: #eef5ff; border-radius: 12rpx; border: 1rpx solid #ffe58f; }
.rec-title { font-size: 24rpx; font-weight: 600; color: #b8860b; margin-bottom: 12rpx; }
.rec-chips { display: flex; flex-wrap: wrap; gap: 12rpx; }
.kp-chip {
  display: flex; flex-direction: column; align-items: center;
  padding: 10rpx 16rpx; border-radius: 12rpx; border: 2rpx solid;
  min-width: 120rpx; cursor: pointer;
}
.chip-red    { border-color: #ff4d4f; background: #fff2f0; }
.chip-yellow { border-color: #ffb020; background: #eef5ff; }
.chip-green  { border-color: #52c41a; background: #f6ffed; }
.chip-name { font-size: 24rpx; font-weight: 600; color: #333; margin-bottom: 4rpx; }
.chip-acc  { font-size: 28rpx; font-weight: 700; }
.chip-red .chip-acc    { color: #ff4d4f; }
.chip-yellow .chip-acc { color: #ffb020; }
.chip-green .chip-acc  { color: #52c41a; }
.chip-weak { font-size: 18rpx; color: #999; margin-top: 2rpx; }
.rec-loading { font-size: 24rpx; color: #999; margin-top: 8rpx; }

.suggest-row { display: flex; gap: 12rpx; align-items: center; margin-bottom: 12rpx; }
.suggest-ipt { flex: 1; margin-bottom: 0; }
.suggest-btn { font-size: 26rpx; color: var(--c-primary); font-weight: 700; white-space: nowrap; }
.q-block { border-top: 1rpx solid var(--c-border); padding-top: 12rpx; margin-bottom: 12rpx; }
.q-head { font-size: 26rpx; color: var(--c-text-second); margin-bottom: 8rpx; }
.q-del { color: #e54d42; margin-left: 12rpx; }
.q-stem { width: 100%; height: 140rpx; font-size: 28rpx; border: 1rpx solid var(--c-border); border-radius: 8rpx; padding: 12rpx; margin-bottom: 12rpx; box-sizing: border-box; }
.btn-ghost { background: var(--c-bg-page); color: var(--c-text-body); border-radius: var(--r-btn); padding: 16rpx; font-size: 26rpx; margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.empty { font-size: 26rpx; color: var(--c-text-hint); padding: 24rpx 0; text-align: center; }
.row { display: flex; justify-content: space-between; align-items: center; padding: 16rpx 0; border-bottom: 1rpx solid var(--c-border); }
.row-title { font-size: 28rpx; color: var(--c-text-body); display: block; }
.row-sub { font-size: 22rpx; color: var(--c-text-hint); }
.op { font-size: 26rpx; color: var(--c-primary); margin-left: 16rpx; }
</style>

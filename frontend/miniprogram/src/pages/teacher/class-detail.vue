<template>
  <view class="page">
    <view class="tabs">
      <text class="tab" :class="{ active: tab === 'students' }" @tap="tab = 'students'">学生</text>
      <text class="tab" :class="{ active: tab === 'report' }" @tap="switchReport">综合报告</text>
    </view>

    <button class="btn-assign" @tap="goAssignments">📋 出卷 / 作业</button>

    <view v-if="tab === 'students'">
      <view v-if="loading" class="tip">加载中…</view>
      <view v-else-if="students.length === 0" class="tip">班级暂无学生</view>
      <view v-for="s in students" :key="s.student_id" class="card s-item">
        <text class="s-id">{{ s.nickname || ('学生 ' + s.student_id.slice(0, 8) + '…') }}</text>
        <text class="s-rm" @tap.stop="onRemove(s.student_id)">移除</text>
      </view>
      <view class="card">
        <text class="hint">添加学生（输入已绑定学生的 UUID）：</text>
        <input v-model="newStudentId" class="input" placeholder="学生 UUID" />
        <button class="btn-primary" :disabled="!newStudentId || adding" @tap="onAdd">
          {{ adding ? '添加中…' : '添加' }}
        </button>
      </view>
    </view>

    <view v-else>
      <view v-if="reportLoading" class="tip">生成报告中…</view>
      <view v-else-if="!report" class="tip">无数据</view>
      <view v-else>
        <view class="card">
          <view class="stat-row">
            <view class="stat"><text class="num">{{ report.student_count }}</text><text class="lbl">学生数</text></view>
            <view class="stat"><text class="num">{{ report.total_questions }}</text><text class="lbl">总错题</text></view>
            <view class="stat"><text class="num">{{ Math.round(report.avg_mastery_rate * 100) }}%</text><text class="lbl">班均掌握率</text></view>
          </view>
        </view>
        <view v-if="report.top_error_types.length" class="card">
          <view class="card-title">班级高频错误</view>
          <view v-for="e in report.top_error_types.slice(0, 5)" :key="e.type" class="row">
            <text>{{ e.type }}</text><text class="count">{{ e.count }}</text>
          </view>
        </view>
        <view v-if="report.students_ranking.length" class="card">
          <view class="card-title">掌握率排名</view>
          <view v-for="(s, i) in report.students_ranking" :key="s.student_id" class="row">
            <text>{{ i + 1 }}. {{ s.nickname || ('学生 ' + s.student_id.slice(0, 8) + '…') }}</text>
            <text class="count">{{ Math.round(s.mastery_rate * 100) }}%</text>
          </view>
        </view>
      </view>
    </view>
  </view>
</template>
<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { listClassStudents, addClassStudents, removeClassStudent, getClassReport } from '@/api/classes'
import type { ClassStudentOut, ClassReport } from '@/types/api'
const classId = ref('')
const tab = ref<'students' | 'report'>('students')
const students = ref<ClassStudentOut[]>([])
const loading = ref(false)
const adding = ref(false)
const newStudentId = ref('')
const report = ref<ClassReport | null>(null)
const reportLoading = ref(false)
async function loadStudents() {
  loading.value = true
  try { const r = await listClassStudents(classId.value); students.value = r.data || [] }
  finally { loading.value = false }
}
async function switchReport() {
  tab.value = 'report'
  reportLoading.value = true
  try { const r = await getClassReport(classId.value); report.value = r.data || null }
  finally { reportLoading.value = false }
}
async function onAdd() {
  adding.value = true
  try { await addClassStudents(classId.value, [newStudentId.value.trim()]); newStudentId.value = ''; await loadStudents(); uni.showToast({ title: '已添加', icon: 'success' }) }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
  finally { adding.value = false }
}
async function onRemove(sid: string) {
  try { await removeClassStudent(classId.value, sid); await loadStudents() }
  catch (e: any) { uni.showToast({ title: e?.message || '失败', icon: 'none' }) }
}
function goAssignments() { uni.navigateTo({ url: `/pages/teacher/assignments?classId=${classId.value}` }) }
onMounted(() => {
  const pages = getCurrentPages()
  classId.value = (pages[pages.length - 1] as any).options?.classId || ''
  if (classId.value) loadStudents()
})
</script>
<style scoped>
.page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.tabs { display: flex; gap: 16rpx; padding: 8rpx 0 16rpx; }
.tab { padding: 12rpx 32rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.tab.active { background: var(--c-primary); color: var(--c-ink); font-weight: 700; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 12rpx; }
.tip { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.s-item { display: flex; justify-content: space-between; align-items: center; }
.s-id { font-size: 26rpx; color: var(--c-text-body); }
.s-rm { font-size: 24rpx; color: var(--c-danger); padding: 8rpx 16rpx; }
.hint { font-size: 22rpx; color: var(--c-text-hint); display: block; margin-bottom: 12rpx; }
.btn-assign { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 16rpx; font-size: 26rpx; font-weight: 700; margin-bottom: 16rpx; }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; width: 100%; box-sizing: border-box; margin-bottom: 12rpx; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 16rpx; font-weight: 700; font-size: 26rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.stat-row { display: flex; justify-content: space-around; }
.stat { text-align: center; }
.num { font-size: 48rpx; font-weight: 800; color: var(--c-ink); display: block; }
.lbl { font-size: 22rpx; color: var(--c-text-hint); }
.row { display: flex; justify-content: space-between; padding: 6rpx 0; border-bottom: 1rpx solid var(--c-border); font-size: 26rpx; color: var(--c-text-body); }
.count { color: var(--c-gold); font-weight: 700; }
</style>

<!-- src/pages/teacher/students.vue -->
<template>
  <view class="teacher-page">

    <!-- 成为教师 / 教师信息 -->
    <view class="card">
      <view class="card-title">教师身份</view>
      <view v-if="isTeacher" class="teacher-badge">
        <text class="badge-text">✅ 教师账号</text>
        <text v-if="profile" class="subject-text">科目：{{ profile.subject || '未设置' }}</text>
      </view>
      <view v-else>
        <input
          v-model="subjectInput"
          class="input"
          placeholder="任教科目（选填，如：英语）"
        />
        <button class="btn-primary" :disabled="becoming" @tap="handleBecomeTeacher">
          {{ becoming ? '处理中…' : '成为教师' }}
        </button>
      </view>
    </view>

    <!-- 邀请学生（教师专用） -->
    <view v-if="isTeacher" class="card">
      <view class="card-title">邀请学生绑定</view>
      <button class="btn-secondary" :disabled="generatingCode" @tap="handleGenerateCode">
        {{ generatingCode ? '生成中…' : '生成邀请码' }}
      </button>
      <view v-if="inviteCode" class="invite-box">
        <text class="invite-code">{{ inviteCode.code }}</text>
        <text class="invite-expire">24小时内有效</text>
        <button size="mini" class="btn-copy" @tap="copyCode">复制</button>
      </view>
    </view>

    <!-- 学生列表（教师专用） -->
    <view v-if="isTeacher" class="card">
      <view class="card-title">我的学生（{{ students.length }}）</view>
      <view v-if="loadingStudents" class="tip">加载中…</view>
      <view v-else-if="students.length === 0" class="tip">
        暂无绑定学生，请生成邀请码邀请学生扫描绑定。
      </view>
      <view
        v-for="s in students"
        :key="s.student_id"
        class="student-item"
        @tap="goToStudent(s.student_id)"
      >
        <text class="student-id">学生 {{ s.student_id.slice(0, 8) }}…</text>
        <text class="student-bind-date">绑定：{{ s.bound_at ? s.bound_at.slice(0, 10) : '-' }}</text>
        <text class="arrow">›</text>
      </view>
    </view>

    <!-- 绑定老师（所有用户） -->
    <view class="card">
      <view class="card-title">绑定老师</view>
      <input
        v-model="bindCodeInput"
        class="input"
        placeholder="输入老师的6位邀请码"
        maxlength="6"
        @input="bindCodeInput = bindCodeInput.toUpperCase()"
      />
      <button class="btn-primary" :disabled="binding" @tap="handleBind">
        {{ binding ? '绑定中…' : '绑定老师' }}
      </button>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import {
  becomeTeacher,
  createInviteCode,
  bindTeacher,
  getMyStudents,
} from '@/api/teacher'
import type { TeacherProfileOut, InviteCodeOut, TeacherStudentOut } from '@/types/api'

const auth = useAuthStore()

const isTeacher = ref(false)
const profile = ref<TeacherProfileOut | null>(null)
const subjectInput = ref('')
const becoming = ref(false)

const inviteCode = ref<InviteCodeOut | null>(null)
const generatingCode = ref(false)

const students = ref<TeacherStudentOut[]>([])
const loadingStudents = ref(false)

const bindCodeInput = ref('')
const binding = ref(false)

onMounted(async () => {
  if (!auth.user) return
  isTeacher.value = auth.user.role === 'teacher'
  if (isTeacher.value) {
    await loadStudents()
  }
})

async function handleBecomeTeacher() {
  becoming.value = true
  try {
    profile.value = await becomeTeacher(subjectInput.value || undefined)
    isTeacher.value = true
    if (auth.user) auth.user.role = 'teacher'
    await loadStudents()
    uni.showToast({ title: '已成为教师', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '操作失败', icon: 'none' })
  } finally {
    becoming.value = false
  }
}

async function handleGenerateCode() {
  generatingCode.value = true
  try {
    inviteCode.value = await createInviteCode()
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  } finally {
    generatingCode.value = false
  }
}

function copyCode() {
  if (!inviteCode.value) return
  uni.setClipboardData({
    data: inviteCode.value.code,
    success: () => uni.showToast({ title: '已复制', icon: 'success' }),
  })
}

async function loadStudents() {
  loadingStudents.value = true
  try {
    students.value = await getMyStudents()
  } finally {
    loadingStudents.value = false
  }
}

async function handleBind() {
  if (bindCodeInput.value.length !== 6) {
    uni.showToast({ title: '请输入6位邀请码', icon: 'none' })
    return
  }
  binding.value = true
  try {
    await bindTeacher(bindCodeInput.value)
    bindCodeInput.value = ''
    uni.showToast({ title: '绑定成功', icon: 'success' })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
  } finally {
    binding.value = false
  }
}

function goToStudent(studentId: string) {
  uni.navigateTo({ url: `/pages/teacher/student-detail?studentId=${studentId}` })
}
</script>

<style scoped>
.teacher-page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.teacher-badge { display: flex; flex-direction: column; gap: 8rpx; }
.badge-text { font-size: 28rpx; color: var(--c-success); }
.subject-text { font-size: 24rpx; color: var(--c-text-hint); }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin-bottom: 16rpx; width: 100%; box-sizing: border-box; }
.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; font-weight: 700; text-align: center; margin-top: 8rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }
.btn-secondary { background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 20rpx; font-size: 28rpx; font-weight: 600; text-align: center; }
.invite-box { margin-top: 16rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; display: flex; align-items: center; gap: 16rpx; }
.invite-code { font-size: 48rpx; font-weight: 800; letter-spacing: 8rpx; color: var(--c-ink); flex: 1; }
.invite-expire { font-size: 22rpx; color: var(--c-text-hint); }
.btn-copy { background: var(--c-primary); color: var(--c-ink); font-size: 24rpx; font-weight: 600; border-radius: var(--r-sm); padding: 8rpx 16rpx; }
.tip { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 24rpx 0; }
.student-item { display: flex; align-items: center; padding: 20rpx 0; border-bottom: 1rpx solid var(--c-border); }
.student-item:last-child { border-bottom: none; }
.student-id { flex: 1; font-size: 28rpx; color: var(--c-text-body); }
.student-bind-date { font-size: 24rpx; color: var(--c-text-hint); margin-right: 8rpx; }
.arrow { font-size: 32rpx; color: var(--c-text-hint); }
</style>

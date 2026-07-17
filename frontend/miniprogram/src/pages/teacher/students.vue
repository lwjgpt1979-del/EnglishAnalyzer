<!-- src/pages/teacher/students.vue -->
<template>
  <view class="teacher-page">

    <view v-if="isTeacher && certStatus !== 'certified'" class="cert-banner" @tap="goCert">
      <view class="ic ic-warning" style="width:30rpx;height:30rpx"/>
      <text>教师未认证（{{ certStatusLabel }}）—— 点击去认证</text>
    </view>
    <view v-if="isTeacher" class="quick-row">
      <view class="quick-btn" @tap="goCert"><view class="ic ic-clipboard" style="width:30rpx;height:30rpx"/><text>认证</text></view>
      <view class="quick-btn" @tap="goClasses"><view class="ic ic-school" style="width:30rpx;height:30rpx"/><text>班级管理</text></view>
    </view>

    <!-- 月度额度（§5.6）-->
    <view v-if="isTeacher && quota" class="card quota-card">
      <view class="card-title">我的额度（本月）</view>
      <view class="quota-row" v-for="q in [
        { label: '绑定学生', d: quota.students },
        { label: '本月出卷', d: quota.paper },
        { label: '本月批改/点评', d: quota.grading },
      ]" :key="q.label">
        <view class="quota-fill" :class="{ low: q.d.remaining_pct < quota.warn_threshold_pct }" :style="{ width: Math.min(100, q.d.limit ? q.d.used / q.d.limit * 100 : 0) + '%' }" />
        <text class="quota-label">{{ q.label }}</text>
        <text class="quota-num">{{ q.d.used }}/{{ q.d.limit }}</text>
      </view>
      <text class="quota-tip">每月 {{ quota.reset_day }} 号重置；剩余低于 {{ quota.warn_threshold_pct }}% 将提醒</text>
    </view>

    <!-- 成为教师 / 教师信息 -->
    <view class="card">
      <view class="card-title">教师身份</view>
      <view v-if="isTeacher" class="teacher-badge">
        <view class="badge-text"><view class="ic ic-check-circle" style="width:30rpx;height:30rpx"/><text>教师账号</text></view>
        <text v-if="profile" class="subject-text">科目：{{ profile.subject || '未设置' }}</text>
      </view>
      <view v-else>
        <view class="become-intro">
          <text class="become-intro-title">开通教师身份后，你可以：</text>
          <view class="become-feat"><view class="ic ic-school" style="width:32rpx;height:32rpx"/><text>创建班级、邀请学生加入</text></view>
          <view class="become-feat"><view class="ic ic-clipboard" style="width:32rpx;height:32rpx"/><text>布置作业、按薄弱知识点一键出卷</text></view>
          <view class="become-feat"><view class="ic ic-chart" style="width:32rpx;height:32rpx"/><text>查看每位学生的知识点掌握台账</text></view>
        </view>
        <input
          v-model="subjectInput"
          class="input"
          placeholder="任教科目（选填，如：英语）"
        />
        <button class="btn-primary" :disabled="becoming" @tap="handleBecomeTeacher">
          {{ becoming ? '处理中…' : '成为教师' }}
        </button>
        <text class="become-divider-hint">
          如果你是学生，想连接自己的老师 → 请使用下方「绑定老师」
        </text>
      </view>
    </view>

    <!-- 邀请学生（教师专用） -->
    <view v-if="isTeacher" class="card">
      <view class="card-title">邀请学生绑定</view>
      <view class="invite-actions">
        <button class="btn-primary half" :disabled="loadingQr" @tap="onGenQr">
          {{ loadingQr ? '生成中…' : '微信扫码' }}
        </button>
        <button class="btn-secondary half" @tap="showSmsDialog = true">短信邀请</button>
      </view>

      <!-- 二维码弹层 -->
      <view v-if="qr" class="modal" @tap.self="qr = null">
        <view class="modal-card">
          <image class="qr-img" :src="'data:image/png;base64,' + qr.qrcode_base64" mode="aspectFit" />
          <text class="qr-tip">让学生用微信扫一扫，自动打开小程序并绑定您。</text>
          <view class="qr-fallback">
            <text>或手动输入邀请码：</text>
            <text class="qr-code">{{ qr.code }}</text>
            <button size="mini" class="btn-copy" @tap="copyQrCode">复制</button>
          </view>
          <button class="btn-secondary" @tap="qr = null">关闭</button>
        </view>
      </view>

      <!-- 短信弹层 -->
      <view v-if="showSmsDialog" class="modal" @tap.self="showSmsDialog = false">
        <view class="modal-card">
          <view class="card-title">短信邀请学生</view>
          <input v-model="smsPhone" class="input" placeholder="对方手机号" maxlength="11" />
          <text class="dev-hint">将给该手机号发送邀请码短信。</text>
          <button class="btn-primary" :disabled="smsSending || smsPhone.length !== 11" @tap="onSendSms">
            {{ smsSending ? '发送中…' : '发送' }}
          </button>
          <button class="btn-secondary" @tap="showSmsDialog = false">取消</button>
        </view>
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
        <view class="s-info">
          <text class="student-id">{{ s.nickname || ('学生 ' + s.student_id.slice(0, 8) + '…') }}</text>
          <text class="student-bind-date">绑定：{{ s.bound_at ? s.bound_at.slice(0, 10) : '-' }}</text>
        </view>
        <view class="s-actions" @tap.stop>
          <text class="arrow">›</text>
          <button size="mini" class="btn-rm" :disabled="removingStudentId === s.student_id" @tap.stop="onRemoveStudent(s.student_id)">
            {{ removingStudentId === s.student_id ? '…' : '移除' }}
          </button>
        </view>
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

    <!-- 我的老师列表（学生视角，V2 M19） -->
    <view v-if="myTeachers.length > 0" class="card">
      <view class="card-title">我的老师（{{ myTeachers.length }}）</view>
      <view v-for="t in myTeachers" :key="t.teacher_id" class="student-item">
        <view class="s-info">
          <text class="student-id">{{ t.nickname || ('老师 ' + t.teacher_id.slice(0, 8) + '…') }}</text>
          <text class="student-bind-date">{{ t.subject ? '科目：' + t.subject + '　' : '' }}绑定：{{ t.bound_at ? t.bound_at.slice(0, 10) : '-' }}</text>
        </view>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { useAuthStore } from '@/stores/auth'
import {
  becomeTeacher,
  createInviteCode,
  bindTeacher,
  getMyStudents,
  teacherInviteQrcode,
  teacherInviteSms,
  removeStudent,
  getMyTeachers,
  getMyQuota,
  type TeacherQuota,
} from '@/api/teacher'
import { request } from '@/utils/request'
import type { TeacherProfileOut, InviteCodeOut, TeacherStudentOut, QRCodeOut, MyTeacherOut } from '@/types/api'

const auth = useAuthStore()

const isTeacher = ref(false)
const profile = ref<TeacherProfileOut | null>(null)
const subjectInput = ref('')
const becoming = ref(false)

const inviteCode = ref<InviteCodeOut | null>(null)
const generatingCode = ref(false)

const students = ref<TeacherStudentOut[]>([])
const loadingStudents = ref(false)
const removingStudentId = ref<string | null>(null)
const myTeachers = ref<MyTeacherOut[]>([])

const bindCodeInput = ref('')
const binding = ref(false)

const certStatus = ref<string>('uncertified')
const certStatusLabel = computed(() => ({ uncertified: '未认证', pending: '审核中', rejected: '已拒绝', certified: '已认证' } as any)[certStatus.value] || certStatus.value)
function goCert() { uni.navigateTo({ url: '/pages/teacher/cert' }) }
function goClasses() { uni.navigateTo({ url: '/pages/teacher/classes' }) }
async function loadCertStatus() {
  if (!isTeacher.value) return
  try { const r: any = await request('/api/v1/teacher/profile', { method: 'POST', data: {} }); certStatus.value = r.data?.cert_status || 'uncertified' } catch {}
}

const quota = ref<TeacherQuota | null>(null)
async function loadQuota() {
  if (!isTeacher.value) return
  try { quota.value = await getMyQuota() } catch { /* 未认证等忽略 */ }
}

onMounted(async () => {
  if (!auth.user) return
  isTeacher.value = auth.user.role === 'teacher'
  if (isTeacher.value) {
    await loadStudents()
  }
  loadCertStatus()
  loadQuota()
  // 加载学生视角的已绑定老师列表（M19）
  try { myTeachers.value = await getMyTeachers() } catch { /* 静默忽略 */ }
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

async function onRemoveStudent(studentId: string) {
  const { confirm } = await new Promise<{ confirm: boolean }>(resolve =>
    uni.showModal({ title: '移除学生', content: '确认将该学生从您的学生列表中移除？', success: resolve })
  )
  if (!confirm) return
  removingStudentId.value = studentId
  try {
    await removeStudent(studentId)
    uni.showToast({ title: '已移除', icon: 'success' })
    await loadStudents()
  } catch (e: any) {
    uni.showToast({ title: e?.message || '移除失败', icon: 'none' })
  } finally {
    removingStudentId.value = null
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

const qr = ref<QRCodeOut | null>(null)
const loadingQr = ref(false)
const showSmsDialog = ref(false)
const smsPhone = ref('')
const smsSending = ref(false)

async function onGenQr() {
  loadingQr.value = true
  try {
    qr.value = await teacherInviteQrcode() as any
  } catch (e: any) {
    uni.showToast({ title: e?.message || '失败', icon: 'none' })
  } finally { loadingQr.value = false }
}

async function onSendSms() {
  smsSending.value = true
  try {
    await teacherInviteSms(smsPhone.value)
    uni.showToast({ title: '短信已发送', icon: 'success' })
    showSmsDialog.value = false
    smsPhone.value = ''
  } catch (e: any) {
    uni.showToast({ title: e?.message || '发送失败', icon: 'none' })
  } finally { smsSending.value = false }
}

function copyQrCode() {
  if (!qr.value) return
  uni.setClipboardData({
    data: qr.value.code,
    success: () => uni.showToast({ title: '已复制', icon: 'success' }),
  })
}

// 扫码进入：scene 形如 t:CODE → 自动调老师绑定
onLoad((options) => {
  const sceneRaw = (options as any)?.scene
  if (!sceneRaw) return
  const scene = decodeURIComponent(sceneRaw)
  if (!scene.startsWith('t:')) return
  const code = scene.slice(2)
  if (!code) return
  uni.showLoading({ title: '正在绑定老师…' })
  bindTeacher(code)
    .then(() => {
      uni.hideLoading()
      uni.showToast({ title: '已绑定老师', icon: 'success' })
      // 刷新学生侧"我的家人/我绑定的老师"列表（如果该页面有的话）
      if (typeof loadStudents === 'function') loadStudents()
    })
    .catch((e: any) => {
      uni.hideLoading()
      uni.showToast({ title: e?.message || '绑定失败', icon: 'none' })
    })
})
</script>

<style scoped>
.teacher-page { padding: 16rpx; background: var(--c-bg-page); min-height: 100vh; }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0, 0, 0, 0.04); }
.card-title { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); margin-bottom: 16rpx; }
.teacher-badge { display: flex; flex-direction: column; gap: 8rpx; }
.badge-text { font-size: 28rpx; color: var(--c-success); display: flex; align-items: center; gap: 8rpx; }
.subject-text { font-size: 24rpx; color: var(--c-text-hint); }
.input { border: 2rpx solid var(--c-border); border-radius: var(--r-md); padding: 16rpx; font-size: 28rpx; margin-bottom: 16rpx; width: 100%; box-sizing: border-box; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; font-weight: 700; text-align: center; margin-top: 8rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }
.btn-secondary { background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 20rpx; font-size: 28rpx; font-weight: 600; text-align: center; }
.invite-box { margin-top: 16rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; display: flex; align-items: center; gap: 16rpx; }
.invite-code { font-size: 48rpx; font-weight: 800; letter-spacing: 8rpx; color: var(--c-ink); flex: 1; }
.invite-expire { font-size: 22rpx; color: var(--c-text-hint); }
.btn-copy { background: var(--c-primary); color: var(--c-on-primary); font-size: 24rpx; font-weight: 600; border-radius: var(--r-sm); padding: 8rpx 16rpx; }
.tip { font-size: 26rpx; color: var(--c-text-hint); text-align: center; padding: 24rpx 0; }
.student-item { display: flex; align-items: center; justify-content: space-between; padding: 20rpx 0; border-bottom: 1rpx solid var(--c-border); }
.student-item:last-child { border-bottom: none; }
.s-info { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.s-actions { display: flex; align-items: center; gap: 12rpx; }
.btn-rm { background: #fdecea; color: #e74c3c; border: none; border-radius: 8rpx; font-size: 22rpx; padding: 0 16rpx; height: 52rpx; line-height: 52rpx; }
.btn-rm[disabled] { opacity: 0.5; }
.student-id { flex: 1; font-size: 28rpx; color: var(--c-text-body); }
.student-bind-date { font-size: 24rpx; color: var(--c-text-hint); margin-right: 8rpx; }
.arrow { font-size: 32rpx; color: var(--c-text-hint); }
.cert-banner { background: var(--c-orange); color: #fff; font-size: 24rpx; font-weight: 700; padding: 16rpx 24rpx; border-radius: var(--r-md); margin-bottom: 12rpx; display: flex; align-items: center; justify-content: center; gap: 8rpx; }
.quick-row { display: flex; gap: 12rpx; margin-bottom: 12rpx; }
.quick-btn { flex: 1; display: flex; align-items: center; justify-content: center; gap: 8rpx; background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid var(--c-gold); border-radius: var(--r-md); padding: 16rpx; font-size: 26rpx; font-weight: 600; }
.invite-actions { display: flex; gap: 12rpx; }
.half { flex: 1; margin-top: 0; }
.modal { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
.modal-card { background: var(--c-bg-card); border-radius: var(--r-xl); padding: var(--sp-5); width: 80%; max-width: 600rpx; box-shadow: 0 8rpx 32rpx rgba(0,0,0,.2); }
.qr-img { width: 100%; height: 480rpx; }
.qr-tip { display: block; text-align: center; font-size: 26rpx; color: var(--c-text-second); margin: 16rpx 0; line-height: 1.5; }
.qr-fallback { display: flex; align-items: center; gap: 12rpx; margin: 16rpx 0; padding: 12rpx; background: var(--c-bg-soft); border-radius: var(--r-md); }
.qr-code { flex: 1; font-size: 36rpx; font-weight: 800; letter-spacing: 4rpx; color: var(--c-ink); }
.dev-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 16rpx; }
.become-intro { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 20rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 10rpx; }
.become-intro-title { font-size: 26rpx; font-weight: 700; color: var(--c-ink); margin-bottom: 4rpx; }
.become-feat { font-size: 25rpx; color: var(--c-text-body); line-height: 1.5; display: flex; align-items: center; gap: 8rpx; }
.become-divider-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 16rpx; line-height: 1.5; }
/* 进度即底色:配额用量铺背景(保留预警色义,用浅色) */
.quota-row { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between; padding: 12rpx 16rpx; border-radius: 12rpx; background: #f5f6f8; margin: 12rpx 0; }
.quota-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: #e4f5df; transition: width .3s; }
.quota-fill.low { background: #fbe6cf; }
.quota-label { position: relative; font-size: 24rpx; color: var(--c-text-body); }
.quota-num { position: relative; font-size: 24rpx; color: var(--c-text-hint); }
.quota-tip { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 8rpx; }
</style>

<!-- src/pages/index/index.vue -->
<template>
  <view class="home-page">
    <view class="topbar">
      <view class="bell-wrap" @tap="goMessages">
        <text class="bell">🔔</text>
        <text v-if="unreadCount > 0" class="badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</text>
      </view>
    </view>
    <view class="hero">
      <text class="hero-title">{{ heroTitle }}</text>
      <text class="hero-sub">{{ heroSub }}</text>
    </view>

    <!-- 身份切换器：仅在拥有 ≥2 个身份时显示 -->
    <view v-if="availableRoles.length > 1" class="role-seg">
      <text
        v-for="r in availableRoles"
        :key="r.key"
        class="role-seg-item"
        :class="{ active: activeRole === r.key }"
        @tap="switchRole(r.key)"
      >{{ r.label }}</text>
    </view>

    <!-- ───────── 学生身份 ───────── -->
    <template v-if="activeRole === 'student'">
      <!-- 今日学习计划（M9）-->
      <view v-if="auth.isLoggedIn() && plan && plan.tasks.length" class="plan-card">
        <view class="plan-head">
          <text class="plan-title">📅 今日学习计划</text>
          <text class="plan-progress">{{ plan.completed_count }}/{{ plan.total_count }} 完成</text>
        </view>
        <view class="plan-bar-track">
          <view
            class="plan-bar-fill"
            :style="{ width: (plan.total_count ? plan.completed_count / plan.total_count * 100 : 0) + '%' }"
          />
        </view>
        <view
          v-for="(t, i) in plan.tasks"
          :key="i"
          class="plan-task"
          @tap="() => goTask(t)"
        >
          <text class="plan-check" :class="{ done: t.done }">{{ t.done ? '✓' : '○' }}</text>
          <view class="plan-task-body">
            <text class="plan-task-title" :class="{ done: t.done }">{{ t.title }}</text>
            <text class="plan-task-sub">{{ t.subtitle }}</text>
          </view>
          <text class="plan-task-arrow">›</text>
        </view>
        <text v-if="!plan.checkin_done" class="plan-checkin-tip">完成学习后别忘了去「词力通」打卡 →</text>
      </view>

      <!-- 开始学习主卡片 -->
      <view class="learn-card" @tap="goLearn">
        <view class="learn-left">
          <text class="learn-icon">📖</text>
          <view class="learn-text">
            <text class="learn-title">开始学习</text>
            <text class="learn-sub">{{ preferredLabel || '选择教材开始' }}</text>
          </view>
        </view>
        <text class="learn-arrow">›</text>
      </view>

      <view class="quick-grid">
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/practice/adaptive' })">
          <text class="quick-icon">🤖</text>
          <text class="quick-label">智能出题</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/upload/index' })">
          <text class="quick-icon">📷</text>
          <text class="quick-label">单题上传</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })">
          <text class="quick-icon">📄</text>
          <text class="quick-label">上传整卷</text>
        </view>
        <view class="quick-card" @tap="() => uni.switchTab({ url: '/pages/wrong-questions/list' })">
          <text class="quick-icon">📚</text>
          <text class="quick-label">我的错题</text>
        </view>
        <view class="quick-card" @tap="() => uni.switchTab({ url: '/pages/diagnosis/index' })">
          <text class="quick-icon">📊</text>
          <text class="quick-label">学情报告</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/vocabulary/index' })">
          <text class="quick-icon">🔤</text>
          <text class="quick-label">词力通</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/essay/index' })">
          <text class="quick-icon">✍️</text>
          <text class="quick-label">作文精修</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/assignments/index' })">
          <text class="quick-icon">📋</text>
          <text class="quick-label">老师任务</text>
        </view>
      </view>
    </template>

    <!-- ───────── 教师身份 ───────── -->
    <template v-else-if="activeRole === 'teacher'">
      <view
        v-if="certStatus && certStatus !== 'certified'"
        class="cert-banner"
        @tap="() => uni.navigateTo({ url: '/pages/teacher/cert' })"
      >
        <text>⚠️ 教师资质未认证，点击去认证以解锁全部功能</text>
      </view>

      <view class="quick-grid">
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/classes' })">
          <text class="quick-icon">🏫</text>
          <text class="quick-label">班级管理</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/students' })">
          <text class="quick-icon">👥</text>
          <text class="quick-label">我的学生</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/classes' })">
          <text class="quick-icon">📋</text>
          <text class="quick-label">出卷 / 作业</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/cert' })">
          <text class="quick-icon">📜</text>
          <text class="quick-label">资质认证</text>
        </view>
      </view>
      <text class="role-hint">出卷、班级 KP 统计与一键布置作业均在「班级管理」内进入对应班级后操作。</text>
    </template>

    <!-- ───────── 家长身份 ───────── -->
    <template v-else-if="activeRole === 'relative'">
      <view class="child-section">
        <view v-if="children.length === 0" class="child-empty">
          <text class="child-empty-icon">👨‍👩‍👧</text>
          <text class="child-empty-text">还没有绑定孩子</text>
        </view>
        <view
          v-for="c in children"
          :key="c.student_id"
          class="child-card"
          @tap="() => goChild(c.student_id)"
        >
          <view class="child-avatar">{{ (c.nickname || '孩').slice(0, 1) }}</view>
          <view class="child-info">
            <text class="child-name">{{ c.nickname || ('孩子 ' + c.student_id.slice(0, 6)) }}</text>
            <text class="child-sub">查看学情 · 掌握台账 · 周报</text>
          </view>
          <text class="child-arrow">›</text>
        </view>
      </view>
      <button class="btn-role-action" @tap="() => uni.navigateTo({ url: '/pages/relative/center' })">
        ＋ 绑定 / 管理孩子
      </button>
    </template>

    <view v-if="!auth.isLoggedIn()" class="login-banner">
      <text class="login-tip">登录后解锁 AI 分析功能</text>
      <button class="btn-login" @tap="auth.login()">微信一键登录</button>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '@/stores/auth'
import { onShow } from '@dcloudio/uni-app'
import { getUnreadCount } from '@/api/notifications'
import { getMyStudentsAsRelative } from '@/api/relative'
import { getTodayPlan } from '@/api/learningPlan'
import { request } from '@/utils/request'
import type { BoundStudent, TodayPlanOut, PlanTask } from '@/types/api'

const auth = useAuthStore()

const unreadCount = ref(0)
async function loadUnread() {
  if (!auth.isLoggedIn()) { unreadCount.value = 0; return }
  try { const r = await getUnreadCount(); unreadCount.value = r.data?.count || 0 } catch { /* ignore */ }
}
function goMessages() { uni.navigateTo({ url: '/pages/messages/index' }) }

// ── 身份切换 ────────────────────────────────────────────────────────────────
type RoleKey = 'student' | 'teacher' | 'relative'
const ROLE_STORAGE_KEY = 'home_active_role'

const children = ref<BoundStudent[]>([])
const certStatus = ref<string>('')
const plan = ref<TodayPlanOut | null>(null)

async function loadPlan() {
  if (!auth.isLoggedIn()) { plan.value = null; return }
  try { plan.value = await getTodayPlan() } catch { plan.value = null }
}

function goTask(t: PlanTask) {
  if (t.action === 'review') {
    uni.navigateTo({ url: '/pages/wrong-questions/review' })
  } else if (t.action === 'learn') {
    goLearn()
  } else { // practice
    if (t.kp_id) {
      uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${t.kp_id}` })
    } else {
      uni.navigateTo({ url: '/pages/practice/adaptive' })
    }
  }
}

const isTeacher = computed(() => (auth.user as any)?.role === 'teacher')
const isRelative = computed(() => children.value.length > 0)

// 可用身份：学生人人都有；教师按 role；家长按是否绑定孩子
const availableRoles = computed(() => {
  const list: { key: RoleKey; label: string }[] = [{ key: 'student', label: '我是学生' }]
  if (isTeacher.value) list.push({ key: 'teacher', label: '我是老师' })
  if (isRelative.value) list.push({ key: 'relative', label: '我是家长' })
  return list
})

const activeRole = ref<RoleKey>('student')

function switchRole(key: RoleKey) {
  activeRole.value = key
  uni.setStorageSync(ROLE_STORAGE_KEY, key)
}

/** 选定初始身份：上次选择仍可用则沿用，否则回退学生 */
function resolveInitialRole() {
  const keys = availableRoles.value.map((r) => r.key)
  const saved = uni.getStorageSync(ROLE_STORAGE_KEY) as RoleKey | ''
  activeRole.value = saved && keys.includes(saved) ? saved : 'student'
}

async function loadRoleData() {
  if (!auth.isLoggedIn()) { children.value = []; certStatus.value = ''; return }
  // 家长身份：拉绑定的孩子
  try { children.value = await getMyStudentsAsRelative() } catch { children.value = [] }
  // 教师身份：拉认证状态（仅当是老师）
  if (isTeacher.value) {
    try {
      const r: any = await request('/api/v1/teacher/profile', { method: 'POST', data: {} })
      certStatus.value = r.data?.cert_status || 'uncertified'
    } catch { certStatus.value = '' }
  }
  resolveInitialRole()
  loadPlan()
}

const heroTitle = computed(() => (
  { student: 'engGramer', teacher: '教师工作台', relative: '家长中心' }[activeRole.value]
))
const heroSub = computed(() => (
  { student: '英语 AI 知识学习', teacher: '班级 · 学生 · 作业', relative: '关注孩子的学习' }[activeRole.value]
))

const preferredLabel = computed(() => {
  const u = auth.user as any
  if (!u?.preferred_textbook_version) return ''
  return `${u.preferred_textbook_version} ${u.preferred_grade} ${u.preferred_semester}学期`
})

function goLearn() {
  const t = (auth.user as any)?.preferred_textbook_version || '译林版'
  const g = (auth.user as any)?.preferred_grade || '小学5年级'
  const s = (auth.user as any)?.preferred_semester || '上'
  const url = `/pages/curriculum/units?textbook=${encodeURIComponent(t)}&grade=${encodeURIComponent(g)}&semester=${encodeURIComponent(s)}`
  uni.navigateTo({ url })
}

function goChild(studentId: string) {
  uni.navigateTo({ url: `/pages/relative/student-view?studentId=${studentId}` })
}

onShow(() => {
  loadUnread()
  loadRoleData()
})

onMounted(() => {
  if (auth.isLoggedIn() && auth.user && (auth.user as any).profile_completed === false) {
    uni.redirectTo({ url: '/pages/auth/complete-profile' })
    return
  }
  // 新手引导：已登录、未选教材偏好、且本设备未看过引导
  if (
    auth.isLoggedIn() &&
    auth.user &&
    !(auth.user as any).preferred_textbook_version &&
    !uni.getStorageSync('onboarding_done')
  ) {
    uni.navigateTo({ url: '/pages/onboarding/index' })
    return
  }
  loadUnread()
  loadRoleData()
})
</script>

<style scoped>
.home-page { padding: 40rpx 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.hero { text-align: center; padding: 60rpx 0 32rpx; }
.hero-title { font-size: var(--fs-display); font-weight: 800; color: var(--c-ink); display: block; }
.hero-sub { font-size: var(--fs-h2); color: var(--c-text-hint); display: block; margin-top: 12rpx; }

/* 身份切换器 */
.role-seg {
  display: flex; background: var(--c-bg-card); border-radius: var(--r-pill);
  padding: 6rpx; margin-bottom: 28rpx; box-shadow: var(--shadow-sm);
}
.role-seg-item {
  flex: 1; text-align: center; padding: 16rpx 0; font-size: var(--fs-body);
  color: var(--c-text-second); border-radius: var(--r-pill); transition: all .2s;
}
.role-seg-item.active { background: var(--g-primary); color: var(--c-on-primary); font-weight: 700; box-shadow: var(--shadow-primary); }

/* 今日学习计划（M9）*/
.plan-card {
  background: var(--c-bg-card); border-radius: var(--r-lg);
  padding: 28rpx 28rpx 20rpx; margin-bottom: 24rpx;
  box-shadow: var(--shadow-md);
}
.plan-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16rpx; }
.plan-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-ink); }
.plan-progress { font-size: 24rpx; color: var(--c-primary); font-weight: 700; }
.plan-bar-track { height: 12rpx; background: var(--c-bg-soft); border-radius: 999rpx; overflow: hidden; margin-bottom: 16rpx; }
.plan-bar-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; transition: width .3s; }
.plan-task { display: flex; align-items: center; gap: 16rpx; padding: 18rpx 0; border-bottom: 1rpx solid var(--c-border); }
.plan-task:last-of-type { border-bottom: none; }
.plan-check { width: 40rpx; height: 40rpx; line-height: 40rpx; text-align: center; border-radius: 50%; background: var(--c-bg-soft); color: var(--c-text-hint); font-size: 26rpx; flex-shrink: 0; }
.plan-check.done { background: var(--c-success); color: #fff; }
.plan-task-body { flex: 1; display: flex; flex-direction: column; gap: 4rpx; }
.plan-task-title { font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.plan-task-title.done { color: var(--c-text-hint); text-decoration: line-through; }
.plan-task-sub { font-size: 22rpx; color: var(--c-text-hint); }
.plan-task-arrow { font-size: 40rpx; color: var(--c-text-hint); font-weight: 700; }
.plan-checkin-tip { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 12rpx; }

.learn-card {
  background: var(--g-hero);
  border-radius: var(--r-lg);
  padding: 40rpx 32rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24rpx;
  box-shadow: var(--shadow-primary);
}
.learn-left { display: flex; align-items: center; gap: 24rpx; }
.learn-icon { font-size: 68rpx; }
.learn-text { display: flex; flex-direction: column; gap: 8rpx; }
.learn-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-on-primary); }
.learn-sub { font-size: var(--fs-body); color: var(--c-on-primary); opacity: 0.85; }
.learn-arrow { font-size: 48rpx; color: var(--c-on-primary); opacity: 0.8; font-weight: 700; }
.quick-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20rpx; margin-bottom: 32rpx; }
.quick-card {
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: 40rpx 0;
  text-align: center;
  box-shadow: var(--shadow-sm);
  transition: transform .15s, box-shadow .15s;
}
.quick-card:active { transform: translateY(2rpx) scale(0.98); box-shadow: var(--shadow-md); }
.quick-icon { font-size: 58rpx; display: block; margin-bottom: 16rpx; }
.quick-label { font-size: var(--fs-body); color: var(--c-text-body); font-weight: 500; }

/* 教师身份 */
.cert-banner {
  background: #fff7e6; border: 1rpx solid #ffe58f; color: #ad6800;
  border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 24rpx; font-size: var(--fs-body);
}
.role-hint { display: block; font-size: 24rpx; color: var(--c-text-hint); line-height: 1.6; padding: 0 8rpx; }

/* 家长身份 */
.child-section { margin-bottom: 24rpx; }
.child-empty { text-align: center; padding: 60rpx 0; }
.child-empty-icon { font-size: 80rpx; display: block; margin-bottom: 16rpx; }
.child-empty-text { font-size: var(--fs-body); color: var(--c-text-hint); }
.child-card {
  background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx 32rpx;
  display: flex; align-items: center; gap: 24rpx; margin-bottom: 16rpx;
  box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04);
}
.child-avatar {
  width: 80rpx; height: 80rpx; border-radius: 50%; background: var(--g-primary);
  color: var(--c-on-primary); font-size: 36rpx; font-weight: 800;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.child-info { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.child-name { font-size: var(--fs-h2); font-weight: 700; color: var(--c-ink); }
.child-sub { font-size: 24rpx; color: var(--c-text-hint); }
.child-arrow { font-size: 48rpx; color: var(--c-text-hint); font-weight: 700; }
.btn-role-action {
  background: var(--c-bg-card); color: var(--c-text-body); border: 2rpx solid var(--c-border);
  border-radius: var(--r-btn); font-size: var(--fs-body); padding: 20rpx; margin-bottom: 32rpx;
}

.login-banner {
  background: var(--c-bg-card);
  border-radius: var(--r-lg);
  padding: 36rpx 32rpx;
  text-align: center;
  box-shadow: var(--shadow-sm);
}
.login-tip { font-size: var(--fs-body); color: var(--c-text-second); display: block; margin-bottom: 24rpx; }
.btn-login { background: var(--g-primary); color: var(--c-on-primary); border-radius: var(--r-btn); font-size: var(--fs-h2); font-weight: 700; box-shadow: var(--shadow-primary); }
.topbar { display: flex; justify-content: flex-end; padding: 8rpx 0 16rpx; }
.bell-wrap { position: relative; padding: 8rpx; }
.bell { font-size: 40rpx; }
.badge { position: absolute; top: 0; right: 0; background: var(--c-danger); color: #fff; font-size: 20rpx; min-width: 28rpx; height: 28rpx; line-height: 28rpx; padding: 0 6rpx; border-radius: 999rpx; text-align: center; font-weight: 700; }
</style>

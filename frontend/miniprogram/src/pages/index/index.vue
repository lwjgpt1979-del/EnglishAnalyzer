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
          <view class="plan-title-wrap">
            <view class="plan-title-icon" />
            <text class="plan-title">今日学习计划</text>
          </view>
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
          :class="[`lv-${t.level || 'none'}`, { done: t.done }]"
          @tap="() => goTask(t)"
        >
          <view class="task-badge" :class="[`badge-${t.type}`, { done: t.done }]" />
          <view class="plan-task-body">
            <text class="plan-task-title" :class="{ done: t.done }">{{ taskTitle(t) }}</text>
            <view class="plan-task-meta">
              <text
                v-if="t.accuracy != null"
                class="acc-pill"
                :class="`pill-${t.level}`"
              >{{ (t.accuracy * 100).toFixed(0) }}%</text>
              <text class="plan-task-sub">{{ taskSub(t) }}</text>
            </view>
          </view>
          <text class="plan-task-arrow">›</text>
        </view>
        <text v-if="!plan.checkin_done" class="plan-checkin-tip">完成学习后别忘了去「词力通」打卡 →</text>
      </view>

      <!-- 开始学习主卡片 -->
      <view class="learn-card" @tap="goLearn">
        <view class="learn-left">
          <view class="learn-icon" />
          <view class="learn-text">
            <text class="learn-title">开始学习</text>
            <text class="learn-sub">{{ preferredLabel || '选择教材开始' }}</text>
          </view>
        </view>
        <text class="learn-arrow">›</text>
      </view>

      <view class="quick-grid">
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/practice/adaptive' })">
          <view class="qi qi-ai" />
          <text class="quick-label">智能出题</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/upload/index' })">
          <view class="qi qi-camera" />
          <text class="quick-label">单题上传</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })">
          <view class="qi qi-file" />
          <text class="quick-label">上传整卷</text>
        </view>
        <view class="quick-card" @tap="() => uni.switchTab({ url: '/pages/wrong-questions/list' })">
          <view class="qi qi-book" />
          <text class="quick-label">我的错题</text>
        </view>
        <view class="quick-card" @tap="() => uni.switchTab({ url: '/pages/diagnosis/index' })">
          <view class="qi qi-chart" />
          <text class="quick-label">学情报告</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/vocabulary/index' })">
          <view class="qi qi-vocab" />
          <text class="quick-label">词力通</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/essay/index' })">
          <view class="qi qi-pen" />
          <text class="quick-label">作文精修</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/assignments/index' })">
          <view class="qi qi-clipboard" />
          <text class="quick-label">老师任务</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/listening/index' })">
          <view class="qi qi-headphone" />
          <text class="quick-label">听力练习</text>
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

// 任务卡视觉辅助
function taskTitle(t: PlanTask) {
  return t.title.replace(/^攻克薄弱点：/, '')
}
function taskSub(t: PlanTask) {
  // 去掉与正确率胶囊重复的「正确率 X% ·」前缀
  return t.subtitle.replace(/^正确率\s*\d+%\s*[·•・]\s*/, '')
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
.plan-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16rpx; }
.plan-title-wrap { display: flex; align-items: center; gap: 12rpx; }
.plan-title-icon {
  width: 40rpx; height: 40rpx; flex-shrink: 0;
  background-repeat: no-repeat; background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='4' width='18' height='18' rx='2'/%3E%3Cline x1='16' y1='2' x2='16' y2='6'/%3E%3Cline x1='8' y1='2' x2='8' y2='6'/%3E%3Cline x1='3' y1='10' x2='21' y2='10'/%3E%3C/svg%3E");
}
.plan-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-ink); }
.plan-progress { font-size: 24rpx; color: var(--c-primary); font-weight: 700; }
.plan-bar-track { height: 12rpx; background: var(--c-bg-soft); border-radius: 999rpx; overflow: hidden; margin-bottom: 16rpx; }
.plan-bar-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; transition: width .3s; }
.plan-task {
  position: relative;
  display: flex; align-items: center; gap: 20rpx;
  padding: 22rpx 24rpx; margin-top: 14rpx;
  background: #fff;
  border: 1rpx solid var(--c-border);
  border-radius: var(--r-md);
  overflow: hidden;
  transition: transform .12s, box-shadow .12s;
}
.plan-task:active { transform: scale(0.985); box-shadow: 0 6rpx 20rpx rgba(61,139,245,.12); }
/* 左侧优先级色条 */
.plan-task::before {
  content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 8rpx;
  background: var(--c-primary);
}
.plan-task.lv-none::before   { background: #7bbde8; }
.plan-task.lv-weak::before   { background: #bdd8e9; }
.plan-task.lv-medium::before { background: #ffb020; }
.plan-task.lv-good::before   { background: #18a058; }
.plan-task.done { background: var(--c-bg-soft); border-color: transparent; opacity: .7; }
.plan-task.done::before { background: var(--c-success); }

/* 类型图标徽章（线性 SVG，统一描边风格）*/
.task-badge {
  width: 64rpx; height: 64rpx; border-radius: 18rpx; flex-shrink: 0;
  background-repeat: no-repeat; background-position: center; background-size: 36rpx 36rpx;
}
.badge-weak_kp {
  background-color: #e7f0f8;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237ba6c9' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='9'/%3E%3Ccircle cx='12' cy='12' r='5'/%3E%3Ccircle cx='12' cy='12' r='1.6' fill='%237ba6c9'/%3E%3C/svg%3E");
}
.badge-review {
  background-color: #e9f4fb;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%237bbde8' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 12a9 9 0 0 1 15-6.7L21 8'/%3E%3Cpath d='M21 3v5h-5'/%3E%3Cpath d='M21 12a9 9 0 0 1-15 6.7L3 16'/%3E%3Cpath d='M3 21v-5h5'/%3E%3C/svg%3E");
}
.badge-learn {
  background-color: #e9f7ef;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%2318a058' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z'/%3E%3Cpath d='M4 19a2 2 0 0 1 2-2h13'/%3E%3C/svg%3E");
}
.task-badge.done {
  background-color: var(--c-success);
  background-size: 34rpx 34rpx;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M20 6 9 17l-5-5'/%3E%3C/svg%3E");
}

/* 文本区 */
.plan-task-body { flex: 1; display: flex; flex-direction: column; gap: 8rpx; min-width: 0; }
.plan-task-title { font-size: 29rpx; font-weight: 700; color: var(--c-ink); line-height: 1.35; }
.plan-task-title.done { color: var(--c-text-hint); text-decoration: line-through; }
.plan-task-meta { display: flex; align-items: center; gap: 12rpx; flex-wrap: wrap; }
.acc-pill { font-size: 20rpx; font-weight: 700; padding: 3rpx 14rpx; border-radius: var(--r-pill); }
.acc-pill.pill-weak   { background: #dfeaf3; color: #527d9e; }
.acc-pill.pill-medium { background: #fff0d6; color: #b9780f; }
.acc-pill.pill-good   { background: #d8f5e6; color: #128048; }
.plan-task-sub { font-size: 22rpx; color: var(--c-text-hint); }
.plan-task-arrow { font-size: 40rpx; color: var(--c-text-disabled, #c4ccd6); font-weight: 700; flex-shrink: 0; }
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
.learn-icon {
  width: 72rpx; height: 72rpx; flex-shrink: 0;
  background-repeat: no-repeat; background-position: center; background-size: contain;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ffffff' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z'/%3E%3Cpath d='M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z'/%3E%3C/svg%3E");
}
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

/* 功能图标徽章（统一线性图标）*/
.qi {
  width: 92rpx; height: 92rpx; margin: 0 auto 16rpx;
  border-radius: 24rpx;
  background-color: var(--c-primary-faint);
  background-repeat: no-repeat; background-position: center; background-size: 48rpx 48rpx;
}
.qi-ai { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 3l1.7 4.3L18 9l-4.3 1.7L12 15l-1.7-4.3L6 9l4.3-1.7z'/%3E%3Cpath d='M18.5 14l.9 2 2 .9-2 .9-.9 2-.9-2-2-.9 2-.9z'/%3E%3C/svg%3E"); }
.qi-camera { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z'/%3E%3Ccircle cx='12' cy='13' r='4'/%3E%3C/svg%3E"); }
.qi-file { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpath d='M14 2v6h6'/%3E%3Cpath d='M9 13h6'/%3E%3Cpath d='M9 17h6'/%3E%3C/svg%3E"); }
.qi-book { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z'/%3E%3C/svg%3E"); }
.qi-chart { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='6' y1='20' x2='6' y2='15'/%3E%3Cline x1='12' y1='20' x2='12' y2='9'/%3E%3Cline x1='18' y1='20' x2='18' y2='4'/%3E%3C/svg%3E"); }
.qi-vocab { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z'/%3E%3Cpath d='M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z'/%3E%3C/svg%3E"); }
.qi-pen { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 20h9'/%3E%3Cpath d='M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z'/%3E%3C/svg%3E"); }
.qi-clipboard { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2'/%3E%3Crect x='8' y='2' width='8' height='4' rx='1'/%3E%3Cpath d='M9 13l2 2 4-4'/%3E%3C/svg%3E"); }
.qi-headphone { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M3 18v-6a9 9 0 0 1 18 0v6'/%3E%3Cpath d='M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3z'/%3E%3Cpath d='M3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z'/%3E%3C/svg%3E"); }

/* 教师身份 */
.cert-banner {
  background: #fff7e6; border: 1rpx solid #ffe58f; color: #b8860b;
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

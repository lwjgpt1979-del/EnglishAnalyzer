<!-- src/pages/index/index.vue -->
<template>
  <view class="home-page">
    <view class="topbar">
      <view class="bell-wrap" @tap="goMessages">
        <view class="ic ic-bell bell" />
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
      <view v-if="auth.isLoggedIn() && plan && planHasContent" class="plan-card">
        <!-- 折叠标题栏(进度即底色) -->
        <view class="plan-head" @tap="togglePlan">
          <view class="plan-head-fill" :style="{ width: planPct + '%' }" />
          <view class="plan-title-wrap">
            <view class="ic ic-calendar plan-title-icon" />
            <text class="plan-title">今日学习计划</text>
          </view>
          <view class="plan-head-right">
            <text class="plan-progress">{{ plan.completed_count }}/{{ plan.total_count }} 完成</text>
            <view class="ic plan-chev" :class="planFolded ? 'ic-chevron-down' : 'ic-chevron-up'" />
          </view>
        </view>

        <!-- 折叠态:一行摘要 -->
        <text v-if="planFolded" class="plan-summary">{{ planSummary }}</text>

        <!-- 展开态:两来源便当 + 复习条 -->
        <view v-else class="plan-body">
          <block v-for="src in plan.sources" :key="src.source">
            <view v-if="src.available" class="src-head">
              <view class="ic src-head-ic" :class="src.source === 'homework' ? 'ic-file' : 'ic-book'" />
              <text class="src-head-title">{{ src.title }}</text>
              <text class="src-head-sub">{{ src.subtitle }}</text>
            </view>
            <view v-if="src.available" class="tile-grid">
              <view
                v-for="t in src.tiles"
                :key="t.module"
                class="tile"
                :class="src.source === 'homework' ? 'tile-hw' : 'tile-course'"
                @tap="() => goTile(t)"
              >
                <view class="tile-fill" :style="{ width: tilePct(t) + '%' }" />
                <view class="tile-inner">
                  <view class="tile-row1">
                    <view class="tile-ic" :class="'mic-' + t.module" />
                    <text class="tile-num">{{ t.count }}</text>
                  </view>
                  <text class="tile-cap">{{ t.title }} · {{ tileCap(t, src.source) }}</text>
                </view>
              </view>
            </view>
          </block>

          <!-- 今日复习条(虚线描边,蓝 C) -->
          <view class="review-bar" @tap="goReview">
            <view class="ic ic-refresh review-ic" />
            <text class="review-title">今日复习</text>
            <text class="review-sub">{{ plan.review.subtitle }}</text>
            <text class="review-arrow">›</text>
          </view>

          <text v-if="!plan.checkin_done" class="plan-checkin-tip">完成学习后别忘了去「词力通」打卡 →</text>
        </view>
      </view>

      <!-- 课程精讲主卡片(接替原「开始学习」) -->
      <view class="learn-card" @tap="() => uni.navigateTo({ url: '/pages/intensive/course' })">
        <view class="learn-left">
          <view class="learn-icon" />
          <view class="learn-text">
            <text class="learn-title">课程精讲</text>
            <text class="learn-sub">{{ courseSub }}</text>
          </view>
        </view>
        <text class="learn-arrow">›</text>
      </view>

      <view class="quick-grid">
        <!-- 作业流:上传作业 + 作业精讲 同一行(quick-card 同款) -->
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })">
          <view class="qi qi-file" />
          <text class="quick-label">上传作业</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/intensive/homework' })">
          <view class="qi qi-book" />
          <text class="quick-label">作业精讲</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/practice/adaptive' })">
          <view class="qi qi-ai" />
          <text class="quick-label">智能出题</text>
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
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/reading-expression/grade' })">
          <view class="qi qi-read-check" />
          <text class="quick-label">阅读表达</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/writing/practice' })">
          <view class="qi qi-write" />
          <text class="quick-label">书面表达</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/assignments/index' })">
          <view class="qi qi-clipboard" />
          <text class="quick-label">老师任务</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/listening/index' })">
          <view class="qi qi-headphone" />
          <text class="quick-label">听力练习</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/long-sentence/index' })">
          <view class="qi qi-pen" />
          <text class="quick-label">长难句</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/grammar/index' })">
          <view class="qi qi-book" />
          <text class="quick-label">语法精进</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/self-exam/index' })">
          <view class="qi qi-exam" />
          <text class="quick-label">自助出卷</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/speaking/index' })">
          <view class="qi qi-speak" />
          <text class="quick-label">口语对话</text>
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
        <view class="ic ic-warning cert-banner-ic" />
        <text>教师资质未认证，点击去认证以解锁全部功能</text>
      </view>

      <view class="quick-grid">
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/classes' })">
          <view class="ic ic-school quick-icon" />
          <text class="quick-label">班级管理</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/students' })">
          <view class="ic ic-user quick-icon" />
          <text class="quick-label">我的学生</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/classes' })">
          <view class="ic ic-clipboard quick-icon" />
          <text class="quick-label">出卷 / 作业</text>
        </view>
        <view class="quick-card" @tap="() => uni.navigateTo({ url: '/pages/teacher/cert' })">
          <view class="ic ic-file quick-icon" />
          <text class="quick-label">资质认证</text>
        </view>
      </view>
      <text class="role-hint">出卷、班级 KP 统计与一键布置作业均在「班级管理」内进入对应班级后操作。</text>
    </template>

    <!-- ───────── 家长身份 ───────── -->
    <template v-else-if="activeRole === 'relative'">
      <view class="child-section">
        <view v-if="children.length === 0" class="child-empty">
          <view class="ic ic-user child-empty-icon" />
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
import { useBrandingStore } from '@/stores/branding'
import { onShow } from '@dcloudio/uni-app'
import { getUnreadCount } from '@/api/notifications'
import { getMyStudentsAsRelative } from '@/api/relative'
import { getTodayPlan } from '@/api/learningPlan'
import { request } from '@/utils/request'
import type { BoundStudent, TodayPlanOut, PlanTile } from '@/types/api'

const auth = useAuthStore()
const branding = useBrandingStore()

const unreadCount = ref(0)
async function loadUnread() {
  if (!auth.isLoggedIn()) { unreadCount.value = 0; return }
  try { const r = await getUnreadCount(); unreadCount.value = r?.count || 0 } catch { /* ignore */ }
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

// ── 折叠态(记住用户偏好)──
const PLAN_FOLD_KEY = 'planFolded'
const planFolded = ref(false)
try { planFolded.value = !!uni.getStorageSync(PLAN_FOLD_KEY) } catch { /* ignore */ }
function togglePlan() {
  planFolded.value = !planFolded.value
  try { uni.setStorageSync(PLAN_FOLD_KEY, planFolded.value) } catch { /* ignore */ }
}

// ── 计划视觉派生 ──
const planHasContent = computed(() => {
  if (!plan.value) return false
  if (plan.value.review.count > 0) return true
  return plan.value.sources.some(s => s.available && s.tiles.some(t => t.total > 0))
})
const planPct = computed(() =>
  plan.value && plan.value.total_count
    ? Math.round(plan.value.completed_count / plan.value.total_count * 100) : 0)
const planSummary = computed(() => {
  if (!plan.value) return ''
  const sum = (src: string) =>
    plan.value!.sources.find(s => s.source === src)?.tiles.reduce((a, t) => a + t.count, 0) || 0
  return `作业 ${sum('homework')} · 课程 ${sum('course')} · 复习 ${plan.value.review.count}`
})
function tilePct(t: PlanTile) { return t.total > 0 ? Math.round(t.studied / t.total * 100) : 0 }
function tileCap(t: PlanTile, source: string) {
  if (t.total <= 0) return source === 'course' ? '未开始' : '暂无'
  // 课程:当前单元制,数字=今日封顶量,另标单元剩余;作业:全部积压,标已学/总
  return source === 'course' ? `今日 ${t.count} · 单元剩 ${t.total - t.studied}` : `已 ${t.studied}/${t.total}`
}
function goTile(t: PlanTile) { if (t.route) uni.navigateTo({ url: t.route }) }
function goReview() { uni.navigateTo({ url: plan.value?.review.route || '/pages/wrong-questions/review' }) }

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
  { student: branding.appName, teacher: '教师工作台', relative: '家长中心' }[activeRole.value]
))
const heroSub = computed(() => (
  { student: '英语 AI 知识学习', teacher: '班级 · 学生 · 作业', relative: '关注孩子的学习' }[activeRole.value]
))

// 课程精讲主卡副标题:带当前学期(8上册),未设教材则引导选教材
const courseSub = computed(() => {
  const u = auth.user as any
  if (!u?.preferred_textbook_version) return '选择教材开始'
  const sem = (u.preferred_grade && u.preferred_semester) ? ` · ${u.preferred_grade}${u.preferred_semester}册` : ''
  return `按教材课程学${sem}`
})

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
  padding: 20rpx 20rpx 16rpx; margin-bottom: 24rpx;
  box-shadow: var(--shadow-md);
}
/* 进度即底色:完成度铺标题栏背景 */
.plan-head { position: relative; overflow: hidden; display: flex; justify-content: space-between; align-items: center; padding: 16rpx 18rpx; border-radius: 14rpx; }
.plan-head-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; background: #e8f2ff; transition: width .3s; }
.plan-title-wrap { position: relative; display: flex; align-items: center; gap: 10rpx; }
.plan-title-icon { width: 36rpx; height: 36rpx; flex-shrink: 0; }
.plan-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-ink); }
.plan-head-right { position: relative; display: flex; align-items: center; gap: 10rpx; }
.plan-progress { font-size: 24rpx; color: #185FA5; font-weight: 700; }
.plan-chev { width: 30rpx; height: 30rpx; }
.plan-summary { display: block; font-size: 24rpx; color: var(--c-text-second); padding: 12rpx 18rpx 4rpx; }
.plan-body { padding-top: 4rpx; }
/* 来源分区标题 */
.src-head { display: flex; align-items: center; gap: 8rpx; margin: 16rpx 4rpx 10rpx; }
.src-head-ic { width: 28rpx; height: 28rpx; }
.src-head-title { font-size: 24rpx; font-weight: 700; color: #0C447C; }
.src-head-sub { font-size: 22rpx; color: #185FA5; background: #E6F1FB; padding: 2rpx 14rpx; border-radius: 999rpx; }

/* 模块便当网格 */
.tile-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12rpx; }
.tile { position: relative; overflow: hidden; border-radius: 16rpx; padding: 16rpx; transition: transform .12s; }
.tile:active { transform: scale(0.98); }
.tile-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; transition: width .3s; }
.tile-inner { position: relative; }
.tile-row1 { display: flex; justify-content: space-between; align-items: center; }
.tile-ic { width: 34rpx; height: 34rpx; background-repeat: no-repeat; background-position: center; background-size: contain; }
.tile-num { font-size: 34rpx; font-weight: 800; }
.tile-cap { display: block; font-size: 22rpx; margin-top: 4rpx; }
/* 作业:实心蓝块 */
.tile-hw { background: #EEF5FF; border: 1rpx solid #B5D4F4; }
.tile-hw .tile-fill { background: #B5D4F4; }
.tile-hw .tile-num, .tile-hw .tile-cap { color: #0C447C; }
/* 课程:白底蓝描边 */
.tile-course { background: var(--c-bg-card); border: 2rpx solid #85B7EB; }
.tile-course .tile-fill { background: #E6F1FB; }
.tile-course .tile-num { color: #0C447C; }
.tile-course .tile-cap { color: #185FA5; }

/* 今日复习条(虚线描边) */
.review-bar { display: flex; align-items: center; gap: 10rpx; border: 2rpx dashed #85B7EB; border-radius: 16rpx; padding: 16rpx 18rpx; margin-top: 12rpx; }
.review-bar:active { background: #f4f9ff; }
.review-ic { width: 32rpx; height: 32rpx; flex-shrink: 0; }
.review-title { font-size: 26rpx; font-weight: 700; color: #0C447C; }
.review-sub { flex: 1; font-size: 22rpx; color: #185FA5; }
.review-arrow { font-size: 34rpx; color: #85B7EB; }

.plan-checkin-tip { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 12rpx; text-align: center; }

/* 模块图标(线性 SVG,主色蓝 #185FA5) */
.mic-word { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23185FA5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E"); }
.mic-grammar { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23185FA5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 20h9'/%3E%3Cpath d='M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z'/%3E%3C/svg%3E"); }
.mic-sentence { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23185FA5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='4' y1='7' x2='20' y2='7'/%3E%3Cline x1='4' y1='12' x2='16' y2='12'/%3E%3Cline x1='4' y1='17' x2='11' y2='17'/%3E%3C/svg%3E"); }
.mic-reading { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23185FA5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 4h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z'/%3E%3Cpath d='M22 4h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z'/%3E%3C/svg%3E"); }

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
.quick-icon { width: 58rpx; height: 58rpx; display: block; margin: 0 auto 16rpx; }
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
.qi-exam { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z'/%3E%3Cpath d='M14 2v6h6'/%3E%3Cpath d='M9 13l2 2 4-4'/%3E%3C/svg%3E"); }
.qi-speak { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z'/%3E%3Cpath d='M8 9h8'/%3E%3Cpath d='M8 13h5'/%3E%3C/svg%3E"); }
.qi-read-check { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z'/%3E%3Cpath d='M9 9l2 2 4-4'/%3E%3C/svg%3E"); }
.qi-write { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h5'/%3E%3Cpath d='M14 2v6h6'/%3E%3Cpath d='M18.5 14.5a2.1 2.1 0 0 1 3 3L17 22l-4 1 1-4z'/%3E%3C/svg%3E"); }

/* 教师身份 */
.cert-banner {
  background: #fff7e6; border: 1rpx solid #ffe58f; color: #b8860b;
  border-radius: var(--r-lg); padding: 24rpx; margin-bottom: 24rpx; font-size: var(--fs-body);
  display: flex; align-items: center; gap: 12rpx;
}
.cert-banner-ic { width: 36rpx; height: 36rpx; flex-shrink: 0; }
.role-hint { display: block; font-size: 24rpx; color: var(--c-text-hint); line-height: 1.6; padding: 0 8rpx; }

/* 家长身份 */
.child-section { margin-bottom: 24rpx; }
.child-empty { text-align: center; padding: 60rpx 0; }
.child-empty-icon { width: 80rpx; height: 80rpx; display: block; margin: 0 auto 16rpx; }
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
.bell { width: 40rpx; height: 40rpx; }
.badge { position: absolute; top: 0; right: 0; background: var(--c-danger); color: #fff; font-size: 20rpx; min-width: 28rpx; height: 28rpx; line-height: 28rpx; padding: 0 6rpx; border-radius: 999rpx; text-align: center; font-weight: 700; }
</style>

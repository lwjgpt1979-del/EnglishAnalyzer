<!-- 新手引导页（V2 M31）
  触发条件：登录且未选教材且未看过引导
  流程：Step 1 功能介绍 → Step 2 选教材 → Step 3 完成
-->
<template>
  <view class="ob-wrap">

    <!-- ── Step 1：功能介绍 ── -->
    <view v-if="step === 1" class="ob-page">
      <view class="ob-header">
        <text class="ob-logo">engGramer</text>
        <text class="ob-tagline">英语 AI 知识学习，专为你定制</text>
      </view>

      <!-- 功能卡片轮播 -->
      <swiper
        class="feat-swiper"
        :current="featIndex"
        indicator-dots
        indicator-color="rgba(0,0,0,0.2)"
        indicator-active-color="#1a1a1a"
        @change="onFeatChange"
        circular
      >
        <swiper-item v-for="f in features" :key="f.title">
          <view class="feat-card">
            <text class="feat-emoji">{{ f.emoji }}</text>
            <text class="feat-title">{{ f.title }}</text>
            <text class="feat-desc">{{ f.desc }}</text>
          </view>
        </swiper-item>
      </swiper>

      <view class="ob-actions">
        <button class="btn-primary" @tap="step = 2">开始设置 →</button>
        <text class="skip-link" @tap="skipOnboarding">跳过引导</text>
      </view>
    </view>

    <!-- ── Step 2：选教材偏好 ── -->
    <view v-else-if="step === 2" class="ob-page">
      <view class="ob-header">
        <text class="ob-step-no">第 2 步 / 共 2 步</text>
        <text class="ob-step-title">选择你的教材</text>
        <text class="ob-step-sub">后续可在「个人中心 → 我的偏好」随时修改</text>
      </view>

      <view class="pref-form">
        <view class="pref-row">
          <text class="pref-label">教材版本</text>
          <picker :range="textbookOptions" @change="onTextbookChange">
            <view class="pref-picker">
              <text>{{ textbook || '请选择' }}</text>
              <text class="pref-arrow">›</text>
            </view>
          </picker>
        </view>

        <view class="pref-row">
          <text class="pref-label">年级</text>
          <picker :range="gradeOptions" @change="onGradeChange">
            <view class="pref-picker">
              <text>{{ grade || '请选择' }}</text>
              <text class="pref-arrow">›</text>
            </view>
          </picker>
        </view>

        <view class="pref-row">
          <text class="pref-label">学期</text>
          <picker :range="semesterOptions" @change="onSemesterChange">
            <view class="pref-picker">
              <text>{{ semester ? semester + '学期' : '请选择' }}</text>
              <text class="pref-arrow">›</text>
            </view>
          </picker>
        </view>
      </view>

      <view class="ob-actions">
        <button
          class="btn-primary"
          :disabled="!canConfirm || saving"
          @tap="confirmPreference"
        >
          {{ saving ? '保存中…' : '完成设置 →' }}
        </button>
        <text class="skip-link" @tap="skipOnboarding">暂时跳过</text>
      </view>
    </view>

    <!-- ── Step 3：完成 ── -->
    <view v-else-if="step === 3" class="ob-page ob-done">
      <text class="done-emoji">🎉</text>
      <text class="done-title">设置完成！</text>
      <text class="done-sub">
        已为你选好
        <text class="done-pref">{{ textbook }} {{ grade }} {{ semester }}学期</text>
        的课程内容
      </text>
      <view class="ob-actions">
        <button class="btn-primary" @tap="goLearn">开始学习 →</button>
      </view>
    </view>

  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { updateProfile } from '@/api/auth'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const step = ref(1)
const featIndex = ref(0)
const saving = ref(false)

// ── 功能介绍数据 ──────────────────────────────────────────────────────────────
const features = [
  {
    emoji: '📖',
    title: '系统化知识学习',
    desc: '按教材 → 单元 → 知识点浏览，六大维度（听力/词汇/语法/阅读/翻译/写作）全覆盖',
  },
  {
    emoji: '🤖',
    title: 'AI 智能出题',
    desc: '根据你的薄弱知识点，AI 自动生成个性化练习题，精准强化短板',
  },
  {
    emoji: '📄',
    title: '整卷上传分析',
    desc: '上传做过的试卷，AI 识别并标记错题，自动归入错题本',
  },
  {
    emoji: '📊',
    title: '学情诊断报告',
    desc: '实时追踪知识点掌握度，展示题型分布和难度分析',
  },
  {
    emoji: '🔤',
    title: '词力通单词打卡',
    desc: 'SM-2 记忆曲线算法，科学复习词汇，连续打卡激励坚持学习',
  },
]

function onFeatChange(e: any) {
  featIndex.value = e.detail.current
}

// ── 教材选择 ───────────────────────────────────────────────────────────────────
const textbookOptions = ['译林版', '人教PEP', '外研版']
const gradeOptions = ['小学5年级', '小学6年级', '初中7年级', '初中8年级', '初中9年级']
const semesterOptions = ['上', '下']

const textbook = ref('')
const grade = ref('')
const semester = ref<'上' | '下' | ''>('')

function onTextbookChange(e: any) { textbook.value = textbookOptions[e.detail.value] }
function onGradeChange(e: any) { grade.value = gradeOptions[e.detail.value] }
function onSemesterChange(e: any) { semester.value = semesterOptions[e.detail.value] as '上' | '下' }

const canConfirm = computed(() => !!textbook.value && !!grade.value && !!semester.value)

// ── 操作 ───────────────────────────────────────────────────────────────────────
async function confirmPreference() {
  if (!canConfirm.value || saving.value) return
  saving.value = true
  try {
    const updated = await updateProfile({
      preferred_textbook_version: textbook.value,
      preferred_grade: grade.value,
      preferred_semester: semester.value as '上' | '下',
    })
    // 更新本地 user 状态
    auth.user = { ...auth.user, ...updated } as any
    _markDone()
    step.value = 3
  } catch {
    uni.showToast({ title: '保存失败，请重试', icon: 'none' })
  } finally {
    saving.value = false
  }
}

function skipOnboarding() {
  _markDone()
  uni.switchTab({ url: '/pages/index/index' })
}

function goLearn() {
  _markDone()
  const t = textbook.value || (auth.user as any)?.preferred_textbook_version || '译林版'
  const g = grade.value || (auth.user as any)?.preferred_grade || '小学5年级'
  const s = semester.value || (auth.user as any)?.preferred_semester || '上'
  uni.redirectTo({
    url: `/pages/curriculum/units?textbook=${encodeURIComponent(t)}&grade=${encodeURIComponent(g)}&semester=${encodeURIComponent(s)}`,
  })
}

function _markDone() {
  uni.setStorageSync('onboarding_done', '1')
}
</script>

<style scoped>
.ob-wrap {
  min-height: 100vh;
  background: #fffef0;
  display: flex;
  flex-direction: column;
}

.ob-page {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 80rpx 40rpx 60rpx;
  min-height: 100vh;
  box-sizing: border-box;
}

/* ── Header ── */
.ob-header { margin-bottom: 48rpx; }
.ob-logo {
  font-size: 56rpx;
  font-weight: 900;
  color: #1a1a1a;
  display: block;
  margin-bottom: 16rpx;
}
.ob-tagline {
  font-size: 30rpx;
  color: #666;
  display: block;
}
.ob-step-no {
  font-size: 24rpx;
  color: #999;
  display: block;
  margin-bottom: 16rpx;
}
.ob-step-title {
  font-size: 48rpx;
  font-weight: 800;
  color: #1a1a1a;
  display: block;
  margin-bottom: 12rpx;
}
.ob-step-sub {
  font-size: 26rpx;
  color: #888;
  display: block;
}

/* ── 功能卡片 ── */
.feat-swiper {
  flex: 1;
  height: 480rpx;
  margin-bottom: 48rpx;
}
.feat-card {
  height: 100%;
  background: #fff;
  border-radius: 32rpx;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 60rpx 48rpx;
  box-shadow: 0 8rpx 32rpx rgba(0, 0, 0, 0.06);
  box-sizing: border-box;
}
.feat-emoji {
  font-size: 96rpx;
  display: block;
  margin-bottom: 32rpx;
}
.feat-title {
  font-size: 36rpx;
  font-weight: 800;
  color: #1a1a1a;
  display: block;
  margin-bottom: 20rpx;
  text-align: center;
}
.feat-desc {
  font-size: 26rpx;
  color: #666;
  display: block;
  text-align: center;
  line-height: 1.6;
}

/* ── 教材选择表单 ── */
.pref-form {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  margin-bottom: 48rpx;
}
.pref-row {
  background: #fff;
  border-radius: 20rpx;
  padding: 32rpx 32rpx;
  display: flex;
  align-items: center;
  justify-content: space-between;
  box-shadow: 0 4rpx 16rpx rgba(0, 0, 0, 0.04);
}
.pref-label {
  font-size: 30rpx;
  font-weight: 600;
  color: #1a1a1a;
}
.pref-picker {
  display: flex;
  align-items: center;
  gap: 8rpx;
  font-size: 28rpx;
  color: #555;
}
.pref-arrow {
  font-size: 36rpx;
  color: #bbb;
}

/* ── 完成页 ── */
.ob-done {
  align-items: center;
  justify-content: center;
  text-align: center;
}
.done-emoji {
  font-size: 120rpx;
  display: block;
  margin-bottom: 40rpx;
}
.done-title {
  font-size: 52rpx;
  font-weight: 900;
  color: #1a1a1a;
  display: block;
  margin-bottom: 20rpx;
}
.done-sub {
  font-size: 28rpx;
  color: #666;
  display: block;
  margin-bottom: 60rpx;
  line-height: 1.8;
}
.done-pref {
  color: #e8b800;
  font-weight: 700;
}

/* ── 底部操作区 ── */
.ob-actions {
  display: flex;
  flex-direction: column;
  gap: 24rpx;
  align-items: center;
}
.btn-primary {
  width: 100%;
  background: #ffb020;
  color: #1a1a1a;
  border-radius: 999rpx;
  font-size: 32rpx;
  font-weight: 800;
  padding: 28rpx 0;
  border: none;
}
.btn-primary[disabled] {
  opacity: 0.45;
}
.skip-link {
  font-size: 26rpx;
  color: #aaa;
  text-decoration: underline;
  padding: 8rpx;
}
</style>

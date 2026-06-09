<template>
  <view class="page">
    <!-- 加载中 -->
    <view v-if="loading" class="empty">正在为你智能组卷…</view>

    <!-- 无薄弱数据 -->
    <view v-else-if="!questions.length" class="empty-card card">
      <text class="empty-icon">📝</text>
      <text class="empty-title">暂无推荐题目</text>
      <text class="empty-hint">先完成一些练习或上传错题，AI 就能为你精准出题了</text>
      <button class="btn-primary" @tap="goBack">返回</button>
    </view>

    <!-- 答题中 -->
    <view v-else-if="!finished">
      <!-- 薄弱点 banner -->
      <view class="banner">
        <text class="banner-label" v-if="unitTitle">{{ unitTitle }} · 薄弱点：</text>
        <text class="banner-label" v-else>针对你的薄弱点：</text>
        <text class="banner-kps">{{ weakKpNames.join('、') }}</text>
      </view>

      <view class="progress">
        <text>{{ currentIdx + 1 }} / {{ questions.length }}</text>
      </view>

      <view class="card">
        <view class="qtype">{{ current.question_type }} · 难度 {{ current.difficulty }}</view>
        <text class="stem">{{ current.stem }}</text>

        <!-- 单选 / 完型 / 阅读 -->
        <view v-if="['单选','完型','阅读'].includes(current.question_type) && current.options" class="options">
          <view
            v-for="(opt, i) in current.options" :key="i"
            class="option"
            :class="{
              selected: userAnswer === letter(i),
              correct: feedback && letter(i) === feedback.correct_answer,
              wrong: feedback && userAnswer === letter(i) && !feedback.correct,
            }"
            @tap="feedback ? null : (userAnswer = letter(i))"
          >{{ opt }}</view>
        </view>

        <!-- 填空 -->
        <view v-else-if="current.question_type === '填空'" class="fill">
          <input
            v-model="userAnswer"
            class="fill-input"
            placeholder="请输入答案"
            :disabled="!!feedback"
          />
        </view>

        <!-- 判断 -->
        <view v-else-if="current.question_type === '判断'" class="judge">
          <view
            v-for="opt in ['对', '错']" :key="opt"
            class="option"
            :class="{
              selected: userAnswer === opt,
              correct: feedback && opt === feedback.correct_answer,
              wrong: feedback && userAnswer === opt && !feedback.correct,
            }"
            @tap="feedback ? null : (userAnswer = opt)"
          >{{ opt }}</view>
        </view>

        <!-- 写作 / 连线（简化：文本输入） -->
        <view v-else class="fill">
          <textarea
            v-model="userAnswer"
            class="fill-textarea"
            placeholder="请输入你的答案"
            :disabled="!!feedback"
            auto-height
          />
        </view>

        <!-- 反馈 -->
        <view v-if="feedback" class="feedback" :class="{ ok: feedback.correct }">
          <text class="fb-title">{{ feedback.correct ? '✓ 答对了' : '✗ 答错了' }}</text>
          <text class="fb-ans">正确答案：{{ feedback.correct_answer }}</text>
          <text class="fb-exp">{{ feedback.explanation }}</text>
        </view>

        <button
          class="btn-primary"
          :disabled="!canSubmit"
          @tap="feedback ? next() : submit()"
        >
          {{ feedback ? (isLast ? '查看结果' : '下一题') : '提交答案' }}
        </button>
      </view>
    </view>

    <!-- 完成 -->
    <view v-else class="finish-card card">
      <text class="finish-icon">🎉</text>
      <text class="finish-title">智能练习完成</text>
      <text class="finish-meta">共 {{ questions.length }} 题，答对 {{ correctCount }} 道</text>
      <text class="finish-rate">正确率 {{ Math.round(correctCount / questions.length * 100) }}%</text>

      <!-- 按 KP 拆解 -->
      <view v-if="kpStats.length" class="kp-breakdown">
        <text class="kp-breakdown-title">各知识点表现</text>
        <view v-for="stat in kpStats" :key="stat.name" class="kp-stat-row">
          <text class="kp-stat-name">{{ stat.name }}</text>
          <view class="kp-stat-bar-wrap">
            <view
              class="kp-stat-bar"
              :style="{ width: (stat.total > 0 ? stat.correct / stat.total * 100 : 0) + '%' }"
              :class="stat.correct === stat.total ? 'full' : stat.correct > 0 ? 'partial' : 'none'"
            />
          </view>
          <text class="kp-stat-num">{{ stat.correct }}/{{ stat.total }}</text>
        </view>
      </view>

      <view class="finish-actions">
        <button class="btn-primary" @tap="retryAdaptive">再练一组 →</button>
        <button class="btn-secondary" @tap="goDiagnosis">查看学情报告</button>
        <button class="btn-ghost" @tap="goBack">返回</button>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getAdaptiveSet, submitAttempt } from '@/api/questions'
import type { SimQuestionOut, PracticeResultOut } from '@/types/api'

const loading = ref(true)
const questions = ref<SimQuestionOut[]>([])
const weakKpNames = ref<string[]>([])
const currentIdx = ref(0)
const userAnswer = ref('')
const feedback = ref<PracticeResultOut | null>(null)
const correctCount = ref(0)
const finished = ref(false)
const unitId = ref<string | undefined>(undefined)
const unitTitle = ref('')

// 记录每题作答结果（供完成页按 KP 分析）
interface AnswerRecord { kp_name: string; correct: boolean }
const answerRecords = ref<AnswerRecord[]>([])

const current = computed(() => questions.value[currentIdx.value])
const isLast = computed(() => currentIdx.value === questions.value.length - 1)
const canSubmit = computed(() => !!feedback.value || !!userAnswer.value.trim())

// 按 KP 聚合正确数 / 总数
const kpStats = computed(() => {
  const map = new Map<string, { correct: number; total: number }>()
  for (const r of answerRecords.value) {
    const name = r.kp_name || '其他'
    const slot = map.get(name) || { correct: 0, total: 0 }
    slot.total++
    if (r.correct) slot.correct++
    map.set(name, slot)
  }
  return Array.from(map.entries()).map(([name, s]) => ({ name, ...s }))
})

function letter(i: number): string {
  return ['A', 'B', 'C', 'D'][i] ?? ''
}

// 加载智能题集
async function loadAdaptiveSet() {
  loading.value = true
  try {
    const result = await getAdaptiveSet(5, unitId.value)
    questions.value = result.questions
    weakKpNames.value = result.weak_kp_names
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}

onLoad((q: any) => {
  unitId.value = q?.unit_id || undefined
  unitTitle.value = q?.unit_title ? decodeURIComponent(q.unit_title) : ''
  loadAdaptiveSet()
})

async function submit() {
  if (!current.value) return
  try {
    const r = await submitAttempt({
      question_id: current.value.id,
      user_answer: userAnswer.value.trim(),
    })
    feedback.value = r
    if (r.correct) correctCount.value++
    // 记录作答结果
    answerRecords.value.push({
      kp_name: current.value.kp_name || '其他',
      correct: r.correct,
    })
  } catch (e: any) {
    uni.showToast({ title: e?.message || '提交失败', icon: 'none' })
  }
}

function next() {
  if (isLast.value) {
    finished.value = true
    return
  }
  currentIdx.value++
  userAnswer.value = ''
  feedback.value = null
}

function goBack() {
  uni.navigateBack()
}

function retryAdaptive() {
  questions.value = []
  weakKpNames.value = []
  currentIdx.value = 0
  userAnswer.value = ''
  feedback.value = null
  correctCount.value = 0
  finished.value = false
  answerRecords.value = []
  loading.value = true
  loadAdaptiveSet()
}

function goDiagnosis() {
  uni.switchTab({ url: '/pages/diagnosis/index' })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }

.banner {
  background: var(--c-primary-faint);
  border-radius: var(--r-md);
  padding: 16rpx 20rpx;
  margin-bottom: 16rpx;
  display: flex;
  flex-wrap: wrap;
  gap: 4rpx;
}
.banner-label { font-size: 24rpx; color: var(--c-text-second); }
.banner-kps { font-size: 24rpx; font-weight: 700; color: var(--c-gold); }

.progress { text-align: center; padding: 12rpx 0; font-size: 24rpx; color: var(--c-text-second); }

.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: var(--sp-4); box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qtype { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 12rpx; }
.stem { display: block; font-size: 30rpx; font-weight: 600; color: var(--c-ink); line-height: 1.5; margin-bottom: 24rpx; }

.options, .judge { display: flex; flex-direction: column; gap: 12rpx; margin-bottom: 24rpx; }
.option { padding: 20rpx; border: 2rpx solid var(--c-border); border-radius: var(--r-md); font-size: 28rpx; color: var(--c-text-body); }
.option.selected { border-color: var(--c-gold); background: var(--c-primary-faint); font-weight: 600; }
.option.correct { border-color: #2ecc71; background: #eafaf1; }
.option.wrong { border-color: var(--c-danger); background: var(--c-danger-bg); }

.fill-input {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  height: 72rpx;
  line-height: 72rpx;
  padding: 0 20rpx;
  font-size: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
  width: 100%;
}
.fill-textarea {
  border: 2rpx solid var(--c-border);
  border-radius: var(--r-md);
  min-height: 160rpx;
  padding: 16rpx 20rpx;
  font-size: 28rpx;
  margin-bottom: 24rpx;
  box-sizing: border-box;
  width: 100%;
}

.feedback { background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 8rpx; }
.feedback.ok { background: #eafaf1; }
.fb-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.fb-ans { font-size: 24rpx; color: var(--c-text-body); }
.fb-exp { font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; }

.btn-primary { background: var(--c-primary); color: var(--c-ink); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-primary[disabled] { background: var(--c-primary-soft); color: #b9a94e; }

.empty-card { display: flex; flex-direction: column; align-items: center; gap: 16rpx; padding: 60rpx 40rpx; text-align: center; }
.empty-icon { font-size: 80rpx; }
.empty-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-ink); }
.empty-hint { font-size: 26rpx; color: var(--c-text-second); line-height: 1.6; }

.finish-card { display: flex; flex-direction: column; gap: 16rpx; align-items: center; text-align: center; padding: 48rpx; }
.finish-icon { font-size: 80rpx; }
.finish-title { font-size: var(--fs-h1); font-weight: 800; color: var(--c-ink); }
.finish-meta { font-size: 28rpx; color: var(--c-text-second); }
.finish-rate { font-size: 40rpx; font-weight: 800; color: var(--c-gold); }

/* KP 分析 */
.kp-breakdown { width: 100%; margin-top: 8rpx; margin-bottom: 8rpx; }
.kp-breakdown-title { font-size: 24rpx; color: var(--c-text-hint); display: block; text-align: left; margin-bottom: 12rpx; }
.kp-stat-row { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; }
.kp-stat-name { font-size: 24rpx; color: var(--c-text-body); width: 160rpx; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; flex-shrink: 0; text-align: left; }
.kp-stat-bar-wrap { flex: 1; height: 12rpx; background: #f0f0f0; border-radius: 999rpx; overflow: hidden; }
.kp-stat-bar { height: 100%; border-radius: 999rpx; transition: width 0.4s; }
.kp-stat-bar.full { background: #22c55e; }
.kp-stat-bar.partial { background: #f5c518; }
.kp-stat-bar.none { background: #ef4444; width: 4rpx !important; }
.kp-stat-num { font-size: 22rpx; color: var(--c-text-hint); width: 60rpx; text-align: right; flex-shrink: 0; }

/* 完成页按钮组 */
.finish-actions { width: 100%; display: flex; flex-direction: column; gap: 16rpx; margin-top: 8rpx; }
.btn-secondary { background: #fff; color: var(--c-ink); border: 2rpx solid var(--c-border); border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; }
.btn-ghost { background: transparent; color: var(--c-text-hint); border: none; font-size: 26rpx; padding: 8rpx; }
</style>

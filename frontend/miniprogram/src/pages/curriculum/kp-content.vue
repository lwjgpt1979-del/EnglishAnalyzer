<template>
  <view class="page">
    <!-- 外层关联视图 3-Tab -->
    <view class="tabs">
      <view
        v-for="t in viewTabs" :key="t.key"
        class="tab" :class="{ active: activeView === t.key }"
        @tap="switchView(t.key)"
      >{{ t.label }}</view>
    </view>

    <!-- 掌握卡片 -->
    <view class="mastery-card" v-if="mastery && mastery.total > 0">
      <view class="mastery-row">
        <text class="mastery-label">正确率</text>
        <text class="mastery-val accent">{{ mastery.accuracy !== null ? Math.round(mastery.accuracy * 100) + '%' : '—' }}</text>
      </view>
      <view class="mastery-row">
        <text class="mastery-label">练习次数</text>
        <text class="mastery-val">{{ mastery.total }} 题</text>
      </view>
      <view class="mastery-row" v-if="mastery.last_activity_at">
        <text class="mastery-label">最近练习</text>
        <text class="mastery-val">{{ mastery.last_activity_at.slice(0, 10) }}</text>
      </view>
    </view>

    <!-- Tab 1: 课本内容（含 4 维度子 tab） -->
    <template v-if="activeView === 'content'">
      <view class="subtabs">
        <view
          v-for="d in dims" :key="d.key"
          class="subtab" :class="{ active: activeDim === d.key }"
          @tap="activeDim = d.key"
        >{{ d.label }}</view>
      </view>
      <view v-if="loading" class="empty">加载中…</view>
      <view v-else-if="!currentContent" class="empty">该维度暂无内容</view>
      <scroll-view v-else scroll-y class="content">
        <rich-text :nodes="md2html(currentContent.content_md || '')" class="md" />
      </scroll-view>
      <view class="practice-bar">
        <button class="btn-secondary" @tap="goPractice">练习（5 题）</button>
        <button class="btn-primary" @tap="goExam">模拟考（10 题）</button>
      </view>
    </template>

    <!-- Tab 2: 仿真题列表 -->
    <template v-else-if="activeView === 'questions'">
      <view v-if="qLoading" class="empty">加载中…</view>
      <view v-else-if="questions.length === 0" class="empty">暂无仿真题</view>
      <scroll-view v-else scroll-y class="list">
        <view
          v-for="(q, i) in questions" :key="q.id"
          class="card" @tap="goPractice"
        >
          <view class="card-head">
            <text class="tag">{{ q.question_type }}</text>
            <text class="diff">难度 {{ q.difficulty }}</text>
          </view>
          <text class="card-stem">{{ i + 1 }}. {{ q.stem }}</text>
        </view>
        <view class="list-foot">点击任意题开始练习</view>
      </scroll-view>
    </template>

    <!-- Tab 3: 我做过的相关题 -->
    <template v-else>
      <view v-if="wLoading" class="empty">加载中…</view>
      <view v-else-if="wrongs.length === 0" class="empty">还没有相关错题，去练习试试吧</view>
      <scroll-view v-else scroll-y class="list">
        <view
          v-for="w in wrongs" :key="w.id"
          class="card" @tap="goWrongDetail(w.id)"
        >
          <view class="card-head">
            <text class="tag tag-wrong" v-if="!w.is_mastered">未掌握</text>
            <text class="tag tag-ok" v-else>已掌握</text>
            <text class="diff" v-if="w.question_type">{{ w.question_type }}</text>
          </view>
          <text class="card-stem">{{ w.question_text || '（题目图片，点击查看）' }}</text>
        </view>
      </scroll-view>
    </template>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { getKpContents, getKpMastery } from '@/api/curriculum'
import { listPracticeQuestions } from '@/api/questions'
import { listWrongQuestionsByKp } from '@/api/wrongQuestions'
import { md2html } from '@/utils/md'
import type { KPContentOut, KpMasteryItem, SimQuestionOut, WrongQuestionOut } from '@/types/api'

type ViewKey = 'content' | 'questions' | 'wrong'
const viewTabs: { key: ViewKey; label: string }[] = [
  { key: 'content', label: '课本内容' },
  { key: 'questions', label: '仿真题' },
  { key: 'wrong', label: '我做过的相关题' },
]
const activeView = ref<ViewKey>('content')

// —— Tab 1：课本内容 ——
const dims = [
  { key: 'listening',   label: '听力' },
  { key: 'vocabulary',  label: '词汇' },
  { key: 'grammar',     label: '语法' },
  { key: 'reading',     label: '阅读' },
  { key: 'translation', label: '翻译' },
  { key: 'writing',     label: '写作' },
]
const contents = ref<KPContentOut[]>([])
const activeDim = ref('grammar')
const loading = ref(true)
const kpId = ref('')

const currentContent = computed(
  () => contents.value.find(c => c.dimension === activeDim.value) || null,
)

// —— 掌握台账 ——
const mastery = ref<KpMasteryItem | null>(null)

async function loadMastery() {
  try {
    mastery.value = await getKpMastery(kpId.value)
  } catch { /* 静默失败 */ }
}

// —— Tab 2：仿真题（懒加载） ——
const questions = ref<SimQuestionOut[]>([])
const qLoading = ref(false)
const qLoaded = ref(false)

// —— Tab 3：相关错题（懒加载） ——
const wrongs = ref<WrongQuestionOut[]>([])
const wLoading = ref(false)
const wLoaded = ref(false)

onLoad(async (q: any) => {
  kpId.value = q.id || ''
  try {
    contents.value = await getKpContents(q.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
  loadMastery()
})

onShow(() => {
  if (kpId.value) loadMastery()
})

async function switchView(key: ViewKey) {
  activeView.value = key
  if (key === 'questions' && !qLoaded.value) await loadQuestions()
  if (key === 'wrong' && !wLoaded.value) await loadWrongs()
}

async function loadQuestions() {
  qLoading.value = true
  try {
    questions.value = await listPracticeQuestions(kpId.value, 20)
    qLoaded.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    qLoading.value = false
  }
}

async function loadWrongs() {
  wLoading.value = true
  try {
    const res = await listWrongQuestionsByKp(kpId.value, 0, 50)
    wrongs.value = res.items
    wLoaded.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    wLoading.value = false
  }
}

function goPractice() {
  uni.navigateTo({ url: `/pages/practice/v2-session?kp=${kpId.value}&dim=${activeDim.value}` })
}

function goExam() {
  uni.navigateTo({ url: `/pages/practice/v2-exam?kp=${kpId.value}&count=10&dim=${activeDim.value}` })
}

function goWrongDetail(id: string) {
  uni.navigateTo({ url: `/pages/wrong-questions/detail?id=${id}` })
}
</script>

<style scoped>
.page { padding: 0; background: var(--c-bg-page); min-height: 100vh; display: flex; flex-direction: column; }
.tabs { display: flex; background: var(--c-bg-card); border-bottom: 1rpx solid var(--c-border); }
.tab {
  flex: 1; text-align: center; padding: 24rpx 0; font-size: 28rpx;
  color: var(--c-text-second); position: relative;
}
.tab.active { color: var(--c-ink); font-weight: 700; }
.tab.active::after {
  content: ''; position: absolute; left: 25%; right: 25%; bottom: 0;
  height: 4rpx; background: var(--c-primary);
}
.subtabs { display: flex; background: var(--c-bg-soft); border-bottom: 1rpx solid var(--c-border); }
.subtab {
  flex: 1; text-align: center; padding: 18rpx 0; font-size: 26rpx; color: var(--c-text-second);
}
.subtab.active { color: var(--c-primary); font-weight: 700; }
.empty { text-align: center; padding: 80rpx 24rpx; color: var(--c-text-hint); font-size: 28rpx; }
.content { flex: 1; padding: 24rpx; }
.md { font-size: 28rpx; line-height: 1.7; color: var(--c-text-body); }
.list { flex: 1; padding: 16rpx 24rpx; }
.card {
  background: var(--c-bg-card); border: 1rpx solid var(--c-border);
  border-radius: var(--r-card, 16rpx); padding: 24rpx; margin-bottom: 16rpx;
}
.card-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; }
.tag { font-size: 22rpx; padding: 4rpx 14rpx; border-radius: 999rpx; background: var(--c-bg-soft); color: var(--c-text-second); }
.tag-wrong { background: #FDECEC; color: #D14343; }
.tag-ok { background: #E7F6EC; color: #2E8B57; }
.diff { font-size: 22rpx; color: var(--c-text-hint); }
.card-stem { font-size: 28rpx; line-height: 1.6; color: var(--c-text-body); display: block; }
.list-foot { text-align: center; padding: 24rpx 0 40rpx; color: var(--c-text-hint); font-size: 24rpx; }
.practice-bar { padding: 24rpx; background: var(--c-bg-card); border-top: 1rpx solid var(--c-border); display: flex; gap: 16rpx; }
.btn-primary, .btn-secondary { flex: 1; border-radius: var(--r-btn); padding: 20rpx; font-weight: 700; font-size: 28rpx; text-align: center; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); }
.btn-secondary { background: var(--c-bg-soft); color: var(--c-text-body); border: 2rpx solid var(--c-border); }
.mastery-card {
  background: var(--c-bg-card); border-bottom: 1rpx solid var(--c-border);
  padding: 20rpx 32rpx; display: flex; gap: 40rpx;
}
.mastery-row { display: flex; flex-direction: column; align-items: center; }
.mastery-label { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 4rpx; }
.mastery-val { font-size: 30rpx; font-weight: 700; color: var(--c-text-body); }
.mastery-val.accent { color: var(--c-primary); }
</style>

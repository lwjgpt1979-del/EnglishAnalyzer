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

    <!-- 语法类 KP:R10 四维掌握卡(识别/纠错/产出/迁移 + 诚实标签 + 直达检测) -->
    <view class="g4-card" v-if="isGrammar && gStatus">
      <view class="g4-head">
        <text class="g4-label" :class="'st-' + gStatus.status">{{ gStatus.label }}</text>
        <view class="g4-btn" @tap="goGrammar">{{ gActionText }}</view>
      </view>
      <view class="g4-dims">
        <view class="g4-dim" v-for="d in G_DIMS" :key="d.key">
          <text class="g4-dim-label">{{ d.label }}</text>
          <view class="g4-bar"><view class="g4-fill" :style="{ width: Math.round(((gStatus as any)[d.key] || 0) * 100) + '%' }" /></view>
          <text class="g4-dim-val">{{ Math.round(((gStatus as any)[d.key] || 0) * 100) }}%</text>
        </view>
        <view class="g4-dim">
          <text class="g4-dim-label">迁移</text>
          <text class="g4-dim-val" :class="{ ok: gStatus.transfer_ok }">{{ gStatus.transfer_ok ? '已通过' : '未通过' }}</text>
        </view>
      </view>
      <text class="g4-evidence" v-if="gStatus.evidence?.length">{{ gStatus.evidence.join(';') }}</text>
    </view>

    <!-- 非语法类:正确率台账;没练过给「摸底」引导而非整块消失 -->
    <view class="mastery-card" v-else-if="mastery && mastery.total > 0">
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
    <view class="mastery-card mastery-hint" v-else-if="mastery !== null || !loading">
      <text class="mastery-tip">还没检测过这个知识点 —— 先做 5 题摸个底,看看自己会不会</text>
    </view>

    <!-- Tab 1: 课本内容(只展示有内容的维度) -->
    <template v-if="activeView === 'content'">
      <view class="subtabs" v-if="availDims.length > 1">
        <view
          v-for="d in availDims" :key="d.key"
          class="subtab" :class="{ active: activeDim === d.key }"
          @tap="activeDim = d.key"
        >{{ d.label }}</view>
      </view>
      <view v-if="loading" class="empty">加载中…</view>
      <view v-else-if="availDims.length === 0" class="empty">
        <text class="empty-title">讲解内容制作中</text>
        <text class="empty-sub">这个知识点的课本讲解还没上线\n可以先练几题检验掌握情况,或看「仿真题」</text>
      </view>
      <scroll-view v-else scroll-y class="content">
        <view class="dim-badge" v-if="availDims.length === 1">{{ availDims[0].label }}</view>
        <rich-text :nodes="md2html(currentContent?.content_md || '')" class="md" />
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
        <view class="list-foot">点击任意题进入本知识点练习</view>
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
import { getKpStatus } from '@/api/grammar'
import { listPracticeQuestions } from '@/api/questions'
import { listWrongQuestionsByKp } from '@/api/wrongQuestions'
import { md2html } from '@/utils/md'
import type { KPContentOut, KpMasteryItem, SimQuestionOut, WrongQuestionOut } from '@/types/api'

type ViewKey = 'content' | 'questions' | 'wrong'
const viewTabs: { key: ViewKey; label: string }[] = [
  { key: 'content', label: '课本内容' },
  { key: 'questions', label: '仿真题' },
  { key: 'wrong', label: '相关错题' },
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
const activeDim = ref('')
const loading = ref(true)
const kpId = ref('')
const kpName = ref('')

// 只保留真有内容的维度做 tab(避免让用户挨个点 6 个空维度)
const availDims = computed(() =>
  dims.filter(d => contents.value.some(
    c => c.dimension === d.key && (c.content_md || '').trim())))

const currentContent = computed(
  () => contents.value.find(c => c.dimension === activeDim.value) || null,
)

function setTitle(name: string) {
  if (!name) return
  kpName.value = name
  uni.setNavigationBarTitle({ title: name })
}

// —— 掌握台账 ——
const mastery = ref<KpMasteryItem | null>(null)

async function loadMastery() {
  try {
    mastery.value = await getKpMastery(kpId.value)
    if (!kpName.value && mastery.value?.kp_name) setTitle(mastery.value.kp_name)
  } catch { /* 静默失败 */ }
}

// —— R10 语法四维掌握(仅语法类 KP:识别/纠错/产出/迁移 BKT + 诚实标签)——
const isGrammar = ref(false)
type GStatus = Awaited<ReturnType<typeof getKpStatus>>
const gStatus = ref<GStatus | null>(null)
const G_DIMS = [
  { key: 'recognize', label: '识别' },
  { key: 'detect', label: '纠错' },
  { key: 'produce_score', label: '产出' },
] as const

async function loadGrammarStatus() {
  if (!isGrammar.value) return
  try { gStatus.value = await getKpStatus(kpId.value) } catch { /* 静默:退回旧台账 */ }
}

const gActionText = computed(() => {
  const s = gStatus.value?.status
  if (s === 'mastered') return '复测巩固'
  if (s === 'due_retain') return '去复测'
  if (s === 'learning' || s === 'retaining') return '继续闯关'
  return '测一测'
})

function goGrammar() {
  uni.navigateTo({
    url: `/pages/grammar/index?kp_id=${kpId.value}&name=${encodeURIComponent(kpName.value || '')}`,
  })
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
  if (q.name) setTitle(decodeURIComponent(q.name))
  isGrammar.value = q.cat === 'grammar'
  try {
    contents.value = await getKpContents(q.id)
    // 默认落在第一个「有内容」的维度(而不是写死语法);全空则留空展示整体空态
    activeDim.value = availDims.value[0]?.key || ''
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
  loadMastery()
  loadGrammarStatus()
})

onShow(() => {
  if (!kpId.value) return
  loadMastery()
  loadGrammarStatus()   // 从语法检测页返回后刷新四维
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

// 只有当前维度真有内容时才按维度练;否则按整个知识点练(避免"暂无内容却练该维度"的矛盾)
function dimParam(): string {
  return currentContent.value ? `&dim=${activeDim.value}` : ''
}

function goPractice() {
  uni.navigateTo({ url: `/pages/practice/v2-session?kp=${kpId.value}${dimParam()}` })
}

function goExam() {
  uni.navigateTo({ url: `/pages/practice/v2-exam?kp=${kpId.value}&count=10${dimParam()}` })
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
/* 空态撑满剩余空间:练习按钮才能贴住底部,不再悬在页面中间 */
.empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80rpx 48rpx; color: var(--c-text-hint); font-size: 28rpx; text-align: center;
}
.empty-title { font-size: 32rpx; color: var(--c-text-second); font-weight: 600; margin-bottom: 16rpx; }
.empty-sub { font-size: 26rpx; color: var(--c-text-hint); line-height: 1.7; white-space: pre-line; }
.mastery-hint { justify-content: center; }
.mastery-tip { font-size: 24rpx; color: var(--c-text-second); }
.dim-badge {
  display: inline-block; font-size: 22rpx; color: var(--c-primary);
  background: rgba(61, 139, 245, 0.08); border-radius: 999rpx;
  padding: 4rpx 18rpx; margin-bottom: 16rpx;
}
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
/* R10 语法四维掌握卡 */
.g4-card {
  background: var(--c-bg-card); border-bottom: 1rpx solid var(--c-border);
  padding: 20rpx 32rpx 16rpx;
}
.g4-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 14rpx; }
.g4-label { font-size: 26rpx; font-weight: 700; padding: 4rpx 18rpx; border-radius: 999rpx; }
.st-mastered { background: #E7F6EC; color: #2E8B57; }
.st-learning { background: #FFF4E5; color: #B7791F; }
.st-due_retain { background: #FDECEC; color: #D14343; }
.st-retaining { background: #EAF3FE; color: var(--c-primary); }
.st-new { background: var(--c-bg-soft); color: var(--c-text-second); }
.g4-btn {
  font-size: 24rpx; color: var(--c-on-primary); background: var(--c-primary);
  border-radius: 999rpx; padding: 8rpx 28rpx; font-weight: 600;
}
.g4-dims { display: flex; gap: 24rpx; }
.g4-dim { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.g4-dim-label { font-size: 22rpx; color: var(--c-text-hint); }
.g4-bar { width: 100%; height: 10rpx; background: var(--c-bg-soft); border-radius: 999rpx; overflow: hidden; }
.g4-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; }
.g4-dim-val { font-size: 22rpx; color: var(--c-text-second); font-weight: 600; }
.g4-dim-val.ok { color: #2E8B57; }
.g4-evidence { display: block; margin-top: 12rpx; font-size: 22rpx; color: var(--c-text-hint); }

.mastery-card {
  background: var(--c-bg-card); border-bottom: 1rpx solid var(--c-border);
  padding: 20rpx 32rpx; display: flex; gap: 40rpx;
}
.mastery-row { display: flex; flex-direction: column; align-items: center; }
.mastery-label { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 4rpx; }
.mastery-val { font-size: 30rpx; font-weight: 700; color: var(--c-text-body); }
.mastery-val.accent { color: var(--c-primary); }
</style>

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

    <!-- 非语法类:加权掌握度台账;没练过给「摸底」引导而非整块消失 -->
    <view class="mastery-card" v-else-if="mastery && mastery.total > 0">
      <view class="mastery-stats">
        <view class="mastery-row">
          <text class="mastery-label">掌握度</text>
          <text class="mastery-val accent">{{ mastery.mastery != null ? Math.round(mastery.mastery * 100) + '%' : '—' }}</text>
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
      <text class="mastery-evidence" v-if="(mastery.mastery_events ?? 0) < 10">
        证据不足:仅 {{ mastery.mastery_events ?? 0 }} 次判定,多练几题评估更准
      </text>
    </view>
    <view class="mastery-card mastery-hint" v-else-if="mastery !== null || !loading">
      <text class="mastery-tip">还没检测过这个知识点 —— 先做 5 题摸个底,看看自己会不会</text>
    </view>

    <!-- Tab 1: 课本内容(按讲解环节) -->
    <template v-if="activeView === 'content'">
      <view class="subtabs" v-if="availDims.length > 1">
        <view
          v-for="d in availDims" :key="d.key"
          class="subtab" :class="{ active: activeSection === d.key }"
          @tap="activeSection = d.key"
        >{{ d.label }}</view>
      </view>
      <view v-if="loading" class="empty">加载中…</view>
      <view v-else-if="availDims.length === 0" class="empty">
        <text class="empty-title">讲解内容制作中</text>
        <text class="empty-sub">这个知识点的课本讲解还没上线\n可以先练几题检验掌握情况,或看「仿真题」</text>
      </view>
      <scroll-view v-else scroll-y class="content">
        <view class="lecture-card">
          <view class="lecture-head">
            <text class="lecture-bar" />
            <text class="lecture-title">{{ currentTitle }}</text>
          </view>
          <rich-text :nodes="md2html(cleanContent)" class="md" />
        </view>

        <!-- 看例句 环节下：本单元教材原始例句（结构化解析产物） -->
        <view class="lecture-card tb-card" v-if="activeSection === 'examples' && textbookSentences.length">
          <view class="lecture-head">
            <text class="lecture-bar tb-bar" />
            <text class="lecture-title">{{ unitId ? '教材原句（本单元）' : '教材原句' }}</text>
          </view>
          <view class="tb-list">
            <view class="tb-item" v-for="(s, i) in textbookSentences" :key="i">
              <text class="tb-dot" />
              <text class="tb-text">{{ s.text }}</text>
            </view>
          </view>
        </view>
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
import { getKpContents, getKpMastery, getTextbookSentences } from '@/api/curriculum'
import type { TextbookSentence } from '@/api/curriculum'
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

// —— Tab 1：课本内容(按考点类型的教学环节 section,后台单一真源下发)——
const contents = ref<KPContentOut[]>([])
const activeSection = ref('')
const loading = ref(true)
const kpId = ref('')
const kpName = ref('')
const unitId = ref('')

// 本单元教材原始例句（结构化解析产物）；在「看例句」环节下追加展示
const textbookSentences = ref<TextbookSentence[]>([])

// 环节做 subtab:后端只返回已发布且有正文的环节(concept/rule/…),按返回顺序
const availDims = computed(() =>
  contents.value
    .filter(c => (c.content_md || '').trim())
    .map(c => ({ key: c.section_key, label: c.title })))

const currentContent = computed(
  () => contents.value.find(c => c.section_key === activeSection.value) || null,
)
const currentTitle = computed(
  () => availDims.value.find(d => d.key === activeSection.value)?.label || '',
)
// 去掉正文开头与环节同名的粗体标题(如「**一句话搞懂**:」),避免和上方 tab / 卡片标题重复
const cleanContent = computed(() => {
  let md = (currentContent.value?.content_md || '').trim()
  const t = currentTitle.value
  if (t) {
    const esc = t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    md = md.replace(new RegExp('^\\s*\\*\\*\\s*' + esc + '\\s*\\*\\*\\s*[：:]?\\s*'), '')
  }
  return md.trim()
})

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
  unitId.value = q.unit || ''
  if (q.name) setTitle(decodeURIComponent(q.name))
  isGrammar.value = q.cat === 'grammar'
  try {
    contents.value = await getKpContents(q.id)
    // 默认落在第一个有内容的环节;全空则展示整体空态「讲解内容制作中」
    activeSection.value = availDims.value[0]?.key || ''
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
  // 本单元教材原句（有 unit 上下文则收敛到本单元，否则取该考点全部已发布单元）
  try {
    textbookSentences.value = await getTextbookSentences(q.id, unitId.value || undefined)
  } catch { /* 无原句静默 */ }
  loadMastery()
  loadGrammarStatus()
})

onShow(() => {
  if (!kpId.value) return
  loadMastery()
  loadGrammarStatus()   // 从语法检测页返回后刷新四维
  // 从错题详情订正返回后刷新错题掌握徽标(已加载过才刷,避免首进空跑)
  if (wLoaded.value) refreshWrongs()
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

// 静默刷新错题列表(从错题详情订正返回后更新已掌握徽标),不置 wLoading 以免列表闪现「加载中」
async function refreshWrongs() {
  try {
    const res = await listWrongQuestionsByKp(kpId.value, 0, 50)
    wrongs.value = res.items
  } catch { /* 刷新失败保留旧列表,静默 */ }
}

// 讲解环节是教学内容、不是练习维度:练习一律按整个知识点(不再带 dim 参数)
function goPractice() {
  uni.navigateTo({ url: `/pages/practice/v2-session?kp=${kpId.value}` })
}

function goExam() {
  uni.navigateTo({ url: `/pages/practice/v2-exam?kp=${kpId.value}&count=10` })
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
/* 分段胶囊子 tab:整段一个软底容器,选中项为白底浮起 */
.subtabs {
  display: flex; gap: 8rpx; margin: 20rpx 24rpx 4rpx; padding: 6rpx;
  background: var(--c-bg-soft); border-radius: 999rpx;
}
.subtab {
  flex: 1; text-align: center; padding: 16rpx 0; font-size: 26rpx;
  color: var(--c-text-second); border-radius: 999rpx; transition: all .15s;
}
.subtab.active {
  color: var(--c-primary); font-weight: 700; background: var(--c-bg-card);
  box-shadow: 0 2rpx 8rpx rgba(0, 0, 0, .06);
}
/* 空态撑满剩余空间:练习按钮才能贴住底部,不再悬在页面中间 */
.empty {
  flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 80rpx 48rpx; color: var(--c-text-hint); font-size: 28rpx; text-align: center;
}
.empty-title { font-size: 32rpx; color: var(--c-text-second); font-weight: 600; margin-bottom: 16rpx; }
.empty-sub { font-size: 26rpx; color: var(--c-text-hint); line-height: 1.7; white-space: pre-line; }
.mastery-hint { justify-content: center; }
.mastery-tip { font-size: 24rpx; color: var(--c-text-second); }
.content { flex: 1; padding: 24rpx; }
/* 讲解白卡:浮在页面底色上,圆角 + 柔和阴影,内容不再顶边平铺 */
.lecture-card {
  background: var(--c-bg-card); border-radius: 24rpx;
  padding: 32rpx 32rpx 36rpx; box-shadow: 0 4rpx 20rpx rgba(0, 0, 0, .04);
}
.lecture-head { display: flex; align-items: center; margin-bottom: 20rpx; }
.lecture-bar {
  width: 8rpx; height: 32rpx; border-radius: 999rpx;
  background: var(--c-primary); margin-right: 14rpx;
}
.lecture-title { font-size: 32rpx; font-weight: 700; color: var(--c-ink); }
/* 正文:容器字号会 cascade 到 md2html 输出的无字号 <p>(mp-weixin rich-text 靠内联样式,外部 CSS 进不去内部) */
.md { font-size: 30rpx; line-height: 1.85; color: var(--c-text-body); }
/* 教材原句卡 */
.tb-card { margin-top: 20rpx; }
.tb-bar { background: var(--c-gold, #ffb020); }
.tb-list { display: flex; flex-direction: column; gap: 18rpx; }
.tb-item { display: flex; align-items: flex-start; gap: 14rpx; }
.tb-dot { width: 12rpx; height: 12rpx; border-radius: 999rpx; background: var(--c-gold, #ffb020); margin-top: 14rpx; flex-shrink: 0; }
.tb-text { flex: 1; font-size: 30rpx; line-height: 1.7; color: var(--c-text-body); }
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
  padding: 20rpx 32rpx; display: flex; flex-direction: column; gap: 10rpx;
}
.mastery-stats { display: flex; gap: 40rpx; }
.mastery-evidence { font-size: 22rpx; color: var(--c-text-hint); }
.mastery-row { display: flex; flex-direction: column; align-items: center; }
.mastery-label { font-size: 22rpx; color: var(--c-text-hint); margin-bottom: 4rpx; }
.mastery-val { font-size: 30rpx; font-weight: 700; color: var(--c-text-body); }
.mastery-val.accent { color: var(--c-primary); }
</style>

<!-- src/pages/wrong-questions/list.vue —— 我的错题(统一:一份错题 wrong_record) -->
<template>
  <view class="list-page">
    <!-- 今日错题复习（遗忘曲线）-->
    <view v-if="reviewDue > 0" class="review-banner" @tap="goReview">
      <view class="rb-left">
        <view class="ic ic-brain rb-icon" />
        <view class="rb-text">
          <text class="rb-title">今日错题复习</text>
          <text class="rb-sub">{{ reviewDue }} 道到期 · 遗忘曲线智能安排</text>
        </view>
      </view>
      <text class="rb-arrow">开始 ›</text>
    </view>

    <!-- 语法 / 词汇 筛选 -->
    <view class="src-tabs">
      <text v-for="t in KIND_TABS" :key="t.value" class="src-tab" :class="{ active: kind === t.value }" @tap="switchKind(t.value)">{{ t.label }}</text>
    </view>

    <!-- 状态子筛选:待巩固 / 巩固中 / 已掌握（带计数） -->
    <scroll-view class="status-scroll" scroll-x enhanced>
      <view class="status-row">
        <view
          v-for="s in STATUS_TABS"
          :key="s.value"
          class="status-chip"
          :class="{ active: status === s.value, [s.value || 'all']: true }"
          @tap="switchStatus(s.value)"
        >
          <text>{{ s.label }}</text>
          <text class="chip-n">{{ s.n }}</text>
        </view>
      </view>
    </scroll-view>

    <!-- 加载态 -->
    <view v-if="loading && items.length === 0" class="center-tip">加载中…</view>

    <!-- 空状态 -->
    <view v-else-if="!loading && items.length === 0" class="center-tip">
      <text>{{ status ? '这个状态下暂无错题' : '还没有错题，去上传作业吧 📄' }}</text>
      <button
        v-if="!status"
        class="btn-sm"
        @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })"
      >
        上传作业
      </button>
    </view>

    <!-- 列表 -->
    <view v-else class="wq-list">
      <view v-for="wq in activeItems" :key="wq.id" class="wq-card" :class="{ 'is-done': wq.lifecycle === 'mastered' }"
        @tap="() => uni.navigateTo({ url: '/pages/wrong-questions/detail?id=' + wq.id })">
        <!-- 顶部:状态 pill + 来源 -->
        <view class="wq-top">
          <view class="status-pill" :class="statusClass(wq)">{{ statusLabel(wq) }}</view>
          <text
            v-if="wq.source_route"
            class="src-chip src-link"
            @tap.stop="goSource(wq)"
          >{{ sourceText(wq) }} ›</text>
          <text v-else class="src-chip">{{ sourceText(wq) }}</text>
        </view>

        <!-- 题干 -->
        <text class="wq-stem">{{ cardText(wq) }}</text>

        <!-- 标签行:考点类型 + 考点名 + 题型 -->
        <view class="wq-tags">
          <text class="mini-tag" :class="kindClass(wq)">{{ kindLabel(wq) }}</text>
          <text v-if="wq.kp_name" class="mini-tag mini-kp">{{ wq.kp_name }}</text>
          <text v-if="wq.question_type" class="mini-tag">{{ wq.question_type }}</text>
        </view>

        <!-- 底部:进度 + 主动作(语法→练同类 / 词汇→学这个词) -->
        <view class="wq-foot">
          <text class="wq-progress">{{ progressText(wq) }}</text>
          <view
            v-if="wq.kp_kind === 'vocab'"
            class="prac-btn"
            :class="{ loading: vlLoading === wq.id }"
            @tap.stop="learnVocab(wq)"
          >
            <view class="ic ic-book prac-ic" />
            <text>{{ vlLoading === wq.id ? '打开中…' : '学这个词' }}</text>
          </view>
          <view
            v-else
            class="prac-btn"
            :class="{ loading: pracLoading === wq.id }"
            @tap.stop="practiceWrong(wq)"
          >
            <view class="ic ic-sparkle prac-ic" />
            <text>{{ pracLoading === wq.id ? '出题中…' : '练同类' }}</text>
          </view>
        </view>
      </view>

      <!-- 已掌握折叠区（仅「全部」视图）-->
      <view v-if="showFold" class="fold-bar" @tap="doneOpen = !doneOpen">
        <text>✓ 已掌握 {{ counts.mastered }}</text>
        <text class="fold-arrow">{{ doneOpen ? '收起 ▴' : '展开 ▾' }}</text>
      </view>
      <view v-if="showFold && doneOpen" class="done-list">
        <view v-for="wq in doneItems" :key="wq.id" class="done-row">
          <view class="status-pill s-done">已掌握</view>
          <text class="done-stem">{{ cardText(wq) }}</text>
        </view>
        <text v-if="doneItems.length < counts.mastered" class="done-hint">继续下拉「加载更多」可看到全部已掌握</text>
      </view>

      <!-- 加载更多 -->
      <view v-if="hasMore" class="load-more" @tap="loadMore">
        {{ loading ? '加载中…' : '加载更多' }}
      </view>
      <view v-else-if="items.length > 0" class="load-more gray">已加载全部</view>
    </view>

    <!-- 练同类仿真题(逐题作答判分,与作业详情共用组件) -->
    <PracticeQuiz
      v-if="pracOpen"
      :kp="pracKp"
      :questions="pracList"
      :recorder="pracRecorder"
      @close="onPracClose"
    />

    <!-- 词汇错题「学这个词」:富词卡(配图/短语/发音/跟读)-->
    <view v-if="vlCardOpen && vlSim" class="modal" @tap="closeVocabCard">
      <view class="modal-card" @tap.stop>
        <view class="modal-head">
          <text class="modal-title">学这个词</text>
          <text v-if="vlSim.mastered" class="wl-done">已掌握</text>
        </view>

        <scroll-view scroll-y class="modal-body">
          <!-- 图左 + 词/音标/释义右 -->
          <view class="wc-top">
            <image v-if="cardImg" class="wc-img" :src="cardImg" mode="aspectFit" />
            <view v-else class="wc-img wc-img-empty"><text>🖼️</text></view>
            <view class="wc-info">
              <text class="wc-word">{{ vlSim.card.word }}</text>
              <text v-if="vlSim.card.phonetic" class="wc-phon">/{{ vlSim.card.phonetic }}/</text>
              <text v-if="vlSim.card.def_zh" class="wc-mean">{{ vlSim.card.def_zh }}</text>
            </view>
          </view>
          <!-- 例句 -->
          <view v-if="vlSim.card.example" class="wc-row">
            <text class="wc-tag">例句</text>
            <view class="wc-rowtext">
              <text class="wc-en">{{ vlSim.card.example }}</text>
              <text v-if="vlSim.card.example_zh" class="wc-zh">{{ vlSim.card.example_zh }}</text>
            </view>
          </view>
          <!-- 短语 -->
          <view v-if="vlSim.card.phrase" class="wc-row">
            <text class="wc-tag">短语</text>
            <view class="wc-rowtext">
              <text class="wc-en">{{ vlSim.card.phrase.en }}</text>
              <text v-if="vlSim.card.phrase.zh" class="wc-zh">{{ vlSim.card.phrase.zh }}</text>
            </view>
          </view>
          <!-- 单词发音 + 跟读:同一行 -->
          <view class="wc-btns">
            <view class="wc-btn" @tap="playVocabAudio" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-volume" style="width:30rpx;height:30rpx" /><text>单词发音</text></view>
            <view class="wc-btn primary" @tap="openVocabShadow" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-mic" style="width:30rpx;height:30rpx;filter:brightness(0) invert(1)" /><text>跟读</text><view v-if="!ent.can('vocab.shadow')" class="ic ic-lock" style="width:28rpx;height:28rpx;filter:brightness(0) invert(1)" /></view>
          </view>
        </scroll-view>

        <view class="modal-actions">
          <view class="modal-btn primary" @tap.stop="startVocabQuiz"><text>开始仿真练习 · 5 题</text></view>
          <view class="modal-btn ghost" @tap.stop="closeVocabCard"><text>完成</text></view>
        </view>
      </view>
    </view>

    <!-- 仿真练习 5 题(纯选择,复用 PracticeQuiz;5 题全对→判掌握)-->
    <PracticeQuiz
      v-if="vlQuizOpen && vlSim"
      :kp="vlSim.card.word"
      :questions="vlSim.questions"
      :recorder="vocabRecorder"
      last-label="查看结果"
      @close="onVocabQuizClose"
    />

    <!-- 跟读(会员专享)-->
    <ShadowModal :open="shadowOpen" :text="shadowText" :scorer="shadowScore"
      @close="shadowOpen = false" @paywall="onShadowPaywall" />
    <Paywall :open="showPaywall" :feature="ent.feature('vocab.shadow')" emoji="🎤"
      title="跟读评测是会员专享" @close="showPaywall = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getReviewQueue, getWrongCenterCounts, listWrongCenter, practiceWrongCenter, recordPracticeResult, getVocabSim, submitVocabSimResult, type WrongCenterItem, type WrongCenterCounts, type PracticeQuestion, type VocabSimPayload } from '@/api/wrongQuestions'
import { shadowScore } from '@/api/vocabulary'
import PracticeQuiz from '@/components/PracticeQuiz.vue'
import ShadowModal from '@/components/ShadowModal.vue'
import Paywall from '@/components/Paywall.vue'
import { useAuthStore } from '@/stores/auth'
import { useEntitlementsStore } from '@/stores/entitlements'

const auth = useAuthStore()
const ent = useEntitlementsStore()

// 练同类仿真题(可作答判分)
const pracOpen = ref(false)
const pracLoading = ref('')
const pracKp = ref('')
const pracWid = ref('')
const pracList = ref<PracticeQuestion[]>([])

async function practiceWrong(wq: WrongCenterItem) {
  if (pracLoading.value) return
  pracLoading.value = wq.id
  try {
    const r = await practiceWrongCenter(wq.id)
    if (!r.questions.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    pracKp.value = r.knowledge_point
    pracWid.value = wq.id
    pracList.value = r.questions
    pracOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '出题失败', icon: 'none' }) }
  finally { pracLoading.value = '' }
}
// 结算器:回写成绩(记 practice + 语法推进 SM-2),返回结果文案给组件展示
async function pracRecorder(total: number, correct: number): Promise<string> {
  const r = await recordPracticeResult(pracWid.value, total, correct)
  loadCounts()
  return r.just_mastered ? '🎉 恭喜，这道错题已掌握！' : `已计入巩固：本轮 ${correct}/${total} 正确`
}
function onPracClose() {
  pracOpen.value = false
  reload()
}

// ── 词汇错题「学这个词」:富词卡 + 仿真练习 5 题(纯选择,5 题全对→判掌握、进已掌握)──
const vlLoading = ref('')
const vlSim = ref<VocabSimPayload | null>(null)
const vlCardOpen = ref(false)     // 富词卡弹层
const vlQuizOpen = ref(false)     // 仿真练习 5 题(PracticeQuiz)
// 跟读(会员专享)
const shadowOpen = ref(false)
const shadowText = ref('')
const showPaywall = ref(false)

const cardImg = computed(() => {
  const imgs = vlSim.value?.card.image_urls
  return imgs && imgs.length ? imgs[0] : ''
})

async function learnVocab(wq: WrongCenterItem) {
  if (vlLoading.value) return
  vlLoading.value = wq.id
  try {
    vlSim.value = await getVocabSim(wq.id)   // 富卡(无媒体即时生成)+ 5 题(全局缓存复用)
    vlCardOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '打开失败', icon: 'none' }) }
  finally { vlLoading.value = '' }
}
function closeVocabCard() {
  vlCardOpen.value = false
  reload()   // 反映练习后状态
}
function startVocabQuiz() {
  if (!vlSim.value?.questions.length) { uni.showToast({ title: '暂无练习题', icon: 'none' }); return }
  vlCardOpen.value = false
  vlQuizOpen.value = true
}
// 仿真练习一轮结算:5 题全对 → 判掌握、进已掌握;返回结果文案给组件
async function vocabRecorder(total: number, correct: number): Promise<string> {
  if (!vlSim.value) return ''
  const r = await submitVocabSimResult(vlSim.value.wrong_record_id, total, correct)
  loadCounts()
  if (r.mastered) return '🎉 5 题全对，这个词已掌握！'
  return correct >= total ? '本轮全对，继续保持' : `本轮 ${correct}/${total} 正确，全对即掌握`
}
function onVocabQuizClose() {
  vlQuizOpen.value = false
  reload()
}
function playVocabAudio() {
  const url = vlSim.value?.card.audio_url
  if (!url) return
  const ctx = uni.createInnerAudioContext()
  ctx.src = url; ctx.play()
}
function openVocabShadow() {
  if (!ent.can('vocab.shadow')) { showPaywall.value = true; return }   // 跟读为会员专享
  shadowText.value = vlSim.value?.card.example || vlSim.value?.card.word || ''
  if (!shadowText.value) { uni.showToast({ title: '暂无可跟读内容', icon: 'none' }); return }
  shadowOpen.value = true
}
function onShadowPaywall() {
  shadowOpen.value = false
  showPaywall.value = true
}

// 点击错题来源 → 回到来源(整卷详情/作业详情);navigateTo 入栈,原生返回即「立即回来」
function goSource(wq: WrongCenterItem) {
  if (!wq.source_route) return
  uni.navigateTo({
    url: wq.source_route,
    fail: () => uni.showToast({ title: '来源已不可用', icon: 'none' }),
  })
}

// 今日复习到期数
const reviewDue = ref(0)
async function loadReviewDue() {
  try {
    const r = await getReviewQueue()
    reviewDue.value = (r.stats?.due_today || 0) + (r.stats?.new_unscheduled || 0)
  } catch { reviewDue.value = 0 }
}
function goReview() {
  uni.navigateTo({ url: '/pages/wrong-questions/review' })
}
onShow(() => { loadReviewDue(); if (items.value.length) reload() })

const items = ref<WrongCenterItem[]>([])
function cardText(wq: WrongCenterItem): string {
  return wq.stem || '错题（点击查看）'
}
function kindLabel(wq: WrongCenterItem): string {
  return wq.kp_kind === 'grammar' ? '语法' : wq.kp_kind === 'vocab' ? '词汇' : '错题'
}
function kindClass(wq: WrongCenterItem): string {
  return wq.kp_kind === 'grammar' ? 'k-gram' : wq.kp_kind === 'vocab' ? 'k-vocab' : 'k-none'
}
function kindIcon(wq: WrongCenterItem): string {
  return wq.kp_kind === 'grammar' ? 'ic-edit' : wq.kp_kind === 'vocab' ? 'ic-book' : 'ic-file'
}
// 来源展示名:整卷 → 我的作业
function sourceText(wq: WrongCenterItem): string {
  return wq.source_label === '整卷' ? '我的作业' : (wq.source_label || '错题')
}
// 状态 pill(三态)
function statusLabel(wq: WrongCenterItem): string {
  return wq.lifecycle === 'mastered' ? '已掌握' : wq.lifecycle === 'reviewing' ? '巩固中' : '待巩固'
}
function statusClass(wq: WrongCenterItem): string {
  return wq.lifecycle === 'mastered' ? 's-done' : wq.lifecycle === 'reviewing' ? 's-review' : 's-pending'
}
// 进度小字
function progressText(wq: WrongCenterItem): string {
  if (wq.lifecycle === 'mastered') return '已过关'
  if (wq.lifecycle === 'pending') return '还没开始巩固'
  if (wq.next_review_at) return `下次复习 ${dueText(wq.next_review_at)}`
  if (wq.practice_count > 0) return `已练 ${wq.practice_correct}/${wq.practice_count}`
  return '巩固中'
}
function dueText(d: string): string {
  const today = new Date(); today.setHours(0, 0, 0, 0)
  const t = new Date(d + 'T00:00:00')
  const diff = Math.round((t.getTime() - today.getTime()) / 86400000)
  if (diff <= 0) return '今天'
  if (diff === 1) return '明天'
  return d.slice(5)
}

const total = ref(0)
const loading = ref(false)
const skip = ref(0)
const LIMIT = 20
const hasMore = ref(true)
const kind = ref('')
const status = ref('')
const doneOpen = ref(false)
const counts = ref<WrongCenterCounts>({ all: 0, pending: 0, reviewing: 0, mastered: 0 })
const KIND_TABS = [
  { label: '全部', value: '' },
  { label: '语法', value: 'grammar' },
  { label: '词汇', value: 'vocab' },
]
const STATUS_TABS = computed(() => [
  { label: '全部', value: '', n: counts.value.all },
  { label: '待巩固', value: 'pending', n: counts.value.pending },
  { label: '巩固中', value: 'reviewing', n: counts.value.reviewing },
  { label: '已掌握', value: 'mastered', n: counts.value.mastered },
])
// 全部视图:未掌握正常列,已掌握折叠沉底
const activeItems = computed(() =>
  status.value === '' ? items.value.filter(i => i.lifecycle !== 'mastered') : items.value)
const doneItems = computed(() => items.value.filter(i => i.lifecycle === 'mastered'))
const showFold = computed(() => status.value === '' && counts.value.mastered > 0)

async function loadCounts() {
  try { counts.value = await getWrongCenterCounts(kind.value) } catch { /* 忽略 */ }
}

function reload() {
  items.value = []
  skip.value = 0
  hasMore.value = true
  doneOpen.value = false
  loadCounts()
  loadItems()
}

function switchKind(v: string) {
  if (kind.value === v) return
  kind.value = v
  status.value = ''
  reload()
}
function switchStatus(v: string) {
  if (status.value === v) return
  status.value = v
  items.value = []
  skip.value = 0
  hasMore.value = true
  loadItems()
}

onMounted(async () => {
  if (!auth.isLoggedIn()) {
    await auth.login()
  }
  await loadCounts()
  await loadItems()
})

async function loadItems() {
  if (loading.value) return
  loading.value = true
  try {
    const res = await listWrongCenter(kind.value, status.value, skip.value, LIMIT)
    items.value.push(...res.items)
    total.value = res.total
    hasMore.value = items.value.length < res.total
  } catch (e) {
    uni.showToast({ title: (e as Error).message, icon: 'error' })
  } finally {
    loading.value = false
  }
}

async function loadMore() {
  if (loading.value || !hasMore.value) return
  const nextSkip = skip.value + LIMIT
  skip.value = nextSkip
  try {
    await loadItems()
  } catch {
    skip.value = nextSkip - LIMIT
  }
}
</script>

<style scoped>
.list-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
/* 今日复习横幅 */
.review-banner {
  display: flex; align-items: center; justify-content: space-between;
  background: var(--g-hero); border-radius: var(--r-lg); padding: 28rpx 32rpx;
  margin-bottom: 24rpx; box-shadow: var(--shadow-primary);
}
.rb-left { display: flex; align-items: center; gap: 20rpx; }
.rb-icon { width: 52rpx; height: 52rpx; }
.rb-text { display: flex; flex-direction: column; gap: 4rpx; }
.rb-title { font-size: var(--fs-h2); font-weight: 800; color: var(--c-on-primary); }
.rb-sub { font-size: 22rpx; color: var(--c-on-primary); opacity: 0.9; }
.rb-arrow { font-size: 28rpx; font-weight: 700; color: var(--c-on-primary); white-space: nowrap; }
.center-tip { text-align: center; padding: 120rpx 0; color: var(--c-text-hint); font-size: 28rpx; }
.btn-sm {
  margin-top: 32rpx;
  background: var(--c-primary);
  color: var(--c-on-primary);
  font-size: 28rpx;
  font-weight: 700;
  border-radius: var(--r-btn);
}
.wq-list { display: flex; flex-direction: column; gap: 20rpx; }
.wq-card {
  background: var(--c-bg-card);
  border-radius: 24rpx;
  padding: 24rpx 26rpx;
  box-shadow: 0 6rpx 28rpx rgba(17, 24, 39, 0.05);
  display: flex; flex-direction: column; gap: 16rpx;
}
/* 顶部:类型徽章 + 来源 */
.wq-top { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.kind-badge {
  display: inline-flex; align-items: center; gap: 8rpx;
  height: 44rpx; padding: 0 18rpx; border-radius: 999rpx;
  font-size: 24rpx; font-weight: 700;
}
.kind-ic { width: 28rpx; height: 28rpx; }
.k-gram { background: #e8f1ff; color: #2f77e6; }
.k-vocab { background: #fff0e4; color: #f0821e; }
.k-none { background: var(--c-bg-soft); color: var(--c-text-second); }
.src-chip {
  font-size: 23rpx; color: var(--c-text-second);
  background: var(--c-bg-soft); padding: 7rpx 18rpx; border-radius: 999rpx;
  white-space: nowrap; flex-shrink: 0;
}
.src-link { background: #f0ecff; color: #6D28D9; font-weight: 600; }
/* 题干 */
.wq-stem {
  font-size: 30rpx; color: var(--c-ink); font-weight: 600; line-height: 1.5;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2;
  overflow: hidden; text-overflow: ellipsis;
}
/* 标签行 */
.wq-tags { display: flex; flex-wrap: wrap; gap: 10rpx; }
.mini-tag {
  font-size: 22rpx; color: var(--c-text-second); background: var(--c-bg-soft);
  padding: 5rpx 16rpx; border-radius: 999rpx;
}
.mini-kp { background: var(--c-primary-faint); color: var(--c-primary-deep); font-weight: 600; }
.mini-done { background: #e6f8ee; color: #18a058; font-weight: 600; }
/* 考点类型 mini-tag 上色(双类提高优先级,盖过 .mini-tag) */
.mini-tag.k-gram { background: #e8f1ff; color: #2f77e6; font-weight: 600; }
.mini-tag.k-vocab { background: #fff0e4; color: #f0821e; font-weight: 600; }
.mini-tag.k-none { background: var(--c-bg-soft); color: var(--c-text-second); }
/* 底部 */
.wq-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 2rpx; }
.prac-btn {
  display: inline-flex; align-items: center; gap: 8rpx;
  height: 58rpx; padding: 0 26rpx; border-radius: 999rpx;
  background: var(--c-primary-faint); color: var(--c-primary-deep);
  border: 2rpx solid var(--c-primary); font-size: 24rpx; font-weight: 700;
}
.prac-btn.loading { opacity: 0.6; }
.prac-ic { width: 26rpx; height: 26rpx; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 60; padding: 40rpx; }
.modal-card { width: 100%; max-width: 640rpx; max-height: 80vh; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.modal-head { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-score { font-size: 22rpx; color: var(--c-text-second); white-space: nowrap; }
.modal-x { width: 56rpx; height: 56rpx; display: flex; align-items: center; justify-content: center; font-size: 30rpx; color: var(--c-text-hint); flex-shrink: 0; }
.modal-body { flex: 1; margin: 16rpx 0; }
.muted { color: var(--c-text-hint); font-size: 24rpx; }
/* 逐题:进度 */
.pr-top { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; margin-top: 8rpx; }
.pr-idx { font-size: 24rpx; color: var(--c-text-second); font-weight: 600; white-space: nowrap; }
.pr-dots { display: flex; gap: 10rpx; flex-wrap: wrap; }
.pr-dot { width: 18rpx; height: 18rpx; border-radius: 50%; background: #dfe4ea; }
.pr-dot.cur { background: var(--c-primary); transform: scale(1.15); }
.pr-dot.ok { background: #18a058; }
.pr-dot.no { background: #e35b5b; }
/* 逐题:结果页 */
.pr-result { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 60rpx 0; gap: 16rpx; }
.pr-score { font-size: 72rpx; font-weight: 800; color: var(--c-primary); }
.pr-msg { font-size: 27rpx; color: var(--c-text-second); text-align: center; padding: 0 24rpx; line-height: 1.6; }
.opt-dim { opacity: 0.5; }
/* 练同类每题 */
.pq { padding: 18rpx 0; border-top: 2rpx solid #eef1f5; }
.pq:first-child { border-top: none; padding-top: 6rpx; }
.pq-stem { display: block; font-size: 27rpx; line-height: 1.6; color: var(--c-ink); font-weight: 600; }
.pq-opts { display: flex; flex-direction: column; gap: 12rpx; margin-top: 14rpx; }
.pq-opt { display: flex; align-items: center; gap: 14rpx; font-size: 26rpx; color: var(--c-ink); background: var(--c-bg-card); border: 2rpx solid var(--c-border); border-radius: 16rpx; padding: 18rpx 20rpx; line-height: 1.4; }
.opt-badge { flex-shrink: 0; width: 44rpx; height: 44rpx; border-radius: 50%; background: var(--c-bg-soft); color: var(--c-text-second); font-size: 24rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.opt-txt { flex: 1; }
.pq-opt.opt-correct { background: #e6f8ee; border-color: #18a058; color: #128a4c; font-weight: 600; }
.pq-opt.opt-correct .opt-badge { background: #18a058; color: #fff; }
.pq-opt.opt-wrong { background: #fdecec; border-color: #e35b5b; color: #c33; }
.pq-opt.opt-wrong .opt-badge { background: #e35b5b; color: #fff; }
.pq-fb { margin-top: 10rpx; }
.pq-fb .fb-ok { font-size: 24rpx; color: #128a4c; font-weight: 600; }
.pq-fb .fb-no { font-size: 24rpx; color: #c33; font-weight: 600; }
.pq-expl { display: block; margin-top: 8rpx; font-size: 23rpx; color: var(--c-text-second); line-height: 1.6; }
.modal-actions { display: flex; gap: 16rpx; }
.modal-btn { flex: 1; text-align: center; font-size: 27rpx; font-weight: 700; border-radius: 999rpx; padding: 16rpx; }
.modal-btn.ghost { background: var(--c-bg-soft); color: var(--c-text-second); }
.modal-btn.primary { background: var(--c-primary); color: #fff; }
.modal-btn.disabled { opacity: 0.5; }

/* 词汇学词双维进度 */
.vl-bars { display: flex; flex-direction: column; gap: 10rpx; margin: 14rpx 0 4rpx; }
.vl-bar { display: flex; align-items: center; gap: 12rpx; }
.vl-bar-l { font-size: 22rpx; color: var(--c-text-second); width: 56rpx; }
.vl-track { flex: 1; height: 14rpx; background: #eef1f5; border-radius: 999rpx; overflow: hidden; }
.vl-fill { height: 100%; border-radius: 999rpx; }
.vl-fill.recep { background: #3d8bf5; }
.vl-fill.prod { background: #ff8a3d; }
.vl-bar-n { font-size: 21rpx; color: var(--c-text-hint); width: 72rpx; text-align: right; }
.vl-bar-n.ok { color: #18a058; font-weight: 700; }
/* 单词卡 */
.vl-card { background: var(--c-bg-page); border-radius: 16rpx; padding: 20rpx; margin-bottom: 8rpx; }
.vl-word-row { display: flex; align-items: baseline; gap: 14rpx; }
.vl-word { font-size: 40rpx; font-weight: 800; color: var(--c-ink); }
.vl-phon { font-size: 24rpx; color: var(--c-text-second); }
.vl-audio { margin-left: auto; }
.vl-def { display: block; margin-top: 10rpx; font-size: 27rpx; color: var(--c-ink); }
.vl-eg { display: block; margin-top: 8rpx; font-size: 24rpx; color: var(--c-text-second); line-height: 1.5; }
/* 拼写 */
.vl-spell-input { margin-top: 12rpx; height: 76rpx; background: var(--c-bg-page); border: 2rpx solid var(--c-border); border-radius: 12rpx; padding: 0 20rpx; font-size: 28rpx; }
.vl-spell-btn { margin-top: 12rpx; text-align: center; background: var(--c-primary); color: #fff; font-size: 26rpx; font-weight: 700; border-radius: 999rpx; padding: 14rpx; }
.vl-spell-btn.disabled { opacity: 0.5; }
.src-tabs { display: flex; gap: 16rpx; padding: 16rpx 0 10rpx; }
.src-tab { padding: 10rpx 28rpx; background: var(--c-bg-card); border-radius: var(--r-pill); font-size: 26rpx; color: var(--c-text-second); }
.src-tab.active { background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; }

/* 状态子筛选 chip */
.status-scroll { width: 100%; margin-bottom: 8rpx; white-space: nowrap; }
.status-row { display: flex; flex-direction: row; gap: 12rpx; padding: 6rpx 0 10rpx; }
.status-chip {
  display: inline-flex; align-items: center; gap: 8rpx; flex-shrink: 0;
  padding: 8rpx 20rpx; border-radius: 999rpx; font-size: 24rpx;
  background: var(--c-bg-card); color: var(--c-text-second); border: 2rpx solid transparent;
}
.status-chip .chip-n { font-size: 20rpx; opacity: 0.7; }
.status-chip.active { font-weight: 700; }
.status-chip.active.all { background: #eef1f5; color: var(--c-ink); border-color: #d5dae2; }
.status-chip.active.pending { background: #fff0e4; color: #c96a12; border-color: #f0821e; }
.status-chip.active.reviewing { background: #e8f1ff; color: #185FA5; border-color: #3d8bf5; }
.status-chip.active.mastered { background: #e6f8ee; color: #128a4c; border-color: #18a058; }

/* 状态 pill */
.status-pill { font-size: 22rpx; font-weight: 700; padding: 4rpx 16rpx; border-radius: 999rpx; }
.s-pending { background: #fff0e4; color: #c96a12; }
.s-review { background: #e8f1ff; color: #185FA5; }
.s-done { background: #e6f8ee; color: #128a4c; }
/* 已掌握卡片灰显 */
.wq-card.is-done { opacity: 0.6; }
.wq-progress { color: var(--c-text-hint); font-size: 23rpx; }

/* 已掌握折叠区 */
.fold-bar { display: flex; align-items: center; justify-content: space-between; padding: 18rpx 24rpx; margin-top: 4rpx; background: var(--c-bg-card); border-radius: 16rpx; font-size: 25rpx; font-weight: 600; color: #128a4c; }
.fold-arrow { font-size: 23rpx; color: var(--c-text-second); font-weight: 400; }
.done-list { margin-top: 12rpx; display: flex; flex-direction: column; gap: 10rpx; }
.done-row { display: flex; align-items: center; gap: 14rpx; background: var(--c-bg-card); border-radius: 14rpx; padding: 16rpx 18rpx; opacity: 0.65; }
.done-stem { flex: 1; min-width: 0; font-size: 26rpx; color: var(--c-text-second); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.done-hint { text-align: center; font-size: 21rpx; color: var(--c-text-hint); padding: 8rpx 0; }
.wq-date { color: var(--c-text-hint); font-size: 24rpx; }
.load-more { text-align: center; padding: 32rpx; color: var(--c-text-second); font-size: 28rpx; }
.gray { color: var(--c-text-hint); }
/* 词汇错题「学这个词」富词卡(对齐词力通词卡) */
.wl-done { font-size: 22rpx; font-weight: 700; color: #1b7a3d; background: #d8f3dc; padding: 4rpx 16rpx; border-radius: 999rpx; }
.wc-top { display: flex; gap: 20rpx; padding-bottom: 20rpx; border-bottom: 1rpx solid var(--c-bg-soft); }
.wc-img { width: 300rpx; height: 280rpx; border-radius: 16rpx; flex-shrink: 0; background: var(--c-bg-soft); }
.wc-img-empty { display: flex; align-items: center; justify-content: center; font-size: 80rpx; opacity: .5; }
.wc-info { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 10rpx; min-width: 0; }
.wc-word { font-size: 52rpx; font-weight: 900; color: var(--c-ink); }
.wc-phon { font-size: 28rpx; color: var(--c-text-second); }
.wc-mean { font-size: 32rpx; color: var(--c-text-body); font-weight: 600; }
.wc-row { display: flex; gap: 16rpx; padding: 18rpx 0; border-bottom: 1rpx solid var(--c-bg-soft); }
.wc-tag { flex-shrink: 0; font-size: 22rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 5rpx 16rpx; border-radius: var(--r-pill); height: 34rpx; line-height: 34rpx; }
.wc-rowtext { flex: 1; display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.wc-en { font-size: 30rpx; color: var(--c-text-body); line-height: 1.5; }
.wc-zh { font-size: 24rpx; color: var(--c-text-hint); }
.wc-btns { display: flex; gap: 18rpx; margin: 24rpx 0 8rpx; }
.wc-btn { flex: 1; text-align: center; font-size: 28rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 16rpx 0; border-radius: var(--r-pill); }
.wc-btn.primary { background: var(--c-primary); color: var(--c-on-primary); }
</style>

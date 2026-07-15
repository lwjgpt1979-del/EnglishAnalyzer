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
      <view v-for="wq in activeItems" :key="wq.id" class="wq-card" :class="{ 'is-done': wq.lifecycle === 'mastered' }">
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

    <!-- 练同类仿真题 弹层(可作答判分) -->
    <view v-if="pracOpen" class="modal" @tap.self="pracOpen = false">
      <view class="modal-card">
        <view class="modal-head">
          <text class="modal-title">同类练习 · {{ pracKp }}</text>
          <text class="modal-score">已答 {{ answeredCount }}/{{ pracList.length }} · 对 {{ correctCount }}</text>
        </view>
        <scroll-view scroll-y class="modal-body">
          <view v-for="(q, i) in pracList" :key="q.id || i" class="pq">
            <text class="pq-stem">{{ i + 1 }}. {{ q.stem }}</text>
            <view v-if="q.options" class="pq-opts">
              <view
                v-for="(v, oi) in q.options"
                :key="oi"
                class="pq-opt"
                :class="optCls(q, v)"
                @tap="pickOpt(q, v)"
              >
                <text class="opt-badge">{{ letter(oi) }}</text>
                <text class="opt-txt">{{ optText(v) }}</text>
              </view>
            </view>
            <view v-if="pracState[q.id]" class="pq-fb">
              <text :class="pracState[q.id].correct ? 'fb-ok' : 'fb-no'">
                {{ pracState[q.id].correct ? '✓ 答对' : '✗ 答错，正确：' + q.answer }}
              </text>
              <text v-if="q.explanation" class="pq-expl">{{ q.explanation }}</text>
            </view>
          </view>
          <text v-if="!pracList.length" class="muted">未生成题目</text>
        </scroll-view>
        <view class="modal-actions">
          <view class="modal-btn ghost" @tap="pracOpen = false"><text>关闭</text></view>
          <view
            class="modal-btn primary"
            :class="{ disabled: answeredCount === 0 || pracSaving }"
            @tap="finishPractice"
          ><text>{{ pracSaving ? '保存中…' : '完成练习' }}</text></view>
        </view>
      </view>
    </view>

    <!-- 词汇错题「学这个词」词力通双维闭环 -->
    <view v-if="vlOpen && vl" class="modal" @tap.self="vlOpen = false">
      <view class="modal-card">
        <view class="modal-head">
          <text class="modal-title">学这个词</text>
          <text class="modal-score">接收 {{ pct(vlRecep) }}% · 产出 {{ pct(vlProd) }}%</text>
        </view>

        <!-- 双维进度条 -->
        <view class="vl-bars">
          <view class="vl-bar">
            <text class="vl-bar-l">接收</text>
            <view class="vl-track"><view class="vl-fill recep" :style="{ width: pct(vlRecep) + '%' }" /></view>
            <text class="vl-bar-n" :class="{ ok: vlRecep >= RECEP_θ }">{{ vlRecep >= RECEP_θ ? '达标' : pct(vlRecep) + '%' }}</text>
          </view>
          <view class="vl-bar">
            <text class="vl-bar-l">产出</text>
            <view class="vl-track"><view class="vl-fill prod" :style="{ width: pct(vlProd) + '%' }" /></view>
            <text class="vl-bar-n" :class="{ ok: vlProd >= RECEP_θ }">{{ vlProd >= RECEP_θ ? '达标' : pct(vlProd) + '%' }}</text>
          </view>
        </view>

        <scroll-view scroll-y class="modal-body">
          <!-- 单词卡 -->
          <view class="vl-card">
            <view class="vl-word-row">
              <text class="vl-word">{{ vl.word.word }}</text>
              <text v-if="vl.word.phonetic" class="vl-phon">/{{ vl.word.phonetic }}/</text>
              <view v-if="vl.word.audio_url" class="vl-audio" @tap="playWordAudio"><view class="ic ic-volume" style="width:30rpx;height:30rpx" /></view>
            </view>
            <text v-if="defZh()" class="vl-def">{{ defZh() }}</text>
            <text v-if="vl.word.examples && vl.word.examples.length" class="vl-eg">{{ vl.word.examples[0].en }}</text>
          </view>

          <!-- 接收探针 -->
          <view v-for="probe in vl.recep_probes" :key="probe.key" class="pq">
            <text class="pq-stem">{{ probe.prompt }}</text>
            <view class="pq-opts">
              <view
                v-for="(opt, oi) in probe.options"
                :key="oi"
                class="pq-opt"
                :class="receptCls(probe, opt)"
                @tap="pickRecep(probe, opt)"
              >{{ opt }}</view>
            </view>
          </view>

          <!-- 拼写产出 -->
          <view class="pq">
            <text class="pq-stem">{{ vl.spell_prompt }}</text>
            <input
              class="vl-spell-input"
              :value="vlSpellInput"
              :disabled="!!vlSpellDone"
              placeholder="拼出这个单词"
              @input="vlSpellInput = $event.detail.value"
            />
            <view v-if="!vlSpellDone" class="vl-spell-btn" :class="{ disabled: !vlSpellInput.trim() || vlSaving }" @tap="submitSpell">
              <text>{{ vlSaving ? '判分中…' : '提交拼写' }}</text>
            </view>
            <view v-else class="pq-fb">
              <text :class="vlSpellDone.correct ? 'fb-ok' : 'fb-no'">
                {{ vlSpellDone.correct ? '✓ 拼对' : '✗ 拼错，正确：' + vlSpellDone.answer }}
              </text>
            </view>
          </view>
        </scroll-view>

        <view class="modal-actions">
          <view class="modal-btn ghost" @tap="vlOpen = false"><text>完成</text></view>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getReviewQueue, getWrongCenterCounts, listWrongCenter, practiceWrongCenter, recordPracticeResult, getVocabLearn, submitVocabRecep, submitVocabSpell, type WrongCenterItem, type WrongCenterCounts, type PracticeQuestion, type VocabLearnPayload, type VocabProbe } from '@/api/wrongQuestions'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

// 练同类仿真题(可作答判分)
const pracOpen = ref(false)
const pracLoading = ref('')
const pracKp = ref('')
const pracWid = ref('')
const pracList = ref<PracticeQuestion[]>([])
const pracState = reactive<Record<string, { picked: string; correct: boolean }>>({})
const pracSaving = ref(false)
const answeredCount = computed(() => Object.keys(pracState).length)
const correctCount = computed(() => Object.values(pracState).filter(s => s.correct).length)
const letter = (i: number) => String.fromCharCode(65 + i)

async function practiceWrong(wq: WrongCenterItem) {
  if (pracLoading.value) return
  pracLoading.value = wq.id
  try {
    const r = await practiceWrongCenter(wq.id)
    pracKp.value = r.knowledge_point
    pracWid.value = wq.id
    pracList.value = r.questions
    Object.keys(pracState).forEach(k => delete pracState[k])
    pracOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '出题失败', icon: 'none' }) }
  finally { pracLoading.value = '' }
}
function pickOpt(q: PracticeQuestion, opt: string) {
  if (pracState[q.id]) return   // 已作答锁定
  pracState[q.id] = { picked: opt, correct: (q.answer || '').trim() === opt.trim() }
}
function optCls(q: PracticeQuestion, opt: string): string {
  const st = pracState[q.id]
  if (!st) return ''
  if ((q.answer || '').trim() === opt.trim()) return 'opt-correct'
  if (st.picked === opt) return 'opt-wrong'
  return ''
}
// 去掉选项自带的「A. 」前缀,统一用左侧字母徽章展示
function optText(v: string): string {
  return (v || '').replace(/^\s*[A-Da-d][.、)]\s*/, '')
}
async function finishPractice() {
  if (pracSaving.value || answeredCount.value === 0) return
  pracSaving.value = true
  try {
    const r = await recordPracticeResult(pracWid.value, answeredCount.value, correctCount.value)
    uni.showToast({
      title: r.just_mastered ? '🎉 已掌握！' : `本轮 ${correctCount.value}/${answeredCount.value}，已进入巩固`,
      icon: 'none',
    })
    pracOpen.value = false
    reload()
  } catch (e: any) {
    uni.showToast({ title: e?.message || '保存失败', icon: 'none' })
  } finally { pracSaving.value = false }
}

// ── 词汇错题「学这个词」词力通双维闭环(P3)──
const vlOpen = ref(false)
const vlLoading = ref('')
const vlSaving = ref(false)
const vl = ref<VocabLearnPayload | null>(null)
const vlProbeState = reactive<Record<string, { picked: string; correct: boolean; answer: string }>>({})
const vlSpellInput = ref('')
const vlSpellDone = ref<{ correct: boolean; answer: string } | null>(null)
const vlRecep = ref(0)
const vlProd = ref(0)
const RECEP_θ = 0.85
const pct = (x: number) => Math.min(100, Math.round(x * 100))

async function learnVocab(wq: WrongCenterItem) {
  if (vlLoading.value) return
  vlLoading.value = wq.id
  try {
    const p = await getVocabLearn(wq.id)
    vl.value = p
    vlRecep.value = p.recep; vlProd.value = p.prod
    Object.keys(vlProbeState).forEach(k => delete vlProbeState[k])
    vlSpellInput.value = ''; vlSpellDone.value = null
    vlOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '打开失败', icon: 'none' }) }
  finally { vlLoading.value = '' }
}
function defZh(): string {
  const d = vl.value?.word.definitions
  if (Array.isArray(d) && d.length && typeof d[0] === 'object') return d[0].zh || d[0].en || ''
  return ''
}
async function pickRecep(probe: VocabProbe, opt: string) {
  if (!vl.value || vlProbeState[probe.key]) return
  try {
    const r = await submitVocabRecep(vl.value.wrong_record_id, probe.key, opt)
    vlProbeState[probe.key] = { picked: opt, correct: r.correct, answer: r.correct_answer }
    vlRecep.value = r.recep; vlProd.value = r.prod
    afterVocab(r.just_mastered)
  } catch (e: any) { uni.showToast({ title: e?.message || '提交失败', icon: 'none' }) }
}
function receptCls(probe: VocabProbe, opt: string): string {
  const st = vlProbeState[probe.key]
  if (!st) return ''
  if (opt === st.answer) return 'opt-correct'
  if (st.picked === opt) return 'opt-wrong'
  return ''
}
async function submitSpell() {
  if (!vl.value || vlSaving.value || vlSpellDone.value || !vlSpellInput.value.trim()) return
  vlSaving.value = true
  try {
    const r = await submitVocabSpell(vl.value.wrong_record_id, vlSpellInput.value.trim())
    vlSpellDone.value = { correct: r.correct, answer: r.correct_answer }
    vlRecep.value = r.recep; vlProd.value = r.prod
    afterVocab(r.just_mastered)
  } catch (e: any) { uni.showToast({ title: e?.message || '提交失败', icon: 'none' }) }
  finally { vlSaving.value = false }
}
function afterVocab(justMastered: boolean) {
  loadCounts()
  if (justMastered) {
    uni.showToast({ title: '🎉 这个词已掌握！', icon: 'none' })
    setTimeout(() => { vlOpen.value = false; reload() }, 900)
  }
}
function playWordAudio() {
  const url = vl.value?.word.audio_url
  if (!url) return
  const ctx = uni.createInnerAudioContext()
  ctx.src = url; ctx.play()
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
.modal-head { display: flex; align-items: baseline; justify-content: space-between; gap: 12rpx; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-score { font-size: 22rpx; color: var(--c-text-second); white-space: nowrap; }
.modal-body { flex: 1; margin: 16rpx 0; }
.muted { color: var(--c-text-hint); font-size: 24rpx; }
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
</style>

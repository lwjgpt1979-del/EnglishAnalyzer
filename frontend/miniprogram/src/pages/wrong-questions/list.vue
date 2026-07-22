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

    <!-- 来源 tab(纯按来源) -->
    <scroll-view class="src-scroll" scroll-x enhanced>
      <view class="src-row">
        <text v-for="t in SOURCE_TABS" :key="t.value" class="src-tab" :class="{ active: source === t.value }" @tap="switchSource(t.value)">{{ t.label }}</text>
      </view>
    </scroll-view>

    <!-- 真实错题侧:副筛选 + 视图切换 + 折叠分组卡 -->
    <template v-if="source !== 'practice' && source !== 'ls'">
      <!-- 状态筛选(未/巩固中/已巩固,复用 SM-2 生命周期) -->
      <view class="ls2-tabs">
        <text v-for="t in RSTATUS_TABS" :key="t.v" class="ls2-tab" :class="{ on: rstatus === t.v }" @tap="switchRStatus(t.v)">{{ t.label }}</text>
      </view>
      <view class="ctrl-row">
        <view class="kind-chips">
          <text v-for="k in KIND_TABS" :key="k.value" class="kind-chip" :class="{ active: kind === k.value }" @tap="switchKind(k.value)">{{ k.label }}</text>
        </view>
        <view class="view-seg">
          <text class="view-t" :class="{ on: view === 'kp' }" @tap="switchView('kp')">按考点</text>
          <text class="view-t" :class="{ on: view === 'batch' }" @tap="switchView('batch')">按批次</text>
        </view>
      </view>

      <view v-if="groupsLoading && !groups.length" class="center-tip">加载中…</view>
      <view v-else-if="!groupsLoading && !groups.length" class="center-tip">
        <text>该状态下暂无错题</text>
        <button v-if="!rstatus" class="btn-sm" @tap="() => uni.navigateTo({ url: '/pages/user-papers/upload' })">上传作业</button>
      </view>

      <!-- 时间分段(本周/2-4周/更早)→ 折叠分组卡(进度即底色) -->
      <template v-else>
      <block v-for="b in LS_BUCKETS" :key="b.v">
      <template v-if="groupsInBucket(b.v).length">
      <view class="ls2-sec" :class="b.v">{{ b.label }}<text v-if="b.v === 'old'" class="ls2-badge">超1周未巩固</text></view>
      <view class="grp-list">
        <view v-for="g in groupsInBucket(b.v)" :key="groupKey(g)" class="grp">
          <view class="grp-head" @tap="toggleGroup(g)">
            <view class="grp-fill" :style="{ width: (g.rate * 100) + '%' }" />
            <view class="grp-in">
              <text class="grp-name">{{ groupTitle(g) }}</text>
              <text class="grp-cnt">错{{ g.count }}</text>
              <text class="grp-rate">{{ g.mastered }}/{{ g.count }} 掌握</text>
              <text class="grp-chev">{{ openGroups[groupKey(g)] ? '▾' : '›' }}</text>
            </view>
          </view>
          <!-- 展开:该组错题(点行进详情;快捷练同类/学词) -->
          <view v-if="openGroups[groupKey(g)]" class="grp-sub">
            <view v-if="!groupItems[groupKey(g)]" class="sub-tip">加载中…</view>
            <template v-else>
              <view v-for="wq in groupItems[groupKey(g)]" :key="wq.id" class="qrow" :class="{ done: wq.lifecycle === 'mastered' }"
                @tap="() => uni.navigateTo({ url: '/pages/wrong-questions/detail?id=' + wq.id })">
                <view class="qdot" :class="statusClass(wq)" />
                <view class="qbody">
                  <text class="qstem">{{ cardText(wq) }}</text>
                  <view class="qtags">
                    <text class="mini-tag" :class="kindClass(wq)">{{ kindLabel(wq) }}</text>
                    <text v-if="wq.kp_name" class="mini-tag mini-kp">{{ wq.kp_name }}</text>
                  </view>
                </view>
                <view v-if="wq.kp_kind === 'vocab'" class="qgo" :class="{ loading: vlLoading === wq.id }" @tap.stop="learnVocab(wq)">{{ vlLoading === wq.id ? '…' : '学词' }}</view>
                <view v-else class="qgo" :class="{ loading: pracLoading === wq.id }" @tap.stop="practiceWrong(wq)">{{ pracLoading === wq.id ? '…' : '练同类' }}</view>
              </view>
            </template>
          </view>
        </view>
      </view>
      </template>
      </block>
      </template>
    </template>

    <!-- 长难句薄弱侧:时间线诊断(本周/2-4周/更早 · 状态tab · 四类错误徽章 · 展开四分区)-->
    <template v-else-if="source === 'ls'">
      <view class="ls2-tabs">
        <text v-for="t in LS_STATUS" :key="t.v" class="ls2-tab" :class="{ on: lsStatus === t.v }" @tap="lsStatus = t.v">{{ t.label }} {{ lsCount(t.v) }}</text>
      </view>
      <view v-if="lsLoading && !lsDiag.length" class="center-tip">加载中…</view>
      <view v-else-if="!lsFiltered.length" class="center-tip"><text>暂无长难句诊断 🎯</text></view>
      <template v-else>
        <block v-for="b in LS_BUCKETS" :key="b.v">
          <template v-if="bucketItems(b.v).length">
            <view class="ls2-sec" :class="b.v">{{ b.label }}<text v-if="b.v === 'old'" class="ls2-badge">超1周未巩固</text></view>
            <view class="ls2-tl">
              <view v-for="(d, di) in bucketItems(b.v)" :key="di" class="ls2-node">
                <view class="ls2-dot" :class="d.status" />
                <view class="ls2-card" :class="d.status" @tap="toggleDiag(d)">
                  <view class="ls2-fill" :style="{ width: (d.status === 'done' ? 100 : d.mastery) + '%' }" />
                  <view class="ls2-in">
                    <view class="ls2-top">
                      <text class="ls2-sent">{{ d.sentence }}</text>
                      <text v-if="d.status === 'done'" class="ls2-ck">✓</text>
                      <text v-else class="ls2-pct" :class="d.status">{{ d.mastery }}%</text>
                    </view>
                    <view class="ls2-kinds">
                      <text v-for="c in d.cats" :key="c.cat" class="ls2-kb" :class="[catCls(c.cat), { zero: !c.count }]">{{ c.cat }} {{ c.count ? '错' + c.count : '✓' }}</text>
                    </view>
                    <view class="ls2-meta"><text class="ls2-st" :class="d.status">{{ statusLabel2(d.status) }}</text> · {{ d.date }}</view>
                    <template v-if="openDiag[diagKey(d)]">
                      <view v-for="c in d.cats" :key="'e' + c.cat" class="ls2-grp">
                        <view class="ls2-gh"><text class="ls2-gt" :class="catCls(c.cat)">{{ c.cat }}</text><text class="ls2-gs">{{ c.count ? '错' + c.count : '全对 ✓' }}</text><text class="ls2-grp-rp" @tap.stop="diagRetrain(d, c.cat)">重练 ›</text></view>
                        <view v-if="c.items.length" class="ls2-items">
                          <text v-for="(it, ii) in c.items" :key="ii" class="ls2-it" :class="it.ok ? 'ok' : 'err'">{{ it.role }}{{ it.ok ? '✓' : ' 错' + it.wrong }}</text>
                        </view>
                        <text v-else class="ls2-empty">暂无记录</text>
                      </view>
                    </template>
                  </view>
                </view>
              </view>
            </view>
          </template>
        </block>
      </template>
    </template>

    <!-- 练习巩固侧:练习衍生薄弱项(词·维聚合,连对 N 次清除) -->
    <template v-else>
      <view class="prac-banner"><text>来自「考点扩展测试」里答错的薄弱考点,单独存放、不计入真实错题。连对练熟即消失。</text></view>
      <view v-if="consolLoading && !consol.length" class="center-tip">加载中…</view>
      <view v-else-if="!consolGroups.length" class="center-tip"><text>暂无练习巩固项 🎯</text></view>
      <view v-else class="grp-list">
        <!-- 词折叠头(底色=整体练熟度)+ 逐维行 -->
        <view v-for="g in consolGroups" :key="g.word_id" class="pfold">
          <view class="pf-head" @tap="toggleWord(g.word_id)">
            <view class="pf-fill" :style="{ width: g.rate + '%' }" />
            <view class="pf-in">
              <text class="pf-word">{{ g.word }}</text>
              <text class="pf-meta">{{ g.dims.length }} 维待练 · 错{{ g.miss }}</text>
              <view class="pf-retrain" :class="{ loading: rpLoading === g.word_id }" @tap.stop="retrainAll(g)">{{ rpLoading === g.word_id ? '出题中…' : '重练全部 · ' + g.dims.length + '题' }}</view>
              <text class="pf-chev">{{ openWords[g.word_id] ? '▾' : '›' }}</text>
            </view>
          </view>
          <template v-if="openWords[g.word_id]">
            <view v-for="it in g.dims" :key="it.id" class="pf-row">
              <text class="pf-tag">练习衍生</text>
              <text class="pf-dim">{{ it.dim_label }}</text>
              <text class="pf-cnt">错{{ it.miss_count }}</text>
              <view class="pf-dots">
                <view v-for="n in it.master_n" :key="n" class="pc-dot" :class="{ on: n <= it.streak }" />
              </view>
              <text class="pf-rp" :class="{ loading: rpLoading === it.id }" @tap.stop="retrain(it)">{{ rpLoading === it.id ? '…' : '重练 ›' }}</text>
            </view>
          </template>
        </view>
      </view>
    </template>

    <!-- 重练该维(逐题回传:错→回增本条/对→连对+1达2清除) -->
    <PracticeQuiz v-if="rpOpen" kp="重练该维" :questions="rpQs" @finishDetail="onRpDetail" @close="onRpClose" />

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
import { computed, onMounted, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import { getReviewQueue, getWrongGrouped, getConsolidation, getLsConsolidation, listWrongCenter, practiceWrongCenter, recordPracticeResult, getVocabSim, submitVocabSimResult, type WrongCenterItem, type WrongGroup, type WrongListQuery, type ConsolidationItem, type LsConsolItem, type LsDim, type PracticeQuestion, type VocabSimPayload } from '@/api/wrongQuestions'
import { getLsDiagnostics, type LsDiag } from '@/api/longSentence'
import { shadowScore, getKpTest, recordKpPractice } from '@/api/vocabulary'
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

// 今日复习到期数(待复习优先条)
const reviewDue = ref(0)
async function loadReviewDue() {
  try {
    const r = await getReviewQueue()
    reviewDue.value = (r.stats?.due_today || 0) + (r.stats?.new_unscheduled || 0)
  } catch { reviewDue.value = 0 }
}
function goReview() { uni.navigateTo({ url: '/pages/wrong-questions/review' }) }

// 卡片文案助手
function cardText(wq: WrongCenterItem): string { return wq.stem || '错题（点击查看）' }
function kindLabel(wq: WrongCenterItem): string { return wq.kp_kind === 'grammar' ? '语法' : wq.kp_kind === 'vocab' ? '词汇' : '错题' }
function kindClass(wq: WrongCenterItem): string { return wq.kp_kind === 'grammar' ? 'k-gram' : wq.kp_kind === 'vocab' ? 'k-vocab' : 'k-none' }
function statusClass(wq: WrongCenterItem): string { return wq.lifecycle === 'mastered' ? 's-done' : wq.lifecycle === 'reviewing' ? 's-review' : 's-pending' }

// —— 来源 tab(纯按来源)+ 副筛选(语法/词汇)+ 视图(按考点/按批次) ——
// 上传的一律是作业(已无真题上传;历史「整卷」已洗为「作业」)
// 长难句薄弱(value=ls)= 探针练习衍生句卡;练习巩固(词)= 考点扩展练习衍生词卡
const SOURCE_TABS = [
  { label: '作业错题', value: '作业' },
  { label: '长难句薄弱', value: 'ls' },
  { label: '平台错题', value: '平台' },
  { label: '练习巩固(词)', value: 'practice' },
]
const KIND_TABS = [
  { label: '全部', value: '' },
  { label: '语法', value: 'grammar' },
  { label: '词汇', value: 'vocab' },
]
const source = ref('作业')
const kind = ref('')
const view = ref<'kp' | 'batch'>('kp')

const groups = ref<WrongGroup[]>([])
const groupsLoading = ref(false)
const openGroups = reactive<Record<string, boolean>>({})
const groupItems = reactive<Record<string, WrongCenterItem[]>>({})
// 状态筛选(未/巩固中/已巩固,复用 SM-2)+ 时间分段(本周/2-4周/更早)
const RSTATUS_TABS = [{ v: '', label: '全部' }, { v: 'pending', label: '未巩固' }, { v: 'reviewing', label: '巩固中' }, { v: 'mastered', label: '已巩固' }] as const
const rstatus = ref<'' | 'pending' | 'reviewing' | 'mastered'>('')
function switchRStatus(v: string) { if (rstatus.value === v) return; rstatus.value = v as any; loadGroups() }
function groupsInBucket(b: string) { return groups.value.filter(g => (g.bucket || 'old') === b) }

function groupKey(g: WrongGroup): string { return view.value === 'kp' ? (g.kp || '未分类') : (g.source_id || '') }
function groupTitle(g: WrongGroup): string {
  if (view.value === 'kp') return g.kp || '未分类'
  const d = g.last_at ? g.last_at.slice(5, 10).replace('-', '月') + '日' : ''
  return `${d} ${source.value === '作业' ? '作业卷' : source.value}`.trim()
}

async function loadGroups() {
  groupsLoading.value = true
  try {
    const r = await getWrongGrouped(view.value, source.value, kind.value, rstatus.value)
    groups.value = r.groups
  } catch { groups.value = [] } finally { groupsLoading.value = false }
  for (const k in openGroups) delete openGroups[k]   // 折叠态清空,重新展开再拉
  for (const k in groupItems) delete groupItems[k]
}
async function toggleGroup(g: WrongGroup) {
  const key = groupKey(g)
  openGroups[key] = !openGroups[key]
  if (openGroups[key] && !groupItems[key]) {
    try {
      const q: WrongListQuery = { sourceLabel: source.value, kind: kind.value, status: rstatus.value, limit: 100 }
      if (view.value === 'kp') q.kpName = g.kp
      else q.sourceId = g.source_id
      const res = await listWrongCenter(q)
      groupItems[key] = res.items
    } catch { groupItems[key] = [] }
  }
}
function loadForSource() {
  if (source.value === 'practice') loadConsolidation()
  else if (source.value === 'ls') loadLsConsol()
  else loadGroups()
}
function switchSource(v: string) { if (source.value === v) return; source.value = v; loadForSource() }
function switchKind(v: string) { if (kind.value === v) return; kind.value = v; loadGroups() }
function switchView(v: 'kp' | 'batch') { if (view.value === v) return; view.value = v; loadGroups() }
function reload() { loadForSource() }   // 练同类/学词/重练后回刷

// —— 长难句薄弱 tab(时间线诊断:状态tab + 本周/2-4周/更早 + 四类徽章卡 + 展开四分区)——
const LS_STATUS = [{ v: 'all', label: '全部' }, { v: 'no', label: '未巩固' }, { v: 'ing', label: '巩固中' }, { v: 'done', label: '已巩固' }] as const
const LS_BUCKETS = [{ v: 'week', label: '本周' }, { v: 'mid', label: '2-4周' }, { v: 'old', label: '更早' }] as const
const lsDiag = ref<LsDiag[]>([])
const lsLoading = ref(false)
const lsStatus = ref<'all' | 'no' | 'ing' | 'done'>('all')
const openDiag = reactive<Record<string, boolean>>({})
function diagKey(d: LsDiag) { return d.sentence }
function toggleDiag(d: LsDiag) { const k = diagKey(d); openDiag[k] = !openDiag[k] }
const lsFiltered = computed(() => lsStatus.value === 'all' ? lsDiag.value : lsDiag.value.filter(d => d.status === lsStatus.value))
function bucketItems(b: string) { return lsFiltered.value.filter(d => d.bucket === b) }
function lsCount(v: string) { return v === 'all' ? lsDiag.value.length : lsDiag.value.filter(d => d.status === v).length }
function statusLabel2(s: string) { return s === 'done' ? '已巩固' : s === 'ing' ? '巩固中' : '未巩固' }
function catCls(cat: string) { return cat === '成分' ? 'kc-comp' : cat === '合成' ? 'kc-asm' : cat === '语法' ? 'kc-gram' : 'kc-word' }
async function loadLsConsol() {
  lsLoading.value = true
  try { lsDiag.value = (await getLsDiagnostics()).items } catch { lsDiag.value = [] } finally { lsLoading.value = false }
}
// 重练:成分/合成/语法 → 精读闯关(答题即经 hook 回写细分诊断);重点词 → 学本句词(词力通式)
function diagRetrain(d: LsDiag, cat: string) {
  if (!d.sentence) return
  const url = cat === '重点词'
    ? `/pages/vocabulary/index?source=sentence&text=${encodeURIComponent(d.sentence)}`
    : `/pages/user-papers/sentence?text=${encodeURIComponent(d.sentence)}`
  uni.navigateTo({ url })
}

// —— 练习巩固 tab(练习衍生薄弱项,按词折叠 + 逐维行,连对 N 次清除)——
const consol = ref<ConsolidationItem[]>([])
const consolLoading = ref(false)
const openWords = reactive<Record<string, boolean>>({})
function toggleWord(wid: string) { openWords[wid] = !openWords[wid] }
// 按词聚合:每词一折叠块,底色=整体练熟度(总连对 / (维数×N))
interface ConsolGroup { word_id: string; word: string; dims: ConsolidationItem[]; miss: number; streak: number; master_n: number; rate: number }
const consolGroups = computed<ConsolGroup[]>(() => {
  const m = new Map<string, ConsolGroup>()
  for (const it of consol.value) {
    const key = it.word_id || it.kp_name || it.id
    if (!m.has(key)) m.set(key, { word_id: key, word: it.word || (it.kp_name || '').split('·')[0] || '词', dims: [], miss: 0, streak: 0, master_n: it.master_n, rate: 0 })
    const g = m.get(key)!; g.dims.push(it); g.miss += it.miss_count; g.streak += it.streak
  }
  const arr = [...m.values()]
  arr.forEach(g => { const denom = g.dims.length * (g.master_n || 2); g.rate = denom ? Math.round((g.streak / denom) * 100) : 0 })
  return arr
})
async function loadConsolidation() {
  consolLoading.value = true
  try {
    consol.value = (await getConsolidation()).items
    const first = consol.value[0]?.word_id   // 默认展开第一个词(不覆盖用户手动折叠)
    if (first && Object.keys(openWords).length === 0) openWords[first] = true
  } catch { consol.value = [] } finally { consolLoading.value = false }
}
// 重练(该维一套 / 全部薄弱维各一题)→ 逐题回传(错→回增本条/对→连对+1达2清除)
const rpOpen = ref(false)
const rpLoading = ref('')
const rpWid = ref('')
const rpQs = ref<Array<{ id: string; stem: string; options: string[]; answer: string; explanation: string }>>([])
const rpDimMap = new Map<string, { dim: string; stem: string }>()
async function retrain(it: ConsolidationItem) {
  if (!it.word_id || rpLoading.value) return
  rpLoading.value = it.id
  try {
    const qs = await getKpTest(it.word_id, undefined, it.dim)
    if (!qs.length) { uni.showToast({ title: '暂无该维题目', icon: 'none' }); return }
    rpWid.value = it.word_id
    rpDimMap.clear()
    qs.forEach(q => rpDimMap.set(q.id, { dim: q.dimension, stem: q.stem }))
    rpQs.value = qs.map(q => ({ id: q.id, stem: `【${q.dimension_label}】${q.stem}`, options: q.options, answer: q.answer, explanation: q.explanation }))
    rpOpen.value = true
  } catch { uni.showToast({ title: '出题失败,稍后重试', icon: 'none' }) } finally { rpLoading.value = '' }
}
// 重练全部薄弱维:该词各薄弱维各抽 1 题混成一套(逐题按 dimension 回传,各维连对独立累计)
async function retrainAll(g: ConsolGroup) {
  if (!g.word_id || rpLoading.value) return
  rpLoading.value = g.word_id
  try {
    const qs = await getKpTest(g.word_id)   // 每维一题(全维)
    const weak = new Set(g.dims.map(d => d.dim))
    const pick = qs.filter(q => weak.has(q.dimension))
    if (!pick.length) { uni.showToast({ title: '暂无题目', icon: 'none' }); return }
    rpWid.value = g.word_id
    rpDimMap.clear()
    pick.forEach(q => rpDimMap.set(q.id, { dim: q.dimension, stem: q.stem }))
    rpQs.value = pick.map(q => ({ id: q.id, stem: `【${q.dimension_label}】${q.stem}`, options: q.options, answer: q.answer, explanation: q.explanation }))
    rpOpen.value = true
  } catch { uni.showToast({ title: '出题失败,稍后重试', icon: 'none' }) } finally { rpLoading.value = '' }
}
async function onRpDetail(results: Array<{ id: string; correct: boolean }>) {
  const payload = results
    .map(r => ({ ...rpDimMap.get(r.id), correct: r.correct }))
    .filter((p): p is { dim: string; stem: string; correct: boolean } => !!p.dim)
    .map(p => ({ dim: p.dim, correct: p.correct, stem: p.stem }))
  if (payload.length && rpWid.value) { try { await recordKpPractice(rpWid.value, payload) } catch { /* 静默 */ } }
}
function onRpClose() { rpOpen.value = false; loadConsolidation() }

onShow(() => { loadReviewDue(); if (source.value === 'practice') { if (consol.value.length) loadConsolidation() } else if (source.value === 'ls') { loadLsConsol() } else if (groups.value.length) loadGroups() })
onMounted(async () => {
  if (!auth.isLoggedIn()) await auth.login()
  await loadReviewDue()
  await loadGroups()
})
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

/* P2 来源 tab(横滑)+ 副筛选 + 视图切换 */
.src-scroll { width: 100%; white-space: nowrap; margin-bottom: 4rpx; }
.src-row { display: flex; flex-direction: row; gap: 16rpx; padding: 12rpx 0 10rpx; }
.src-row .src-tab { flex-shrink: 0; }
.ctrl-row { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; margin-bottom: 16rpx; }
.kind-chips { display: flex; gap: 10rpx; }
.kind-chip { font-size: 23rpx; padding: 6rpx 20rpx; border-radius: var(--r-pill); background: var(--c-bg-card); color: var(--c-text-second); }
.kind-chip.active { background: var(--c-primary-faint); color: var(--c-primary-deep); font-weight: 700; }
.view-seg { display: flex; background: var(--c-bg-soft); border-radius: var(--r-pill); padding: 4rpx; }
.view-t { font-size: 23rpx; padding: 6rpx 20rpx; border-radius: var(--r-pill); color: var(--c-text-second); }
.view-t.on { background: var(--c-bg-card); color: var(--c-primary-deep); font-weight: 700; }

/* 折叠分组卡:进度即底色 */
.grp-list { display: flex; flex-direction: column; gap: 16rpx; }
.grp { background: var(--c-bg-card); border-radius: 20rpx; overflow: hidden; box-shadow: 0 4rpx 20rpx rgba(17, 24, 39, 0.04); }
.grp-head { position: relative; overflow: hidden; }
.grp-fill { position: absolute; left: 0; top: 0; bottom: 0; background: linear-gradient(90deg, #e9f6f1, #f4fbf8); transition: width .3s; }
.grp-in { position: relative; display: flex; align-items: center; gap: 14rpx; padding: 26rpx 26rpx; }
.grp-name { font-size: 30rpx; font-weight: 800; color: var(--c-ink); flex-shrink: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.grp-cnt { font-size: 21rpx; font-weight: 700; color: #c33; background: #fdecec; padding: 3rpx 14rpx; border-radius: 999rpx; flex-shrink: 0; }
.grp-rate { margin-left: auto; font-size: 24rpx; font-weight: 800; color: #2fa98a; flex-shrink: 0; }
.grp-chev { font-size: 26rpx; color: var(--c-text-hint); flex-shrink: 0; }

/* 展开:该组错题行 */
.grp-sub { padding: 4rpx 20rpx 12rpx; border-top: 2rpx dashed var(--c-bg-soft); }
.sub-tip { text-align: center; color: var(--c-text-hint); font-size: 24rpx; padding: 20rpx 0; }
.qrow { display: flex; align-items: center; gap: 14rpx; padding: 18rpx 6rpx; border-bottom: 2rpx solid #f4f6f9; }
.qrow:last-child { border-bottom: none; }
.qrow.done { opacity: 0.55; }
.qdot { width: 14rpx; height: 14rpx; border-radius: 50%; flex-shrink: 0; }
.qdot.s-pending { background: #f0821e; }
.qdot.s-review { background: #3d8bf5; }
.qdot.s-done { background: #18a058; }
.qbody { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8rpx; }
.qstem { font-size: 26rpx; color: var(--c-ink); line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.qtags { display: flex; gap: 8rpx; }
.qgo { flex-shrink: 0; font-size: 23rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 8rpx 20rpx; }
.qgo.loading { opacity: 0.6; }

/* 练习巩固卡(练习衍生·隔离) */
.prac-banner { background: #f4f2ec; border: 2rpx solid #e4ddca; border-radius: 14rpx; padding: 16rpx 20rpx; margin-bottom: 16rpx; }
.prac-banner text { font-size: 23rpx; color: #8a7b52; line-height: 1.55; }
/* 练习巩固:词折叠头(底色=整体练熟度)+ 逐维行 */
.pfold { background: #fff; border: 2rpx solid #e4ddca; border-left: 8rpx solid #d8c88f; border-radius: 18rpx; overflow: hidden; }
.pf-head { position: relative; overflow: hidden; }
.pf-fill { position: absolute; left: 0; top: 0; bottom: 0; background: linear-gradient(90deg, #f2ecd8, #faf7ee); transition: width .3s; }
.pf-in { position: relative; display: flex; align-items: center; gap: 12rpx; padding: 22rpx 24rpx; }
.pf-word { font-size: 32rpx; font-weight: 800; color: var(--c-ink); flex-shrink: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pf-meta { font-size: 21rpx; color: #8a7b52; flex-shrink: 0; }
.pf-retrain { margin-left: auto; flex-shrink: 0; font-size: 23rpx; font-weight: 700; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 10rpx 22rpx; }
.pf-retrain.loading { opacity: 0.6; }
.pf-chev { font-size: 26rpx; color: #b0a680; flex-shrink: 0; }
.pf-row { display: flex; align-items: center; gap: 12rpx; padding: 18rpx 24rpx; border-top: 2rpx dashed #ece4cf; }
.pf-tag { font-size: 19rpx; font-weight: 700; color: #8a7b52; background: #efe9d8; padding: 2rpx 12rpx; border-radius: 999rpx; }
.pf-dim { font-size: 24rpx; font-weight: 700; color: var(--c-ink); }
.pf-cnt { font-size: 20rpx; font-weight: 700; color: #c33; background: #fdecec; padding: 2rpx 12rpx; border-radius: 999rpx; }
.pf-dots { display: flex; align-items: center; gap: 8rpx; margin-left: auto; }
.pf-rp { flex-shrink: 0; font-size: 23rpx; font-weight: 700; color: var(--c-primary-deep); }
.pf-rp.loading { opacity: 0.6; }
.pc-dot { width: 20rpx; height: 20rpx; border-radius: 50%; border: 3rpx solid #cbb96f; box-sizing: border-box; }
.pc-dot.on { background: #2fa98a; border-color: #2fa98a; }

/* 长难句薄弱 句卡(蓝调,区别于词卡金调) */
.pfold.ls { border-color: #cfe0fa; border-left-color: #5b8def; }
.pfold.ls .pf-fill { background: linear-gradient(90deg, #eaf1fc, #f6f9ff); }
.pf-in.ls-in { flex-direction: column; align-items: stretch; gap: 12rpx; }
.ls-htop { display: flex; align-items: center; gap: 12rpx; }
.ls-badge { font-size: 19rpx; font-weight: 700; color: #3a6bc0; background: #e7effc; padding: 2rpx 14rpx; border-radius: 999rpx; }
.ls-sent { font-size: 25rpx; font-weight: 600; color: var(--c-ink); line-height: 1.5;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.ls-all { text-align: center; background: #5b8def; color: #fff; font-size: 24rpx; font-weight: 700; border-radius: 12rpx; padding: 16rpx 0; }
.pf-tag.whole { color: #3a6bc0; background: #e7effc; }
/* 句子成分理解块(方案B) */
.cu-sec { background: #fff; border: 2rpx solid #cfe0fa; border-radius: 18rpx; padding: 20rpx; margin-bottom: 18rpx; }
.cu-h { display: flex; align-items: baseline; gap: 12rpx; margin-bottom: 14rpx; }
.cu-t { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.cu-subt { font-size: 21rpx; color: var(--c-text-hint); }
.cu-skill { position: relative; overflow: hidden; border: 2rpx solid var(--c-border); border-radius: 14rpx; margin-bottom: 12rpx; }
.cu-fill { position: absolute; left: 0; top: 0; bottom: 0; background: linear-gradient(90deg, #e9f6f1, #f4fbf8); transition: width .3s; }
.cu-in { position: relative; display: flex; align-items: center; gap: 12rpx; padding: 20rpx 22rpx; }
.cu-nm { display: flex; flex-direction: column; gap: 2rpx; }
.cu-n { font-size: 27rpx; font-weight: 800; color: var(--c-ink); }
.cu-d { font-size: 20rpx; color: var(--c-text-hint); }
.cu-err { font-size: 20rpx; font-weight: 700; color: #c33; background: #fdecec; padding: 2rpx 14rpx; border-radius: 999rpx; margin-left: auto; }
.cu-rate { font-size: 27rpx; font-weight: 900; color: #2fa98a; }
.cu-cv { font-size: 24rpx; color: var(--c-text-hint); width: 24rpx; text-align: center; }
.cu-row { display: flex; align-items: center; gap: 12rpx; padding: 14rpx 22rpx; border-top: 2rpx dashed var(--c-border); }
.cu-role { font-size: 20rpx; font-weight: 700; color: #b5651a; background: #fcf1e6; padding: 2rpx 14rpx; border-radius: 8rpx; flex-shrink: 0; }
.cu-sent { flex: 1; min-width: 0; font-size: 23rpx; color: var(--c-text-second); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cu-wc { font-size: 20rpx; color: #c33; flex-shrink: 0; }
.cu-rp { font-size: 22rpx; font-weight: 700; color: var(--c-primary-deep); flex-shrink: 0; }
/* 长难句时间线诊断(变体2) */
.ls2-tabs { display: flex; gap: 24rpx; padding: 6rpx 0 14rpx; overflow-x: auto; white-space: nowrap; }
.ls2-tab { font-size: 26rpx; color: var(--c-text-second); padding: 6rpx 0; flex-shrink: 0; }
.ls2-tab.on { color: var(--c-primary); font-weight: 800; border-bottom: 4rpx solid var(--c-primary); }
.ls2-sec { font-size: 25rpx; font-weight: 800; color: var(--c-text-second); margin: 14rpx 0 12rpx 4rpx; display: flex; align-items: center; gap: 12rpx; }
.ls2-sec.old { color: #e0863a; }
.ls2-badge { font-size: 19rpx; font-weight: 700; color: #e0863a; background: #fcf1e6; padding: 2rpx 12rpx; border-radius: 8rpx; }
.ls2-tl { position: relative; padding-left: 40rpx; }
.ls2-tl::before { content: ''; position: absolute; left: 12rpx; top: 10rpx; bottom: 10rpx; width: 3rpx; background: var(--c-border); }
.ls2-node { position: relative; margin-bottom: 16rpx; }
.ls2-dot { position: absolute; left: -34rpx; top: 28rpx; width: 22rpx; height: 22rpx; border-radius: 50%; border: 5rpx solid var(--c-bg-page); box-sizing: border-box; }
.ls2-dot.no { background: #b7c0cc; }
.ls2-dot.ing { background: var(--c-primary); }
.ls2-dot.done { background: #2fa98a; }
.ls2-card { position: relative; overflow: hidden; background: var(--c-bg-card); border: 2rpx solid var(--c-border); border-radius: 18rpx; }
.ls2-fill { position: absolute; left: 0; top: 0; bottom: 0; }
.ls2-card.ing .ls2-fill { background: linear-gradient(90deg, #e8f2ff, #f4f9ff); }
.ls2-card.done .ls2-fill { background: linear-gradient(90deg, #e9f6f1, #f4fbf8); }
.ls2-in { position: relative; padding: 20rpx 22rpx; }
.ls2-top { display: flex; align-items: flex-start; gap: 12rpx; }
.ls2-sent { flex: 1; font-size: 27rpx; font-weight: 700; color: var(--c-ink); line-height: 1.5; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; }
.ls2-pct { font-size: 32rpx; font-weight: 900; flex-shrink: 0; }
.ls2-pct.no { color: #94a3b8; }
.ls2-pct.ing { color: var(--c-primary); }
.ls2-pct.done { color: #2fa98a; }
.ls2-ck { font-size: 34rpx; font-weight: 900; color: #2fa98a; flex-shrink: 0; }
.ls2-kinds { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 12rpx; }
.ls2-kb { font-size: 20rpx; font-weight: 700; padding: 4rpx 14rpx; border-radius: 8rpx; }
.ls2-kb.kc-comp { background: #f2edfb; color: #7a5cd0; }
.ls2-kb.kc-asm { background: #fcf1e6; color: #e0863a; }
.ls2-kb.kc-gram { background: #eaf2fe; color: #3d8bf5; }
.ls2-kb.kc-word { background: #fbf0e4; color: #c77d2e; }
.ls2-kb.zero { opacity: .4; }
.ls2-meta { font-size: 21rpx; color: var(--c-text-hint); margin-top: 10rpx; }
.ls2-st { font-weight: 700; }
.ls2-st.ing { color: var(--c-primary); }
.ls2-st.done { color: #2fa98a; }
.ls2-grp { border-top: 2rpx dashed var(--c-border); margin-top: 12rpx; padding-top: 12rpx; }
.ls2-gh { display: flex; align-items: center; gap: 10rpx; margin-bottom: 8rpx; }
.ls2-gt { font-size: 24rpx; font-weight: 800; }
.ls2-gt.kc-comp { color: #7a5cd0; }
.ls2-gt.kc-asm { color: #e0863a; }
.ls2-gt.kc-gram { color: #3d8bf5; }
.ls2-gt.kc-word { color: #c77d2e; }
.ls2-gs { font-size: 20rpx; color: var(--c-text-hint); }
.ls2-grp-rp { margin-left: auto; font-size: 22rpx; font-weight: 700; color: var(--c-primary-deep); }
.ls2-items { display: flex; flex-wrap: wrap; gap: 10rpx; }
.ls2-it { font-size: 21rpx; padding: 4rpx 12rpx; border-radius: 8rpx; border: 2rpx solid var(--c-border); }
.ls2-it.ok { background: #f4fbf8; border-color: #cfeee1; color: #2fa98a; }
.ls2-it.err { background: #fdf0ec; border-color: #f2cabd; color: #d9573f; }
.ls2-empty { font-size: 20rpx; color: var(--c-text-hint); }
.lsd-component { color: #3a6bc0; }
.lsd-comprehension { color: #2fa98a; }
.lsd-grammar { color: #7a5cd0; }
.lsd-keyword { color: #c77d2e; }

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

<!-- src/pages/essay/train.vue 写作能力训练 -->
<template>
  <view class="et-page">
    <!-- 选题 -->
    <view v-if="phase === 'pick'">
      <view class="et-head">
        <view class="et-title" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-pen" style="width:34rpx;height:34rpx"/><text>写作能力训练</text></view>
        <view class="et-link" style="display:flex;align-items:center;gap:6rpx" @tap="goErrorBook"><view class="ic ic-book" style="width:28rpx;height:28rpx"/><text>错因本</text></view>
      </view>
      <view class="genre-chips">
        <text class="gchip" :class="{ on: !genre }" @tap="setGenre('')">全部</text>
        <text v-for="g in genres" :key="g" class="gchip" :class="{ on: genre === g }" @tap="setGenre(g)">{{ g }}</text>
      </view>
      <view v-if="loading" class="tip">加载题库…</view>
      <view v-for="p in prompts" :key="p.id" class="p-card" @tap="pickPrompt(p)">
        <view class="p-top"><text class="p-genre">{{ p.genre }}</text><text class="p-words" v-if="p.word_min">{{ p.word_min }}-{{ p.word_max }}词</text></view>
        <text class="p-title">{{ p.title }}</text>
        <text class="p-sc">{{ p.scenario }}</text>
      </view>
      <view class="p-card custom" @tap="pickCustom">
        <view class="p-title" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-plus" style="width:30rpx;height:30rpx"/><text>自定义题目</text></view>
        <text class="p-sc">粘贴一道作文题/情景，AI 帮你审题</text>
      </view>
    </view>

    <view v-else-if="phase === 'custom'">
      <view class="et-head"><text class="et-back" @tap="phase = 'pick'">← 返回</text><text class="et-title">自定义题目</text></view>
      <textarea v-model="customText" class="ta" placeholder="粘贴或输入作文题目/情景…" />
      <button class="btn-primary" :disabled="!customText.trim() || analyzing" @tap="analyzeCustom">
        {{ analyzing ? 'AI 审题中…' : 'AI 审题 →' }}
      </button>
    </view>

    <view v-else-if="phase === 'analyze' && analysis">
      <view class="et-head"><text class="et-back" @tap="phase = 'pick'">← 换题</text><text class="et-title">审题 · {{ gateN }}/4</text></view>
      <view class="a-card"><text class="a-sc">{{ analysis.scenario }}</text></view>

      <!-- Q1 收信人(仅书信类)-->
      <view v-if="hasAud" class="qc">
        <view class="qc-h"><text class="qc-n">1</text>写给谁?<text v-if="q1ok && q1" class="qc-ck">✓</text></view>
        <view class="qc-opts"><text v-for="o in q1opts" :key="o" class="qopt" :class="optCls(q1, o, analysis.audience || '')" @tap="q1 = o">{{ o }}</text></view>
        <view v-if="q1" class="qexpl" :class="{ bad: !q1ok }">{{ q1ok ? ('✓ 收信人=' + analysis.audience + ',称呼用 Dear ' + analysis.audience + ',') : ('✗ 收信人应是 ' + analysis.audience) }}</view>
      </view>

      <!-- Q2 体裁 -->
      <view class="qc">
        <view class="qc-h"><text class="qc-n">2</text>什么体裁?<text v-if="q2ok" class="qc-ck">✓</text></view>
        <view class="qc-opts"><text v-for="o in q2opts" :key="o" class="qopt" :class="optCls(q2, o, analysis.genre)" @tap="q2 = o">{{ o }}</text></view>
        <view v-if="q2" class="qexpl" :class="{ bad: !q2ok }">{{ q2ok ? (analysis.genre_explain || ('✓ ' + analysis.genre)) : ('✗ 应是 ' + analysis.genre) }}</view>
      </view>

      <!-- Q3 必写要点(多选)-->
      <view class="qc">
        <view class="qc-h"><text class="qc-n">3</text>必写要点?(多选)<text v-if="q3ok" class="qc-ck">✓</text></view>
        <view class="qc-opts"><text v-for="o in q3opts" :key="o" class="qopt" :class="ptCls(o)" @tap="pickPt(o)">{{ o }}</text></view>
        <view v-if="q3.length" class="qexpl" :class="{ bad: !q3ok }">{{ q3ok ? ('✓ 这 ' + analysis.required_points.length + ' 点都要,漏一个扣一片分') : ('✗ 只需:' + analysis.required_points.join(' / ')) }}</view>
      </view>

      <!-- Q4 人称/时态 -->
      <view class="qc">
        <view class="qc-h"><text class="qc-n">4</text>人称 / 时态?<text v-if="q4ok" class="qc-ck">✓</text></view>
        <view class="qc-opts"><text v-for="o in q4popts" :key="o" class="qopt" :class="optCls(q4p, o, analysis.person || '')" @tap="q4p = o">{{ o }}</text></view>
        <view class="qc-opts" style="margin-top:10rpx"><text v-for="o in q4topts" :key="o" class="qopt" :class="optCls(q4t, o, analysis.tense || '')" @tap="q4t = o">{{ o }}</text></view>
        <view v-if="q4p && q4t" class="qexpl" :class="{ bad: !q4ok }">{{ q4ok ? ('✓ 本题用 ' + analysis.person + ' + ' + analysis.tense) : ('✗ 应是 ' + (analysis.person || '') + ' + ' + (analysis.tense || '')) }}</view>
      </view>

      <button class="btn-primary" :class="{ dis: !gateOk }" :disabled="!gateOk" @tap="startWrite">{{ gateOk ? '开始写作 →' : ('审题 ' + gateN + '/4 · 答对全部解锁') }}</button>
    </view>

    <view v-else-if="phase === 'write'" class="write-wrap">
      <view class="et-head">
        <text class="et-back" @tap="phase = 'analyze'">← 审题</text>
        <view class="w-timer" style="display:flex;align-items:center;gap:6rpx"><view class="ic ic-clock" style="width:30rpx;height:30rpx"/><text>{{ timerText }}</text></view>
        <text class="w-count" :class="wordRange.cls">{{ wordRange.txt }}</text>
      </view>
      <!-- 要点覆盖自检 -->
      <view class="w-cover">
        <text class="wc-h">要点覆盖 {{ coveredPts.length }}/{{ (analysis?.required_points || []).length }} · 写到就点亮</text>
        <view class="wc-chips">
          <text v-for="(pt, i) in (analysis?.required_points || [])" :key="i" class="wc-chip" :class="{ on: coveredPts.includes(pt) }" @tap="togglePt(pt)">{{ coveredPts.includes(pt) ? '✓ ' : '' }}{{ pt }}</text>
        </view>
      </view>
      <textarea v-model="draft" class="ta ta-write" placeholder="在这里限时写作…（点下方支架可插入句子）" />
      <button class="btn-primary" :disabled="!draft.trim() || diagnosing" @tap="openSelfCheck" style="display:flex;align-items:center;justify-content:center;gap:8rpx">
        <text>{{ diagnosing ? 'AI 诊断中…' : (ent.can('essay.diagnose') ? '提交诊断' + quotaHint : '提交诊断') }}</text>
        <view v-if="!diagnosing && !ent.can('essay.diagnose')" class="ic ic-lock" style="width:30rpx;height:30rpx"/>
      </button>

      <!-- 写作支架抽屉 -->
      <view class="drawer" :class="{ closed: !drawerOpen }">
        <view class="dw-h" @tap="drawerOpen = !drawerOpen"><text class="dw-t">写作支架</text><text class="dw-c">点句即插入 · {{ drawerOpen ? '收起 ⌄' : '展开 ⌃' }}</text></view>
        <template v-if="drawerOpen">
          <view class="dw-tabs">
            <text class="dw-tab" :class="{ on: drawerTab === 'tpl' }" @tap="drawerTab = 'tpl'">模版骨架</text>
            <text class="dw-tab" :class="{ on: drawerTab === 'high' }" @tap="drawerTab = 'high'">高分句</text>
            <text class="dw-tab" :class="{ on: drawerTab === 'mine' }" @tap="drawerTab = 'mine'">✦ 你学过的句</text>
          </view>
          <scroll-view scroll-y class="dw-body">
            <text v-if="drawerTab === 'tpl'" class="dw-tpl">{{ scaffold?.template || '暂无模版' }}</text>
            <template v-else-if="drawerTab === 'high'">
              <view v-if="!scaffold?.high_sentences?.length" class="dw-empty">暂无高分句</view>
              <view v-for="(s, i) in (scaffold?.high_sentences || [])" :key="i" class="dw-sen" @tap="insertSent(s)"><text class="dw-sx">{{ s }}</text><text class="dw-ins">插入 +</text></view>
            </template>
            <template v-else>
              <view v-if="!scaffold?.my_sentences?.length" class="dw-empty">还没学过的长难句可套用(去长难句模块学一些)</view>
              <view v-for="(s, i) in (scaffold?.my_sentences || [])" :key="i" class="dw-sen mine" @tap="insertSent(s.text)"><text class="dw-sx">{{ s.text }}<text class="dw-src"> 来自你学过 {{ s.date }}</text></text><text class="dw-ins">插入 +</text></view>
            </template>
          </scroll-view>
        </template>
      </view>
    </view>

    <view v-else-if="phase === 'result' && diag">
      <view class="et-head"><view class="et-title" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-chart" style="width:34rpx;height:34rpx"/><text>诊断结果</text></view><view class="et-link" style="display:flex;align-items:center;gap:6rpx" @tap="goErrorBook"><view class="ic ic-book" style="width:28rpx;height:28rpx"/><text>错因本</text></view></view>
      <view class="r-score">
        <view class="r-total"><text class="r-num">{{ diag.total }}</text><text class="r-full">/{{ diag.total_full }}</text></view>
        <text class="r-band" :class="bandClass(diag.overall_band)">{{ diag.overall_band }}</text>
      </view>
      <view class="r-dims">
        <view v-for="d in diag.scores" :key="d.dimension" class="r-dim">
          <text class="rd-name">{{ d.dimension }}</text>
          <text class="rd-score">{{ d.score }}/{{ d.full }}</text>
          <text class="rd-band" :class="bandClass(d.band)">{{ d.band }}</text>
        </view>
      </view>

      <view class="r-card">
        <view class="r-h" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-check-circle" style="width:30rpx;height:30rpx"/><text>要点核对（{{ coveredCount }}/{{ diag.missing_points.length }}）</text></view>
        <view v-for="(m, i) in diag.missing_points" :key="i" class="mp-row" :class="{ miss: !m.covered }">
          <view class="ic mp-ic" :class="m.covered ? 'ic-check-circle' : 'ic-x-circle'" style="width:28rpx;height:28rpx"/><text class="mp-x">{{ m.point }}</text>
        </view>
      </view>

      <view v-if="diag.upgrade_tips.length" class="r-card up">
        <view class="r-h" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-trend-up" style="width:30rpx;height:30rpx"/><text>升档建议</text></view>
        <view v-for="(u, i) in diag.upgrade_tips" :key="i" class="up-row"><text class="up-d">{{ u.dimension }}</text><text class="up-t">{{ u.tip }}</text></view>
      </view>

      <!-- 卷面标记:原文高亮错误,点红处跳清单 -->
      <view v-if="markedCount" class="r-card">
        <view class="r-h" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-pen" style="width:30rpx;height:30rpx"/><text>卷面 · 标出 {{ markedCount }} 处(点红处看纠错)</text></view>
        <view class="paper-txt">
          <text v-for="(s, i) in markedSegs" :key="i" :class="{ mark: s.idx >= 0, cur: s.idx === openIssue }" @tap="tapMark(s.idx)">{{ s.t }}</text>
        </view>
      </view>

      <view v-if="diag.issues.length" class="r-card">
        <view class="r-h" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-pen" style="width:30rpx;height:30rpx"/><text>逐处纠错（已记入错因本）</text></view>
        <view v-for="(it, i) in diag.issues" :key="i" class="iss" :class="{ cur: openIssue === i }">
          <view class="iss-top"><text class="iss-type">{{ it.type }}</text></view>
          <view class="iss-o" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-x-circle" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ it.original }}</text></view>
          <view class="iss-s" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-check-circle" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ it.suggestion }}</text></view>
          <text v-if="it.explanation" class="iss-e">{{ it.explanation }}</text>
        </view>
      </view>

      <button class="btn-primary" style="margin-bottom:16rpx" @tap="openUpgrade">✦ 逐句升级(套你学过的句)→</button>
      <view class="r-btns">
        <button class="btn-ghost half" @tap="rewrite">改写本题</button>
        <button class="btn-primary half" @tap="phase = 'pick'">换一题</button>
      </view>
    </view>

    <!-- S5 逐句升级 -->
    <view v-if="showUpgrade" class="modal" @tap="showUpgrade = false">
      <view class="modal-card up-card" @tap.stop>
        <text class="sc-title">逐句升级 · 平句 → 高分句</text>
        <text class="sc-sub">优先套用你学过的长难句;点「应用」改进</text>
        <view v-if="upgrading" class="up-load">AI 升级中…</view>
        <view v-else-if="!upgrades.length" class="up-load">暂无可升级的句子 🎉</view>
        <scroll-view v-else scroll-y class="up-list">
          <view v-for="(u, i) in upgrades" :key="i" class="up-item" :class="{ mine: u.from_mine }">
            <text class="up-o">你的句:{{ u.original }}</text>
            <text class="up-arr">↓</text>
            <text class="up-u">{{ u.from_mine ? '✦ ' : '' }}{{ u.upgraded }}</text>
            <text v-if="u.note" class="up-note">{{ u.note }}</text>
            <view class="up-act" :class="{ on: applied.includes(i) }" @tap="toggleApply(i)">{{ applied.includes(i) ? '✓ 已应用' : '应用' }}</view>
          </view>
        </scroll-view>
        <view class="sc-acts">
          <view class="sc-btn ghost" @tap="showUpgrade = false">关闭</view>
          <view class="sc-btn primary" @tap="copyImproved">复制改进版({{ applied.length }})</view>
        </view>
      </view>
    </view>

    <!-- S3 提交前自检 -->
    <view v-if="showSelfCheck" class="modal" @tap="showSelfCheck = false">
      <view class="modal-card" @tap.stop>
        <text class="sc-title">提交前自检</text>
        <text class="sc-sub">对齐审题门槛,别漏点/差字数</text>
        <view v-for="c in selfChecks" :key="c.key" class="sc-row">
          <text class="sc-ic" :class="c.info ? 'info' : (c.ok ? 'ok' : 'warn')">{{ c.info ? 'ⓘ' : (c.ok ? '✓' : '!') }}</text>
          <text class="sc-l">{{ c.label }}</text>
          <text class="sc-v">{{ c.val }}</text>
          <text v-if="(!c.ok && c.warn) || c.info" class="sc-warn" :class="{ info: c.info }">{{ c.warn }}</text>
        </view>
        <view class="sc-acts">
          <view class="sc-btn ghost" @tap="showSelfCheck = false">返回改改</view>
          <view class="sc-btn primary" @tap="confirmSubmit">确认提交诊断</view>
        </view>
      </view>
    </view>

    <Paywall :open="showPaywall" :feature="ent.feature('essay.diagnose')" emoji="✍️"
      title="作文诊断是会员专享" @close="showPaywall = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getEssayPrompts, analyzeEssayPrompt, diagnoseEssay, getWritingScaffold, upgradeEssay, type EssayPrompt, type PromptAnalysis, type EssayDiagnosis, type WritingScaffold, type SentenceUpgrade } from '@/api/essay'
import { useAuthStore } from '@/stores/auth'
import { useEntitlementsStore } from '@/stores/entitlements'
import Paywall from '@/components/Paywall.vue'

const auth = useAuthStore()
const phase = ref<'pick' | 'custom' | 'analyze' | 'write' | 'result'>('pick')
const genres = ['书信', '通知', '记叙', '议论', '看图', '应用文', '读后续写']
const genre = ref('')
const prompts = ref<EssayPrompt[]>([])
const loading = ref(false)

const analysis = ref<PromptAnalysis | null>(null)
const curPromptId = ref<string | null>(null)
const customText = ref('')
const analyzing = ref(false)

// —— 提问式审题四卡(门槛:四要素全对才解锁写作)——
const q1 = ref(''); const q2 = ref(''); const q3 = ref<string[]>([]); const q4p = ref(''); const q4t = ref('')
const PERSONS = ['第一人称', '第三人称']
const TENSES = ['一般现在时', '一般将来时', '一般过去时']
function _uniq(a: string[]) { return [...new Set(a.filter(Boolean))] }
const hasAud = computed(() => !!(analysis.value?.audience))
const q1opts = computed(() => _uniq([analysis.value?.audience || '', '同学', '老师']))
const q2opts = computed(() => _uniq([analysis.value?.genre || '', ...(analysis.value?.genre_distractors || [])]))
const q3opts = computed(() => _uniq([...(analysis.value?.required_points || []), ...(analysis.value?.point_distractors || [])]))
const q4popts = computed(() => _uniq([analysis.value?.person || '', ...PERSONS]))
const q4topts = computed(() => _uniq([analysis.value?.tense || '', ...TENSES]))
const q1ok = computed(() => !hasAud.value || q1.value === analysis.value?.audience)
const q2ok = computed(() => !!q2.value && q2.value === analysis.value?.genre)
const q3ok = computed(() => { const r = analysis.value?.required_points || []; return r.length > 0 && r.every(p => q3.value.includes(p)) && q3.value.every(p => r.includes(p)) })
const q4ok = computed(() => !!q4p.value && !!q4t.value && q4p.value === (analysis.value?.person || q4p.value) && q4t.value === (analysis.value?.tense || q4t.value))
const gateN = computed(() => [(!hasAud.value || q1ok.value), q2ok.value, q3ok.value, q4ok.value].filter(Boolean).length)
const gateOk = computed(() => gateN.value === 4)
function pickPt(pt: string) { const i = q3.value.indexOf(pt); i >= 0 ? q3.value.splice(i, 1) : q3.value.push(pt) }
function optCls(chosen: string, val: string, correct: string) { if (!chosen) return ''; if (val === correct) return 'ok'; if (val === chosen) return 'wrong'; return '' }
function ptCls(pt: string) { const r = analysis.value?.required_points || []; if (!q3.value.length) return ''; return q3.value.includes(pt) ? (r.includes(pt) ? 'ok' : 'wrong') : '' }
function resetAnalyze() { q1.value = ''; q2.value = ''; q3.value = []; q4p.value = ''; q4t.value = '' }

const draft = ref('')
const showPoints = ref(true)
const diagnosing = ref(false)
const diag = ref<EssayDiagnosis | null>(null)
const showPaywall = ref(false)
const ent = useEntitlementsStore()

// 计时
const seconds = ref(0)
let _timer: ReturnType<typeof setInterval> | null = null
const timerText = computed(() => {
  const m = Math.floor(seconds.value / 60), s = seconds.value % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
})
const wordCount = computed(() => (draft.value.trim().match(/[A-Za-z']+/g) || []).length)
const quotaHint = computed(() => {
  const f = ent.feature('essay.diagnose')
  return f.mode === 'quota' && f.quota_left != null ? `（本月剩 ${f.quota_left} 次）` : ''
})
const coveredCount = computed(() => diag.value ? diag.value.missing_points.filter(m => m.covered).length : 0)

function bandClass(b?: string) {
  return b === '优秀' ? 'b-ex' : b === '良好' ? 'b-good' : b === '合格' ? 'b-ok' : 'b-low'
}
function setGenre(g: string) { genre.value = g; loadPrompts() }
async function loadPrompts() {
  loading.value = true
  try { prompts.value = await getEssayPrompts(undefined, genre.value || undefined) }
  catch (e) { uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
function pickPrompt(p: EssayPrompt) {
  curPromptId.value = p.id
  analysis.value = { title: p.title, genre: p.genre, scenario: p.scenario, required_points: p.required_points, person: p.person, tense: p.tense, word_min: p.word_min, word_max: p.word_max }
  resetAnalyze(); phase.value = 'analyze'
}
function pickCustom() { customText.value = ''; phase.value = 'custom' }
async function analyzeCustom() {
  analyzing.value = true
  try {
    analysis.value = await analyzeEssayPrompt({ text: customText.value.trim() })
    curPromptId.value = null
    resetAnalyze(); phase.value = 'analyze'
  } catch (e) { uni.showToast({ title: (e as Error).message || '审题失败', icon: 'none' }) }
  finally { analyzing.value = false }
}
// —— 写作页:词数区间 + 要点自检 + 抽屉支架 ——
const scaffold = ref<WritingScaffold | null>(null)
const drawerOpen = ref(true)
const drawerTab = ref<'tpl' | 'high' | 'mine'>('high')
const coveredPts = ref<string[]>([])
function togglePt(pt: string) { const i = coveredPts.value.indexOf(pt); i >= 0 ? coveredPts.value.splice(i, 1) : coveredPts.value.push(pt) }
const wordRange = computed(() => {
  const min = analysis.value?.word_min || 0, max = analysis.value?.word_max || 0, n = wordCount.value
  if (!min) return { txt: `${n} 词`, cls: '' }
  if (n < min) return { txt: `${n} / ${min}~${max} · 还差 ${min - n}`, cls: 'few' }
  if (max && n > max) return { txt: `${n} / ${min}~${max} · 超 ${n - max}`, cls: 'over' }
  return { txt: `${n} / ${min}~${max} ✓`, cls: 'ok' }
})
function insertSent(s: string) {
  const d = draft.value
  draft.value = d + (d && !/\s$/.test(d) ? ' ' : '') + s + ' '
  uni.showToast({ title: '已插入', icon: 'none' })
}
// —— S3 提交前自检 ——
const showSelfCheck = ref(false)
const selfChecks = computed(() => {
  const req = analysis.value?.required_points || []
  const cov = coveredPts.value.length
  const wr = wordRange.value
  return [
    { key: 'pt', ok: req.length > 0 && cov >= req.length, label: '要点覆盖', val: `${cov}/${req.length}`, warn: cov < req.length ? '还有要点没点亮,可能漏点' : '' },
    { key: 'wc', ok: wr.cls === 'ok' || wr.cls === '', label: '词数', val: wr.txt.replace(/ ✓$/, ''), warn: wr.cls === 'few' ? '字数不够' : wr.cls === 'over' ? '超出字数' : '' },
    { key: 'pn', info: true, ok: true, label: '人称 / 时态', val: `${analysis.value?.person || ''} · ${analysis.value?.tense || ''}`, warn: '自己再核对一遍' },
  ]
})
function openSelfCheck() {
  if (!ent.can('essay.diagnose')) { showPaywall.value = true; return }
  showSelfCheck.value = true
}
function confirmSubmit() { showSelfCheck.value = false; submitDiagnose() }

// —— S4 批改卷面标记:在提交原文里定位每个 issue.original,分段高亮,点红处跳清单 ——
const openIssue = ref(-1)
const markedSegs = computed(() => {
  const text = draft.value || ''
  const issues = diag.value?.issues || []
  const used = new Array(text.length).fill(false)
  const marks: { start: number; end: number; idx: number }[] = []
  const lower = text.toLowerCase()
  issues.forEach((it, idx) => {
    const o = (it.original || '').trim()
    if (!o) return
    const from = lower.indexOf(o.toLowerCase())
    if (from < 0) return
    const end = from + o.length
    let overlap = false
    for (let i = from; i < end; i++) { if (used[i]) { overlap = true; break } }
    if (overlap) return
    for (let i = from; i < end; i++) used[i] = true
    marks.push({ start: from, end, idx })
  })
  marks.sort((a, b) => a.start - b.start)
  const segs: { t: string; idx: number }[] = []
  let pos = 0
  for (const m of marks) {
    if (m.start > pos) segs.push({ t: text.slice(pos, m.start), idx: -1 })
    segs.push({ t: text.slice(m.start, m.end), idx: m.idx })
    pos = m.end
  }
  if (pos < text.length) segs.push({ t: text.slice(pos), idx: -1 })
  return segs
})
const markedCount = computed(() => markedSegs.value.filter(s => s.idx >= 0).length)
function tapMark(idx: number) { if (idx >= 0) openIssue.value = idx }

// —— S5 逐句升级(平句→高分句,优先套自学句)——
const showUpgrade = ref(false)
const upgrading = ref(false)
const upgrades = ref<SentenceUpgrade[]>([])
const applied = ref<number[]>([])
async function openUpgrade() {
  showUpgrade.value = true
  if (upgrades.value.length || upgrading.value) return
  upgrading.value = true
  try { upgrades.value = (await upgradeEssay(draft.value.trim(), analysis.value?.genre || undefined)).upgrades }
  catch (e) { uni.showToast({ title: (e as Error).message || '升级失败', icon: 'none' }) }
  finally { upgrading.value = false }
}
function toggleApply(i: number) { const k = applied.value.indexOf(i); k >= 0 ? applied.value.splice(k, 1) : applied.value.push(i) }
const improvedText = computed(() => {
  let t = draft.value || ''
  applied.value.forEach(i => { const u = upgrades.value[i]; if (u && t.includes(u.original)) t = t.replace(u.original, u.upgraded) })
  return t
})
function copyImproved() {
  uni.setClipboardData({ data: improvedText.value, success: () => uni.showToast({ title: '改进版已复制', icon: 'none' }) })
}
function startWrite() {
  if (!gateOk.value) return
  draft.value = ''; seconds.value = 0; coveredPts.value = []; phase.value = 'write'
  if (_timer) clearInterval(_timer)
  _timer = setInterval(() => { seconds.value++ }, 1000)
  getWritingScaffold(analysis.value?.genre || undefined).then(r => { scaffold.value = r }).catch(() => { scaffold.value = null })
}
async function submitDiagnose() {
  if (!ent.can('essay.diagnose')) { showPaywall.value = true; return }   // 点前拦截
  if (_timer) { clearInterval(_timer); _timer = null }
  diagnosing.value = true
  try {
    diag.value = await diagnoseEssay({
      draft_text: draft.value.trim(),
      prompt_id: curPromptId.value || undefined,
      prompt_text: curPromptId.value ? undefined : analysis.value?.scenario,
      timed_seconds: seconds.value,
    })
    phase.value = 'result'; openIssue.value = -1
    ent.fetch()   // 配额变化，刷新能力图
  } catch (e) {
    if ((e as { code?: number }).code === 403) { showPaywall.value = true }
    else uni.showToast({ title: (e as Error).message || '诊断失败', icon: 'none' })
  } finally { diagnosing.value = false }
}
function rewrite() { startWrite() }
function goErrorBook() { uni.navigateTo({ url: '/pages/essay/error-book' }) }

onMounted(async () => { if (!auth.isLoggedIn()) await auth.login(); ent.ensure(); loadPrompts() })
onUnmounted(() => { if (_timer) clearInterval(_timer) })
</script>

<style scoped>
.et-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.tip { text-align: center; padding: 80rpx; color: var(--c-text-hint); }
.et-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18rpx; }
.et-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.et-link { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); }
.et-back { font-size: 28rpx; color: var(--c-text-hint); }
.genre-chips { display: flex; flex-wrap: wrap; gap: 12rpx; margin-bottom: 18rpx; }
.gchip { font-size: 24rpx; color: var(--c-text-second); background: var(--c-bg-card); border-radius: var(--r-pill); padding: 8rpx 24rpx; }
.gchip.on { color: #fff; background: var(--c-primary); font-weight: 700; }
.p-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 22rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); display: flex; flex-direction: column; gap: 8rpx; }
.p-card.custom { background: var(--c-primary-faint); border: 2rpx dashed var(--c-primary-soft); }
.p-top { display: flex; justify-content: space-between; }
.p-genre { font-size: 20rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); border-radius: var(--r-pill); padding: 3rpx 16rpx; }
.p-words { font-size: 22rpx; color: var(--c-text-hint); }
.p-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.p-sc { font-size: 24rpx; color: var(--c-text-second); line-height: 1.5; }
.ta { width: 100%; box-sizing: border-box; min-height: 240rpx; background: var(--c-bg-card); border-radius: var(--r-md); padding: 22rpx; font-size: 28rpx; line-height: 1.6; }
.ta-write { min-height: 520rpx; }
.a-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 22rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 10rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.a-t { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.a-sc { font-size: 26rpx; color: var(--c-text-body); line-height: 1.6; }
.a-meta { display: flex; flex-wrap: wrap; gap: 10rpx; }
.a-tag { font-size: 22rpx; color: var(--c-primary-deep); background: var(--c-primary-faint); border-radius: var(--r-pill); padding: 4rpx 16rpx; }
.a-pt-title { font-size: 26rpx; font-weight: 800; color: #c98314; }
.a-pt { display: flex; gap: 12rpx; align-items: flex-start; }
.a-pt-n { flex-shrink: 0; width: 36rpx; height: 36rpx; line-height: 36rpx; text-align: center; font-size: 22rpx; font-weight: 800; color: #fff; background: #ffab40; border-radius: 50%; }
.a-pt-x { font-size: 26rpx; color: var(--c-text-body); line-height: 1.5; flex: 1; }
.w-timer { font-size: 30rpx; font-weight: 800; color: var(--c-primary-deep); }
.w-count { font-size: 24rpx; color: var(--c-text-hint); }
.w-points { background: #fff7e8; border-radius: var(--r-md); padding: 14rpx 18rpx; margin-bottom: 14rpx; }
.wp-h { font-size: 24rpx; font-weight: 700; color: #c98314; }
.wp-x { display: block; font-size: 24rpx; color: #8a6516; line-height: 1.6; margin-top: 4rpx; }
.r-score { display: flex; align-items: center; justify-content: center; gap: 20rpx; padding: 24rpx 0; }
.r-total { display: flex; align-items: baseline; }
.r-num { font-size: 88rpx; font-weight: 900; color: var(--c-ink); }
.r-full { font-size: 32rpx; color: var(--c-text-hint); }
.r-band { font-size: 28rpx; font-weight: 800; padding: 6rpx 22rpx; border-radius: var(--r-pill); }
.b-ex { color: #fff; background: #34c759; }
.b-good { color: #fff; background: #5aa9f8; }
.b-ok { color: #fff; background: #ffab40; }
.b-low { color: #fff; background: #ff6b6b; }
.r-dims { display: flex; gap: 14rpx; margin-bottom: 16rpx; }
.r-dim { flex: 1; background: var(--c-bg-card); border-radius: var(--r-md); padding: 16rpx; display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.rd-name { font-size: 24rpx; color: var(--c-text-second); }
.rd-score { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.rd-band { font-size: 18rpx; padding: 1rpx 12rpx; border-radius: var(--r-pill); }
.r-card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 20rpx 22rpx; margin-bottom: 16rpx; display: flex; flex-direction: column; gap: 8rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.r-card.up { background: #eef9f0; }
.r-h { font-size: 26rpx; font-weight: 800; color: var(--c-ink); }
.mp-row { display: flex; gap: 12rpx; align-items: center; }
.mp-row.miss { }
.mp-ic { font-size: 26rpx; color: #34c759; font-weight: 800; }
.mp-row.miss .mp-ic { color: #ff6b6b; }
.mp-x { font-size: 25rpx; color: var(--c-text-body); }
.mp-row.miss .mp-x { color: #ff6b6b; font-weight: 600; }
.up-row { display: flex; gap: 12rpx; align-items: flex-start; }
.up-d { flex-shrink: 0; font-size: 22rpx; font-weight: 800; color: #1b7a3d; background: #d8f3dc; border-radius: var(--r-pill); padding: 2rpx 14rpx; }
.up-t { font-size: 25rpx; color: #2c5f3a; line-height: 1.5; flex: 1; }
.iss { padding: 12rpx 0; border-bottom: 1rpx solid var(--c-bg-soft); display: flex; flex-direction: column; gap: 4rpx; }
.iss-type { font-size: 20rpx; font-weight: 700; color: #d6457e; background: #fff0f5; border-radius: var(--r-pill); padding: 2rpx 14rpx; align-self: flex-start; }
.iss-o { font-size: 25rpx; color: #ff6b6b; }
.iss-s { font-size: 25rpx; color: #1b7a3d; }
.iss-e { font-size: 22rpx; color: var(--c-text-hint); }
.r-btns { display: flex; gap: 16rpx; margin-top: 8rpx; }
.half { flex: 1; }
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 999; }
.pw-card { width: 560rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 40rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; }
.pw-emoji { font-size: 72rpx; }
.pw-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.pw-desc { font-size: 26rpx; color: var(--c-text-second); text-align: center; line-height: 1.6; }
.pw-card .btn-primary { width: 100%; }
.pw-close { font-size: 26rpx; color: var(--c-text-hint); padding: 8rpx; }
/* 审题四卡 */
.qc { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 20rpx 22rpx; margin-bottom: 14rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.qc-h { font-size: 28rpx; font-weight: 800; color: var(--c-ink); margin-bottom: 14rpx; display: flex; align-items: center; gap: 10rpx; }
.qc-n { width: 36rpx; height: 36rpx; border-radius: 50%; background: #eaf2fe; color: var(--c-primary); font-size: 22rpx; font-weight: 800; display: flex; align-items: center; justify-content: center; }
.qc-ck { margin-left: auto; color: #2fa98a; font-size: 26rpx; font-weight: 900; }
.qc-opts { display: flex; flex-wrap: wrap; gap: 14rpx; }
.qopt { font-size: 26rpx; padding: 12rpx 26rpx; border-radius: 999rpx; border: 3rpx solid var(--c-border); color: var(--c-text-second); }
.qopt.ok { border-color: #2fa98a; background: #f4fbf8; color: #128a4c; font-weight: 700; }
.qopt.wrong { border-color: #d9573f; background: #fdf0ec; color: #d9573f; }
.qexpl { margin-top: 14rpx; font-size: 23rpx; line-height: 1.55; color: #128a4c; background: #f4fbf8; border: 2rpx solid #cfeee1; border-radius: 12rpx; padding: 12rpx 14rpx; }
.qexpl.bad { color: #d9573f; background: #fdf0ec; border-color: #f2cabd; }
.btn-primary.dis { background: #c5ccd6 !important; color: #fff; }
/* 写作页 S2 */
.write-wrap { padding-bottom: 200rpx; }
.w-count.few { color: #e0863a; } .w-count.over { color: #d9573f; } .w-count.ok { color: #2fa98a; }
.w-cover { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 18rpx 20rpx; margin-bottom: 14rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.wc-h { font-size: 22rpx; color: var(--c-text-hint); display: block; margin-bottom: 12rpx; }
.wc-chips { display: flex; flex-wrap: wrap; gap: 12rpx; }
.wc-chip { font-size: 24rpx; padding: 8rpx 20rpx; border-radius: 999rpx; background: #f1f3f7; color: #9aa4b2; }
.wc-chip.on { background: #e9f6f1; color: #2fa98a; font-weight: 700; }
.drawer { position: fixed; left: 0; right: 0; bottom: 0; background: #fff; border-top: 2rpx solid var(--c-border); border-radius: 24rpx 24rpx 0 0; box-shadow: 0 -6rpx 30rpx rgba(20,40,70,.1); padding: 18rpx 22rpx calc(env(safe-area-inset-bottom) + 18rpx); z-index: 40; }
.drawer.closed { padding-bottom: calc(env(safe-area-inset-bottom) + 18rpx); }
.dw-h { display: flex; align-items: center; }
.dw-t { font-size: 28rpx; font-weight: 800; color: var(--c-ink); }
.dw-c { margin-left: auto; font-size: 21rpx; color: var(--c-text-hint); }
.dw-tabs { display: flex; gap: 14rpx; margin: 14rpx 0; }
.dw-tab { font-size: 23rpx; padding: 8rpx 18rpx; border-radius: 999rpx; background: #eef3f9; color: var(--c-text-second); }
.dw-tab.on { background: var(--c-primary); color: #fff; font-weight: 700; }
.dw-body { max-height: 300rpx; }
.dw-tpl { font-size: 24rpx; color: var(--c-text-body); line-height: 1.7; }
.dw-empty { font-size: 23rpx; color: var(--c-text-hint); padding: 20rpx 0; }
.dw-sen { display: flex; align-items: center; gap: 12rpx; background: #eef4fd; border: 2rpx solid #d6e5fb; border-radius: 12rpx; padding: 14rpx; margin-bottom: 10rpx; }
.dw-sen.mine { background: #f4fbf8; border-color: #cfeee1; }
.dw-sx { flex: 1; font-size: 24rpx; color: #185FA5; line-height: 1.5; }
.dw-sen.mine .dw-sx { color: #128a4c; }
.dw-src { font-size: 19rpx; color: #c77d2e; }
.dw-ins { font-size: 22rpx; font-weight: 800; color: var(--c-primary); flex-shrink: 0; }
.dw-sen.mine .dw-ins { color: #128a4c; }
/* S3 提交自检弹层 */
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 60; padding: 40rpx; }
.modal-card { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 32rpx 28rpx; box-sizing: border-box; }
.sc-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); display: block; }
.sc-sub { font-size: 22rpx; color: var(--c-text-hint); display: block; margin: 6rpx 0 18rpx; }
.sc-row { display: flex; align-items: center; gap: 12rpx; padding: 14rpx 0; border-top: 2rpx solid var(--c-border); }
.sc-row:first-of-type { border-top: 0; }
.sc-ic { width: 40rpx; height: 40rpx; border-radius: 50%; font-size: 24rpx; font-weight: 900; display: flex; align-items: center; justify-content: center; flex-shrink: 0; color: #fff; }
.sc-ic.ok { background: #2fa98a; } .sc-ic.warn { background: #e0863a; } .sc-ic.info { background: #eaf2fe; color: var(--c-primary); }
.sc-l { font-size: 27rpx; font-weight: 700; color: var(--c-ink); }
.sc-v { margin-left: auto; font-size: 24rpx; color: var(--c-text-second); }
.sc-warn { flex-basis: 100%; font-size: 21rpx; color: #e0863a; padding-left: 52rpx; }
.sc-warn.info { color: var(--c-text-hint); }
.sc-acts { display: flex; gap: 16rpx; margin-top: 22rpx; }
.sc-btn { flex: 1; text-align: center; font-size: 28rpx; font-weight: 700; border-radius: 999rpx; padding: 18rpx; }
.sc-btn.ghost { background: var(--c-bg-soft, #eef1f5); color: var(--c-text-second); }
.sc-btn.primary { background: var(--c-primary); color: #fff; }
/* S4 卷面标记 */
.paper-txt { font-size: 27rpx; line-height: 1.9; color: var(--c-text-body); }
.paper-txt .mark { color: #d9573f; border-bottom: 3rpx solid #d9573f; padding: 0 2rpx; }
.paper-txt .cur { background: #fdecec; border-radius: 4rpx; }
.iss.cur { background: #fff6f4; border-radius: 12rpx; box-shadow: 0 0 0 3rpx #f2cabd; }
/* S5 逐句升级 */
.up-card { max-width: 660rpx; }
.up-load { text-align: center; color: var(--c-text-hint); font-size: 26rpx; padding: 40rpx 0; }
.up-list { max-height: 60vh; margin: 8rpx 0; }
.up-item { border: 2rpx solid var(--c-border); border-radius: 14rpx; padding: 16rpx; margin-bottom: 14rpx; }
.up-item.mine { border-color: #cfeee1; background: #f4fbf8; }
.up-o { display: block; font-size: 24rpx; color: var(--c-text-hint); line-height: 1.5; }
.up-arr { display: block; text-align: center; color: var(--c-primary); font-size: 22rpx; margin: 4rpx 0; }
.up-u { display: block; font-size: 26rpx; font-weight: 600; color: #185FA5; line-height: 1.55; }
.up-item.mine .up-u { color: #128a4c; }
.up-note { display: block; font-size: 21rpx; color: var(--c-text-second); margin-top: 6rpx; line-height: 1.5; }
.up-act { margin-top: 10rpx; align-self: flex-start; display: inline-block; font-size: 23rpx; font-weight: 700; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.up-act.on { background: #2fa98a; border-color: #2fa98a; color: #fff; }
</style>

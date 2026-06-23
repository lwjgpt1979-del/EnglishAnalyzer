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
      <view class="et-head"><text class="et-back" @tap="phase = 'pick'">← 换题</text><text class="et-title">审题</text></view>
      <view class="a-card">
        <text class="a-t">{{ analysis.title }}</text>
        <text class="a-sc">{{ analysis.scenario }}</text>
        <view class="a-meta">
          <text v-if="analysis.genre" class="a-tag">{{ analysis.genre }}</text>
          <text v-if="analysis.person" class="a-tag">{{ analysis.person }}</text>
          <text v-if="analysis.tense" class="a-tag">{{ analysis.tense }}</text>
          <text v-if="analysis.word_min" class="a-tag">{{ analysis.word_min }}-{{ analysis.word_max }}词</text>
        </view>
      </view>
      <view class="a-card">
        <view class="a-pt-title" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-pin" style="width:30rpx;height:30rpx"/><text>必答要点（漏一点扣一片分）</text></view>
        <view v-for="(pt, i) in analysis.required_points" :key="i" class="a-pt"><text class="a-pt-n">{{ i + 1 }}</text><text class="a-pt-x">{{ pt }}</text></view>
      </view>
      <button class="btn-primary" @tap="startWrite">开始写作 →</button>
    </view>

    <view v-else-if="phase === 'write'">
      <view class="et-head">
        <text class="et-back" @tap="phase = 'analyze'">← 审题</text>
        <view class="w-timer" style="display:flex;align-items:center;gap:6rpx"><view class="ic ic-clock" style="width:30rpx;height:30rpx"/><text>{{ timerText }}</text></view>
        <text class="w-count">{{ wordCount }} 词</text>
      </view>
      <view class="w-points" @tap="showPoints = !showPoints">
        <view class="wp-h" style="display:flex;align-items:center;gap:6rpx"><view class="ic ic-pin" style="width:26rpx;height:26rpx"/><text>要点{{ showPoints ? ' ▲' : ' ▼' }}</text></view>
        <view v-if="showPoints">
          <text v-for="(pt, i) in (analysis?.required_points || [])" :key="i" class="wp-x">· {{ pt }}</text>
        </view>
      </view>
      <textarea v-model="draft" class="ta ta-write" placeholder="在这里限时写作…" />
      <button class="btn-primary" :disabled="!draft.trim() || diagnosing" @tap="submitDiagnose" style="display:flex;align-items:center;justify-content:center;gap:8rpx">
        <text>{{ diagnosing ? 'AI 诊断中…' : (ent.can('essay.diagnose') ? '提交诊断' + quotaHint : '提交诊断') }}</text>
        <view v-if="!diagnosing && !ent.can('essay.diagnose')" class="ic ic-lock" style="width:30rpx;height:30rpx"/>
      </button>
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

      <view v-if="diag.issues.length" class="r-card">
        <view class="r-h" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-pen" style="width:30rpx;height:30rpx"/><text>逐处纠错（已记入错因本）</text></view>
        <view v-for="(it, i) in diag.issues" :key="i" class="iss">
          <view class="iss-top"><text class="iss-type">{{ it.type }}</text></view>
          <view class="iss-o" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-x-circle" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ it.original }}</text></view>
          <view class="iss-s" style="display:flex;align-items:flex-start;gap:8rpx"><view class="ic ic-check-circle" style="width:26rpx;height:26rpx;flex-shrink:0;margin-top:4rpx"/><text>{{ it.suggestion }}</text></view>
          <text v-if="it.explanation" class="iss-e">{{ it.explanation }}</text>
        </view>
      </view>

      <view class="r-btns">
        <button class="btn-ghost half" @tap="rewrite">改写本题</button>
        <button class="btn-primary half" @tap="phase = 'pick'">换一题</button>
      </view>
    </view>

    <Paywall :open="showPaywall" :feature="ent.feature('essay.diagnose')" emoji="✍️"
      title="作文诊断是会员专享" @close="showPaywall = false" />
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { getEssayPrompts, analyzeEssayPrompt, diagnoseEssay, type EssayPrompt, type PromptAnalysis, type EssayDiagnosis } from '@/api/essay'
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
  phase.value = 'analyze'
}
function pickCustom() { customText.value = ''; phase.value = 'custom' }
async function analyzeCustom() {
  analyzing.value = true
  try {
    analysis.value = await analyzeEssayPrompt({ text: customText.value.trim() })
    curPromptId.value = null
    phase.value = 'analyze'
  } catch (e) { uni.showToast({ title: (e as Error).message || '审题失败', icon: 'none' }) }
  finally { analyzing.value = false }
}
function startWrite() {
  draft.value = ''; seconds.value = 0; phase.value = 'write'
  if (_timer) clearInterval(_timer)
  _timer = setInterval(() => { seconds.value++ }, 1000)
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
    phase.value = 'result'
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
</style>

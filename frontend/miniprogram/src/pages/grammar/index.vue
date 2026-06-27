<template>
  <view class="g-page">
    <view v-if="loading" class="center-tip">加载中…</view>

    <!-- ① 推进环主页 ────────────────────────────────────────── -->
    <view v-else-if="phase === 'home'">
      <view class="hero">
        <text class="hero-t">语法精进</text>
        <text class="hero-sub">真会才算会 · 识别→纠错→产出→迁移→隔期复测</text>
      </view>

      <view v-if="batch" class="home-body">
        <view class="stat-row">
          <view class="stat"><text class="stat-n">{{ batch.stats.mastered }}</text><text class="stat-l">已掌握</text></view>
          <view class="stat"><text class="stat-n">{{ batch.stats.due }}</text><text class="stat-l">待复测</text></view>
          <view class="stat"><text class="stat-n">{{ batch.stats.remaining_new }}</text><text class="stat-l">待学</text></view>
        </view>

        <!-- 间隔维持 -->
        <view v-if="batch.maintain.length" class="sec">
          <view class="sec-hd"><view class="ic ic-refresh" /><text>间隔维持 · 隔期复测</text></view>
          <view v-for="m in batch.maintain" :key="m.kp_id" class="kp-row" @tap="startRetention(m.kp_id, m.kp_name)">
            <text class="kp-name">{{ m.kp_name }}</text>
            <text class="kp-tag warn">复测</text>
          </view>
        </view>

        <!-- 新点推进 -->
        <view class="sec">
          <view class="sec-hd"><view class="ic ic-flag" /><text>新点推进 · 学下一个</text></view>
          <view v-if="!batch.new.length" class="empty-tip">没有待学的新语法点了 🎉</view>
          <view v-for="(n, i) in batch.new" :key="n.kp_id" class="kp-row" @tap="startLearn(n.kp_id, n.name)">
            <text class="kp-idx">{{ i + 1 }}</text>
            <text class="kp-name">{{ n.name }}</text>
            <view class="kp-bar"><view class="kp-bar-in" :style="{ width: Math.round(n.recognize * 100) + '%' }" /></view>
          </view>
        </view>

        <!-- 综合运用 -->
        <view v-if="batch.apply" class="sec apply">
          <view class="sec-hd"><view class="ic ic-layers" /><text>综合运用</text></view>
          <text class="apply-hint">{{ batch.apply.hint }}</text>
        </view>
      </view>

      <view class="home-foot">
        <view class="btn-ghost" @tap="openPlacement"><view class="ic ic-target" /><text>分级测验(定起点)</text></view>
      </view>
    </view>

    <!-- ② 分级测验(CAT) ────────────────────────────────────── -->
    <view v-else-if="phase === 'placement'">
      <view v-if="!pl.done && pl.item" class="card">
        <view class="card-hd">
          <text class="card-step">定级中 · 已答 {{ pl.progress?.asked || 0 }} 题</text>
          <text class="card-skip" @tap="phase = 'home'">退出</text>
        </view>
        <text class="q-stem">{{ pl.item.item.stem }}</text>
        <view class="opts">
          <text v-for="(o, i) in pl.item.item.options" :key="i" class="opt" @tap="answerPlacement(o)">{{ o }}</text>
        </view>
        <text class="q-hint">凭直觉作答即可,这只是为你定起点</text>
      </view>

      <view v-else-if="pl.done" class="card">
        <view class="result-hd"><view class="ic ic-chart" /><text class="result-t2">你的语法掌握定位</text></view>

        <!-- 摘要条:实测两档高亮,推定两档置灰 -->
        <view class="heat-sum">
          <view class="sum-cell ok"><text class="sum-n">{{ heatStats.已会 }}</text><text class="sum-l">已会</text></view>
          <view class="sum-cell low"><text class="sum-n">{{ heatStats.重点补 }}</text><text class="sum-l">重点补</text></view>
          <view class="sum-cell none"><text class="sum-n">{{ heatStats.推定已会 }}</text><text class="sum-l">推定已会</text></view>
          <view class="sum-cell none"><text class="sum-n">{{ heatStats.未学 }}</text><text class="sum-l">未学</text></view>
        </view>

        <!-- 建议起点:最该立刻看的一条 -->
        <view v-if="pl.start_line" class="start-card">
          <text class="start-cap">建议从这里开始</text>
          <text class="start-name">{{ pl.start_line.name }}</text>
        </view>
        <text class="result-note">定级只是估个起点:「推定已会」是推断的、没实测;真正掌握靠之后逐点「四维过关 + 隔期复测」夯实。</text>

        <!-- 实测结果(有据):重点补在前、已会在后,高亮 -->
        <view v-if="heatTested.length" class="heat-list">
          <text class="heat-sec">实测结果 · {{ heatTested.length }}</text>
          <view v-for="h in heatTested" :key="h.kp_id" class="heat-row" :class="heatCls(h.status)">
            <text class="hr-name">{{ h.name }}</text><text class="hr-b">{{ h.status }}</text>
          </view>
        </view>

        <!-- 推定已会:未实测,置灰可折叠 -->
        <view v-if="heatInfer.length" class="heat-more" @tap="showInfer = !showInfer">
          {{ showInfer ? '收起推定已会' : ('展开推定已会 · ' + heatInfer.length + '(未实测)') }}
        </view>
        <view v-if="showInfer" class="heat-list">
          <view v-for="h in heatInfer" :key="h.kp_id" class="heat-row none">
            <text class="hr-name">{{ h.name }}</text><text class="hr-b">推定已会</text>
          </view>
        </view>

        <!-- 未学:置灰可折叠 -->
        <view v-if="heatUnlearned.length" class="heat-more" @tap="showUnlearned = !showUnlearned">
          {{ showUnlearned ? '收起未学点' : ('展开未学点 · ' + heatUnlearned.length) }}
        </view>
        <view v-if="showUnlearned" class="heat-list">
          <view v-for="h in heatUnlearned" :key="h.kp_id" class="heat-row none">
            <text class="hr-name">{{ h.name }}</text><text class="hr-b">未学</text>
          </view>
        </view>

        <view class="btn-primary" @tap="afterPlacement">开始按计划学 →</view>
      </view>
    </view>

    <!-- ③ 单点四维检测 ──────────────────────────────────────── -->
    <view v-else-if="phase === 'learn' && kp" class="card learn">
      <view class="card-hd">
        <text class="card-step" @tap="backHome">‹ 返回</text>
        <text v-if="kp.status" class="status-badge" :class="statusCls(kp.status.status)">{{ kp.status.label }}</text>
      </view>
      <text class="kp-title">{{ kp.kp_name }}</text>
      <view v-if="kp.status && kp.status.evidence.length" class="evidence">
        <text v-for="(e, i) in kp.status.evidence" :key="i" class="ev">{{ e }}</text>
      </view>

      <!-- 维度进度 -->
      <view class="axes">
        <view class="axis" :class="{ ok: kp.detect >= 0.85 }"><text>纠错</text><text>{{ pct(kp.detect) }}</text></view>
        <view class="axis" :class="{ ok: kp.produce_score >= 0.85 }"><text>产出</text><text>{{ pct(kp.produce_score) }}</text></view>
        <view class="axis" :class="{ ok: kp.transfer_ok }"><text>迁移</text><text>{{ kp.transfer_ok ? '✓' : '—' }}</text></view>
      </view>

      <!-- 识别/纠错探针 -->
      <view v-for="p in kp.probes" :key="p.key" class="probe">
        <text class="probe-q">{{ p.kind === 'detect' ? '【改错】' : '【选择】' }}{{ p.prompt }}</text>
        <view class="opts">
          <text v-for="(o, i) in p.options" :key="i" class="opt"
                :class="optCls(p.key, o)" @tap="pickProbe(p.key, o)">{{ o }}</text>
        </view>
        <view v-if="probeRes[p.key]" class="fb" :class="probeRes[p.key].correct ? 'ok' : 'no'">
          {{ probeRes[p.key].correct ? '✓ 答对了' : ('✗ 正确:' + probeRes[p.key].correct_answer) }}
          <text v-if="probeRes[p.key].misconception" class="mis"> · {{ probeRes[p.key].misconception }}</text>
        </view>
        <view v-else class="probe-submit" :class="{ dis: !probePick[p.key] }" @tap="submitProbe(p.key)">提交</view>
      </view>

      <!-- 产出造句 -->
      <view v-if="kp.produce" class="probe produce">
        <text class="probe-q">✍️ {{ kp.produce.prompt }}</text>
        <template v-if="!produceRes">
          <textarea v-model="produceInput" class="g-input" :maxlength="160" placeholder="用这个语法点写一句英文" auto-height />
          <view class="probe-submit" :class="{ dis: !produceInput.trim() || producing }" @tap="submitProduce">{{ producing ? '评分中…' : '提交造句' }}</view>
        </template>
        <view v-else class="pr-box" :class="produceRes.passed ? 'ok' : 'no'">
          <text class="pr-score">{{ produceRes.total }}/{{ produceRes.max }} · {{ produceRes.passed ? '达标 ✓' : '再打磨' }}</text>
          <view v-for="d in produceRes.dimensions" :key="d.key" class="pr-dim"><text>{{ d.label }}</text><text>{{ d.score }}/{{ d.max }}</text></view>
          <text v-if="produceRes.feedback" class="pr-fb">{{ produceRes.feedback }}</text>
          <text class="pr-redo" @tap="produceRes = null; produceInput = ''">重写</text>
        </view>
      </view>

      <!-- 迁移检测 -->
      <view v-if="kp.has_transfer" class="probe transfer">
        <view v-if="!tf.started" class="probe-submit ghost" @tap="startTransfer">迁移检测 · 换个新句子</view>
        <template v-else-if="tf.probe">
          <text class="probe-q">{{ tf.probe.prompt }}</text>
          <view class="opts">
            <text v-for="(o, i) in tf.probe.options" :key="i" class="opt" :class="{ on: tf.pick === o }" @tap="tf.pick = o">{{ o }}</text>
          </view>
          <view v-if="!tf.result" class="probe-submit" :class="{ dis: !tf.pick }" @tap="submitTransfer">提交</view>
          <view v-else class="fb" :class="tf.result.correct ? 'ok' : 'no'">
            {{ tf.result.verdict === 'transferred' ? '✓ 真懂了(能迁移到新语境)' : '✗ 像是记住了原题,正确:' + tf.result.correct_answer }}
          </view>
        </template>
      </view>

      <view v-if="kp.mastered" class="mastered-tip">四维通过!隔 3 天后会有一次复测,通过即「已掌握」。</view>
    </view>

    <!-- 复测 -->
    <view v-else-if="phase === 'retention' && rt.probe" class="card">
      <view class="card-hd"><text class="card-step" @tap="backHome">‹ 返回</text><text class="status-badge warn">隔期复测</text></view>
      <text class="kp-title">{{ rt.name }}</text>
      <text class="probe-q">{{ rt.probe.prompt }}</text>
      <view class="opts">
        <text v-for="(o, i) in rt.probe.options" :key="i" class="opt" :class="{ on: rt.pick === o }" @tap="rt.pick = o">{{ o }}</text>
      </view>
      <view v-if="!rt.result" class="probe-submit" :class="{ dis: !rt.pick }" @tap="submitRetention">提交</view>
      <view v-else class="fb" :class="rt.result.correct ? 'ok' : 'no'">
        {{ rt.result.verdict === 'retained' ? '✓ 仍记得,掌握确认!' : '✗ 有点遗忘,重新学一下' }}
        <view class="probe-submit" style="margin-top:16rpx" @tap="backHome">返回</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { onShow } from '@dcloudio/uni-app'
import {
  getDailyPath, getKpProbes, submitKpProbe, submitKpProduce, getKpTransfer, submitKpTransfer,
  getKpRetention, submitKpRetention, placementStart, placementAnswer,
} from '@/api/grammar'
import type {
  DailyBatch, GrammarProbesOut, GrammarProbeResult, GrammarProduceResult, GrammarProbe,
  PlacementState,
} from '@/api/grammar'

const loading = ref(true)
const phase = ref<'home' | 'placement' | 'learn' | 'retention'>('home')
const batch = ref<DailyBatch | null>(null)

const kp = ref<GrammarProbesOut | null>(null)
const probePick = ref<Record<string, string>>({})
const probeRes = ref<Record<string, GrammarProbeResult>>({})
const produceInput = ref('')
const produceRes = ref<GrammarProduceResult | null>(null)
const producing = ref(false)
const tf = reactive({ started: false, probe: null as GrammarProbe | null, pick: '', result: null as any })
const rt = reactive({ kpId: '', name: '', probe: null as GrammarProbe | null, pick: '', result: null as any })
const pl = reactive<PlacementState>({ done: false })
const showInfer = ref(false)
const showUnlearned = ref(false)
const heatStats = computed(() => {
  const s: Record<string, number> = { 已会: 0, 重点补: 0, 推定已会: 0, 未学: 0 }
  for (const h of (pl.heatmap || [])) s[h.status] = (s[h.status] || 0) + 1
  return s
})
// 实测/有据(高亮):重点补优先列在前,再已会
const heatTested = computed(() => (pl.heatmap || []).filter(h => h.tested)
  .sort((a, b) => (a.status === '重点补' ? 0 : 1) - (b.status === '重点补' ? 0 : 1)))
const heatInfer = computed(() => (pl.heatmap || []).filter(h => h.status === '推定已会'))
const heatUnlearned = computed(() => (pl.heatmap || []).filter(h => h.status === '未学'))

function pct(v: number) { return Math.round((v || 0) * 100) + '%' }
function heatCls(s: string) { return ({ 已会: 'ok', 重点补: 'low', 推定已会: 'none', 未学: 'none' } as Record<string, string>)[s] || 'none' }
function statusCls(s: string) { return ({ mastered: 'ok', due_retain: 'warn', retaining: 'mid', learning: 'mid', new: 'none' } as Record<string, string>)[s] || 'none' }

async function loadHome() {
  loading.value = true
  try { batch.value = await getDailyPath() } catch (e) { uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
function backHome() { phase.value = 'home'; loadHome() }

// ── 单点四维 ──
async function startLearn(kpId: string, name: string) {
  loading.value = true; phase.value = 'learn'
  probePick.value = {}; probeRes.value = {}; produceInput.value = ''; produceRes.value = null
  Object.assign(tf, { started: false, probe: null, pick: '', result: null })
  try { kp.value = await getKpProbes(kpId) } catch { kp.value = { kp_id: kpId, kp_name: name } as any; uni.showToast({ title: '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}
function pickProbe(key: string, o: string) { if (!probeRes.value[key]) probePick.value = { ...probePick.value, [key]: o } }
function optCls(key: string, o: string) {
  const r = probeRes.value[key]
  if (!r) return { on: probePick.value[key] === o }
  return { ok: o === r.correct_answer, no: probePick.value[key] === o && o !== r.correct_answer }
}
async function submitProbe(key: string) {
  const ans = probePick.value[key]; if (!ans || !kp.value) return
  try {
    const r = await submitKpProbe(kp.value.kp_id, key, ans)
    probeRes.value = { ...probeRes.value, [key]: r }
    if (kp.value) { kp.value.detect = r.detect; kp.value.recognize = r.recognize; kp.value.mastered = r.mastered }
  } catch { uni.showToast({ title: '提交失败', icon: 'none' }) }
}
async function submitProduce() {
  const s = produceInput.value.trim(); if (!s || producing.value || !kp.value) return
  producing.value = true
  try {
    const r = await submitKpProduce(kp.value.kp_id, s)
    if (r.graded === false) { uni.showToast({ title: '评分服务暂忙,请重试', icon: 'none' }); return }
    produceRes.value = r
    if (kp.value) { kp.value.produce_score = r.produce_score; kp.value.mastered = r.mastered }
  } catch { uni.showToast({ title: '评分失败', icon: 'none' }) }
  finally { producing.value = false }
}
async function startTransfer() {
  if (!kp.value) return
  tf.started = true
  try { const r = await getKpTransfer(kp.value.kp_id); tf.probe = r.probe } catch { uni.showToast({ title: '加载失败', icon: 'none' }) }
}
async function submitTransfer() {
  if (!tf.pick || !tf.probe || !kp.value) return
  try {
    const r = await submitKpTransfer(kp.value.kp_id, tf.probe.key, tf.pick)
    tf.result = r
    if (kp.value) { kp.value.transfer_ok = r.transfer_ok; kp.value.mastered = r.mastered }
  } catch { uni.showToast({ title: '提交失败', icon: 'none' }) }
}

// ── 复测 ──
async function startRetention(kpId: string, name: string) {
  phase.value = 'retention'; Object.assign(rt, { kpId, name, probe: null, pick: '', result: null })
  try { const r = await getKpRetention(kpId); rt.probe = r.probe } catch { uni.showToast({ title: '加载失败', icon: 'none' }) }
}
async function submitRetention() {
  if (!rt.pick || !rt.probe) return
  try { rt.result = await submitKpRetention(rt.kpId, rt.probe.key, rt.pick) }
  catch { uni.showToast({ title: '提交失败', icon: 'none' }) }
}

// ── 分级测验 ──
async function openPlacement() {
  Object.assign(pl, { done: false, item: undefined, heatmap: undefined, start_line: undefined })
  showInfer.value = false
  showUnlearned.value = false
  phase.value = 'placement'
  try {
    const r = await placementStart({})
    Object.assign(pl, r)
  } catch (e) { uni.showToast({ title: (e as Error).message || '题库不足', icon: 'none' }); phase.value = 'home' }
}
async function answerPlacement(o: string) {
  if (!pl.session_id || !pl.item) return
  const sid = pl.session_id; const kid = pl.item.kp_id
  try { const r = await placementAnswer(sid, kid, o); Object.assign(pl, r) }
  catch { uni.showToast({ title: '提交失败', icon: 'none' }) }
}
function afterPlacement() {
  if (pl.start_line) startLearn(pl.start_line.kp_id, pl.start_line.name)
  else backHome()
}

onShow(() => { if (phase.value === 'home') loadHome() })
</script>

<style scoped>
.g-page { min-height: 100vh; background: var(--c-bg-page, #eef3fb); padding: 24rpx; box-sizing: border-box; }
.center-tip { text-align: center; color: var(--c-text-hint); padding: 120rpx 0; }
.hero { padding: 16rpx 8rpx 24rpx; }
.hero-t { display: block; font-size: 44rpx; font-weight: 900; color: var(--c-ink); }
.hero-sub { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.stat-row { display: flex; gap: 16rpx; margin-bottom: 20rpx; }
.stat { flex: 1; background: var(--c-bg-card, #fff); border-radius: 20rpx; padding: 22rpx 0; text-align: center; box-shadow: 0 4rpx 20rpx rgba(0,0,0,.04); }
.stat-n { display: block; font-size: 40rpx; font-weight: 900; color: var(--c-primary-deep, #2f6fd6); }
.stat-l { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 4rpx; }
.sec { background: var(--c-bg-card, #fff); border-radius: 20rpx; padding: 24rpx; margin-bottom: 20rpx; box-shadow: 0 4rpx 20rpx rgba(0,0,0,.04); }
.sec-hd { display: flex; align-items: center; gap: 10rpx; font-size: 28rpx; font-weight: 800; color: var(--c-ink); margin-bottom: 16rpx; }
.sec-hd .ic { width: 34rpx; height: 34rpx; }
.kp-row { display: flex; align-items: center; gap: 14rpx; padding: 18rpx 4rpx; border-bottom: 2rpx solid #f1f4f9; }
.kp-row:last-child { border-bottom: none; }
.kp-idx { width: 36rpx; height: 36rpx; line-height: 36rpx; text-align: center; font-size: 22rpx; font-weight: 800; color: var(--c-primary-deep); background: var(--c-primary-faint, #e8f1ff); border-radius: 50%; }
.kp-name { flex: 1; font-size: 30rpx; color: var(--c-ink); font-weight: 600; }
.kp-bar { width: 120rpx; height: 12rpx; background: #eef2f7; border-radius: 6rpx; overflow: hidden; }
.kp-bar-in { height: 100%; background: var(--c-primary, #3d8bf5); }
.kp-tag { font-size: 22rpx; padding: 4rpx 14rpx; border-radius: 20rpx; }
.kp-tag.warn { color: #ff8a3d; background: #fff1e6; }
.empty-tip, .apply-hint { font-size: 26rpx; color: var(--c-text-hint); line-height: 1.6; }
.sec.apply { background: linear-gradient(160deg, #eef6ff, #f7fbff); }
.home-foot { margin-top: 8rpx; }
.btn-ghost { display: flex; align-items: center; justify-content: center; gap: 10rpx; background: var(--c-bg-card, #fff); border: 2rpx solid var(--c-primary, #3d8bf5); color: var(--c-primary-deep); border-radius: var(--r-pill, 999rpx); padding: 22rpx; font-size: 28rpx; font-weight: 700; }
.btn-ghost .ic { width: 32rpx; height: 32rpx; }
.btn-primary { background: var(--c-primary, #3d8bf5); color: #fff; border-radius: var(--r-pill, 999rpx); padding: 24rpx; font-size: 30rpx; font-weight: 800; text-align: center; margin-top: 24rpx; }
.card { background: var(--c-bg-card, #fff); border-radius: 24rpx; padding: 32rpx 28rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.05); }
.card-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18rpx; }
.card-step { font-size: 26rpx; color: var(--c-text-hint); }
.card-skip { font-size: 26rpx; color: var(--c-text-hint); }
.q-stem, .kp-title { display: block; font-size: 34rpx; font-weight: 700; color: var(--c-ink); line-height: 1.6; }
.kp-title { font-size: 38rpx; font-weight: 900; margin-bottom: 10rpx; }
.q-hint { display: block; font-size: 22rpx; color: var(--c-text-hint); margin-top: 18rpx; }
.opts { display: flex; flex-direction: column; gap: 14rpx; margin: 22rpx 0 8rpx; }
.opt { padding: 22rpx 24rpx; border-radius: 16rpx; background: #f5f7fa; font-size: 30rpx; color: var(--c-ink); border: 3rpx solid transparent; }
.opt.on { border-color: var(--c-primary); background: var(--c-primary-faint); color: var(--c-primary-deep); font-weight: 700; }
.opt.ok { border-color: #18a058; background: #e6f8ee; color: #18a058; font-weight: 700; }
.opt.no { border-color: #e64f4f; background: #fdecec; color: #e64f4f; }
.result-hd { display: flex; align-items: center; justify-content: center; gap: 12rpx; margin-bottom: 22rpx; }
.result-hd .ic { width: 38rpx; height: 38rpx; }
.result-t2 { font-size: 34rpx; font-weight: 900; color: var(--c-ink); }
/* 摘要条 */
.heat-sum { display: flex; gap: 12rpx; margin-bottom: 24rpx; }
.sum-cell { flex: 1; border-radius: 18rpx; padding: 18rpx 0; display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.sum-cell.ok { background: #e6f8ee; } .sum-cell.mid { background: #fff6e6; } .sum-cell.low { background: #fdecec; } .sum-cell.none { background: #f1f4f9; }
.sum-n { font-size: 40rpx; font-weight: 900; color: var(--c-ink); }
.sum-l { font-size: 22rpx; color: var(--c-text-hint); }
/* 建议起点 */
.start-card { background: linear-gradient(135deg, var(--c-primary, #3d8bf5), #5fa3ff); border-radius: 20rpx; padding: 26rpx; margin-bottom: 22rpx; display: flex; flex-direction: column; gap: 8rpx; }
.start-cap { font-size: 24rpx; color: rgba(255,255,255,.85); }
.start-name { font-size: 36rpx; font-weight: 900; color: #fff; }
.result-note { display: block; font-size: 22rpx; color: var(--c-text-hint); line-height: 1.6; margin: 0 0 18rpx; }
/* 条目列表 */
.heat-sec { display: block; font-size: 24rpx; color: var(--c-text-hint); font-weight: 700; margin: 6rpx 0 12rpx; }
.heat-list { display: flex; flex-direction: column; gap: 12rpx; }
.heat-row { display: flex; align-items: center; justify-content: space-between; gap: 14rpx; border-radius: 14rpx; padding: 18rpx 20rpx; border-left: 8rpx solid #c7d0dc; background: #f7f9fc; }
.heat-row.ok { border-left-color: #18a058; background: #f0faf4; }
.heat-row.mid { border-left-color: #ff8a3d; background: #fff8ef; }
.heat-row.low { border-left-color: #e64f4f; background: #fdf2f2; }
.heat-row.none { border-left-color: #c7d0dc; background: #f7f9fc; }
.hr-name { flex: 1; font-size: 28rpx; font-weight: 600; color: var(--c-ink); }
.hr-b { font-size: 22rpx; color: var(--c-text-hint); flex: none; }
.heat-more { text-align: center; font-size: 26rpx; color: var(--c-primary-deep); padding: 18rpx; }
.status-badge { font-size: 24rpx; font-weight: 700; padding: 6rpx 18rpx; border-radius: 20rpx; }
.status-badge.ok { color: #18a058; background: #e6f8ee; } .status-badge.warn { color: #ff8a3d; background: #fff1e6; } .status-badge.mid { color: var(--c-primary-deep); background: var(--c-primary-faint); } .status-badge.none { color: var(--c-text-hint); background: #f1f4f9; }
.evidence { display: flex; flex-wrap: wrap; gap: 10rpx; margin-bottom: 16rpx; }
.ev { font-size: 22rpx; color: var(--c-text-second); background: #f5f7fa; padding: 6rpx 16rpx; border-radius: 16rpx; }
.axes { display: flex; gap: 14rpx; margin-bottom: 22rpx; }
.axis { flex: 1; background: #f5f7fa; border-radius: 16rpx; padding: 16rpx 0; text-align: center; display: flex; flex-direction: column; gap: 4rpx; font-size: 24rpx; color: var(--c-text-hint); }
.axis.ok { background: #e6f8ee; color: #18a058; font-weight: 700; }
.probe { padding: 22rpx 0; border-top: 2rpx dashed #eef2f7; }
.probe-q { display: block; font-size: 28rpx; font-weight: 600; color: var(--c-ink); line-height: 1.6; }
.probe-submit { margin-top: 14rpx; text-align: center; background: var(--c-primary); color: #fff; font-size: 28rpx; font-weight: 700; padding: 18rpx 0; border-radius: var(--r-pill, 999rpx); }
.probe-submit.dis { background: #d7dde6; }
.probe-submit.ghost { background: #fff; border: 2rpx solid var(--c-primary); color: var(--c-primary-deep); }
.fb { margin-top: 14rpx; font-size: 26rpx; padding: 16rpx; border-radius: 14rpx; }
.fb.ok { background: #e6f8ee; color: #18a058; } .fb.no { background: #fdecec; color: #e64f4f; }
.mis { color: var(--c-text-second); }
.g-input { width: 100%; box-sizing: border-box; min-height: 120rpx; background: #f5f7fa; border-radius: 14rpx; padding: 16rpx; font-size: 28rpx; line-height: 1.6; margin-top: 12rpx; }
.pr-box { margin-top: 14rpx; background: #f7f9fc; border-radius: 14rpx; padding: 18rpx; }
.pr-box.ok { background: #e6f8ee; } .pr-box.no { background: #fff6e6; }
.pr-score { display: block; font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.pr-dim { display: flex; justify-content: space-between; font-size: 25rpx; color: var(--c-text-second); margin-top: 8rpx; }
.pr-fb { display: block; font-size: 25rpx; color: var(--c-text-second); margin-top: 10rpx; line-height: 1.6; }
.pr-redo { display: inline-block; font-size: 26rpx; color: var(--c-primary-deep); font-weight: 700; margin-top: 12rpx; }
.mastered-tip { margin-top: 22rpx; font-size: 25rpx; color: #18a058; background: #e6f8ee; border-radius: 14rpx; padding: 16rpx; line-height: 1.6; }
</style>

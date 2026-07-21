<template>
  <view v-if="loading || net" class="wrn">
    <view class="wrn-head">
      <view class="wrn-title"><view class="ic ic-share" style="width:30rpx;height:30rpx" /><text>错题关系网{{ net && net.word ? ' · ' + net.word : '' }}</text></view>
      <text class="wrn-sub">点词看关系 · 主/次错题</text>
    </view>

    <view v-if="loading" class="wrn-tip">整理关系网中…</view>
    <template v-else-if="net && net.word_id">
      <!-- 多个正确点(多空):答案词 chip,点一个切到它的关系网 -->
      <view v-if="answers.length > 1" class="wrn-ans">
        <text class="wrn-ans-lb">本题选项</text>
        <text v-for="a in answers" :key="a.word_id" class="wrn-ans-chip"
          :class="[a.kind, { on: a.word_id === net.word_id, off: a.switchable === false }]"
          @tap="tapAns(a)">{{ a.word }}</text>
      </view>
      <!-- 辐射图:中心=当前词,周围=考点关系词(可点切换中心) -->
      <view class="wrn-canvas" :style="{ height: BOXH + 'rpx' }">
        <view v-for="(s, i) in satellites" :key="'e'+i" class="wrn-edge" :style="edgeStyle(s)" />
        <view v-for="(s, i) in satellites" :key="'l'+i" class="wrn-elabel"
          :style="{ left: (CX + (s.x - CX) * 0.62 - 26) + 'rpx', top: (CY + (s.y - CY) * 0.62 - 14) + 'rpx', background: relBg(s.rel), color: relFg(s.rel) }">{{ relLabel(s.rel) }}</view>
        <view v-for="(s, i) in satellites" :key="'n'+i" class="wrn-node" :class="{ link: !!s.word_id }"
          :style="{ left: (s.x - 72) + 'rpx', top: (s.y - 26) + 'rpx' }" @tap="tapNode(s)">
          <text class="wrn-word">{{ s.text }}</text>
        </view>
        <view class="wrn-center" :style="{ left: (CX - 104) + 'rpx', top: (CY - 48) + 'rpx' }" @tap="activeTab = 'main'">
          <text class="wrn-cword">{{ net.word }}</text>
          <text v-if="net.gloss" class="wrn-czh">{{ net.gloss }}</text>
        </view>
        <text v-if="!satellites.length" class="wrn-gen" :style="{ top: (CY + 64) + 'rpx' }">考点生成中…</text>
      </view>

      <!-- 联动 tab:主/次错题 + 考点维度 -->
      <view class="wrn-tabs">
        <scroll-view scroll-x class="wrn-tabrow">
          <text class="wrn-tab main" :class="{ on: activeTab === 'main' }" @tap="activeTab = 'main'">主·考{{ net.word }} ({{ net.main.length }})</text>
          <text class="wrn-tab sec" :class="{ on: activeTab === 'secondary' }" @tap="activeTab = 'secondary'">次·当干扰 ({{ net.secondary.length }})</text>
          <text v-for="d in net.dims" :key="d.key" class="wrn-tab kp" :class="{ on: activeTab === d.key }" @tap="activeTab = d.key">{{ d.label }}</text>
        </scroll-view>
      </view>

      <!-- 主/次错题清单 -->
      <template v-if="activeTab === 'main' || activeTab === 'secondary'">
        <view v-if="!activeErrs.length" class="wrn-empty">{{ activeTab === 'main' ? '暂无「考它」的错题' : '暂无「它当干扰」的错题' }}</view>
        <view v-for="e in activeErrs" :key="e.wrong_record_id" class="wrn-ec" @tap="openErr(e)">
          <text class="wrn-eq">{{ e.stem }}</text>
          <view class="wrn-em">
            <text v-if="e.student_answer" class="wr">你选 {{ e.student_answer }}</text>
            <text v-if="e.correct_answer" class="ok">正确 {{ e.correct_answer }}</text>
            <text v-if="e.source" class="src">{{ e.source }}</text>
          </view>
        </view>
      </template>

      <!-- 考点维度内容 -->
      <template v-else>
        <view v-if="activeDim" class="wrn-kp">
          <view v-for="(it, i) in activeDim.items" :key="i" class="kp-line" :class="{ low: it.confidence === 'low', reported: it.id && kpReported[it.id] }">
            <view class="kp-line-body">
              <text class="kp-en">{{ it.text }}<text v-if="it.confidence === 'low'" class="kp-low"> 待核</text></text>
              <text v-if="it.zh || it.note" class="kp-zh">{{ it.zh }}{{ it.note ? (it.zh ? ' · ' : '') + it.note : '' }}</text>
            </view>
            <view v-if="it.id" class="ic ic-flag kp-report" :class="{ done: kpReported[it.id] }" @tap.stop="reportKp(it)" />
          </view>
        </view>
        <button class="wrn-test" :class="{ dis: testLoading }" @tap="openTest">{{ testLoading ? '出题中…' : '考点扩展测试' }}</button>
      </template>
    </template>

    <PracticeQuiz v-if="testOpen" kp="考点扩展" :questions="testQs" :swapper="kpSwapper" @finishDetail="onKpDetail" @close="testOpen = false" />
  </view>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch } from 'vue'
import { getWordNetOfRecord, getWordNet } from '@/api/wrongQuestions'
import type { WordNet, WordNetErr, WordNetKpItem } from '@/api/wrongQuestions'
import { getKpTest, swapKpMcq, reportRelation, recordKpPractice } from '@/api/vocabulary'
import type { KpTestQuestion } from '@/api/vocabulary'
import PracticeQuiz from '@/components/PracticeQuiz.vue'

const props = defineProps<{ wrongRecordId: string }>()

// 报错某条考点(点旗标):report_count++,即时灰掉,待后台复核/低峰 AI 修正
const kpReported = reactive<Record<string, boolean>>({})
async function reportKp(it: WordNetKpItem) {
  if (!it.id || kpReported[it.id]) return
  kpReported[it.id] = true
  try {
    await reportRelation(it.id)
    uni.showToast({ title: '已反馈,待复核', icon: 'none' })
  } catch {
    kpReported[it.id] = false
    uni.showToast({ title: '反馈失败,请重试', icon: 'none' })
  }
}

const REL: Record<string, { c: string; bg: string; fg: string; label: string }> = {
  synonym: { c: '#639922', bg: '#EAF3DE', fg: '#3B6D11', label: '近义' },
  antonym: { c: '#E24B4A', bg: '#FCEBEB', fg: '#A32D2D', label: '反义' },
  confusion: { c: '#EF9F27', bg: '#FAEEDA', fg: '#854F0B', label: '易混' },
  ambiguity: { c: '#7F77DD', bg: '#EEEDFE', fg: '#534AB7', label: '歧义' },
  derivation: { c: '#1D9E75', bg: '#E1F5EE', fg: '#0F6E56', label: '派生' },
  tense: { c: '#1D9E75', bg: '#E1F5EE', fg: '#0F6E56', label: '时态' },
  plural: { c: '#1D9E75', bg: '#E1F5EE', fg: '#0F6E56', label: '单复数' },
  comparative: { c: '#1D9E75', bg: '#E1F5EE', fg: '#0F6E56', label: '比较级' },
  collocation: { c: '#6A8CB5', bg: '#EEF3F9', fg: '#3A5A7D', label: '搭配' },
}
const relLabel = (k: string) => REL[k]?.label || '相关'
const relBg = (k: string) => REL[k]?.bg || '#E6F1FB'
const relFg = (k: string) => REL[k]?.fg || '#185FA5'
const relC = (k: string) => REL[k]?.c || '#85B7EB'

const BOXW = 690, CX = 345, CY = 222, R = 188, BOXH = 456

const net = ref<WordNet | null>(null)
const loading = ref(true)
const centerId = ref<string | null>(null)   // 切换中心用;null=按错题入口
const activeTab = ref<string>('main')
const answers = ref<Array<{ word_id: string; word: string; zh: string }>>([])   // 本题答案词(切换中心时保持)
const testOpen = ref(false)
const testLoading = ref(false)
const testQs = ref<Array<{ id: string; stem: string; options: string[]; answer: string; explanation: string }>>([])

async function load() {
  loading.value = true
  try {
    const r = centerId.value ? await getWordNet(centerId.value) : await getWordNetOfRecord(props.wrongRecordId)
    net.value = r
    if (r.answers && r.answers.length) answers.value = r.answers   // 仅错题入口带答案列表,切换中心不覆盖
    activeTab.value = 'main'
  } catch { net.value = null }
  finally { loading.value = false }
}
watch(() => props.wrongRecordId, (v) => { if (v) { centerId.value = null; answers.value = []; load() } }, { immediate: true })

// 关系词(辐射图卫星):可链词维项(可切换中心)+ 固定搭配短语(2A,点跳搭配 tab);最多 6,优先有 word_id 的
const satellites = computed(() => {
  const n = net.value
  if (!n) return [] as Array<{ text: string; word_id: string | null; rel: string; x: number; y: number }>
  const items: Array<{ text: string; word_id: string | null; rel: string }> = []
  for (const d of n.dims) {
    if (!d.relational) continue
    for (const it of d.items) items.push({ text: it.text, word_id: it.word_id, rel: d.key })
  }
  // 2A:功能词等可链词少时,补固定搭配短语作节点(不可切换,点=跳搭配 tab)
  const colloc = n.dims.find(d => d.key === 'collocation')
  if (colloc) for (const it of colloc.items) items.push({ text: it.text, word_id: null, rel: 'collocation' })
  items.sort((a, b) => (a.word_id ? 0 : 1) - (b.word_id ? 0 : 1))
  const top = items.slice(0, 6)
  const m = top.length
  return top.map((it, i) => {
    const ang = (-90 + i * (360 / Math.max(m, 1))) * Math.PI / 180
    return { ...it, x: CX + R * Math.cos(ang), y: CY + R * Math.sin(ang) }
  })
})
function edgeStyle(s: { x: number; y: number; rel: string }) {
  const dx = s.x - CX, dy = s.y - CY
  const len = Math.sqrt(dx * dx + dy * dy)
  const ang = Math.atan2(dy, dx) * 180 / Math.PI
  return `left:${CX}rpx; top:${CY - 2}rpx; width:${len}rpx; transform:rotate(${ang}deg); transform-origin:0 50%; background:${relC(s.rel)};`
}

const activeErrs = computed<WordNetErr[]>(() =>
  activeTab.value === 'main' ? (net.value?.main || []) : (net.value?.secondary || []))
const activeDim = computed(() => net.value?.dims.find(d => d.key === activeTab.value) || null)

// 叶子节点:不下钻,点它跳到对应考点维度 tab 看解释
function tapNode(s: { rel?: string }) {
  if (s.rel) activeTab.value = s.rel
}
// 顶部答案 chip:有错题记录(switchable)才切中心;空壳(如缩写只当 chip)只标色不可切
function tapAns(a: { word_id: string; switchable?: boolean }) {
  if (a.switchable === false) { uni.showToast({ title: '该词暂无关联错题', icon: 'none' }); return }
  switchCenter({ word_id: a.word_id })
}
function switchCenter(s: { word_id: string | null }) {
  if (!s.word_id || s.word_id === net.value?.word_id) return
  centerId.value = s.word_id
  load()
}
function openErr(e: WordNetErr) {
  uni.navigateTo({ url: '/pages/wrong-questions/detail?id=' + e.wrong_record_id })
}
// 考点扩展测试逐题维度映射(id→{dim,stem}),做完把错误维回传成练习衍生错题
const kpDimMap = new Map<string, { dim: string; stem: string }>()
const kpTestWid = ref('')
async function openTest() {
  const wid = net.value?.word_id
  if (!wid || testLoading.value) return
  testLoading.value = true
  try {
    const qs: KpTestQuestion[] = await getKpTest(wid, net.value?.sense_id || undefined)   // 限定当前义项
    if (!qs.length) { uni.showToast({ title: '该词暂无考点题', icon: 'none' }); return }
    kpTestWid.value = wid
    kpDimMap.clear()
    qs.forEach(q => kpDimMap.set(q.id, { dim: q.dimension, stem: q.stem }))
    testQs.value = qs.map(q => ({ id: q.id, stem: `【${q.dimension_label}】${q.stem}`, options: q.options, answer: q.answer, explanation: q.explanation }))
    testOpen.value = true
  } catch { uni.showToast({ title: '出题失败,稍后重试', icon: 'none' }) }
  finally { testLoading.value = false }
}
// 换一题:报错该题 + 换同维度另一道
async function kpSwapper(q: { id: string }) {
  const nq = await swapKpMcq(q.id) as KpTestQuestion
  if (!nq || !nq.id) return null
  kpDimMap.set(nq.id, { dim: nq.dimension, stem: nq.stem })
  return { id: nq.id, stem: `【${nq.dimension_label}】${nq.stem}`, options: nq.options, answer: nq.answer, explanation: nq.explanation }
}
// 逐题结果回传:错误维 → 练习衍生错题(隔离);对 → 连对+1达2掌握清除
async function onKpDetail(results: Array<{ id: string; correct: boolean }>) {
  const payload = results
    .map(r => ({ ...kpDimMap.get(r.id), correct: r.correct }))
    .filter((p): p is { dim: string; stem: string; correct: boolean } => !!p.dim)
    .map(p => ({ dim: p.dim, correct: p.correct, stem: p.stem }))
  if (payload.length && kpTestWid.value) {
    try { await recordKpPractice(kpTestWid.value, payload) } catch { /* 静默 */ }
  }
}
</script>

<style scoped>
.wrn { background: #fff; border-radius: 20rpx; padding: 22rpx; margin-top: 20rpx; }
.wrn-head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 8rpx; }
.wrn-title { display: flex; align-items: center; gap: 8rpx; font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.wrn-sub { font-size: 22rpx; color: #9aa3b0; }
.wrn-tip, .wrn-empty { text-align: center; color: #9aa3b0; font-size: 26rpx; padding: 40rpx 0; }
.wrn-ans { display: flex; align-items: center; flex-wrap: wrap; gap: 12rpx; padding: 6rpx 0 12rpx; }
.wrn-ans-lb { font-size: 22rpx; color: #9aa3b0; }
.wrn-ans-chip { font-size: 25rpx; padding: 8rpx 22rpx; border-radius: 26rpx; border: 1rpx solid #E3E8EF; }
.wrn-ans-chip.correct { background: #E6F1FB; border-color: #85B7EB; color: #185FA5; }   /* 正确值·蓝 */
.wrn-ans-chip.wrong { background: #FCEBEB; border-color: #E88; color: #A32D2D; }        /* 学生错选·红 */
.wrn-ans-chip.other { background: #F1EFE8; border-color: #D3D1C7; color: #6b665e; }     /* 其他干扰·灰 */
.wrn-ans-chip.on { background: #E1F5EE; border-color: #1D9E75; color: #0F6E56; font-weight: 700; }   /* 当前中心 */
.wrn-ans-chip.off { opacity: .5; }   /* 无错题记录·不可切 */
.wrn-canvas { position: relative; width: 690rpx; }
.wrn-edge { position: absolute; height: 4rpx; border-radius: 2rpx; }
.wrn-elabel { position: absolute; width: 52rpx; height: 28rpx; line-height: 28rpx; text-align: center; font-size: 20rpx; font-weight: 500; border-radius: 8rpx; }
.wrn-node { position: absolute; width: 144rpx; box-sizing: border-box; height: 52rpx; display: flex; align-items: center; justify-content: center; padding: 0 8rpx; background: #E6F1FB; border: 2rpx solid #85B7EB; border-radius: 14rpx; }
.wrn-node.link { background: #E6F1FB; border-color: #5B9BE8; }
.wrn-word { font-size: 24rpx; font-weight: 600; color: #0C447C; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.wrn-gen { position: absolute; left: 0; width: 690rpx; text-align: center; font-size: 22rpx; color: #9aa3b0; }
.wrn-center { position: absolute; width: 208rpx; box-sizing: border-box; height: 96rpx; border-radius: 20rpx; background: #E1F5EE; border: 3rpx solid #1D9E75; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 6rpx 14rpx; }
.wrn-cword { max-width: 180rpx; font-size: 30rpx; font-weight: 700; color: #0F6E56; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.wrn-czh { max-width: 180rpx; font-size: 20rpx; color: #0F6E56; margin-top: 2rpx; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
.wrn-tabs { margin-top: 8rpx; padding-top: 12rpx; border-top: 1rpx solid #EEF2F7; }
.wrn-tabrow { white-space: nowrap; }
.wrn-tab { display: inline-block; font-size: 24rpx; padding: 10rpx 22rpx; margin-right: 12rpx; border-radius: 26rpx; border: 1rpx solid #E3E8EF; color: #6b7178; background: #F7F9FC; }
.wrn-tab.main.on { background: #E1F5EE; border-color: #1D9E75; color: #0F6E56; font-weight: 700; }
.wrn-tab.sec.on { background: #FAEEDA; border-color: #EF9F27; color: #854F0B; font-weight: 700; }
.wrn-tab.kp.on { background: #E6F1FB; border-color: #85B7EB; color: #185FA5; font-weight: 700; }
.wrn-ec { border: 1rpx solid #EEF2F7; border-radius: 14rpx; padding: 14rpx 16rpx; margin-top: 12rpx; background: #FBFCFE; }
.wrn-ec:active { background: #f2f6fc; }
.wrn-eq { display: block; font-size: 26rpx; color: #2a3138; line-height: 1.5; }
.wrn-em { display: flex; flex-wrap: wrap; gap: 14rpx; margin-top: 8rpx; font-size: 22rpx; }
.wrn-em .wr { color: #A32D2D; }
.wrn-em .ok { color: #0F6E56; }
.wrn-em .src { color: #9aa3b0; }
.wrn-kp { padding: 14rpx 0 4rpx; }
.kp-chips { display: flex; flex-wrap: wrap; gap: 10rpx; }
.kp-chip { font-size: 24rpx; color: #0C447C; background: #D6E6FA; padding: 6rpx 16rpx; border-radius: 10rpx; }
.kp-chip.link { background: #C3DEFA; border: 1rpx solid #8FBDEF; }
.kp-chip-zh { color: #4A6785; font-size: 22rpx; }
.kp-line { display: flex; align-items: flex-start; justify-content: space-between; gap: 12rpx; margin: 6rpx 0; }
.kp-line-body { flex: 1; min-width: 0; display: flex; align-items: baseline; flex-wrap: wrap; gap: 12rpx; }
.kp-en { font-size: 26rpx; color: #0C447C; font-weight: 500; }
.kp-line.low .kp-en { color: #8a857c; }
.kp-line.reported { opacity: .4; text-decoration: line-through; }
.kp-report.ic { width: 30rpx; height: 30rpx; flex-shrink: 0; margin-top: 4rpx; opacity: .5; }
.kp-report.ic.done { opacity: .25; }
.kp-low { font-size: 18rpx; color: #b0a99e; }
.kp-zh { flex: 1; font-size: 24rpx; color: #4A6785; }
.wrn-test { margin-top: 14rpx; background: var(--c-primary); color: #fff; font-size: 28rpx; font-weight: 700; border-radius: var(--r-pill); padding: 16rpx 0; }
.wrn-test.dis { opacity: .6; }
</style>

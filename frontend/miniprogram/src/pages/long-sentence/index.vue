<!-- src/pages/long-sentence/index.vue — 长难句学习 -->
<template>
  <view class="ls-page">
    <view v-if="loading" class="center-tip">加载中…</view>
    <view v-else-if="!items.length" class="center-tip">暂无长难句(运营审核发布后可见)</view>

    <view v-else class="scroll">
      <!-- 顶部:今日学习进度 + 打卡 -->
      <view class="header">
        <view class="prog">
          <text class="prog-label">今日学习 <text class="prog-num">{{ index + 1 }}</text>/{{ items.length }} 句</text>
          <view class="prog-bar"><view class="prog-fill" :style="{ width: pct + '%' }" /></view>
        </view>
        <view class="checkin" @tap="soon('打卡日历')"><text>📅 打卡日历</text></view>
      </view>

      <!-- 句子卡 -->
      <view class="card">
        <view class="sent-head">
          <view class="hl">
            <text class="sent-tag">句子 {{ index + 1 }}</text>
            <text class="fav" @tap="soon('收藏')">⭐ 收藏</text>
          </view>
          <view class="pager">
            <text class="pg" :class="{ dis: index === 0 }" @tap="prev">‹ 上一句</text>
            <text class="pg primary" :class="{ dis: index >= items.length - 1 }" @tap="next">下一句 ›</text>
          </view>
        </view>

        <!-- 原句:连续流式段落,每段彩色虚线下划线,序号锚在该段首词下 -->
        <view v-if="showStruct && segments.length" class="sentence">
          <text v-for="s in segments" :key="s.idx" class="seg" :style="{ color: colorOf(s.idx), borderBottomColor: colorOf(s.idx) }"><text class="fw">{{ s.first }}<text class="badge" :style="{ background: colorOf(s.idx) }">{{ s.idx }}</text></text>{{ (s.rest ? ' ' + s.rest : '') + ' ' }}</text>
        </view>
        <text v-else class="plain">{{ detail?.text }}</text>

        <view v-if="showTranslate && analysis?.translation" class="trans">{{ analysis.translation }}</view>

        <!-- 颜色说明(图例):取本句实际出现的颜色,色块 → 成分类型 -->
        <view v-if="showStruct && legend.length" class="legend-wrap">
          <text class="legend-toggle" @tap="showLegend = !showLegend">💡 颜色说明 {{ showLegend ? '▾' : '▸' }}</text>
          <view v-if="showLegend" class="legend">
            <view v-for="l in legend" :key="l.color" class="lg-item">
              <text class="lg-dot" :style="{ background: l.color }" />
              <text class="lg-tx">{{ l.label }}</text>
            </view>
            <text class="legend-note">同色系 = 同一类成分(橙=状语·绿=定语·蓝=主干·紫=名词性从句…),深浅区分小类。</text>
          </view>
        </view>

        <!-- 操作 pill 行 -->
        <view class="acts">
          <view class="act" :class="{ on: playing }" @tap="listen"><text class="act-ic">🔊</text><text class="act-tx">{{ playing ? '停止' : '听原句' }}</text></view>
          <view class="act" :class="{ rec: recording }" @tap="shadow"><text class="act-ic">{{ recording ? '⏺' : '🎤' }}</text><text class="act-tx">{{ recording ? '停止录音' : (scoring ? '评分中…' : '跟读') }}</text></view>
          <view class="act" @tap="showStruct = !showStruct"><text class="act-ic">👁</text><text class="act-tx">{{ showStruct ? '隐藏结构' : '显示结构' }}</text></view>
          <view class="act" @tap="showTranslate = !showTranslate"><text class="act-ic">📝</text><text class="act-tx">翻译</text></view>
          <view class="act" @tap="soon('更多')"><text class="act-ic">···</text><text class="act-tx">更多</text></view>
        </view>

        <!-- 跟读评分结果 -->
        <view v-if="scoring || shadowResult" class="shadow-box">
          <view v-if="scoring" class="sh-loading">🎯 正在评测发音…</view>
          <template v-else-if="shadowResult">
            <view class="sh-head">
              <text class="sh-score" :style="{ color: scoreColor(shadowResult.overall) }">{{ shadowResult.overall }}</text>
              <text class="sh-unit">分</text>
              <text class="sh-level" :style="{ background: scoreColor(shadowResult.overall) }">{{ shadowResult.level }}</text>
              <view v-if="shadowResult.accuracy != null" class="sh-subs">
                <text>准确 {{ shadowResult.accuracy }}</text>
                <text>流利 {{ shadowResult.fluency }}</text>
                <text>完整 {{ shadowResult.completion }}</text>
              </view>
            </view>
            <text v-if="shadowResult.tip" class="sh-tip">💡 {{ shadowResult.tip }}</text>
          </template>
        </view>
      </view>

      <!-- Tab 卡 -->
      <view class="card">
        <view class="tabs">
          <text v-for="t in TABS" :key="t.key" class="tab" :class="{ on: tab === t.key }" @tap="tab = t.key">{{ t.label }}</text>
        </view>

        <!-- 句子结构:思维导图(盒子 + 连线,横向可滚动)-->
        <view v-if="tab === 'struct'">
          <scroll-view scroll-x class="mm-scroll" v-if="tree.length">
            <view class="mm-canvas">
              <LsTreeNode v-for="r in tree" :key="r.idx" :node="r" :color-of="colorOf" :tint-of="tintOf" />
            </view>
          </scroll-view>
          <text v-else class="empty">暂无结构数据</text>
        </view>

        <!-- 句子成分 -->
        <view v-else-if="tab === 'comp'" class="tab-body">
          <view v-for="c in compRows" :key="c.label" class="comp-row">
            <text class="comp-label">{{ c.label }}</text><text class="comp-val">{{ c.val }}</text>
          </view>
          <text v-if="!compRows.length" class="empty">暂无成分数据</text>
        </view>

        <!-- 重点词汇 -->
        <view v-else-if="tab === 'words'" class="tab-body">
          <view v-for="(w, i) in (analysis?.key_words || [])" :key="i" class="word-row">
            <text class="word">{{ w.word }}</text><text class="word-pos" v-if="w.pos">{{ w.pos }}</text><text class="word-mean">{{ w.meaning }}</text>
          </view>
          <text v-if="!(analysis?.key_words || []).length" class="empty">暂无重点词汇</text>
        </view>

        <!-- 语法点 -->
        <view v-else class="tab-body">
          <view v-for="(g, i) in (analysis?.grammar_points || [])" :key="i" class="gp-row">
            <text class="gp-name">{{ g.name }}</text><text class="gp-exp" v-if="g.explanation">{{ g.explanation }}</text>
          </view>
          <text v-if="!(analysis?.grammar_points || []).length" class="empty">暂无语法点</text>
        </view>
      </view>

      <!-- 结构解析 -->
      <view class="card" v-if="analysis?.sentence_type || (analysis?.explanations || []).length || analysis?.summary">
        <view class="sec-row">
          <text class="sec-title">结构解析</text>
          <text class="link" @tap="soon('语法点详解')">查看语法点详解 ›</text>
        </view>
        <text v-if="analysis?.sentence_type" class="stype">这是一个{{ analysis.sentence_type.replace(/。$/, '') }}。</text>
        <view v-for="e in (analysis?.explanations || [])" :key="e.idx" class="exp-row">
          <text class="sno" :style="{ background: colorOf(e.idx) }">{{ e.idx }}</text>
          <text class="exp-text">{{ e.text }}</text>
        </view>
        <text v-if="analysis?.summary" class="summary">{{ analysis.summary }}</text>
      </view>

      <view class="footer-space" />
    </view>

    <!-- 底部固定栏 -->
    <view v-if="!loading && items.length" class="footer">
      <view class="foot-side" @tap="soon('生词本')"><text class="fs-ic">🔖</text><text class="fs-tx">生词本</text></view>
      <view class="foot-main" @tap="next">再学一句</view>
      <view class="foot-side" @tap="soon('错题本')"><text class="fs-ic">❓</text><text class="fs-tx">错题本</text></view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listLongSentences, getLongSentence, ttsSpeakUrl, shadowScoreLs, type LSItem, type LSDetail, type LSAnalysis, type LSShadowResult } from '@/api/longSentence'
import LsTreeNode from './LsTreeNode.vue'

interface TNode { idx: number; type: string; text: string; children: TNode[] }

// 颜色由后端按「成分类型」固定下发(segment.color/tint),前端按 idx 映射;缺省回退到调色板
const PALETTE = ['#8b5cf6', '#10b981', '#14b8a6', '#f59e0b', '#ef4444', '#3b82f6', '#6366f1', '#ec4899', '#0ea5e9']
const TINT = ['#f3effe', '#e7f7ef', '#e6f7f5', '#fef6e7', '#fdeceb', '#eaf1fe', '#eef0fe', '#fdeef6', '#e8f6fe']
const colorMap = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const s of (analysis.value?.segments || [])) if (s.color) m[s.idx] = s.color
  return m
})
const tintMap = computed<Record<number, string>>(() => {
  const m: Record<number, string> = {}
  for (const s of (analysis.value?.segments || [])) if (s.tint) m[s.idx] = s.tint
  return m
})
const colorOf = (idx: number) => colorMap.value[idx] || PALETTE[(idx - 1) % PALETTE.length] || '#666'
const tintOf = (idx: number) => tintMap.value[idx] || TINT[(idx - 1) % TINT.length] || '#f5f5f5'
const TABS = [
  { key: 'struct', label: '句子结构' },
  { key: 'comp', label: '句子成分' },
  { key: 'words', label: '重点词汇' },
  { key: 'grammar', label: '语法点' },
]

const loading = ref(true)
const items = ref<LSItem[]>([])
const index = ref(0)
const detail = ref<LSDetail | null>(null)
const tab = ref('struct')
const showTranslate = ref(false)
const showStruct = ref(true)
const showLegend = ref(false)

const analysis = computed<LSAnalysis | null>(() => detail.value?.analysis || null)
const pct = computed(() => items.value.length ? Math.round((index.value + 1) / items.value.length * 100) : 0)
const segments = computed(() => (analysis.value?.segments || []).slice().sort((a, b) => a.idx - b.idx).map(s => {
  const toks = (s.text || '').trim().split(/\s+/)
  return { ...s, first: toks[0] || '', rest: toks.slice(1).join(' ') }
}))

// 图例:本句实际用到的颜色去重,标签去掉「连词/第N分句」等后缀只留成分名
const legend = computed(() => {
  const seen = new Set<string>()
  const out: { color: string; label: string }[] = []
  for (const s of segments.value) {
    const c = (s as any).color as string | undefined
    if (!c || seen.has(c)) continue
    seen.add(c)
    const label = (s.type || '').replace(/(连词|关联词|第[一二三四五六七八九十]+分句|分句|部分)$/, '') || s.type || '成分'
    out.push({ color: c, label })
  }
  return out
})

const structRows = computed(() => {
  const a = analysis.value
  if (!a?.structure?.length) return []
  const segMap: Record<number, { type: string; text: string }> = {}
  for (const s of (a.segments || [])) segMap[s.idx] = { type: s.type, text: s.text }
  const parentOf: Record<number, number | null> = {}
  for (const st of a.structure) parentOf[st.idx] = st.parent ?? null
  const depth = (idx: number, guard = 0): number => {
    const p = parentOf[idx]
    if (p == null || guard > 10) return 0
    return 1 + depth(p, guard + 1)
  }
  return a.structure
    .map(st => ({ idx: st.idx, depth: Math.min(depth(st.idx), 3), type: segMap[st.idx]?.type || '', text: segMap[st.idx]?.text || '' }))
    .sort((x, y) => x.idx - y.idx)
})

// 句子结构 → 树(供思维导图)
const tree = computed<TNode[]>(() => {
  const a = analysis.value
  if (!a?.structure?.length) return []
  const segMap: Record<number, { type: string; text: string }> = {}
  for (const s of (a.segments || [])) segMap[s.idx] = { type: s.type, text: s.text }
  const nodes: Record<number, TNode> = {}
  for (const st of a.structure) nodes[st.idx] = { idx: st.idx, type: segMap[st.idx]?.type || '', text: segMap[st.idx]?.text || '', children: [] }
  const roots: TNode[] = []
  for (const st of a.structure) {
    const n = nodes[st.idx]
    const p = st.parent
    if (p != null && nodes[p] && p !== st.idx) nodes[p].children.push(n)
    else roots.push(n)
  }
  const sortRec = (ns: TNode[]) => { ns.sort((x, y) => x.idx - y.idx); ns.forEach(c => sortRec(c.children)) }
  sortRec(roots)
  return roots
})

const compRows = computed(() => {
  const c = analysis.value?.components || {}
  const labelMap: Record<string, string> = { subject: '主语', predicate: '谓语', object: '宾语', complement: '补语', attributive: '定语', adverbial: '状语' }
  return Object.entries(c).filter(([, v]) => v).map(([k, v]) => ({ label: labelMap[k] || k, val: v as string }))
})

function soon(name: string) { uni.showToast({ title: name + '·敬请期待', icon: 'none' }) }

/* ── 听原句:TTS 流式音频 ── */
let audioCtx: UniApp.InnerAudioContext | null = null
const playing = ref(false)
function ensureAudio() {
  if (audioCtx) return audioCtx
  audioCtx = uni.createInnerAudioContext()
  audioCtx.onPlay(() => { playing.value = true })
  audioCtx.onEnded(() => { playing.value = false })
  audioCtx.onStop(() => { playing.value = false })
  audioCtx.onError(() => { playing.value = false; uni.showToast({ title: '暂无音频', icon: 'none' }) })
  return audioCtx
}
function listen() {
  const text = detail.value?.text
  if (!text) return
  const ctx = ensureAudio()
  if (playing.value) { ctx.stop(); return }
  ctx.src = ttsSpeakUrl(text)
  ctx.play()
}

/* ── 跟读:录音 → 发音评测 ── */
const recorder = (uni.getRecorderManager ? uni.getRecorderManager() : null)
const recording = ref(false)
const scoring = ref(false)
const shadowResult = ref<LSShadowResult | null>(null)
let recorderBound = false
function fileToBase64(path: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const fsm = (uni as any).getFileSystemManager?.()
    const fallback = () => {
      fetch(path).then(r => r.blob()).then(b => {
        const fr = new FileReader()
        fr.onload = () => resolve(String(fr.result).split(',')[1] || '')
        fr.onerror = () => reject(new Error('读取失败'))
        fr.readAsDataURL(b)
      }).catch(reject)
    }
    if (fsm) fsm.readFile({ filePath: path, encoding: 'base64', success: (r: any) => resolve(r.data as string), fail: fallback })
    else fallback()
  })
}
function bindRecorder() {
  if (!recorder || recorderBound) return
  recorderBound = true
  recorder.onStop(async (res: any) => {
    recording.value = false
    scoring.value = true
    try {
      const b64 = res.tempFilePath ? await fileToBase64(res.tempFilePath) : ''
      shadowResult.value = await shadowScoreLs(detail.value?.text || '', b64, 'mp3')
    } catch { uni.showToast({ title: '评分失败', icon: 'none' }) }
    finally { scoring.value = false }
  })
  recorder.onError(() => { recording.value = false; uni.showToast({ title: '录音失败', icon: 'none' }) })
}
function shadow() {
  if (!recorder) { uni.showToast({ title: '当前环境不支持录音', icon: 'none' }); return }
  bindRecorder()
  if (recording.value) { recorder.stop(); return }
  shadowResult.value = null
  recording.value = true
  recorder.start({ format: 'mp3', duration: 60000 })
}
const scoreColor = (n: number) => n >= 85 ? '#2fc58a' : n >= 70 ? '#f5a623' : '#ff7a59'

async function loadDetail() {
  const it = items.value[index.value]
  if (!it) return
  detail.value = null
  if (playing.value && audioCtx) audioCtx.stop()
  if (recording.value && recorder) recorder.stop()
  shadowResult.value = null
  try { detail.value = await getLongSentence(it.id) } catch { /* ignore */ }
  tab.value = 'struct'; showTranslate.value = false; showStruct.value = true
}
function prev() { if (index.value > 0) { index.value--; loadDetail() } }
function next() { if (index.value < items.value.length - 1) { index.value++; loadDetail() } }

onLoad(async () => {
  try {
    const r = await listLongSentences(50)
    items.value = r.items || []
    if (items.value.length) await loadDetail()
  } finally { loading.value = false }
})
</script>

<style scoped>
.ls-page { min-height: 100vh; background: #f4f6fa; }
.center-tip { text-align: center; color: #999; padding-top: 200rpx; }
.scroll { padding: 20rpx 20rpx 0; }

/* 顶部进度 */
.header { display: flex; align-items: center; gap: 18rpx; margin-bottom: 18rpx; }
.prog { flex: 1; }
.prog-label { font-size: 26rpx; color: #555; }
.prog-num { color: var(--c-primary); font-weight: 700; }
.prog-bar { height: 12rpx; background: #e5e9f0; border-radius: 8rpx; margin-top: 10rpx; overflow: hidden; }
.prog-fill { height: 100%; background: var(--c-primary); border-radius: 8rpx; }
.checkin { background: #fff; border-radius: 28rpx; padding: 10rpx 22rpx; font-size: 24rpx; color: #444; box-shadow: 0 2rpx 8rpx rgba(0,0,0,.04); }

.card { background: #fff; border-radius: 20rpx; padding: 26rpx; margin-bottom: 20rpx; box-shadow: 0 2rpx 14rpx rgba(0,0,0,.04); }

/* 句子卡头 */
.sent-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24rpx; }
.hl { display: flex; align-items: center; gap: 16rpx; }
.sent-tag { background: var(--c-primary-faint); color: var(--c-primary); font-size: 24rpx; padding: 6rpx 18rpx; border-radius: 24rpx; }
.fav { font-size: 24rpx; color: #999; }
.pager { display: flex; gap: 12rpx; }
.pg { font-size: 24rpx; color: #555; background: #fff; border: 1rpx solid #e3e7ee; border-radius: 24rpx; padding: 6rpx 18rpx; }
.pg.primary { background: var(--c-primary); color: var(--c-on-primary); border-color: var(--c-primary); }
.pg.dis { opacity: .4; }

/* 原句:连续流式段落(行内文本自然排满换行);序号锚在每段首词下方 */
.sentence { font-family: Georgia, 'Times New Roman', 'Songti SC', serif; font-size: 32rpx; line-height: 3; }
.seg { border-bottom: 2rpx dashed; padding-bottom: 6rpx; }
.fw { position: relative; }
.badge { position: absolute; left: 50%; top: 130%; transform: translateX(-50%); width: 32rpx; height: 32rpx; line-height: 32rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; }
.plain { font-size: 32rpx; line-height: 1.9; }
.trans { margin: 8rpx 0 0; padding: 16rpx; background: #f7f9fc; border-radius: 12rpx; font-size: 28rpx; color: #555; }

/* 颜色图例 */
.legend-wrap { margin-top: 16rpx; }
.legend-toggle { font-size: 24rpx; color: #888; }
.legend { margin-top: 12rpx; padding: 16rpx; background: #f7f9fc; border-radius: 14rpx; display: flex; flex-wrap: wrap; gap: 12rpx 18rpx; }
.lg-item { display: flex; align-items: center; gap: 8rpx; }
.lg-dot { width: 22rpx; height: 22rpx; border-radius: 6rpx; flex-shrink: 0; }
.lg-tx { font-size: 24rpx; color: #555; }
.legend-note { width: 100%; font-size: 22rpx; color: #999; line-height: 1.6; margin-top: 4rpx; }

/* 操作行 */
.acts { display: flex; justify-content: space-between; margin-top: 20rpx; gap: 10rpx; }
.act { flex: 1; background: #f5f7fa; border-radius: 14rpx; padding: 14rpx 0; display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.act-ic { font-size: 30rpx; }
.act-tx { font-size: 22rpx; color: #666; }
.act.on { background: var(--c-primary-faint); }
.act.on .act-tx { color: var(--c-primary); }
.act.rec { background: #fdecea; }
.act.rec .act-tx { color: #ff7a59; }

/* 跟读评分 */
.shadow-box { margin-top: 18rpx; padding: 20rpx; background: #f7f9fc; border-radius: 14rpx; }
.sh-loading { font-size: 26rpx; color: #888; text-align: center; }
.sh-head { display: flex; align-items: baseline; gap: 10rpx; flex-wrap: wrap; }
.sh-score { font-size: 56rpx; font-weight: 800; }
.sh-unit { font-size: 24rpx; color: #999; }
.sh-level { color: #fff; font-size: 22rpx; padding: 4rpx 16rpx; border-radius: 20rpx; margin-left: 6rpx; }
.sh-subs { display: flex; gap: 18rpx; margin-left: auto; font-size: 22rpx; color: #777; }
.sh-tip { display: block; margin-top: 12rpx; font-size: 25rpx; color: #555; line-height: 1.6; }

/* Tabs */
.tabs { display: flex; border-bottom: 1rpx solid #eee; margin-bottom: 20rpx; }
.tab { flex: 1; text-align: center; font-size: 28rpx; color: #888; padding: 16rpx 0; }
.tab.on { color: var(--c-primary); font-weight: 700; border-bottom: 4rpx solid var(--c-primary); }
.tab-body { min-height: 80rpx; }

/* 思维导图(横向滚动画布)*/
.mm-scroll { width: 100%; white-space: nowrap; }
.mm-canvas { display: inline-flex; justify-content: center; align-items: flex-start; padding: 10rpx 20rpx 20rpx; min-width: 100%; box-sizing: border-box; }

.comp-row { display: flex; padding: 14rpx 0; border-bottom: 1rpx dashed #f0f0f0; }
.comp-label { width: 120rpx; color: #888; font-size: 28rpx; }
.comp-val { flex: 1; font-size: 28rpx; }
.word-row { display: flex; align-items: baseline; gap: 14rpx; padding: 14rpx 0; border-bottom: 1rpx dashed #f0f0f0; }
.word { font-size: 30rpx; font-weight: 600; }
.word-pos { font-size: 24rpx; color: #aaa; }
.word-mean { font-size: 28rpx; color: #555; }
.gp-row { padding: 14rpx 0; border-bottom: 1rpx dashed #f0f0f0; }
.gp-name { font-size: 28rpx; font-weight: 600; color: var(--c-primary); }
.gp-exp { display: block; font-size: 26rpx; color: #666; margin-top: 6rpx; }
.empty { color: #bbb; font-size: 26rpx; }

/* 结构解析 */
.sec-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.sec-title { font-size: 30rpx; font-weight: 700; border-left: 6rpx solid var(--c-primary); padding-left: 14rpx; }
.link { font-size: 24rpx; color: var(--c-primary); background: var(--c-primary-faint); padding: 8rpx 18rpx; border-radius: 24rpx; }
.stype { display: block; font-size: 28rpx; margin-bottom: 12rpx; }
.exp-row { display: flex; gap: 12rpx; padding: 8rpx 0; align-items: flex-start; }
.sno { width: 34rpx; height: 34rpx; line-height: 34rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 20rpx; flex-shrink: 0; }
.exp-text { flex: 1; font-size: 27rpx; color: #555; line-height: 1.6; }
.summary { display: block; margin-top: 14rpx; font-size: 27rpx; color: #777; line-height: 1.7; }
.footer-space { height: 140rpx; }

/* 底部固定 */
.footer { position: fixed; left: 0; right: 0; bottom: 0; display: flex; align-items: center; gap: 20rpx; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: #fff; box-shadow: 0 -2rpx 14rpx rgba(0,0,0,.05); }
.foot-side { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.fs-ic { font-size: 32rpx; }
.fs-tx { font-size: 22rpx; color: #666; }
.foot-main { flex: 1; background: var(--g-primary); color: var(--c-on-primary); text-align: center; font-size: 32rpx; font-weight: 700; padding: 22rpx 0; border-radius: 44rpx; box-shadow: var(--shadow-primary); }
</style>

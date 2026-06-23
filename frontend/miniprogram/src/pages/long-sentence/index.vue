<!-- src/pages/long-sentence/index.vue — 长难句学习 -->
<template>
  <view class="ls-page">
    <view v-if="loading" class="center-tip">加载中…</view>
    <view v-else-if="!items.length" class="center-tip">暂无长难句(运营审核发布后可见)</view>

    <view v-else class="scroll">
      <!-- 顶部:今日学习进度 + 打卡 -->
      <view class="header">
        <view class="prog">
          <text class="prog-label">今日学习 <text class="prog-num">{{ index + 1 }}</text> / {{ items.length }} 句</text>
          <view class="prog-bar"><view class="prog-fill" :style="{ width: pct + '%' }" /></view>
        </view>
        <view class="streak" @tap="openCalendar"><view class="ic ic-flame streak-ic" />{{ checkinStatus ? '连续 ' + checkinStatus.current_streak + ' 天' : '打卡' }}</view>
      </view>

      <!-- 句子卡 -->
      <view class="card sent-card">
        <view class="sc-top">
          <view class="nav">
            <text class="nav-btn" :class="{ dis: index === 0 }" @tap="prev">‹</text>
            <text class="nav-cur">句子 {{ index + 1 }}/{{ items.length }}</text>
            <text class="nav-btn" :class="{ dis: index >= items.length - 1 }" @tap="next">›</text>
          </view>
          <text v-if="srcLabel" class="src-tag">{{ srcLabel }}</text>
          <view class="sc-spacer" />
          <view v-if="difficulty != null" class="diff-ring" :class="diffLevel.cls">
            <text class="dr-num">{{ difficulty }}</text>
            <text class="dr-lb">难度·{{ diffLevel.label }}</text>
          </view>
        </view>

        <!-- 原句:连续流式段落,每段彩色虚线下划线,序号锚在该段首词下(保持原设计,勿改) -->
        <view v-if="showStruct && segments.length" class="sentence" :class="{ eye: eyeMode }" :style="{ fontSize: fontPx + 'rpx' }">
          <text v-for="s in segments" :key="s.idx" class="seg" :style="{ color: colorOf(s.idx), borderBottomColor: colorOf(s.idx) }"><text class="fw">{{ s.first }}<text class="badge" :style="{ background: colorOf(s.idx) }">{{ s.idx }}</text></text>{{ (s.rest ? ' ' + s.rest : '') + ' ' }}</text>
        </view>
        <text v-else class="plain">{{ detail?.text }}</text>

        <view v-if="showTranslate && analysis?.translation" class="trans">{{ analysis.translation }}</view>

        <!-- 图例:本句实际出现的颜色 → 成分类型(内联) -->
        <view v-if="showStruct && legend.length" class="legend">
          <view v-for="l in legend" :key="l.color" class="lg-item">
            <text class="lg-dot" :style="{ background: l.color }" /><text class="lg-tx">{{ l.label }}</text>
          </view>
        </view>

        <!-- 工具栏:听 / 字号 / 护眼 / 翻译 / 收藏 / 更多 -->
        <view class="toolbar">
          <view class="tb" :class="{ on: playing }" @tap="listen"><view class="ic ic-volume tb-ic" /><text class="tb-tx">{{ playing ? '停止' : (loadingAudio ? '…' : '听') }}</text></view>
          <view class="tb" @tap="decFont"><text class="tb-ic tb-az">A−</text><text class="tb-tx">缩小</text></view>
          <view class="tb" @tap="incFont"><text class="tb-ic tb-az">A+</text><text class="tb-tx">放大</text></view>
          <view class="tb" :class="{ on: eyeMode }" @tap="eyeMode = !eyeMode"><view class="ic ic-eye tb-ic" /><text class="tb-tx">护眼</text></view>
          <view class="tb" :class="{ on: showTranslate }" @tap="showTranslate = !showTranslate"><view class="ic ic-translate tb-ic" /><text class="tb-tx">翻译</text></view>
          <view class="tb" :class="{ on: favorited }" @tap="toggleFav"><view class="ic tb-ic" :class="favorited ? 'ic-star-on' : 'ic-star'" /><text class="tb-tx">收藏</text></view>
          <view class="tb" @tap="onMore"><view class="ic ic-more tb-ic" /><text class="tb-tx">更多</text></view>
        </view>
      </view>

      <!-- Tab 卡 -->
      <view class="card">
        <view class="seg-tabs">
          <text v-for="t in TABS" :key="t.key" class="seg-tab" :class="{ on: tab === t.key }" @tap="tab = t.key">{{ t.label }}</text>
        </view>

        <!-- 句子结构:主干 → 从句/修饰(紧凑树)-->
        <view v-if="tab === 'struct'">
          <view v-if="trunkText || clauseSegs.length" class="st">
            <view v-if="trunkText" class="st-trunk">主干:{{ trunkText }}</view>
            <text v-if="clauseSegs.length" class="st-arrow">⌄</text>
            <view v-if="clauseSegs.length" class="st-children">
              <view v-for="s in clauseSegs" :key="s.idx" class="st-clause" :style="{ background: tintOf(s.idx), borderColor: colorOf(s.idx) }">
                <view class="st-chead">
                  <text class="st-cno" :style="{ background: colorOf(s.idx) }">{{ s.idx }}</text>
                  <text class="st-ctype" :style="{ color: colorOf(s.idx) }">{{ s.type }}</text>
                </view>
                <text class="st-ctext">{{ s.text }}</text>
              </view>
            </view>
          </view>
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
            <view class="word-head"><text class="word">{{ w.word }}</text><text v-if="w.pos" class="word-pos">{{ w.pos }}</text></view>
            <text v-if="w.meaning" class="word-mean">{{ w.meaning }}</text>
          </view>
          <text v-if="!(analysis?.key_words || []).length" class="empty">暂无重点词汇</text>
        </view>

        <!-- 语法点 -->
        <view v-else class="tab-body">
          <view v-for="(g, i) in gpList" :key="i" class="gp-row" :style="{ background: g.tint }">
            <text class="gp-name" :style="{ color: g.color }">{{ g.name }}</text>
            <text v-if="g.explanation" class="gp-exp">{{ g.explanation }}</text>
          </view>
          <text v-if="!gpList.length" class="empty">暂无语法点</text>
        </view>
      </view>

      <!-- 结构解析 -->
      <view class="card" v-if="analysis?.sentence_type || (analysis?.explanations || []).length || analysis?.summary">
        <view class="sec-row">
          <text class="sec-title">结构解析</text>
          <text class="link" @tap="openKpDetail">查看语法点详解 ›</text>
        </view>
        <view v-if="analysis?.sentence_type" class="stype">
          <view class="ic ic-layout stype-ic" />
          <text class="stype-tx">{{ analysis.sentence_type.replace(/。$/, '') }}</text>
        </view>
        <view class="tl">
          <view v-for="e in (analysis?.explanations || [])" :key="e.idx" class="tl-row">
            <view class="tl-rail"><text class="tl-dot" :style="{ background: colorOf(e.idx) }">{{ e.idx }}</text></view>
            <text class="tl-text">{{ e.text }}</text>
          </view>
        </view>
        <view v-if="analysis?.summary" class="summary"><text class="summary-lb">小结</text>{{ analysis.summary }}</view>
      </view>

      <view class="footer-space" />
    </view>

    <!-- 底部固定栏 -->
    <view v-if="!loading && items.length" class="footer">
      <view class="foot-side" @tap="go('/pages/vocabulary/index')"><view class="ic ic-book fs-ic" /><text class="fs-tx">生词本</text></view>
      <view class="foot-main" @tap="next">再学一句</view>
      <view class="foot-side" @tap="go('/pages/wrong-questions/list')"><view class="ic ic-help fs-ic" /><text class="fs-tx">错题本</text></view>
    </view>

    <!-- 更多:底部弹层 -->
    <view v-if="moreOpen" class="more-mask" @tap="moreOpen = false">
      <view class="more-sheet" @tap.stop>
        <view class="more-grab" />
        <view class="more-item" @tap="moreToggleStruct"><view class="ic ic-eye mi-ic" /><text class="mi-tx">{{ showStruct ? '隐藏原句结构' : '显示原句结构' }}</text><text class="mi-arrow">›</text></view>
        <view class="more-item" @tap="moreCopy"><view class="ic ic-clipboard mi-ic" /><text class="mi-tx">复制原句</text><text class="mi-arrow">›</text></view>
        <view class="more-item" @tap="moreDiff"><view class="ic ic-chart mi-ic" /><text class="mi-tx">难度说明</text><text class="mi-arrow">›</text></view>
        <view class="more-item" @tap="moreKp"><view class="ic ic-book mi-ic" /><text class="mi-tx">查看语法点详解</text><text class="mi-arrow">›</text></view>
        <view class="more-cancel" @tap="moreOpen = false">取消</view>
      </view>
    </view>

    <!-- 打卡日历弹层 -->
    <view v-if="calOpen" class="cal-mask" @tap="calOpen = false">
      <view class="cal-card" @tap.stop>
        <view class="cal-head">
          <view class="cal-title"><view class="ic ic-calendar cal-title-ic" /><text>学习打卡</text></view>
          <text class="cal-close" @tap="calOpen = false">✕</text>
        </view>
        <view class="cal-stats">
          <view class="cal-stat"><text class="cs-num">{{ cal?.current_streak ?? 0 }}</text><text class="cs-lb">连续天数</text></view>
          <view class="cal-stat"><text class="cs-num">{{ cal?.longest_streak ?? 0 }}</text><text class="cs-lb">历史最高</text></view>
          <view class="cal-stat"><text class="cs-num">{{ cal?.checked_count ?? 0 }}</text><text class="cs-lb">本月打卡</text></view>
        </view>
        <view class="cal-grid">
          <text v-for="w in ['日','一','二','三','四','五','六']" :key="w" class="cal-wd">{{ w }}</text>
          <view v-for="(c, i) in calCells" :key="i" class="cal-cell" :class="{ checked: c.checked, today: c.today, blank: !c.day }">
            <text v-if="c.day">{{ c.day }}</text>
          </view>
        </view>
        <view class="cal-foot">
          <text class="cal-btn" :class="{ done: checkinStatus?.checked_in_today }" @tap="doCheckin">
            {{ checkinStatus?.checked_in_today ? '今日已打卡 ✓' : '立即打卡' }}
          </text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { listLongSentences, getLongSentence, getLsAudioUrl, favoriteLs, ttsSpeakUrl, type LSItem, type LSDetail, type LSAnalysis } from '@/api/longSentence'
import { checkin, getCheckinStatus, getCheckinCalendar, type CheckinStatus, type CheckinCalendar } from '@/api/checkin'

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
const fontPx = ref(32)        // 原句字号(rpx),可调
const eyeMode = ref(false)    // 护眼模式
function incFont() { fontPx.value = Math.min(46, fontPx.value + 4) }
function decFont() { fontPx.value = Math.max(26, fontPx.value - 4) }

const SRC_LABEL: Record<string, string> = { platform_real: '真题', textbook: '教材', uploaded: '上传' }
const srcLabel = computed(() => SRC_LABEL[detail.value?.source_kind || ''] || '')
const difficulty = computed<number | null>(() => {
  const d = analysis.value?.difficulty
  return typeof d === 'number' ? d : null
})
const diffLevel = computed(() => {
  const d = difficulty.value ?? 0
  if (d >= 80) return { label: '高', cls: 'hard' }
  if (d >= 60) return { label: '中', cls: 'mid' }
  return { label: '低', cls: 'easy' }
})

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

// 句子结构:主干(主谓宾)+ 从句/修饰成分(其余段),供「主干→从句」紧凑树
const TRUNK_RE = /主干|主句|主语|谓语|宾语|表语/
const trunkText = computed(() => {
  const a = analysis.value
  if (a?.main_clause) return a.main_clause
  const t = segments.value.filter(s => TRUNK_RE.test(s.type || '')).map(s => s.text).join(' ')
  if (t) return t
  const c = a?.components || {}
  return [c.subject, c.predicate, c.object].filter(Boolean).join(' ')
})
const clauseSegs = computed(() => segments.value.filter(s => !TRUNK_RE.test(s.type || '')))

const compRows = computed(() => {
  const c = analysis.value?.components || {}
  const labelMap: Record<string, string> = { subject: '主语', predicate: '谓语', object: '宾语', complement: '补语', attributive: '定语', adverbial: '状语' }
  return Object.entries(c).filter(([, v]) => v).map(([k, v]) => ({ label: labelMap[k] || k, val: v as string }))
})

// 语法点按「语法族」上色(与句子成分配色呼应)
const _FAM: [RegExp, string, string][] = [
  [/并列/, '#e0529c', '#fce9f3'],
  [/名词性|宾语从句|主语从句|表语从句|同位语/, '#8a5cf0', '#f0ebfe'],
  [/定语/, '#1f9d6b', '#e6f6ef'],
  [/状语/, '#e08a2f', '#fcf0e2'],
  [/非谓语|不定式|分词|动名词/, '#0e9aa7', '#e3f5f6'],
  [/介词/, '#2f9fc4', '#e5f3f9'],
  [/主语|谓语|宾语|表语|主干|主句/, '#3b6fe0', '#eaf0fd'],
]
function famColor(name?: string): { color: string; tint: string } {
  for (const [re, color, tint] of _FAM) if (re.test(name || '')) return { color, tint }
  return { color: '#6b7688', tint: '#eef0f4' }
}
const gpList = computed(() => (analysis.value?.grammar_points || []).map(g => ({ ...g, ...famColor(g.name) })))

function soon(name: string) { uni.showToast({ title: name + '·敬请期待', icon: 'none' }) }
function go(url: string) { uni.navigateTo({ url }) }

/* ── 收藏 ── */
const favorited = ref(false)
async function toggleFav() {
  const id = items.value[index.value]?.id
  if (!id) return
  const target = !favorited.value
  favorited.value = target  // 乐观更新
  try {
    const r = await favoriteLs(id, target)
    favorited.value = r.favorited
    const it = items.value[index.value]; if (it) it.favorited = r.favorited
  } catch {
    favorited.value = !target
    uni.showToast({ title: '操作失败', icon: 'none' })
  }
}

/* ── 更多:自定义底部弹层 ── */
const moreOpen = ref(false)
function onMore() { moreOpen.value = true }
function moreToggleStruct() { showStruct.value = !showStruct.value; moreOpen.value = false }
function moreCopy() {
  moreOpen.value = false
  uni.setClipboardData({ data: detail.value?.text || '', success: () => uni.showToast({ title: '已复制', icon: 'success' }) })
}
function moreDiff() {
  moreOpen.value = false
  const c = analysis.value?.complexity
  const content = c
    ? `难度 ${difficulty.value ?? '—'} · ${diffLevel.value.label}\n从句 ${c.clause_count ?? '—'} · 树深 ${c.tree_depth ?? '—'} · 依存距离 ${c.mdd ?? '—'} · 词数 ${c.word_count ?? '—'}`
    : `难度 ${difficulty.value ?? '暂无'}`
  uni.showModal({ title: '难度说明', content, showCancel: false })
}
function moreKp() { moreOpen.value = false; openKpDetail() }

/* ── 语法点详解:跳关联考点内容页 ── */
function openKpDetail() {
  const node = detail.value?.nodes?.[0]
  if (!node) { uni.showToast({ title: '本句暂无关联语法点', icon: 'none' }); return }
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${node.node_id}` })
}

/* ── 打卡日历 ── */
const checkinStatus = ref<CheckinStatus | null>(null)
const cal = ref<CheckinCalendar | null>(null)
const calOpen = ref(false)
const calCells = computed(() => {
  const c = cal.value
  if (!c) return [] as { day: number; checked?: boolean; today?: boolean }[]
  const checked = new Set((c.days || []).map(d => d.date))
  const first = new Date(c.year, c.month - 1, 1).getDay()  // 0=周日
  const dim = new Date(c.year, c.month, 0).getDate()
  const now = new Date()
  const curMonth = now.getFullYear() === c.year && now.getMonth() + 1 === c.month
  const cells: { day: number; checked?: boolean; today?: boolean }[] = []
  for (let i = 0; i < first; i++) cells.push({ day: 0 })
  for (let d = 1; d <= dim; d++) {
    const ds = `${c.year}-${String(c.month).padStart(2, '0')}-${String(d).padStart(2, '0')}`
    cells.push({ day: d, checked: checked.has(ds), today: curMonth && now.getDate() === d })
  }
  return cells
})
async function openCalendar() {
  calOpen.value = true
  try { cal.value = await getCheckinCalendar() } catch { /* ignore */ }
  try { checkinStatus.value = await getCheckinStatus() } catch { /* ignore */ }
}
async function doCheckin() {
  if (checkinStatus.value?.checked_in_today) return
  try {
    checkinStatus.value = await checkin()
    cal.value = await getCheckinCalendar()
  } catch { uni.showToast({ title: '打卡失败', icon: 'none' }) }
}

/* ── 听原句:首次合成存 COS+回填库,再次直接播库里链接;COS 未配置回退流式 ── */
let audioCtx: UniApp.InnerAudioContext | null = null
const playing = ref(false)
const loadingAudio = ref(false)
const audioUrl = ref<string>('')   // 本句已拿到的直链(库里或刚生成),避免重复请求
function ensureAudio() {
  if (audioCtx) return audioCtx
  audioCtx = uni.createInnerAudioContext()
  audioCtx.onPlay(() => { playing.value = true })
  audioCtx.onEnded(() => { playing.value = false })
  audioCtx.onStop(() => { playing.value = false })
  audioCtx.onError(() => { playing.value = false; uni.showToast({ title: '暂无音频', icon: 'none' }) })
  return audioCtx
}
async function listen() {
  const text = detail.value?.text
  if (!text) return
  const ctx = ensureAudio()
  if (playing.value) { ctx.stop(); return }
  // 1) 已有直链(库里或本次已生成)→ 直接播
  let src = audioUrl.value || detail.value?.audio_url || ''
  // 2) 没有 → 调生成端点(合成→COS→回填库),返回直链
  if (!src) {
    loadingAudio.value = true
    try {
      const r = await getLsAudioUrl(items.value[index.value].id)
      src = r.url || ''
    } catch { /* ignore,走回退 */ }
    finally { loadingAudio.value = false }
  }
  // 3) 仍无直链(COS dev 未配置)→ 回退流式合成接口
  if (src) audioUrl.value = src
  ctx.src = src || ttsSpeakUrl(text)
  ctx.play()
}

async function loadDetail() {
  const it = items.value[index.value]
  if (!it) return
  detail.value = null
  if (playing.value && audioCtx) audioCtx.stop()
  audioUrl.value = ''
  try { detail.value = await getLongSentence(it.id) } catch { /* ignore */ }
  favorited.value = !!(detail.value?.favorited ?? it.favorited)
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
  try { checkinStatus.value = await getCheckinStatus() } catch { /* ignore */ }
})
</script>

<style scoped>
.ls-page { min-height: 100vh; background: #f4f6fa; }
.center-tip { text-align: center; color: #999; padding-top: 200rpx; }
.scroll { padding: 20rpx 20rpx 0; }

/* 顶部进度 */
.header { display: flex; align-items: center; gap: 18rpx; margin-bottom: 20rpx; }
.prog { flex: 1; }
.prog-label { font-size: 26rpx; color: #666; }
.prog-num { color: var(--c-primary); font-weight: 700; }
.prog-bar { height: 10rpx; background: #e5e9f0; border-radius: 8rpx; margin-top: 12rpx; overflow: hidden; }
.prog-fill { height: 100%; background: var(--c-primary); border-radius: 8rpx; transition: width .3s; }
.streak { display: flex; align-items: center; gap: 6rpx; background: #fff; border: 1rpx solid #e8ebf1; border-radius: 28rpx; padding: 8rpx 20rpx; font-size: 23rpx; color: #666; }
.streak-ic.ic { width: 28rpx; height: 28rpx; margin-right: 4rpx; }

.card { background: #fff; border-radius: 24rpx; padding: 28rpx; margin-bottom: 20rpx; box-shadow: 0 2rpx 16rpx rgba(0,0,0,.05); }

/* 句子卡头:翻页 + 来源 + 难度环 */
.sc-top { display: flex; align-items: center; gap: 14rpx; margin-bottom: 20rpx; }
.nav { display: flex; align-items: center; gap: 6rpx; }
.nav-btn { width: 44rpx; height: 44rpx; line-height: 40rpx; text-align: center; border: 1rpx solid #e3e7ee; border-radius: 50%; color: #555; font-size: 32rpx; }
.nav-btn.dis { opacity: .35; }
.nav-cur { font-size: 24rpx; color: #444; min-width: 110rpx; text-align: center; }
.src-tag { background: #f0f2f6; color: #777; font-size: 22rpx; padding: 5rpx 16rpx; border-radius: 24rpx; }
.sc-spacer { flex: 1; }
.diff-ring { display: flex; flex-direction: column; align-items: center; gap: 2rpx; }
.dr-num { width: 78rpx; height: 78rpx; line-height: 72rpx; text-align: center; border-radius: 50%; border: 5rpx solid; font-size: 34rpx; font-weight: 700; }
.dr-lb { font-size: 20rpx; color: #999; }
.diff-ring.hard .dr-num { border-color: #e2504a; color: #e2504a; }
.diff-ring.mid .dr-num { border-color: #e89a1f; color: #d0860f; }
.diff-ring.easy .dr-num { border-color: #1f9d6b; color: #1f9d6b; }

/* 原句:连续流式段落(行内文本自然排满换行);序号锚在每段首词下方(保持原设计) */
.sentence { font-family: Georgia, 'Times New Roman', 'Songti SC', serif; font-size: 32rpx; line-height: 3; transition: background .2s; }
.sentence.eye { background: #f3f0e3; border-radius: 14rpx; padding: 16rpx 20rpx; }
.seg { border-bottom: 2rpx dashed; padding-bottom: 6rpx; }
.fw { position: relative; }
.badge { position: absolute; left: 50%; top: 130%; transform: translateX(-50%); width: 32rpx; height: 32rpx; line-height: 32rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; }
.plain { font-size: 32rpx; line-height: 1.9; }
.trans { margin: 16rpx 0 0; padding: 18rpx; background: #f7f9fc; border-radius: 14rpx; font-size: 28rpx; color: #555; line-height: 1.7; }

/* 颜色图例(内联) */
.legend { margin-top: 18rpx; padding-top: 16rpx; border-top: 1rpx solid #f0f2f5; display: flex; flex-wrap: wrap; gap: 12rpx 22rpx; }
.lg-item { display: flex; align-items: center; gap: 8rpx; }
.lg-dot { width: 18rpx; height: 18rpx; border-radius: 5rpx; flex-shrink: 0; }
.lg-tx { font-size: 23rpx; color: #777; }

/* —— 线性图标(与首页一致:SVG stroke 描边、主色蓝)—— */
.ic { display: inline-block; background-repeat: no-repeat; background-position: center; background-size: contain; width: 36rpx; height: 36rpx; vertical-align: middle; }
.ic-volume { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M11 5 6 9H2v6h4l5 4z'/%3E%3Cpath d='M15.5 8.5a5 5 0 0 1 0 7'/%3E%3Cpath d='M19.07 4.93a10 10 0 0 1 0 14.14'/%3E%3C/svg%3E"); }
.ic-eye { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z'/%3E%3Ccircle cx='12' cy='12' r='3'/%3E%3C/svg%3E"); }
.ic-translate { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m5 8 6 6'/%3E%3Cpath d='m4 14 6-6 2-3'/%3E%3Cpath d='M2 5h12'/%3E%3Cpath d='M7 2h1'/%3E%3Cpath d='m22 22-5-10-5 10'/%3E%3Cpath d='M14 18h6'/%3E%3C/svg%3E"); }
.ic-star { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M12 2l3 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.9 21l1.2-6.8-5-4.9 6.9-1z'/%3E%3C/svg%3E"); }
.ic-star-on { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23ffb020' stroke='%23ffb020' stroke-width='2' stroke-linejoin='round'%3E%3Cpath d='M12 2l3 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.9 21l1.2-6.8-5-4.9 6.9-1z'/%3E%3C/svg%3E"); }
.ic-more { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%233d8bf5'%3E%3Ccircle cx='5' cy='12' r='1.8'/%3E%3Ccircle cx='12' cy='12' r='1.8'/%3E%3Ccircle cx='19' cy='12' r='1.8'/%3E%3C/svg%3E"); }
.ic-flame { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23ff8a3d' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.07-2.14-.22-4.05 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.15.43-2.29 1-3a2.5 2.5 0 0 0 2.5 2.5z'/%3E%3C/svg%3E"); }
.ic-book { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z'/%3E%3C/svg%3E"); }
.ic-help { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='12' cy='12' r='10'/%3E%3Cpath d='M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2.5-3 4'/%3E%3Cpath d='M12 17h.01'/%3E%3C/svg%3E"); }
.ic-clipboard { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2'/%3E%3Crect x='8' y='2' width='8' height='4' rx='1'/%3E%3C/svg%3E"); }
.ic-chart { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cline x1='6' y1='20' x2='6' y2='15'/%3E%3Cline x1='12' y1='20' x2='12' y2='9'/%3E%3Cline x1='18' y1='20' x2='18' y2='4'/%3E%3C/svg%3E"); }
.ic-calendar { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='4' width='18' height='18' rx='2'/%3E%3Cline x1='16' y1='2' x2='16' y2='6'/%3E%3Cline x1='8' y1='2' x2='8' y2='6'/%3E%3Cline x1='3' y1='10' x2='21' y2='10'/%3E%3C/svg%3E"); }
.ic-layout { background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Crect x='3' y='3' width='18' height='18' rx='2'/%3E%3Cpath d='M3 9h18'/%3E%3Cpath d='M9 21V9'/%3E%3C/svg%3E"); }
.stype-ic.ic { width: 30rpx; height: 30rpx; }

/* 工具栏:一排图标按钮 */
.toolbar { display: flex; gap: 8rpx; margin-top: 20rpx; }
.tb { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 8rpx; padding: 14rpx 0; background: #f5f7fa; border-radius: 16rpx; }
.tb-ic.ic { width: 38rpx; height: 38rpx; }
.tb-az { font-size: 30rpx; font-weight: 600; color: var(--c-primary); line-height: 38rpx; }
.tb-tx { font-size: 20rpx; color: #888; }
.tb.on { background: var(--c-primary-faint); }
.tb.on .tb-tx { color: var(--c-primary); }

/* Tabs:分段控件 */
.seg-tabs { display: flex; gap: 6rpx; background: #eef1f6; border-radius: 16rpx; padding: 6rpx; margin-bottom: 24rpx; }
.seg-tab { flex: 1; text-align: center; font-size: 26rpx; color: #888; padding: 16rpx 0; border-radius: 12rpx; }
.seg-tab.on { background: #fff; color: var(--c-primary); font-weight: 700; box-shadow: 0 1rpx 6rpx rgba(0,0,0,.06); }
.tab-body { min-height: 80rpx; }

/* 句子结构:主干 → 从句 紧凑树 */
.st { display: flex; flex-direction: column; align-items: center; padding: 6rpx 0 4rpx; }
.st-trunk { background: var(--c-primary-faint); color: var(--c-primary); font-size: 25rpx; font-weight: 600; padding: 14rpx 22rpx; border-radius: 14rpx; max-width: 100%; box-sizing: border-box; text-align: center; line-height: 1.5; }
.st-arrow { color: #c2c8d2; font-size: 30rpx; line-height: 1; margin: 10rpx 0; }
.st-children { display: flex; flex-wrap: wrap; justify-content: center; gap: 16rpx; width: 100%; }
.st-clause { flex: 1 1 44%; min-width: 240rpx; border: 1rpx solid; border-radius: 14rpx; padding: 14rpx 16rpx; box-sizing: border-box; }
.st-chead { display: flex; align-items: center; gap: 10rpx; margin-bottom: 6rpx; }
.st-cno { width: 28rpx; height: 28rpx; line-height: 28rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; flex-shrink: 0; }
.st-ctype { font-size: 23rpx; font-weight: 700; }
.st-ctext { font-size: 23rpx; color: #6b7178; line-height: 1.5; }

/* 句子成分:标签 chip + 值 */
.comp-row { display: flex; align-items: flex-start; gap: 12rpx; padding: 14rpx 16rpx; background: #f7f9fc; border-radius: 12rpx; margin-bottom: 10rpx; }
.comp-label { flex-shrink: 0; font-size: 21rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 8rpx; padding: 5rpx 14rpx; }
.comp-val { flex: 1; font-size: 24rpx; color: #4a5057; line-height: 1.55; font-family: Georgia, 'Times New Roman', serif; }
/* 重点词汇:卡片 */
.word-row { padding: 14rpx 16rpx; background: #f7f9fc; border-radius: 12rpx; margin-bottom: 10rpx; }
.word-head { display: flex; align-items: baseline; gap: 12rpx; }
.word { font-size: 27rpx; font-weight: 700; color: #333; font-family: Georgia, 'Times New Roman', serif; }
.word-pos { font-size: 20rpx; color: #8a93a3; background: #e9edf3; border-radius: 6rpx; padding: 2rpx 10rpx; }
.word-mean { display: block; font-size: 23rpx; color: #6b7178; margin-top: 6rpx; line-height: 1.55; }
/* 语法点:按语法族上色的浅底卡 + 同色标题 */
.gp-row { padding: 16rpx 18rpx; border-radius: 14rpx; margin-bottom: 10rpx; }
.gp-name { display: block; font-size: 25rpx; font-weight: 700; }
.gp-exp { display: block; font-size: 23rpx; color: #6b7178; margin-top: 6rpx; line-height: 1.6; }
.empty { color: #bbb; font-size: 26rpx; }

/* 结构解析 */
.sec-row { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.sec-title { font-size: 30rpx; font-weight: 700; border-left: 6rpx solid var(--c-primary); padding-left: 14rpx; }
.link { font-size: 24rpx; color: var(--c-primary); background: var(--c-primary-faint); padding: 8rpx 18rpx; border-radius: 24rpx; }
.stype { display: flex; align-items: center; gap: 8rpx; background: var(--c-primary-faint); border-radius: 12rpx; padding: 12rpx 16rpx; margin-bottom: 18rpx; }
.stype-ic { font-size: 24rpx; }
.stype-tx { font-size: 25rpx; font-weight: 600; color: var(--c-primary); }
/* 逐条解析:时间线 */
.tl { padding: 2rpx 0; }
.tl-row { display: flex; gap: 14rpx; position: relative; padding-bottom: 20rpx; }
.tl-rail { position: relative; flex-shrink: 0; width: 32rpx; display: flex; justify-content: center; }
.tl-dot { width: 30rpx; height: 30rpx; line-height: 30rpx; text-align: center; border-radius: 50%; color: #fff; font-size: 18rpx; }
.tl-row:not(:last-child) .tl-rail::before { content: ''; position: absolute; top: 32rpx; bottom: -14rpx; left: 50%; transform: translateX(-50%); width: 2rpx; background: #e9ecf2; }
.tl-text { flex: 1; font-size: 24rpx; color: #6b7178; line-height: 1.65; padding-top: 3rpx; }
.summary { display: block; margin-top: 6rpx; padding: 14rpx 16rpx; background: #f7f9fc; border-radius: 12rpx; font-size: 24rpx; color: #6b7178; line-height: 1.7; }
.summary-lb { font-size: 20rpx; color: #fff; background: #a7b0c0; border-radius: 8rpx; padding: 3rpx 12rpx; margin-right: 10rpx; }
.footer-space { height: 140rpx; }

/* 更多:底部弹层 */
.more-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); z-index: 99; display: flex; align-items: flex-end; }
.more-sheet { width: 100%; background: #fff; border-radius: 28rpx 28rpx 0 0; padding: 12rpx 0 calc(12rpx + env(safe-area-inset-bottom)); }
.more-grab { width: 64rpx; height: 8rpx; background: #e2e6ee; border-radius: 8rpx; margin: 8rpx auto 14rpx; }
.more-item { display: flex; align-items: center; gap: 18rpx; padding: 26rpx 36rpx; }
.more-item:active { background: #f5f7fa; }
.mi-ic.ic { width: 38rpx; height: 38rpx; }
.mi-tx { flex: 1; font-size: 28rpx; color: #2a3138; }
.mi-arrow { color: #c2c8d2; font-size: 30rpx; }
.more-cancel { margin-top: 10rpx; border-top: 12rpx solid #f4f6fa; padding: 28rpx 0; text-align: center; font-size: 28rpx; color: #888; }
.more-cancel:active { background: #f5f7fa; }

/* 打卡日历弹层 */
.cal-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 99; }
.cal-card { width: 600rpx; background: #fff; border-radius: 24rpx; padding: 30rpx; }
.cal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 20rpx; }
.cal-title { font-size: 32rpx; font-weight: 800; display: flex; align-items: center; }
.cal-title-ic.ic { width: 32rpx; height: 32rpx; margin-right: 8rpx; }
.cal-close { font-size: 32rpx; color: #999; padding: 0 10rpx; }
.cal-stats { display: flex; justify-content: space-around; margin-bottom: 24rpx; }
.cal-stat { display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.cs-num { font-size: 44rpx; font-weight: 800; color: var(--c-primary); }
.cs-lb { font-size: 22rpx; color: #888; }
.cal-grid { display: flex; flex-wrap: wrap; }
.cal-wd { width: 14.28%; text-align: center; font-size: 22rpx; color: #aaa; padding: 8rpx 0; }
.cal-cell { width: 14.28%; height: 64rpx; display: flex; align-items: center; justify-content: center; font-size: 24rpx; color: #555; }
.cal-cell.blank { visibility: hidden; }
.cal-cell.checked { color: #fff; }
.cal-cell.checked text { background: var(--c-primary); width: 48rpx; height: 48rpx; line-height: 48rpx; text-align: center; border-radius: 50%; }
.cal-cell.today text { box-shadow: 0 0 0 2rpx var(--c-gold); border-radius: 50%; }
.cal-foot { margin-top: 24rpx; }
.cal-btn { display: block; text-align: center; background: var(--g-primary); color: #fff; font-size: 30rpx; font-weight: 700; padding: 22rpx 0; border-radius: 44rpx; box-shadow: var(--shadow-primary); }
.cal-btn.done { background: #e8eef6; color: #9aa6b6; box-shadow: none; }

/* 底部固定 */
.footer { position: fixed; left: 0; right: 0; bottom: 0; z-index: 20; display: flex; align-items: center; gap: 20rpx; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom)); background: #fff; box-shadow: 0 -2rpx 14rpx rgba(0,0,0,.05); }
.foot-side { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.fs-ic.ic { width: 42rpx; height: 42rpx; }
.fs-tx { font-size: 22rpx; color: #666; }
.foot-main { flex: 1; background: var(--g-primary); color: var(--c-on-primary); text-align: center; font-size: 32rpx; font-weight: 700; padding: 22rpx 0; border-radius: 44rpx; box-shadow: var(--shadow-primary); }
</style>

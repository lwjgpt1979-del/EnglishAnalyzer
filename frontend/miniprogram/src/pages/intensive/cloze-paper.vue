<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!blocks.length" class="tip">该卷没有完形内容</view>
    <template v-else>
      <!-- 方案 S:进度 + 语篇 Tab + 原文 整块吸顶,页底色壳盖住顶边距,避免夹缝露题 -->
      <view class="sticky-stack">
        <view class="rd-head">
          <view class="rd-fill" :class="'rhf-' + readStatus" :style="{ width: readPct + '%' }" />
          <view class="rd-num"><text class="rd-s">{{ readStudied }}</text><text class="rd-t">/{{ readTotal }}</text></view>
          <view class="rd-info">
            <view class="rd-status" :class="'rs-' + readStatus">{{ readStatusLabel }}<text class="rd-pct">{{ readPct }}%</text></view>
            <text class="rd-sub">已精讲 {{ readStudied }} / {{ readTotal }} 空</text>
          </view>
        </view>

        <view v-if="blocks.length > 1" class="pass-tabs">
          <view
            v-for="(bk, bi) in blocks" :key="bi"
            class="pass-tab" :class="{ on: activeBlock === bi }"
            @tap="activeBlock = bi"
          >
            <text class="pt-t">语篇 {{ bi + 1 }}</text>
            <text class="pt-s">{{ tabSub(bk) }}</text>
          </view>
        </view>

        <view v-if="curBlock && curBlock.passage" class="passage">
          <view class="passage-head">
            <text class="passage-title">原文</text>
            <text class="passage-toggle" @tap.stop="collapsed = !collapsed">{{ collapsed ? '展开 ▾' : '收起 ▴' }}</text>
          </view>
          <view v-if="!collapsed" class="passage-body">
            <view class="passage-legend">
              <text class="lg-item"><text class="lg-sample lg-w">重点词</text><text class="lg-hint">（点开词卡）</text></text>
              <text class="lg-item"><text class="lg-sample lg-s">长难句</text><text class="lg-hint">（点开句卡）</text></text>
              <text class="lg-item"><text class="lg-sample lg-b">空号</text><text class="lg-hint">（跳到题）</text></text>
            </view>
            <!-- 扁平节点:mark | blank | seg(勿嵌套字段,防 uni-app 渲染崩) -->
            <view class="passage-text"><template v-for="(node, ni) in passageNodes(activeBlock, curBlock)" :key="ni"><view v-if="node.kind === 'mark'" class="s-mark" @tap.stop="openSentenceIdx(node.sentence_idx!)"><view class="ic ic-list-orange s-mark-ic"></view></view><text v-else-if="node.kind === 'blank'" class="p-blank" :class="node.wrong ? 'bad' : (node.studied ? 'ok' : 'todo')" @tap.stop="scrollToQ(node.no)">{{ node.no }}</text><text v-else-if="node.word_idx != null || node.sentence_idx != null" :class="{ 'seg-w': node.word_idx != null, 'seg-s': node.sentence_idx != null }" @tap.stop="segTap(node)">{{ node.t }}</text><text v-else>{{ node.t }}</text></template></view>
          </view>
        </view>
      </view>

      <template v-if="curBlock">
        <view
          v-for="q in curBlock.questions"
          :id="'cz-' + normNo(q.no)"
          :key="q.id"
          class="q-card"
          :class="{ wrong: q.is_wrong, okborder: !q.is_wrong }"
        >
          <view class="q-head">
            <view class="q-tick" :class="q.studied ? 'done' : ''" />
            <text v-if="q.is_wrong" class="chip bad">错</text>
            <text v-else class="chip ok">对</text>
            <text class="chip">{{ hasOpts(q) ? '单选' : '填空' }}</text>
            <text class="q-no">{{ q.no ? `第 ${q.no} 题` : '' }}</text>
          </view>
          <text class="q-stem">{{ q.stem || '（题干为空）' }}</text>
          <view v-if="hasOpts(q)" class="q-opts">
            <view
              v-for="(op, oi) in q.options" :key="oi"
              class="q-opt"
              :class="optCls(q, op, oi)"
            >
              <text class="q-opt-t">{{ op }}</text>
              <text v-if="optHint(q, op, oi)" class="q-opt-h">{{ optHint(q, op, oi) }}</text>
            </view>
          </view>
          <view class="q-foot">
            <text class="ans" :class="{ bad: q.is_wrong }">
              {{ hasOpts(q) ? '你选' : '你填' }} {{ q.student_answer || '—' }}
              · 正确 {{ q.correct_answer || '—' }}
            </text>
            <text class="go" @tap="openDetail(q)">本题详解 ›</text>
          </view>
        </view>
      </template>
      <view class="foot-pad"></view>
    </template>

    <!-- 底部常驻:本篇精讲(复用阅读 passage-study) -->
    <view v-if="!loading && (curWords.length || curSentences.length)" class="study-bar" @tap="studyOpen = true">
      <view class="ic ic-idea sb-ic"></view>
      <text class="sb-t">本篇精讲</text>
      <text class="sb-cnt">重点词 <text class="sb-n">{{ curWords.length }}</text> · 长难句 <text class="sb-n">{{ curSentences.length }}</text></text>
      <view class="ic ic-chevrons-down sb-up"></view>
    </view>

    <view v-if="studyOpen" class="study-mask" @tap="studyOpen = false">
      <view class="study-panel" @tap.stop>
        <view class="grab"></view>
        <view class="study-hd">
          <view class="ic ic-idea sh-ic"></view>
          <text class="sh-t">本篇精讲</text>
          <view class="ic ic-close sh-x" @tap="studyOpen = false"></view>
        </view>
        <view class="study-seg">
          <text class="seg-i" :class="{ on: studyTab === 'word' }" @tap="studyTab = 'word'">重点词 {{ curWords.length }}</text>
          <text class="seg-i" :class="{ on: studyTab === 'ls' }" @tap="studyTab = 'ls'">长难句 {{ curSentences.length }}</text>
        </view>
        <scroll-view scroll-y class="study-body">
          <template v-if="studyTab === 'word'">
            <KeyWordsList v-if="curWords.length" :words="curWords" :paper-id="paperId" title="读懂本篇 · 重点词" no-card @pick="sheetCard = $event" />
            <view v-else class="tip">本篇暂无重点词</view>
          </template>
          <template v-else>
            <view v-if="!curSentences.length" class="tip">本篇没有长难句</view>
            <view v-else class="ls-hint">点句子看逐句解析(结构 · 语法 · 重点词)</view>
            <view v-for="(s, si) in curSentences" :key="si" class="ls-card" @tap="openSentencePage(s)">
              <text class="ls-no">{{ si + 1 }}</text>
              <text class="ls-text">{{ filledLongSentence(s) || s }}</text>
              <text class="ls-go">拆解 ›</text>
            </view>
          </template>
        </scroll-view>
      </view>
    </view>

    <WordCard :word="sheetCard" :paper-id="paperId" @close="sheetCard = null" />
    <SentenceCard
      :text="sentenceCard?.text || null"
      :parts="sentenceCard?.parts || null"
      :chips="sentenceCard?.chips || null"
      :missing="sentenceCard?.missing || null"
      :paper-id="paperId"
      @close="sentenceCard = null"
    />

    <!-- 本题详解弹层：原题 + 双轴折叠 + 本题巩固 + WRN -->
    <view v-if="detailQ" class="modal" @tap="closeDetail">
      <view class="sheet" @tap.stop>
        <view class="sheet-bar">
          <text class="sheet-t">本题详情</text>
          <text class="sheet-x" @tap="closeDetail">关闭</text>
        </view>
        <scroll-view scroll-y class="sheet-body">
          <view class="warm" :class="{ wrong: detailQ.is_wrong }">
            <view class="q-head">
              <text v-if="detailQ.is_wrong" class="chip bad">错</text>
              <text v-else class="chip ok">对</text>
              <text class="chip">{{ hasOpts(detailQ) ? '单选' : '填空' }}</text>
              <text class="q-no">{{ detailQ.no ? `第 ${detailQ.no} 题` : '' }}</text>
            </view>
            <text class="q-stem">{{ detailQ.stem }}</text>
            <view v-if="hasOpts(detailQ)" class="q-opts">
              <view
                v-for="(op, oi) in detailQ.options" :key="oi"
                class="q-opt"
                :class="optCls(detailQ, op, oi)"
              >
                <text class="q-opt-t">{{ op }}</text>
                <text v-if="optHint(detailQ, op, oi)" class="q-opt-h">{{ optHint(detailQ, op, oi) }}</text>
              </view>
            </view>
            <view class="ansline">
              <text :class="detailQ.is_wrong ? 'x' : 'o'">
                {{ hasOpts(detailQ) ? '你选' : '你填' }} {{ detailQ.student_answer || '—' }}
              </text>
              <text class="o">正确 {{ detailQ.correct_answer || '—' }}</text>
            </view>
          </view>

          <view class="dual-fold" @tap="dualOpen = !dualOpen">
            <text class="dual-sum">{{ dualOpen ? '▾' : '▸' }} 完形双轴解析</text>
          </view>
          <view v-if="dualOpen" class="dual">
            <view v-if="anaLoading" class="muted">解析生成中…</view>
            <template v-else-if="ana && !ana.error">
              <view class="dual-row"><text class="k">线索类型</text><text>{{ ana.clue_type || '—' }}</text></view>
              <view class="dual-row"><text class="k">线索句</text><text>{{ ana.clue || '—' }}</text></view>
              <view class="dual-row"><text class="k">为何对</text><text>{{ ana.answer_reason || '—' }}</text></view>
              <view class="dual-row"><text class="k">干扰错因</text><text>{{ ana.distractor_why || '—' }}</text></view>
              <view class="dual-row"><text class="k">载体槽</text><text>{{ ana.slot || '—' }}</text></view>
            </template>
            <text v-else class="muted">{{ ana?.error || '暂无解析' }}</text>
          </view>

          <view class="drill" :class="{ busy: pracLoading }" @tap="startPractice">
            <view>
              <text class="drill-t">本题巩固</text>
              <text class="drill-d">围绕「{{ ana?.clue_type || '线索' }}」练同类单选</text>
            </view>
            <text class="drill-go">{{ pracLoading ? '…' : '›' }}</text>
          </view>

          <WrongRelationNet
            v-if="detailWrnId"
            :wrong-record-id="detailWrnId"
          />
          <WrongRelationNet
            v-else-if="detailSeeds.correct.length"
            :seed-correct="detailSeeds.correct"
            :seed-wrong="detailSeeds.wrong"
            :seed-other="detailSeeds.other"
          />
        </scroll-view>
      </view>
    </view>

    <PracticeQuiz
      v-if="quizOpen"
      :kp="quizKp"
      :questions="quizQs"
      :recorder="quizRecorder"
      @close="quizOpen = false"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { czHwPassages, type ReadingBlock } from '@/api/curriculum'
import {
  getClozeAnalysis, clozePractice, getPassageStudy,
  type ClozeAnalysis, type StudyWord, type PassageSegment,
} from '@/api/userPapers'
import WrongRelationNet from '@/components/WrongRelationNet.vue'
import PracticeQuiz from '@/components/PracticeQuiz.vue'
import KeyWordsList from '@/components/KeyWordsList.vue'
import WordCard from '@/components/WordCard.vue'
import SentenceCard from '@/components/SentenceCard.vue'

type CzQ = {
  id: string
  no?: string | null
  type?: string | null
  stem?: string | null
  options?: string[] | null
  student_answer?: string | null
  correct_answer?: string | null
  is_wrong?: boolean
  studied?: boolean
  wrong_record_id?: string | null
}

const paperId = ref('')
const loading = ref(true)
const blocks = ref<ReadingBlock[]>([])
const activeBlock = ref(0)
const collapsed = ref(false)

const curBlock = computed(() => blocks.value[activeBlock.value] || null)
const allQs = computed(() => blocks.value.flatMap(b => b.questions || []) as CzQ[])
const readTotal = computed(() => allQs.value.length)
const readStudied = computed(() => allQs.value.filter(q => q.studied).length)
const readPct = computed(() => readTotal.value ? Math.round(readStudied.value / readTotal.value * 100) : 0)
const readStatus = computed(() => {
  if (!readStudied.value) return 'none'
  if (readStudied.value >= readTotal.value) return 'done'
  return 'doing'
})
const readStatusLabel = computed(() => ({ none: '未学', doing: '学习中', done: '已学' }[readStatus.value]))

function tabSub(bk: ReadingBlock) {
  const qs = bk.questions || []
  const st = qs.filter((q: any) => q.studied).length
  return `${qs.length} 空 · ${st} 已学`
}

function hasOpts(q: CzQ | null | undefined) {
  return !!(q?.options && q.options.length)
}
function normNo(raw: any): string {
  const m = String(raw ?? '').match(/\d+/)
  return m ? m[0] : ''
}
function stripOpt(op: string) {
  return String(op || '').replace(/^[A-Da-d][.、)．]\s*/, '').trim()
}
/**
 * 取空的可展示正确词:字母答 → 对应选项正文;否则去选项前缀后的答案。
 */
function resolveCorrectWord(q: CzQ): string {
  const raw = (q.correct_answer || '').trim()
  if (!raw) return ''
  const opts = q.options || []
  if (opts.length && /^[A-Da-d]$/.test(raw)) {
    const i = raw.toUpperCase().charCodeAt(0) - 65
    if (i >= 0 && i < opts.length) return stripOpt(opts[i])
  }
  for (const o of opts) {
    if (raw === o || raw.toUpperCase() === letterOf(opts.indexOf(o))) return stripOpt(o)
    if (raw === stripOpt(o)) return stripOpt(o)
  }
  // 「A. coming」类
  if (/^[A-Da-d][.、)．]/.test(raw)) return stripOpt(raw)
  return raw
}
/** 方案 C 填空结果:有答填绿词;无答降级为 (n) */
type ClozeFillPart = { kind: 'text' | 'fill' | 'hole'; t: string }
type ClozeFillChip = { no: string; word?: string }
type ClozeFillResult = {
  text: string
  parts: ClozeFillPart[]
  missing: string[]
  chips: ClozeFillChip[]
}

/**
 * 方案 C:长难句解析前把空号换成正确答案;无 correct_answer 时保留 (n) 并记 missing。
 * 卷面原文不变,仅句卡 / 完整精讲用。
 */
function fillClozeBlanks(text: string, questions: CzQ[]): ClozeFillResult {
  const empty: ClozeFillResult = { text, parts: [{ kind: 'text', t: text }], missing: [], chips: [] }
  if (!text) return { text: '', parts: [], missing: [], chips: [] }

  const ansByNo: Record<string, string> = {}
  const noSet = new Set<string>()
  for (const q of questions) {
    const no = normNo(q.no)
    if (!no) continue
    noSet.add(no)
    const w = resolveCorrectWord(q)
    if (w) ansByNo[no] = w
  }
  const nos = [...noSet].sort((a, b) => b.length - a.length || Number(b) - Number(a))
  if (!nos.length) return empty

  type Hit = { start: number; end: number; no: string }
  const hits: Hit[] = []
  const covered = (s: number, e: number) => hits.some(h => s < h.end && e > h.start)

  const explicit = /_{2,}\s*(\d{1,2})\s*_{0,}|[（(【\[]\s*(\d{1,2})\s*[）)】\]]/g
  for (const m of text.matchAll(explicit)) {
    const no = m[1] || m[2]
    if (!no || !noSet.has(no) || m.index == null) continue
    const start = m.index, end = start + m[0].length
    if (!covered(start, end)) hits.push({ start, end, no })
  }
  for (const no of nos) {
    if (no.length > 2) continue
    const re = new RegExp(`(^|[^0-9A-Za-z])(${no})(?![0-9])`, 'g')
    for (const m of text.matchAll(re)) {
      if (m.index == null) continue
      const lead = m[1] || ''
      const start = m.index + lead.length, end = start + no.length
      if (!covered(start, end)) hits.push({ start, end, no })
    }
  }
  hits.sort((a, b) => a.start - b.start)
  const kept: Hit[] = []
  for (const h of hits) {
    if (kept.some(k => h.start < k.end && h.end > k.start)) continue
    kept.push(h)
  }
  if (!kept.length) return empty

  const parts: ClozeFillPart[] = []
  const missing: string[] = []
  const chipMap = new Map<string, ClozeFillChip>()
  let cur = 0
  for (const h of kept) {
    if (h.start > cur) parts.push({ kind: 'text', t: text.slice(cur, h.start) })
    const word = ansByNo[h.no]
    if (word) {
      parts.push({ kind: 'fill', t: word })
      if (!chipMap.has(h.no)) chipMap.set(h.no, { no: h.no, word })
    } else {
      parts.push({ kind: 'hole', t: `(${h.no})` })
      if (!missing.includes(h.no)) missing.push(h.no)
      if (!chipMap.has(h.no)) chipMap.set(h.no, { no: h.no })
    }
    cur = h.end
  }
  if (cur < text.length) parts.push({ kind: 'text', t: text.slice(cur) })

  const plain = parts.map(p => p.t).join('')
  const chips = [...chipMap.values()].sort((a, b) => Number(a.no) - Number(b.no))
  return { text: plain, parts, missing, chips }
}

/** 当前语篇小题 → 填空后的长难句纯文本(供精讲页 / 列表展示) */
function filledLongSentence(raw: string | null | undefined): string {
  return fillClozeSentence(raw).text
}

/** 方案 C 完整结果(句卡用) */
function fillClozeSentence(raw: string | null | undefined): ClozeFillResult {
  const t = (raw || '').trim()
  if (!t) return { text: '', parts: [], missing: [], chips: [] }
  return fillClozeBlanks(t, (curBlock.value?.questions || []) as CzQ[])
}
function letterOf(i: number) { return String.fromCharCode(65 + i) }
function isCorrectOpt(q: CzQ, op: string, oi?: number) {
  const ans = (q.correct_answer || '').trim()
  if (!ans) return false
  const au = ans.toUpperCase()
  if (typeof oi === 'number' && au === letterOf(oi)) return true
  const letter = (op.match(/^([A-D])/i) || [])[1]
  if (letter && au === letter.toUpperCase()) return true
  const body = stripOpt(op)
  return au === op.trim().toUpperCase() || au === body.toUpperCase()
}
function isStudentOpt(q: CzQ, op: string, oi?: number) {
  const stu = (q.student_answer || '').trim()
  if (!stu) return false
  const su = stu.toUpperCase()
  if (typeof oi === 'number' && su === letterOf(oi)) return true
  const letter = (op.match(/^([A-D])/i) || [])[1]
  if (letter && su === letter.toUpperCase()) return true
  const body = stripOpt(op)
  return su === op.trim().toUpperCase() || su === body.toUpperCase()
}
function optCls(q: CzQ, op: string, oi: number) {
  if (isCorrectOpt(q, op, oi)) return 'ok'
  if (isStudentOpt(q, op, oi) && q.is_wrong) return 'bad'
  return ''
}
function optHint(q: CzQ, op: string, oi: number) {
  const ok = isCorrectOpt(q, op, oi)
  const stu = isStudentOpt(q, op, oi)
  if (ok && stu) return '正确 · 你选'
  if (ok) return '正确'
  if (stu && q.is_wrong) return '你选'
  return ''
}

/** 扁平渲染节点:句首标 / 空号胶囊 / 文本段(词·句高亮) */
type PassNode = {
  kind: 'mark' | 'blank' | 'seg'
  t?: string
  no?: string
  wrong?: boolean
  studied?: boolean
  word_idx?: number | null
  sentence_idx?: number | null
}

type BlankHit = { start: number; end: number; no: string; wrong: boolean; studied: boolean }

/** 空号在原文中的字符区间(对绿/错红/未学灰) */
function blankHits(grp: ReadingBlock): BlankHit[] {
  const text = grp.passage || ''
  const map: Record<string, { wrong: boolean; studied: boolean }> = {}
  for (const q of (grp.questions || []) as CzQ[]) {
    const no = normNo(q.no)
    if (no) map[no] = { wrong: !!q.is_wrong, studied: !!q.studied }
  }
  const nos = Object.keys(map)
  if (!text || !nos.length) return []
  type Hit = { start: number; end: number; no: string }
  const hits: Hit[] = []
  const covered = (s: number, e: number) => hits.some(h => s < h.end && e > h.start)
  const explicit = /_{2,}\s*(\d{1,2})\s*_{0,}|[（(【\[]\s*(\d{1,2})\s*[）)】\]]/g
  for (const m of text.matchAll(explicit)) {
    const no = m[1] || m[2]
    if (!no || !(no in map) || m.index == null) continue
    const start = m.index, end = start + m[0].length
    if (!covered(start, end)) hits.push({ start, end, no })
  }
  for (const no of nos) {
    if (no.length > 2) continue
    const re = new RegExp(`(^|[^0-9])(${no})(?![0-9])`, 'g')
    for (const m of text.matchAll(re)) {
      if (m.index == null) continue
      const lead = m[1] || ''
      const start = m.index + lead.length, end = start + no.length
      if (!covered(start, end)) hits.push({ start, end, no })
    }
  }
  hits.sort((a, b) => a.start - b.start)
  const kept: BlankHit[] = []
  for (const h of hits) {
    if (kept.some(k => h.start < k.end && h.end > k.start)) continue
    const st = map[h.no]
    kept.push({ ...h, wrong: !!st?.wrong, studied: !!st?.studied })
  }
  return kept
}

/**
 * 方案 A:passage-study 分段 ∩ 空号区间。
 * 空号优先;其余文本带 word_idx/sentence_idx;句首插橙标。
 */
function passageNodes(bi: number, grp: ReadingBlock): PassNode[] {
  const text = grp.passage || ''
  if (!text) return []
  const blanks = blankHits(grp)
  const sd = blockStudy.value[bi]
  const segs: PassageSegment[] = (sd?.segments?.length
    ? sd.segments
    : [{ t: text, word_idx: null, sentence_idx: null }]) as PassageSegment[]

  type Piece = { start: number; end: number; word_idx: number | null; sentence_idx: number | null }
  const pieces: Piece[] = []
  let pos = 0
  for (const s of segs) {
    const len = (s.t || '').length
    pieces.push({
      start: pos, end: pos + len,
      word_idx: s.word_idx ?? null, sentence_idx: s.sentence_idx ?? null,
    })
    pos += len
  }
  // 分段长度与原文不一致时退回「纯空号」,避免错位高亮
  if (pos !== text.length) {
    const out: PassNode[] = []
    let cur = 0
    for (const h of blanks) {
      if (h.start > cur) out.push({ kind: 'seg', t: text.slice(cur, h.start), word_idx: null, sentence_idx: null })
      out.push({ kind: 'blank', no: h.no, wrong: h.wrong, studied: h.studied })
      cur = h.end
    }
    if (cur < text.length) out.push({ kind: 'seg', t: text.slice(cur), word_idx: null, sentence_idx: null })
    return out.length ? out : [{ kind: 'seg', t: text, word_idx: null, sentence_idx: null }]
  }

  const out: PassNode[] = []
  let prevSi: number | null | undefined
  let i = 0
  while (i < text.length) {
    const blank = blanks.find(b => b.start === i)
    if (blank) {
      out.push({ kind: 'blank', no: blank.no, wrong: blank.wrong, studied: blank.studied })
      i = blank.end
      continue
    }
    const piece = pieces.find(p => i >= p.start && i < p.end)
    if (!piece) { i += 1; continue }
    const nextBlank = blanks.find(b => b.start > i)
    const end = Math.min(piece.end, nextBlank ? nextBlank.start : text.length)
    const si = piece.sentence_idx
    if (si != null && si !== prevSi) out.push({ kind: 'mark', sentence_idx: si })
    prevSi = si
    out.push({
      kind: 'seg', t: text.slice(i, end),
      word_idx: piece.word_idx, sentence_idx: piece.sentence_idx,
    })
    i = end
  }
  return out.length ? out : [{ kind: 'seg', t: text, word_idx: null, sentence_idx: null }]
}

function scrollToQ(no: string) {
  if (!no) return
  uni.pageScrollTo({ selector: `#cz-${no}`, duration: 280 })
}

// ── 本篇精讲(与阅读同源 passage-study)────────────────────────────────
const blockStudy = ref<Record<number, { words: StudyWord[]; sentences: string[]; segments: PassageSegment[] }>>({})
const curWords = computed(() => blockStudy.value[activeBlock.value]?.words || [])
const curSentences = computed(() => blockStudy.value[activeBlock.value]?.sentences || [])
const studyOpen = ref(false)
const studyTab = ref<'word' | 'ls'>('word')
const sheetCard = ref<StudyWord | null>(null)
/** 方案 C 句卡:满句 + 分段着色 + 芯片 + 未填空号 */
const sentenceCard = ref<ClozeFillResult | null>(null)

function openFilledCard(raw: string | null | undefined) {
  const r = fillClozeSentence(raw)
  sentenceCard.value = r.text ? r : null
}
function segTap(node: PassNode) {
  const sd = blockStudy.value[activeBlock.value]
  if (!sd || node.kind !== 'seg') return
  if (node.word_idx != null) { sheetCard.value = sd.words[node.word_idx] ?? null; return }
  if (node.sentence_idx != null) openFilledCard(sd.sentences[node.sentence_idx])
}
function openSentenceIdx(sentenceIdx: number) {
  const sd = blockStudy.value[activeBlock.value]
  if (!sd) return
  openFilledCard(sd.sentences[sentenceIdx])
}
function openSentencePage(s: string) {
  const filled = filledLongSentence(s)
  uni.navigateTo({
    url: `/pages/user-papers/sentence?text=${encodeURIComponent(filled || s)}&paperId=${paperId.value}`,
  })
}
async function loadStudy() {
  for (const [bi, bk] of blocks.value.entries()) {
    if (!bk.passage) continue
    try {
      const r = await getPassageStudy(bk.passage, paperId.value || undefined)
      blockStudy.value = {
        ...blockStudy.value,
        [bi]: { words: r.words || [], sentences: r.sentences || [], segments: r.segments || [] },
      }
    } catch { /* 单篇失败不影响其它 */ }
  }
}

const detailQ = ref<CzQ | null>(null)
const dualOpen = ref(false)
const ana = ref<ClozeAnalysis | null>(null)
const anaLoading = ref(false)
const detailWrnId = computed(() => detailQ.value?.wrong_record_id || '')
const detailSeeds = computed(() => {
  const q = detailQ.value
  if (!q || detailWrnId.value) return { correct: [] as string[], wrong: [] as string[], other: [] as string[] }
  const resolve = (raw: string | null | undefined) => {
    const ans = (raw || '').trim()
    if (!ans) return ''
    const opts = q.options || []
    if (opts.length && /^[A-Da-d]$/.test(ans)) {
      const i = ans.toUpperCase().charCodeAt(0) - 65
      if (i >= 0 && i < opts.length) return stripOpt(opts[i])
    }
    for (const o of opts) {
      if (ans === o || ans === stripOpt(o)) return stripOpt(o)
    }
    return ans
  }
  const seedable = (t: string) => !!t && t.length <= 40 && t.split(/\s+/).length <= 4 && /[a-zA-Z]/.test(t)
  const correct = resolve(q.correct_answer)
  const wrong = q.is_wrong ? resolve(q.student_answer) : ''
  const other: string[] = []
  const ca = correct.toLowerCase(), wr = wrong.toLowerCase()
  for (const o of q.options || []) {
    const t = stripOpt(o)
    if (!seedable(t)) continue
    const k = t.toLowerCase()
    if (k === ca || k === wr) continue
    other.push(t)
  }
  return {
    correct: seedable(correct) ? [correct] : [],
    wrong: seedable(wrong) ? [wrong] : [],
    other,
  }
})

async function openDetail(q: CzQ) {
  detailQ.value = q
  dualOpen.value = false
  ana.value = null
  anaLoading.value = true
  try {
    ana.value = await getClozeAnalysis(q.id)
    markStudiedLocal(q.id)
  } catch (e: any) {
    ana.value = { error: e?.message || '解析失败' }
  } finally { anaLoading.value = false }
}
function closeDetail() { detailQ.value = null }

function markStudiedLocal(qid: string) {
  for (const b of blocks.value) {
    for (const q of (b.questions || []) as CzQ[]) {
      if (q.id === qid) q.studied = true
    }
  }
}

const quizOpen = ref(false)
const quizQs = ref<any[]>([])
const quizKp = ref('完形巩固')
const pracLoading = ref(false)
async function startPractice() {
  if (!detailQ.value || pracLoading.value) return
  pracLoading.value = true
  try {
    const r = await clozePractice(detailQ.value.id)
    const qs = (r.questions || []).filter((x: any) => x.stem && x.options?.length >= 2)
    if (!qs.length) { uni.showToast({ title: r.error || '暂无巩固题', icon: 'none' }); return }
    quizKp.value = r.clue_type || ana.value?.clue_type || '完形巩固'
    quizQs.value = qs
    quizOpen.value = true
    markStudiedLocal(detailQ.value.id)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '出题失败', icon: 'none' })
  } finally { pracLoading.value = false }
}
async function quizRecorder(total: number, correct: number) {
  return `本轮 ${correct}/${total} 正确`
}

async function load() {
  if (!paperId.value) return
  loading.value = true
  try {
    blocks.value = (await czHwPassages(paperId.value)).blocks || []
    activeBlock.value = 0
    blockStudy.value = {}
  } catch { blocks.value = [] }
  finally { loading.value = false }
  loadStudy()
}

onLoad((q: any) => {
  paperId.value = q.paperId || ''
  if (q.title) uni.setNavigationBarTitle({ title: decodeURIComponent(q.title) })
  load()
})
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load() })
</script>

<style scoped>
.page {
  min-height: 100vh; background: #f0f6fc;
  /* 顶边距收进 sticky-stack,避免导航与原文夹缝露题 */
  padding: 0 24rpx 140rpx; box-sizing: border-box;
}
.tip { text-align: center; color: #93a0b3; padding: 60rpx 0; }
.foot-pad { height: 120rpx; }

/* 方案 S:进度+Tab+原文整块吸顶 */
.sticky-stack {
  position: sticky; top: 0; z-index: 5;
  background: #f0f6fc;
  padding: 24rpx 24rpx 12rpx;
  margin: 0 -24rpx;
  box-shadow: 0 12rpx 20rpx -10rpx rgba(45, 80, 150, .16);
}
.rd-head {
  position: relative; overflow: hidden; display: flex; align-items: center; gap: 16rpx;
  background: #fff; border: 2rpx solid #e6ebf2; border-radius: 18rpx; padding: 20rpx 22rpx; margin-bottom: 14rpx;
}
.rd-fill { position: absolute; left: 0; top: 0; bottom: 0; transition: width .3s; }
.rhf-doing { background: linear-gradient(90deg,#e8f2ff,#f4f9ff); }
.rhf-done { background: linear-gradient(90deg,#e9f6f1,#f4fbf8); }
.rd-num { position: relative; }
.rd-s { font-size: 40rpx; font-weight: 800; color: #3d8bf5; }
.rd-t { font-size: 24rpx; color: #b7c2d4; font-weight: 700; }
.rd-info { position: relative; }
.rd-status { font-size: 26rpx; font-weight: 800; color: #64748b; }
.rs-doing { color: #3d8bf5; }
.rs-done { color: #2fa98a; }
.rd-pct { margin-left: 8rpx; font-size: 22rpx; }
.rd-sub { display: block; font-size: 22rpx; color: #93a0b3; margin-top: 4rpx; }

.pass-tabs {
  display: flex; gap: 8rpx; background: #fff; border: 2rpx solid #e6ebf2;
  border-radius: 16rpx; padding: 8rpx; margin-bottom: 14rpx;
}
.pass-tab { flex: 1; text-align: center; padding: 14rpx 8rpx; border-radius: 12rpx; }
.pass-tab.on { background: #e8f2ff; }
.pt-t { display: block; font-size: 26rpx; font-weight: 700; color: #64748b; }
.pass-tab.on .pt-t { color: #3d8bf5; }
.pt-s { display: block; font-size: 20rpx; color: #94a3b8; margin-top: 4rpx; }

.passage {
  background: #fff; border: 2rpx solid #e3e9f2; border-radius: 18rpx;
  padding: 22rpx 24rpx; margin-bottom: 0;
  box-shadow: 0 4rpx 20rpx rgba(45, 80, 150, .06);
}
.passage-head { display: flex; justify-content: space-between; align-items: center; }
.passage-title { font-size: 24rpx; font-weight: 700; color: #3d8bf5; }
.passage-toggle {
  font-size: 22rpx; color: #3d8bf5; font-weight: 700;
  padding: 6rpx 14rpx; border-radius: 10rpx;
  background: #e8f2ff; border: 2rpx solid #85B7EB;
}
.passage-body { margin-top: 14rpx; }
.passage-legend {
  display: flex; flex-wrap: wrap; gap: 16rpx 20rpx; align-items: center;
  padding: 12rpx 14rpx; margin-bottom: 16rpx;
  background: #f8fafc; border-radius: 10rpx; border: 1rpx dashed #d7e0ec;
}
.lg-item { font-size: 22rpx; color: #64748b; }
.lg-sample { font-weight: 700; padding-bottom: 2rpx; }
.lg-w { color: #3d8bf5; border-bottom: 2rpx dashed #3d8bf5; }
.lg-s { color: #e08a4c; border-bottom: 2rpx dashed #e08a4c; }
.lg-b { color: #1f8a6e; background: #e9f6f1; border-radius: 6rpx; padding: 0 8rpx; font-size: 20rpx; }
.lg-hint { color: #94a3b8; }
.passage-text {
  /* 方案 R:限高内滚,吸顶时首屏仍露题卡(对齐阅读精讲) */
  display: block; font-size: 28rpx; color: #3a4353; line-height: 2;
  max-height: 42vh; overflow-y: auto; -webkit-overflow-scrolling: touch;
  white-space: pre-wrap; letter-spacing: 0.02em;
}
.seg-w { color: #3d8bf5; font-weight: 600; border-bottom: 2rpx dashed #3d8bf5; }
.seg-s { border-bottom: 2rpx dashed #e08a4c; }
.seg-w.seg-s { color: #3d8bf5; border-bottom-color: #3d8bf5; }
.s-mark {
  display: inline-flex; align-items: center; justify-content: center;
  width: 28rpx; height: 28rpx; margin-right: 6rpx; vertical-align: text-top;
  background: #fdf3ea; border-radius: 6rpx;
}
.s-mark-ic { width: 18rpx; height: 18rpx; }
.p-blank {
  display: inline; font-size: 22rpx; font-weight: 800;
  padding: 2rpx 10rpx; margin: 0 4rpx; border-radius: 8rpx;
}
.p-blank.ok { background: #e9f6f1; color: #1f8a6e; border: 1rpx solid #b7e0d0; }
.p-blank.bad { background: #fcebeb; color: #a32d2d; border: 1rpx solid #f0b6b6; }
.p-blank.todo { background: #eef2f7; color: #64748b; border: 1rpx solid #d5dde8; }

.q-card {
  background: #fff; border: 2rpx solid #e6ebf2; border-radius: 16rpx;
  padding: 20rpx; margin-bottom: 14rpx; border-left: 6rpx solid transparent;
  margin-top: 4rpx;
}
.q-card.wrong { border-left-color: #e24b4a; background: #fffbfb; }
.q-card.okborder { border-left-color: #b7e0d0; }
.q-head { display: flex; align-items: center; gap: 10rpx; margin-bottom: 10rpx; flex-wrap: wrap; }
.q-tick {
  width: 28rpx; height: 28rpx; border-radius: 50%; border: 3rpx solid #c5d0df;
}
.q-tick.done { border-color: #2fa98a; background: #e9f6f1; }
.chip { font-size: 20rpx; font-weight: 800; padding: 2rpx 12rpx; border-radius: 8rpx; background: #e8f2ff; color: #3d8bf5; }
.chip.ok { background: #e9f6f1; color: #2fa98a; }
.chip.bad { background: #fcebeb; color: #a32d2d; }
.q-no { font-size: 24rpx; color: #64748b; font-weight: 700; }
.q-stem { display: block; font-size: 28rpx; line-height: 1.55; color: #1f2937; margin-bottom: 12rpx; }
.q-opts { display: flex; flex-direction: column; gap: 10rpx; margin-bottom: 10rpx; }
.q-opt {
  display: flex; align-items: center; gap: 12rpx;
  padding: 14rpx 16rpx; border-radius: 12rpx; border: 1rpx solid #e6ebf2;
  background: #fafbfd; font-size: 26rpx;
}
.q-opt.ok { background: #e9f6f1; border-color: #b7e0d0; color: #1f8a6e; font-weight: 700; }
.q-opt.bad { background: #fcebeb; border-color: #f0b6b6; color: #a32d2d; font-weight: 700; }
.q-opt-t { flex: 1; }
.q-opt-h { font-size: 22rpx; font-weight: 800; }
.q-foot { display: flex; align-items: center; justify-content: space-between; gap: 12rpx; }
.ans { font-size: 24rpx; color: #2fa98a; font-weight: 700; }
.ans.bad { color: #64748b; }
.go { font-size: 24rpx; font-weight: 800; color: #3d8bf5; flex-shrink: 0; }

.modal {
  position: fixed; inset: 0; background: rgba(15,23,42,.45); z-index: 100;
  display: flex; align-items: flex-end;
}
.sheet {
  width: 100%; max-height: 92vh; background: #f0f6fc;
  border-radius: 28rpx 28rpx 0 0; display: flex; flex-direction: column;
}
.sheet-bar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 24rpx 28rpx 12rpx; background: #fff;
  border-radius: 28rpx 28rpx 0 0; border-bottom: 2rpx solid #e6ebf2;
}
.sheet-t { font-size: 30rpx; font-weight: 800; }
.sheet-x { font-size: 26rpx; color: #64748b; font-weight: 700; }
.sheet-body { flex: 1; max-height: 80vh; padding: 20rpx 24rpx 40rpx; box-sizing: border-box; }
.warm {
  background: #f7f3e6; border: 2rpx solid #e0d6b8; border-radius: 18rpx;
  padding: 20rpx; margin-bottom: 16rpx;
}
.warm.wrong { background: #fff8f0; }
.ansline { display: flex; flex-wrap: wrap; gap: 20rpx; margin-top: 12rpx; font-size: 24rpx; font-weight: 700; }
.ansline .x { color: #e24b4a; }
.ansline .o { color: #2fa98a; }

.dual-fold {
  background: #fff; border: 2rpx dashed #85B7EB; border-radius: 16rpx;
  padding: 18rpx 22rpx; margin-bottom: 12rpx;
}
.dual-sum { font-size: 26rpx; font-weight: 800; color: #3d8bf5; }
.dual {
  background: #fff; border: 2rpx dashed #85B7EB; border-radius: 16rpx;
  padding: 18rpx 22rpx; margin-bottom: 16rpx; margin-top: -6rpx;
}
.dual-row { display: flex; gap: 12rpx; margin: 8rpx 0; font-size: 24rpx; line-height: 1.55; color: #334155; }
.dual-row .k { flex-shrink: 0; min-width: 120rpx; color: #64748b; font-weight: 700; }
.muted { color: #94a3b8; font-size: 24rpx; }

.drill {
  display: flex; align-items: center; gap: 16rpx;
  border-radius: 16rpx; padding: 22rpx 24rpx; margin-bottom: 16rpx;
  border: 3rpx solid #bcd8ff; background: #eaf2ff;
}
.drill.busy { opacity: .65; }
.drill-t { display: block; font-size: 28rpx; font-weight: 800; color: #185fa5; }
.drill-d { display: block; font-size: 22rpx; color: #64748b; margin-top: 4rpx; }
.drill-go { margin-left: auto; color: #185fa5; font-weight: 800; font-size: 32rpx; }

/* 本篇精讲条 / 上拉面板(对齐阅读) */
.study-bar {
  position: fixed; left: 24rpx; right: 24rpx; bottom: 24rpx; z-index: 40;
  display: flex; align-items: center; gap: 12rpx; background: #fff;
  border: 2rpx solid #e6ebf2; border-radius: 18rpx; padding: 20rpx 22rpx;
  box-shadow: 0 -2rpx 24rpx rgba(45, 80, 150, .12), 0 8rpx 24rpx rgba(45, 80, 150, .1);
}
.sb-ic { width: 34rpx; height: 34rpx; flex: none; }
.sb-t { font-size: 28rpx; font-weight: 700; color: #1f2733; }
.sb-cnt { margin-left: auto; font-size: 24rpx; color: #8a95a5; }
.sb-n { color: #3d8bf5; font-weight: 700; }
.sb-up { width: 32rpx; height: 32rpx; flex: none; transform: rotate(180deg); }
.study-mask {
  position: fixed; inset: 0; z-index: 60; background: rgba(20, 28, 40, .45);
  display: flex; align-items: flex-end;
}
.study-panel {
  width: 100%; max-height: 78vh; background: #f4f6fa;
  border-radius: 26rpx 26rpx 0 0; padding: 12rpx 24rpx 32rpx;
  box-sizing: border-box; display: flex; flex-direction: column;
}
.grab { width: 72rpx; height: 8rpx; border-radius: 4rpx; background: #dce3ec; margin: 8rpx auto 14rpx; }
.study-hd { display: flex; align-items: center; gap: 12rpx; padding: 0 2rpx 16rpx; }
.sh-ic { width: 34rpx; height: 34rpx; flex: none; }
.sh-t { font-size: 30rpx; font-weight: 800; color: #1f2733; }
.sh-x { width: 34rpx; height: 34rpx; flex: none; margin-left: auto; }
.study-seg {
  display: flex; gap: 10rpx; background: #e8edf4; border-radius: 16rpx;
  padding: 6rpx; margin-bottom: 16rpx;
}
.seg-i { flex: 1; text-align: center; font-size: 26rpx; color: #6b7688; padding: 14rpx 0; border-radius: 12rpx; }
.seg-i.on { color: #3d8bf5; font-weight: 700; background: #fff; box-shadow: 0 3rpx 10rpx rgba(45, 80, 150, .12); }
.study-body { max-height: 58vh; }
.ls-hint { font-size: 22rpx; color: #93a0b3; margin: 2rpx 4rpx 12rpx; }
.ls-card {
  display: flex; align-items: flex-start; gap: 14rpx; background: #fff;
  border: 2rpx solid #e9edf3; border-radius: 16rpx; padding: 18rpx;
  margin-bottom: 14rpx; box-shadow: 0 4rpx 16rpx rgba(45, 80, 150, .04);
}
.ls-no {
  flex: none; width: 40rpx; height: 40rpx; border-radius: 50%;
  background: #eaf2fe; color: #3d8bf5; font-size: 24rpx; font-weight: 700;
  text-align: center; line-height: 40rpx;
}
.ls-text { flex: 1; min-width: 0; font-size: 25rpx; line-height: 1.6; color: #1f2733; }
.ls-go { flex: none; font-size: 22rpx; font-weight: 600; color: #3d8bf5; margin-top: 6rpx; }
</style>

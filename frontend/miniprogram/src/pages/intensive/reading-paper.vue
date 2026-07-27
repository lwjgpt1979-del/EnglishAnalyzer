<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!blocks.length" class="tip">该卷没有阅读理解内容</view>
    <template v-else>
      <!-- 卷头:整卷精讲进度(进度即底色,背景填充式,全项目统一) -->
      <view class="rd-head">
        <view class="rd-fill" :class="'rhf-' + readStatus" :style="{ width: readPct + '%' }"></view>
        <view class="rd-num"><text class="rd-s">{{ readStudied }}</text><text class="rd-t">/{{ readTotal }}</text></view>
        <view class="rd-info">
          <view class="rd-status" :class="'rs-' + readStatus">{{ readStatusLabel }}<text class="rd-pct">{{ readPct }}%</text></view>
          <text class="rd-sub">已精讲 {{ readStudied }} / {{ readTotal }} 题</text>
        </view>
      </view>
      <view v-for="(bk, bi) in blocks" :key="bi" class="block">
        <!-- 原文:吸顶常驻,读写对照 -->
        <view v-if="bk.passage" class="passage" @tap="toggle(bi)">
          <view class="passage-head">
            <view class="passage-brand">
              <view class="ic-book"></view>
              <text class="passage-title">原文 · 常驻对照</text>
            </view>
            <text class="passage-toggle">{{ collapsed[bi] ? '展开 ▾' : '收起 ▴' }}</text>
          </view>
          <view v-if="!collapsed[bi]" class="passage-text">
            <template v-for="(seg, si) in passageSegs(bi, bk.passage)" :key="si">
              <!-- 高亮片段(词/长难句):catch 掉点击,不再冒泡触发原文收起/展开 -->
              <text v-if="seg.word_idx != null || seg.sentence_idx != null"
                    :class="{ 'ev-hl': seg.ev, 'seg-w': seg.word_idx != null, 'seg-s': seg.sentence_idx != null }"
                    @tap.stop="segTap(bi, seg)">{{ seg.t }}</text>
              <text v-else :class="{ 'ev-hl': seg.ev }">{{ seg.t }}</text>
            </template>
          </view>
        </view>

        <!-- 讲义卡片:题型大标签 + 四件套 -->
        <view v-for="(q, qi) in bk.questions" :key="qi" class="q-card">
          <view class="q-head">
            <view class="q-tick" :class="q.studied ? 'q-tick-done' : 'q-tick-todo'"></view>
            <text class="q-type" :class="typeCls(q)">{{ typeLabel(q) }}</text>
            <text v-if="q.is_wrong" class="st-chip st-bad">答错</text>
            <text v-else class="st-chip st-ok">答对</text>
            <text class="q-no">{{ q.no ? `第 ${q.no} 题` : '' }}</text>
          </view>
          <text class="q-stem">{{ q.stem || '（题干为空）' }}</text>

          <!-- P3 主动作答:选项内嵌题干,点字母作答(治 OCR 抓不到卷面圈选) -->
          <view class="ans-pick">
            <text class="ap-lbl">作答</text>
            <view v-for="L in ['A', 'B', 'C', 'D']" :key="L" class="ap-btn"
                  :class="answered[q.id]?.chosen === L ? (answered[q.id]?.is_correct === false ? 'ap-bad' : 'ap-ok') : ''"
                  @tap="answer(q, L)">{{ L }}</view>
            <text v-if="answered[q.id]" class="ap-res"
                  :class="answered[q.id].is_correct === false ? 'ap-rbad' : 'ap-rok'">
              {{ answered[q.id].is_correct === null ? '已记录' : (answered[q.id].is_correct ? '答对' : '答错') }}
            </text>
          </view>

          <view class="q-ans">
            <view class="ans-chip" :class="q.is_wrong ? 'ac-bad' : 'ac-ok'">
              <text>你选 {{ q.student_answer || '未识别' }}</text>
              <view class="ic ans-ic" :class="q.is_wrong ? 'ic-x-circle' : 'ic-check-circle'"></view>
            </view>
            <view class="ans-chip ac-ok">
              <text>正确 {{ q.correct_answer || '未提供' }}</text>
              <view class="ic ans-ic ic-check-circle"></view>
            </view>
          </view>
          <text v-if="q.explanation" class="q-exp">{{ q.explanation }}</text>

          <!-- 解题精讲 + 练同类 -->
          <view class="q-acts">
            <view class="q-act" :class="{ on: anaOpen[q.id] }" @tap="toggleAna(q, bi)">
              <text>{{ anaLoading[q.id] ? '解析中…' : (anaOpen[q.id] ? '收起解析' : '看解析') }}</text>
            </view>
            <view class="q-act q-act-sim" @tap="practice(q.id)">
              <text>{{ pracLoading === q.id ? '出题中…' : '练同类' }}</text>
            </view>
          </view>

          <!-- 解析面板:四件套(左侧细色条分区) -->
          <view v-if="anaOpen[q.id] && ana[q.id]" class="ana">
            <text v-if="ana[q.id].error" class="ana-err">{{ ana[q.id].error }}</text>
            <template v-else>
              <view v-if="ana[q.id].evidence" class="ab ab-loc">
                <text class="ab-k">① 回原文定位</text>
                <text class="ab-quote">“{{ ana[q.id].evidence }}”</text>
              </view>
              <view v-if="ana[q.id].answer_reason" class="ab ab-why">
                <text class="ab-k">② 为什么对</text>
                <text class="ab-t">{{ ana[q.id].answer_reason }}</text>
              </view>
              <view v-if="hasDistractors(q.id)" class="ab ab-dis">
                <text class="ab-k">③ 干扰项为什么错</text>
                <view v-for="(d, key) in ana[q.id].distractors" :key="key" class="dis-row">
                  <text class="dis-key">{{ key }}</text>
                  <text class="dis-why">{{ d.why_wrong }}</text>
                </view>
              </view>
              <view v-if="ana[q.id].skill_tip" class="ab ab-tip">
                <text class="ab-k">④ 解题技巧</text>
                <text class="ab-t">{{ ana[q.id].skill_tip }}</text>
              </view>
            </template>
          </view>
        </view>
      </view>

      <!-- P2 读后小结·提问块:该卷阅读题按题型对错 + 一句话诊断(进度即底色) -->
      <view v-if="summary && summary.total" class="rs-card">
        <view class="rs-hd">
          <view class="ic-clipboard rs-ic"></view>
          <text class="rs-tt">读后小结</text>
          <text class="rs-meta">已答 {{ summary.answered }}/{{ summary.total }} · 错 {{ summary.wrong }}</text>
        </view>
        <view v-for="(s, i) in summary.by_skill" :key="i" class="rs-row">
          <view class="rs-fill" :class="rateCls(s)" :style="{ width: ratePct(s) + '%' }"></view>
          <text class="rs-sk">{{ s.skill }}</text>
          <text class="rs-rt" :class="rateTxtCls(s)">{{ s.total - s.wrong }}/{{ s.total }} 对</text>
        </view>
        <!-- 长难句块:解析/卡 + 卡在哪些结构 -->
        <view v-if="summary.sentences && summary.sentences.total" class="rs-sub">
          <text class="rs-sub-t">长难句 解析 {{ summary.sentences.total }} · 卡 {{ summary.sentences.stuck }}</text>
          <view v-if="summary.sentences.structures.length" class="rs-chips">
            <text v-for="(s, i) in summary.sentences.structures" :key="i" class="rs-chip rs-chip-s">{{ s.name }} · {{ s.count }}</text>
          </view>
        </view>

        <view v-if="summary.diagnosis" class="rs-diag">
          <view class="ic-stethoscope rs-dic"></view>
          <text>{{ summary.diagnosis }}</text>
        </view>
      </view>

      <view class="foot-pad"></view>
    </template>

    <!-- 底部常驻:本篇精讲(生词 + 长难句)→ 点开上拉面板 -->
    <view v-if="!loading && (allWords.length || allSentences.length)" class="study-bar" @tap="sheetOpen = true">
      <view class="ic ic-idea sb-ic"></view>
      <text class="sb-t">本篇精讲</text>
      <text class="sb-cnt">生词 <text class="sb-n">{{ allWords.length }}</text> · 长难句 <text class="sb-n">{{ allSentences.length }}</text></text>
      <view class="ic ic-chevrons-down sb-up"></view>
    </view>

    <!-- 上拉面板 -->
    <view v-if="sheetOpen" class="sheet-mask" @tap="sheetOpen = false">
      <view class="sheet" @tap.stop>
        <view class="grab"></view>
        <view class="sheet-hd">
          <view class="ic ic-idea sh-ic"></view>
          <text class="sh-t">本篇精讲</text>
          <view class="ic ic-close sh-x" @tap="sheetOpen = false"></view>
        </view>
        <view class="seg">
          <text class="seg-i" :class="{ on: studyTab === 'word' }" @tap="studyTab = 'word'">生词 {{ allWords.length }}</text>
          <text class="seg-i" :class="{ on: studyTab === 'ls' }" @tap="studyTab = 'ls'">长难句 {{ allSentences.length }}</text>
        </view>
        <scroll-view scroll-y class="sheet-body">
          <template v-if="studyTab === 'word'">
            <KeyWordsList v-if="allWords.length" :words="allWords" :paper-id="paperId" title="本篇生词" no-card @pick="sheetCard = $event" />
            <view v-else class="tip">本篇没有生词</view>
          </template>
          <template v-else>
            <view v-if="!allSentences.length" class="tip">本篇没有长难句</view>
            <view v-else class="ls-hint">点句子看逐句解析(结构 · 语法 · 重点词)</view>
            <view v-for="(s, si) in allSentences" :key="si" class="ls-card" @tap="openSentence(s)">
              <text class="ls-no">{{ si + 1 }}</text>
              <text class="ls-text">{{ s }}</text>
              <text class="ls-go">拆解 ›</text>
            </view>
          </template>
        </scroll-view>
      </view>
    </view>

    <!-- 单词卡 / 长难句卡:根层渲染(在 sheet/scroll-view 外),避免被面板压住 -->
    <WordCard :word="sheetCard" :paper-id="paperId" @close="sheetCard = null" />
    <SentenceCard :text="sentenceCard" :paper-id="paperId" @close="sentenceCard = null" />

    <!-- 练同类(统一 PracticeQuiz) -->
    <PracticeQuiz
      v-if="pracOpen"
      :kp="pracKp"
      :questions="pracList"
      :recorder="pracRecorder"
      @close="pracOpen = false"
    />
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { rdHwPassages, type ReadingBlock } from '@/api/curriculum'
import { getReadingAnalysis, readingPractice, recordPaperPractice, getPassageStudy, getReadingSummary,
         recordReadingAnswer,
         type ReadingAnalysis, type SimilarQuestion, type StudyWord, type PassageSegment,
         type ReadingSummary, type ReadingSummarySkill } from '@/api/userPapers'
import PracticeQuiz from '@/components/PracticeQuiz.vue'
import KeyWordsList from '@/components/KeyWordsList.vue'
import WordCard from '@/components/WordCard.vue'
import SentenceCard from '@/components/SentenceCard.vue'

const paperId = ref('')
const sheetCard = ref<StudyWord | null>(null)   // 面板里点词 → 根层弹卡(避免困在 scroll-view)
const sentenceCard = ref<string | null>(null)   // 原文里点长难句 → 根层弹「轻量精讲」卡
const loading = ref(true)
const blocks = ref<ReadingBlock[]>([])
const collapsed = ref<Record<number, boolean>>({})

// 卷头:整卷精讲进度(已看解析/练同类的题数)
const allQs = computed(() => blocks.value.flatMap(b => b.questions))
const readTotal = computed(() => allQs.value.length)
const readStudied = computed(() => allQs.value.filter(q => (q as any).studied).length)
const readPct = computed(() => (readTotal.value ? Math.round((readStudied.value / readTotal.value) * 100) : 0))
const readStatus = computed(() => (readStudied.value <= 0 ? 'todo' : readStudied.value >= readTotal.value ? 'done' : 'doing'))
const readStatusLabel = computed(() => ({ todo: '未学', doing: '学习中', done: '已学' }[readStatus.value]))
function markStudiedLocal(qid: string) {
  for (const b of blocks.value) for (const q of b.questions) if ((q as any).id === qid) (q as any).studied = true
}

function toggle(i: number) { collapsed.value = { ...collapsed.value, [i]: !collapsed.value[i] } }

// P3 主动作答(治 OCR 抓不到卷面圈选):点 A/B/C/D → 记 is_correct → 刷新小结
const answered = ref<Record<string, { chosen: string; is_correct: boolean | null }>>({})
async function answer(q: any, letter: string) {
  try {
    const r = await recordReadingAnswer(q.id, letter)
    answered.value = { ...answered.value, [q.id]: { chosen: r.chosen || letter, is_correct: r.is_correct } }
    markStudiedLocal(q.id)
    try { summary.value = await getReadingSummary(paperId.value) } catch { /* 小结刷新失败不影响作答 */ }
  } catch (e: any) { uni.showToast({ title: e?.message || '记录失败', icon: 'none' }) }
}

// P2 读后小结·提问块(题型正确率 → 进度即底色 + 状态色)
const summary = ref<ReadingSummary | null>(null)
function ratePct(s: ReadingSummarySkill): number { return s.total ? Math.round(((s.total - s.wrong) / s.total) * 100) : 0 }
function rateCls(s: ReadingSummarySkill): string { const p = ratePct(s); return p >= 80 ? 'rsf-good' : p >= 60 ? 'rsf-mid' : 'rsf-weak' }
function rateTxtCls(s: ReadingSummarySkill): string { const p = ratePct(s); return p >= 80 ? 'rst-good' : p >= 60 ? 'rst-mid' : 'rst-weak' }

// 题型大标签:中文题型名(优先解析出的 skill)+ 同系配色
function typeLabel(q: any): string { return ana.value[q.id]?.skill || q.type || '阅读理解' }
function typeCls(q: any): string {
  const s = typeLabel(q)
  if (s.includes('细节')) return 'tt-detail'
  if (s.includes('推')) return 'tt-infer'
  if (s.includes('主旨') || s.includes('大意') || s.includes('标题')) return 'tt-main'
  if (s.includes('词义') || s.includes('猜')) return 'tt-word'
  if (s.includes('态度') || s.includes('观点') || s.includes('情感')) return 'tt-att'
  return 'tt-detail'
}

// 原文内联双高亮:词(浅蓝点线,点开单词详解)+ 长难句(橙红点线,点开轻量精讲卡);
// 句内含重点词时同一片段 word_idx/sentence_idx 同时非空(嵌套) —— 词优先响应点击,
// 句子的下划线仍在该词前后的文字上连续延伸,互不遮挡。
const activeEv = ref<Record<number, string>>({})     // 「回原文定位」答案证据句(蓝底,叠加在词/句高亮之上)
const blockStudy = ref<Record<number, { words: StudyWord[]; sentences: string[]; segments: PassageSegment[] }>>({})

type RenderSeg = PassageSegment & { ev: boolean }
function withEvidence(segs: PassageSegment[], ev: string): RenderSeg[] {
  if (!ev) return segs.map(s => ({ ...s, ev: false }))
  const full = segs.map(s => s.t).join('')
  const idx = full.toLowerCase().indexOf(ev.toLowerCase())
  if (idx < 0) return segs.map(s => ({ ...s, ev: false }))
  const evEnd = idx + ev.length
  const out: RenderSeg[] = []
  let pos = 0
  for (const seg of segs) {
    const segStart = pos, segEnd = pos + seg.t.length
    pos = segEnd
    if (segEnd <= idx || segStart >= evEnd) { out.push({ ...seg, ev: false }); continue }
    const cutStart = Math.max(idx, segStart) - segStart
    const cutEnd = Math.min(evEnd, segEnd) - segStart
    if (cutStart > 0) out.push({ ...seg, t: seg.t.slice(0, cutStart), ev: false })
    out.push({ ...seg, t: seg.t.slice(cutStart, cutEnd), ev: true })
    if (cutEnd < seg.t.length) out.push({ ...seg, t: seg.t.slice(cutEnd), ev: false })
  }
  return out
}
function passageSegs(bi: number, passage: string): RenderSeg[] {
  const sd = blockStudy.value[bi]
  const base: PassageSegment[] = sd?.segments?.length ? sd.segments
    : (passage ? [{ t: passage, word_idx: null, sentence_idx: null }] : [])
  return withEvidence(base, (activeEv.value[bi] || '').trim())
}
function segTap(bi: number, seg: RenderSeg) {
  const sd = blockStudy.value[bi]
  if (!sd) return
  if (seg.word_idx != null) { sheetCard.value = sd.words[seg.word_idx] ?? null; return }   // 句内词优先响应
  if (seg.sentence_idx != null) sentenceCard.value = sd.sentences[seg.sentence_idx] ?? null
}

// 本篇精讲:整卷生词 + 长难句,汇总所有短文(零成本正则),供底部上拉面板
const allWords = ref<StudyWord[]>([])
const allSentences = ref<string[]>([])
const sheetOpen = ref(false)
const studyTab = ref<'word' | 'ls'>('word')
async function loadStudy() {
  const wordMap = new Map<string, StudyWord>()
  const sentSet = new Set<string>()
  const sents: string[] = []
  for (const [bi, bk] of blocks.value.entries()) {
    if (!bk.passage) continue
    try {
      const r = await getPassageStudy(bk.passage, paperId.value || undefined)
      blockStudy.value = { ...blockStudy.value, [bi]: { words: r.words, sentences: r.sentences, segments: r.segments } }
      for (const w of r.words) { const k = w.word_id || w.word; if (!wordMap.has(k)) wordMap.set(k, w) }
      for (const s of r.sentences) { if (s && !sentSet.has(s)) { sentSet.add(s); sents.push(s) } }
    } catch { /* 单篇失败不影响其它 */ }
  }
  allWords.value = [...wordMap.values()]
  allSentences.value = sents
}
function openSentence(s: string) {
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(s)}&paperId=${paperId.value}` })
}

// 解题精讲(缓存·懒加载)
const ana = ref<Record<string, ReadingAnalysis>>({})
const anaOpen = ref<Record<string, boolean>>({})
const anaLoading = ref<Record<string, boolean>>({})
function hasDistractors(id: string): boolean {
  const d = ana.value[id]?.distractors
  return !!d && Object.keys(d).length > 0
}
async function toggleAna(q: any, bi: number) {
  const open = !anaOpen.value[q.id]
  anaOpen.value = { ...anaOpen.value, [q.id]: open }
  if (!open) { activeEv.value = { ...activeEv.value, [bi]: '' }; return }
  if (!ana.value[q.id]) {
    anaLoading.value = { ...anaLoading.value, [q.id]: true }
    try { ana.value = { ...ana.value, [q.id]: await getReadingAnalysis(q.id) } }
    catch (e: any) { ana.value = { ...ana.value, [q.id]: { error: e?.message || '解析失败' } } }
    finally { anaLoading.value = { ...anaLoading.value, [q.id]: false } }
  }
  activeEv.value = { ...activeEv.value, [bi]: ana.value[q.id]?.evidence || '' }
  if (!ana.value[q.id]?.error) markStudiedLocal(q.id)
}

// 练同类(统一 PracticeQuiz)
const pracOpen = ref(false)
const pracLoading = ref('')
const pracKp = ref('')
const pracQid = ref('')
const pracList = ref<SimilarQuestion[]>([])
async function practice(qid: string) {
  if (pracLoading.value) return
  pracLoading.value = qid
  try {
    const r = await readingPractice(qid)
    if (r.error) { uni.showToast({ title: r.error, icon: 'none' }); return }
    if (!r.questions.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    pracKp.value = '阅读理解'; pracList.value = r.questions; pracQid.value = qid; pracOpen.value = true
    markStudiedLocal(qid)
  } catch (e: any) { uni.showToast({ title: e?.message || '出题失败', icon: 'none' }) }
  finally { pracLoading.value = '' }
}
async function pracRecorder(total: number, correct: number): Promise<string> {
  const r = await recordPaperPractice(pracQid.value, total, correct)
  if (r.recorded && r.just_mastered) return '🎉 恭喜，这道错题已掌握！'
  if (r.recorded) return `已计入巩固：本轮 ${correct}/${total} 正确`
  return `本轮 ${correct}/${total} 正确`
}

onLoad(async (q: any) => {
  paperId.value = q.paperId || ''
  if (q.title) uni.setNavigationBarTitle({ title: decodeURIComponent(q.title) })
  try {
    blocks.value = (await rdHwPassages(paperId.value)).blocks
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }   // 原文+题目就绪即渲染首屏,不等生词抽取
  // 本篇精讲(72 生词/长难句抽取较重)异步加载,不阻塞首屏;study-bar 就绪后自动出现
  loadStudy()
  // 读后小结:题型按需补标 + 对错聚合(异步,失败静默)
  try { summary.value = await getReadingSummary(paperId.value) } catch { /* 小结失败不影响精讲 */ }
})
</script>

<style scoped>
.page { min-height: 100vh; background: #f4f6fa; padding: 24rpx; box-sizing: border-box; }
.tip { text-align: center; color: #93a0b3; padding: 60rpx 0; }
.block { margin-bottom: 8rpx; }
.foot-pad { height: 120rpx; }

/* 原文:吸顶常驻 */
.passage { position: sticky; top: 0; z-index: 5; background: #fff; border: 2rpx solid #e3e9f2; border-radius: 18rpx; padding: 20rpx 22rpx; margin-bottom: 16rpx; box-shadow: 0 6rpx 22rpx rgba(45, 80, 150, .08); }
.passage-head { display: flex; align-items: center; justify-content: space-between; }
.passage-brand { display: flex; align-items: center; gap: 10rpx; }
.ic-book { width: 30rpx; height: 30rpx; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E"); background-size: contain; background-repeat: no-repeat; }
.passage-title { font-size: 24rpx; font-weight: 700; color: #3d8bf5; letter-spacing: .5rpx; }
.passage-toggle { font-size: 22rpx; color: #93a0b3; }
.passage-text { display: block; font-size: 26rpx; color: #3a4353; line-height: 1.8; margin-top: 14rpx; max-height: 40vh; overflow-y: auto; white-space: pre-wrap; }
.ev-hl { background: #e4eeff; color: #1f4c8f; border-radius: 4rpx; padding: 0 2rpx; box-shadow: inset 0 -4rpx 0 #7ca9f5; }
/* 原文内联双高亮:词(浅蓝点线)/ 长难句(橙红点线);句内词嵌套时词的下划线优先(点击目标更精确),
   叠一层浅橙底色提示"这是长难句里的词"——句子的橙红下划线仍在词前后文字上连续延伸 */
.seg-w { border-bottom: 3rpx dotted #3d8bf5; }
.seg-s { border-bottom: 3rpx dotted #e08a4c; }
.seg-w.seg-s { border-bottom-color: #3d8bf5; background: #fdf3ea; border-radius: 4rpx; }

/* 卷头进度:进度即底色(背景填充式,全项目统一) */
.rd-head { position: relative; overflow: hidden; display: flex; align-items: center; gap: 16rpx; background: #fff; border: 2rpx solid #e6ebf2; border-radius: 18rpx; padding: 18rpx 20rpx; margin-bottom: 18rpx; box-shadow: 0 6rpx 20rpx rgba(45, 80, 150, .06); }
.rd-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; transition: width .3s; }
.rhf-todo { background: transparent; }
.rhf-doing { background: linear-gradient(90deg, #e8f2ff, #f4f9ff); }
.rhf-done { background: linear-gradient(90deg, #e9f6f1, #f4fbf8); }
.rd-num { position: relative; flex: none; min-width: 92rpx; text-align: center; }
.rd-s { font-size: 42rpx; font-weight: 800; color: #3d7bf0; line-height: 1; }
.rd-t { font-size: 24rpx; font-weight: 700; color: #b7c2d4; }
.rd-info { position: relative; flex: 1; min-width: 0; }
.rd-status { font-size: 26rpx; font-weight: 800; display: flex; align-items: center; gap: 10rpx; }
.rs-todo { color: #94a3b8; }
.rs-doing { color: #3d8bf5; }
.rs-done { color: #2fa98a; }
.rd-pct { font-size: 20rpx; font-weight: 700; color: #3d8bf5; background: #eaf2fe; border-radius: 6rpx; padding: 2rpx 10rpx; }
.rs-done .rd-pct { color: #2fa98a; background: #e8f6ef; }
.rd-sub { display: block; font-size: 21rpx; color: #93a0b3; margin-top: 8rpx; }

/* 讲义卡片 + 每题勾选圈 */
.q-card { background: #fff; border: 2rpx solid #eaeef4; border-radius: 18rpx; padding: 22rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 18rpx rgba(45, 80, 150, .05); }
.q-tick { width: 34rpx; height: 34rpx; border-radius: 50%; flex: none; box-sizing: border-box; }
.q-tick-todo { border: 4rpx solid #cbd3e0; }
.q-tick-done { background: #2fa98a url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%23fff' stroke-width='3.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'/%3E%3C/svg%3E") center/20rpx no-repeat; }
.q-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 14rpx; }
.q-type { font-size: 22rpx; font-weight: 800; color: #fff; border-radius: 999rpx; padding: 4rpx 18rpx; letter-spacing: .5rpx; }
.tt-detail { background: linear-gradient(135deg, #4c97f7, #3d7bf0); }
.tt-infer { background: linear-gradient(135deg, #7c9bd8, #6480c4); }
.tt-main { background: linear-gradient(135deg, #3fb0a4, #2e9a8e); }
.tt-word { background: linear-gradient(135deg, #5aaee0, #3e92ce); }
.tt-att { background: linear-gradient(135deg, #8e93c8, #7276b8); }
.st-chip { font-size: 20rpx; font-weight: 600; border-radius: 8rpx; padding: 3rpx 12rpx; }
.st-bad { color: #dc4c4c; background: #fdecec; }
.st-ok { color: #1a9d63; background: #e8f6ef; }
.q-no { margin-left: auto; font-size: 22rpx; color: #93a0b3; }
.q-stem { display: block; font-size: 27rpx; font-weight: 600; line-height: 1.6; color: #1f2733; }

/* P3 作答器:A/B/C/D 字母选择 */
.ans-pick { display: flex; align-items: center; gap: 12rpx; margin-top: 14rpx; }
.ap-lbl { font-size: 22rpx; color: #93a0b3; }
.ap-btn { width: 56rpx; height: 56rpx; border-radius: 12rpx; border: 2rpx solid #d8e0ec; background: #f5f8fc; color: #2b3546; font-size: 26rpx; font-weight: 700; text-align: center; line-height: 56rpx; }
.ap-ok { border-color: #2fa98a; background: #e8f6ef; color: #1a9d63; }
.ap-bad { border-color: #dc4c4c; background: #fdecec; color: #dc4c4c; }
.ap-res { font-size: 22rpx; font-weight: 700; margin-left: 4rpx; }
.ap-rok { color: #1a9d63; }
.ap-rbad { color: #dc4c4c; }
.q-ans { margin-top: 14rpx; display: flex; flex-wrap: wrap; gap: 10rpx; }
.ans-chip { display: inline-flex; align-items: center; gap: 6rpx; font-size: 23rpx; border-radius: 10rpx; padding: 6rpx 16rpx; }
.ans-ic { width: 26rpx; height: 26rpx; flex-shrink: 0; }
.ac-bad { color: #dc4c4c; background: #fdecec; }
.ac-ok { color: #1a9d63; background: #e8f6ef; }
.q-exp { display: block; font-size: 24rpx; color: #55607a; line-height: 1.6; margin-top: 12rpx; background: #f5f8fc; border-radius: 12rpx; padding: 14rpx 16rpx; }

/* 单题动作 */
.q-acts { display: flex; gap: 12rpx; margin-top: 16rpx; }
.q-act { flex: 1; text-align: center; font-size: 24rpx; font-weight: 600; color: #2f74d6; border: 2rpx solid #d8e4f5; background: #f2f7fd; border-radius: 12rpx; padding: 12rpx 0; }
.q-act.on { background: #e6f0fc; }
.q-act-sim { color: #fff; background: linear-gradient(135deg, #4c97f7, #3d7bf0); border-color: transparent; }

/* 解析面板:四件套左侧细色条分区 */
.ana { margin-top: 14rpx; display: flex; flex-direction: column; gap: 12rpx; }
.ana-err { font-size: 24rpx; color: #93a0b3; }
.ab { border-left: 6rpx solid #ccc; border-radius: 0 14rpx 14rpx 0; padding: 14rpx 18rpx; display: flex; flex-direction: column; gap: 8rpx; }
.ab-k { font-size: 22rpx; font-weight: 800; align-self: flex-start; }
.ab-t { font-size: 24rpx; color: #46506a; line-height: 1.6; }
.ab-quote { font-size: 25rpx; color: #26466f; line-height: 1.6; }
.ab-loc { border-left-color: #3d8bf5; background: #f3f8fe; }
.ab-loc .ab-k { color: #2f74d6; }
.ab-why { border-left-color: #22a76b; background: #f1faf5; }
.ab-why .ab-k { color: #1a9059; }
.ab-dis { border-left-color: #e08a4c; background: #fdf6ef; }
.ab-dis .ab-k { color: #c06a2a; }
.ab-tip { border-left-color: #8a6fd0; background: #f7f4fc; }
.ab-tip .ab-k { color: #7057c0; }
.dis-row { display: flex; gap: 12rpx; align-items: flex-start; }
.dis-key { flex-shrink: 0; width: 40rpx; height: 40rpx; border-radius: 50%; background: #fbe6d4; color: #c06a2a; font-size: 22rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.dis-why { flex: 1; font-size: 23rpx; color: #55607a; line-height: 1.55; }

/* 底部常驻:本篇精讲条 */
.study-bar { position: fixed; left: 24rpx; right: 24rpx; bottom: 24rpx; z-index: 40; display: flex; align-items: center; gap: 12rpx; background: #fff; border: 2rpx solid #e6ebf2; border-radius: 18rpx; padding: 20rpx 22rpx; box-shadow: 0 -2rpx 24rpx rgba(45, 80, 150, .12), 0 8rpx 24rpx rgba(45, 80, 150, .1); }
.sb-ic { width: 34rpx; height: 34rpx; flex: none; }
.sb-t { font-size: 28rpx; font-weight: 700; color: #1f2733; }
.sb-cnt { margin-left: auto; font-size: 24rpx; color: #8a95a5; }
.sb-n { color: #3d8bf5; font-weight: 700; }
.sb-up { width: 32rpx; height: 32rpx; flex: none; transform: rotate(180deg); }

/* 上拉面板 */
.sheet-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; z-index: 60; background: rgba(20, 28, 40, .45); display: flex; align-items: flex-end; }
.sheet { width: 100%; max-height: 78vh; background: #f4f6fa; border-radius: 26rpx 26rpx 0 0; padding: 12rpx 24rpx 32rpx; box-sizing: border-box; display: flex; flex-direction: column; }
.grab { width: 72rpx; height: 8rpx; border-radius: 4rpx; background: #dce3ec; margin: 8rpx auto 14rpx; }
.sheet-hd { display: flex; align-items: center; gap: 12rpx; padding: 0 2rpx 16rpx; }
.sh-ic { width: 34rpx; height: 34rpx; flex: none; }
.sh-t { font-size: 30rpx; font-weight: 800; color: #1f2733; }
.sh-x { width: 34rpx; height: 34rpx; flex: none; margin-left: auto; }
.seg { display: flex; gap: 10rpx; background: #e8edf4; border-radius: 16rpx; padding: 6rpx; margin-bottom: 16rpx; }
.seg-i { flex: 1; text-align: center; font-size: 26rpx; color: #6b7688; padding: 14rpx 0; border-radius: 12rpx; }
.seg-i.on { color: #3d8bf5; font-weight: 700; background: #fff; box-shadow: 0 3rpx 10rpx rgba(45, 80, 150, .12); }
.sheet-body { max-height: 58vh; }
.ls-hint { font-size: 22rpx; color: #93a0b3; margin: 2rpx 4rpx 12rpx; }
.ls-card { display: flex; align-items: flex-start; gap: 14rpx; background: #fff; border: 2rpx solid #e9edf3; border-radius: 16rpx; padding: 18rpx 18rpx; margin-bottom: 14rpx; box-shadow: 0 4rpx 16rpx rgba(45, 80, 150, .04); }
.ls-no { flex: none; width: 40rpx; height: 40rpx; border-radius: 50%; background: #eaf2fe; color: #3d8bf5; font-size: 24rpx; font-weight: 700; text-align: center; line-height: 40rpx; }
.ls-text { flex: 1; min-width: 0; font-size: 25rpx; line-height: 1.6; color: #1f2733; }
.ls-go { flex: none; font-size: 22rpx; font-weight: 600; color: #3d8bf5; margin-top: 6rpx; }

/* P2 读后小结·提问块(题型对错;进度即底色 + 状态色) */
.rs-card { background: #fff; border: 2rpx solid #e6ebf2; border-radius: 18rpx; padding: 20rpx 22rpx; margin: 4rpx 0 16rpx; box-shadow: 0 4rpx 18rpx rgba(45, 80, 150, .05); }
.rs-hd { display: flex; align-items: center; gap: 10rpx; margin-bottom: 16rpx; }
.rs-ic { width: 32rpx; height: 32rpx; flex: none; background-size: contain; background-repeat: no-repeat; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M9 5H7a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2'/%3E%3Crect x='9' y='3' width='6' height='4' rx='1'/%3E%3Cpath d='m9 14 2 2 4-4'/%3E%3C/svg%3E"); }
.rs-tt { font-size: 28rpx; font-weight: 800; color: #1f2733; }
.rs-meta { margin-left: auto; font-size: 23rpx; color: #8a95a5; }
.rs-row { position: relative; overflow: hidden; display: flex; align-items: center; gap: 12rpx; background: #f6f8fb; border-radius: 12rpx; padding: 14rpx 16rpx; margin-bottom: 10rpx; }
.rs-fill { position: absolute; left: 0; top: 0; bottom: 0; width: 0; transition: width .3s; }
.rsf-good { background: linear-gradient(90deg, #e9f6f1, #f4fbf8); }
.rsf-mid { background: linear-gradient(90deg, #e8f2ff, #f4f9ff); }
.rsf-weak { background: linear-gradient(90deg, #fdecec, #fef5f5); }
.rs-sk { position: relative; font-size: 25rpx; font-weight: 700; color: #2b3546; }
.rs-rt { position: relative; margin-left: auto; font-size: 23rpx; font-weight: 700; }
.rst-good { color: #2fa98a; }
.rst-mid { color: #3d8bf5; }
.rst-weak { color: #dc4c4c; }
/* P4 词汇 / 长难句子块 */
.rs-sub { margin-top: 12rpx; }
.rs-sub-t { display: block; font-size: 23rpx; font-weight: 700; color: #55607a; margin-bottom: 8rpx; }
.rs-chips { display: flex; flex-wrap: wrap; gap: 8rpx; }
.rs-chip { font-size: 22rpx; font-weight: 600; border-radius: 8rpx; padding: 5rpx 12rpx; }
.rs-chip-s { color: #7057c0; background: #f2eefb; }
.rs-diag { display: flex; align-items: flex-start; gap: 10rpx; margin-top: 6rpx; background: #eef4ff; border-radius: 12rpx; padding: 14rpx 16rpx; font-size: 23rpx; color: #2f74d6; line-height: 1.55; }
.rs-dic { width: 30rpx; height: 30rpx; flex: none; margin-top: 2rpx; background-size: contain; background-repeat: no-repeat; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='22 12 18 12 15 21 9 3 6 12 2 12'/%3E%3C/svg%3E"); }
</style>

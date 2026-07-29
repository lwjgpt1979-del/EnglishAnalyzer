<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>

    <template v-else-if="paper">
      <view class="head card">
        <view class="head-top">
          <text class="title" @tap="editTitle">{{ paper.title || '未命名作业' }}<text class="title-edit"> ✎</text></text>
          <text class="head-list" @tap="goList">我的作业 ›</text>
        </view>
        <view class="status" :class="statusClass">
          <text>{{ statusText }}</text>
        </view>
        <text class="meta">{{ paper.source_image_urls.length }} 张图片 · {{ paper.question_count }} 道题</text>
      </view>

      <!-- 处理中 -->
      <view v-if="isProcessing" class="card processing">
        <text class="proc-text">正在识别并拆题，请稍候…</text>
        <text class="proc-sub">通常 10~30 秒，可停留在此页等待</text>
      </view>

      <!-- 失败 -->
      <view v-else-if="paper.ocr_status === 'failed'" class="card failed">
        <text class="fail-text">识别失败</text>
        <text class="fail-sub">可能是图片不清晰或顺序问题，请重新拍摄上传</text>
        <button class="btn-secondary" @tap="goUpload">重新上传</button>
      </view>

      <!-- 完成：按题型分块 -->
      <template v-else-if="paper.ocr_status === 'completed'">
        <view v-if="!paper.questions.length" class="card empty-q">
          <text>未识别到题目，请重试或换更清晰的图片</text>
          <button class="btn-secondary" @tap="goUpload">重新上传</button>
        </view>

        <!-- 每个题型 = 一块:题型名 + 本题型 全部|错题 → 原文 → 题目 → 底部三功能 -->
        <view v-for="sec in paperSections" :key="sec.id" class="section">
          <view class="sec-head">
            <text class="sec-bar" />
            <text class="sec-label">{{ sec.label }}</text>
            <text v-if="sec.is_suggested" class="sec-sug">建议·未拍到题型</text>
            <view style="flex:1" />
            <text v-if="sec.id !== 'all'" class="sec-edit" @tap="editSection(sec)">改题型</text>
          </view>
          <!-- 本题型 全部|错题(完形默认全部;其它有错→错题) -->
          <view class="sec-filter">
            <text class="fbtn" :class="{ on: !isWrongView(sec) }" @tap="setWrong(sec, false)">全部 {{ sec.total }}</text>
            <text class="fbtn" :class="{ on: isWrongView(sec) }" @tap="setWrong(sec, true)">错题 {{ sec.wrongCount }}</text>
          </view>

          <template v-for="grp in blocksFor(sec)" :key="grp.key">
            <!-- 原文:完形/阅读 · B 疏朗白卡 + 空号对错胶囊 -->
            <view
              v-if="grp.passage"
              class="card passage-card"
              :class="{ airy: sec.isCloze || sec.isReading }"
              @tap="toggleBlock(grp.key)"
            >
              <view class="passage-head">
                <text class="passage-title">原文{{ grp.blockLabel }}</text>
                <text class="passage-toggle">{{ collapsed[grp.key] ? '展开 ▾' : '收起 ▴' }}</text>
              </view>
              <view v-if="!collapsed[grp.key]" class="passage-text">
                <template v-for="(node, ni) in passageNodes(sec, grp)" :key="ni">
                  <text v-if="node.kind === 'text'">{{ node.t }}</text>
                  <text
                    v-else
                    class="p-blank"
                    :class="node.wrong ? 'bad' : 'ok'"
                    @tap.stop="scrollToQ(node.no)"
                  >{{ node.no }}</text>
                </template>
              </view>
            </view>

            <view
              v-for="q in grp.questions"
              :id="'pq-' + qidKey(q)"
              :key="q.id"
              class="card q-card"
              :class="{ wrong: q.is_wrong, okborder: !q.is_wrong && isClozeSec(sec) }"
            >
              <view class="q-head">
                <text class="q-no">{{ q.question_no ? `第 ${q.question_no} 题` : '题目' }}</text>
                <text v-if="isClozeSec(sec)" class="q-type-pill">{{ hasOpts(q) ? '单选' : '填空' }}</text>
                <view v-if="q.is_wrong" class="q-flag"><view class="ic ic-x-circle" style="width:26rpx;height:26rpx" /><text>错</text></view>
                <view v-else class="q-flag q-ok"><view class="ic ic-check-circle" style="width:26rpx;height:26rpx" /><text>对</text></view>
              </view>
              <text class="q-stem">{{ q.stem || '（题干识别为空）' }}</text>
              <!-- 选择完形:选项对绿/错红 -->
              <view v-if="hasOpts(q)" class="q-opts">
                <view
                  v-for="(op, oi) in q.options"
                  :key="oi"
                  class="q-opt"
                  :class="optCls(q, op, oi)"
                >
                  <text class="q-opt-t">{{ op }}</text>
                  <text v-if="optHint(q, op, oi)" class="q-opt-h">{{ optHint(q, op, oi) }}</text>
                </view>
              </view>
              <!-- 填空:你填/正确;选择也保留一行摘要 -->
              <view class="q-ans" :class="{ compact: hasOpts(q) }">
                <text class="ans-line" :class="{ 'ans-x': q.is_wrong }">
                  {{ hasOpts(q) ? '你选' : '你填' }} {{ q.student_answer || '（未识别）' }}
                </text>
                <text class="ans-line ans-ok">正确 {{ q.correct_answer || '（未提供）' }}</text>
              </view>
              <view v-if="q.explanation" class="q-exp">
                <text class="q-exp-k">解析</text>
                <text class="q-exp-t">{{ q.explanation }}</text>
              </view>
              <!-- 按题型路由动作:阅读小题整收;完形保留加单词(不加错题);其它按考点 -->
              <view v-if="showActs(sec, q)" class="q-acts">
                <template v-if="isClozeSec(sec)">
                  <view class="q-act" :class="{ done: qVocab.has(q.id) }" @tap="addVocabQ(q)">
                    <text>{{ qVocab.has(q.id) ? '已加入单词' : '加入单词学习' }}</text>
                  </view>
                </template>
                <template v-else-if="isReadingSec(sec)">
                  <!-- 阅读/任务型阅读:小题不出加单词·加错题 -->
                </template>
                <template v-else-if="q.kp_kind === 'grammar'">
                  <view class="q-act" :class="{ done: qGrammar.has(q.id) }" @tap="addGrammar(q)">
                    <text>{{ qGrammar.has(q.id) ? '已加入语法' : '加入语法学习' }}</text>
                  </view>
                  <view class="q-act" :class="{ done: qWrong.has(q.id) }" @tap="addToWrong(q)">
                    <text>{{ qWrong.has(q.id) ? '已加入错题' : '加入我的错题' }}</text>
                  </view>
                </template>
                <template v-else-if="q.kp_kind === 'vocab'">
                  <view class="q-act" :class="{ done: qVocab.has(q.id) }" @tap="addVocabQ(q)">
                    <text>{{ qVocab.has(q.id) ? '已加入单词' : '加入单词学习' }}</text>
                  </view>
                  <view class="q-act" :class="{ done: qWrong.has(q.id) }" @tap="addToWrong(q)">
                    <text>{{ qWrong.has(q.id) ? '已加入错题' : '加入我的错题' }}</text>
                  </view>
                </template>
                <template v-else>
                  <view class="q-act" :class="{ done: qWrong.has(q.id) }" @tap="addToWrong(q)">
                    <text>{{ qWrong.has(q.id) ? '已加入错题' : '加入我的错题' }}</text>
                  </view>
                </template>
                <view v-if="q.is_wrong" class="q-act q-act-sim" @tap="practiceSimilar(q.id)">
                  <text>{{ similarLoading ? '生成中…' : '练同类仿真题' }}</text>
                </view>
              </view>
            </view>
          </template>
          <view v-if="!blocksFor(sec).length" class="sec-empty">本题型该筛选下暂无题目</view>

          <!-- 阅读理解:手动加入作业精讲·阅读理解精讲(不自动加入) -->
          <view
            v-if="sec.isReading"
            class="reading-add"
            :class="{ done: isReadingAdded(sec) }"
            @tap="addReading(sec)"
          >
            <view class="ic ic-book" style="width:30rpx;height:30rpx" />
            <text>{{ isReadingAdded(sec) ? '已加入阅读理解精讲' : '加入阅读理解精讲' }}</text>
          </view>

          <!-- 完形填空:手动加入作业精讲·完形填空精讲 -->
          <view
            v-if="sec.isCloze"
            class="reading-add"
            :class="{ done: isClozeAdded(sec) }"
            @tap="addCloze(sec)"
          >
            <view class="ic ic-layout" style="width:30rpx;height:30rpx" />
            <text>{{ isClozeAdded(sec) ? '已加入完形填空精讲' : '加入完形填空精讲' }}</text>
          </view>

          <!-- 底部功能:有原文且非阅读/完形 → 本题生词 + 长难句(阅读/完形改走精讲页) -->
          <view v-if="showPassageTools(sec)" class="sec-tools">
            <text class="tool-chip" :class="{ on: secVocabOpen[sec.id] }" @tap="toggleSecVocab(sec)">本题生词</text>
            <text class="tool-chip" @tap="openSecSentences(sec)">长难句</text>
          </view>

          <!-- 本题生词:懒加载该题型生词 -->
          <view v-if="showPassageTools(sec) && secVocabOpen[sec.id]" class="card tool-panel">
            <text v-if="secVocabLoading[sec.id]" class="muted">加载中…</text>
            <template v-else>
              <text v-if="!(secVocab[sec.id] || []).length" class="muted">本题型没有生词</text>
              <template v-else>
                <view class="gr-chips">
                  <view v-for="w in secVocab[sec.id]" :key="w.word_id" class="gr-chip vw-chip"
                        :class="{ 'vw-on': secPickedHas(sec, w) || w.pinned }" @tap="toggleSecWord(sec, w)">
                    <text>{{ w.word }}</text>
                    <text v-if="w.pinned" class="chip-go">已加</text>
                    <text v-else-if="secPickedHas(sec, w)" class="chip-go">✓</text>
                  </view>
                </view>
                <view v-if="secPickCount(sec)" class="gr-plan-btn" @tap="addSecVocab(sec)">
                  <text class="ic ic-book" /><text>加入待学习（{{ secPickCount(sec) }}）</text>
                </view>
              </template>
            </template>
          </view>
        </view>
      </template>
    </template>

    <!-- 无数据兜底:必须紧跟上面的 loading/paper 链(不能被弹层的 v-if 打断,否则误绑到弹层上) -->
    <view v-else class="empty">作业不存在或无权访问</view>

    <!-- 练同类·逐题作答判分(与我的错题共用组件) -->
    <PracticeQuiz
      v-if="similarOpen"
      :kp="similarKp"
      :questions="similarList"
      :recorder="paperPracRecorder"
      @close="similarOpen = false"
    />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import { getUserPaper, updatePaperSection, getPaperVocab, practiceForQuestion, recordPaperPractice, renamePaper, addQuestionGrammar, addQuestionVocab, addQuestionToWrong, addReadingIntensive, addClozeIntensive, type SimilarQuestion, type PaperVocabWord } from '@/api/userPapers'
import PracticeQuiz from '@/components/PracticeQuiz.vue'
import { addHomeworkWords } from '@/api/vocabulary'
import type { UserPaperDetailOut } from '@/types/api'

const paper = ref<UserPaperDetailOut | null>(null)
const loading = ref(true)
const paperId = ref('')
let timer: ReturnType<typeof setTimeout> | null = null

// 语篇折叠态(完形/阅读短文)
const collapsed = ref<Record<string, boolean>>({})
function toggleBlock(k: string) { collapsed.value = { ...collapsed.value, [k]: !collapsed.value[k] } }

// 按 block_key 归「原文+多小问」组
function toBlocks(qs: any[]) {
  const blocks: any[] = []
  const idxByKey: Record<string, number> = {}
  for (const q of qs) {
    const bk = q.block_key || `__solo_${q.id}`
    if (!(bk in idxByKey)) {
      blocks.push({ key: bk, passage: q.block_key ? (q.passage || '') : '',
                    blockLabel: q.block_key ? ` · ${q.block_key}` : '', questions: [] })
      idxByKey[bk] = blocks.length - 1
    }
    blocks[idxByKey[bk]].questions.push(q)
  }
  return blocks
}
// 每题型一块:全量题 + 错题数(兼容无 sections 的旧数据)
/** 短文挖空族(方案1):恒纳入键 / 有语篇才纳入键 / 标题别名 */
const CLOZE_ST_ALWAYS = new Set(['cloze', 'passage_fill', 'reading_fill', 'fill'])
const CLOZE_ST_IF_PASSAGE = new Set(['vocab_use', 'verb_fill'])
const CLOZE_LABEL_RE = /完形|完型|短文填空|缺词填空|综合填空|首字母|选词填空|阅读填空|阅读填词/
/** 「阅读填空」等不能当阅读理解精讲 */
const READING_FILL_LABEL_RE = /阅读填[空词]|阅读与?填/

const paperSections = computed(() => {
  const build = (id: string, label: string, is_suggested: boolean, qs: any[], section_type?: string | null, inReading?: boolean, inCloze?: boolean) => {
    const st = section_type || null
    const lb = label || ''
    const hasPassage = qs.some((q: any) => q.passage || q.block_key)
    const isCloze = CLOZE_ST_ALWAYS.has(st || '')
      || (CLOZE_ST_IF_PASSAGE.has(st || '') && hasPassage)
      || CLOZE_LABEL_RE.test(lb)
    const isReadingFill = st === 'reading_fill' || READING_FILL_LABEL_RE.test(lb)
    const isReading = !isReadingFill && !isCloze && (
      st === 'reading' || st === 'task_reading' || lb.includes('阅读')
    )
    return {
      id, label, is_suggested, section_type: st, questions: qs, total: qs.length,
      wrongCount: qs.filter((q: any) => q.is_wrong).length,
      hasPassage,
      isReading,
      isCloze,
      inReading: !!inReading,
      inCloze: !!inCloze,
    }
  }
  const out: any[] = []
  for (const sec of (paper.value?.sections || [])) {
    if ((sec.questions || []).length) {
      out.push(build(
        sec.id, sec.label, !!sec.is_suggested, sec.questions, sec.section_type,
        (sec as any).in_reading_intensive, (sec as any).in_cloze_intensive,
      ))
    }
  }
  if (!out.length && (paper.value?.questions || []).length) out.push(build('all', '全部题目', false, paper.value!.questions))
  return out
})
// 本次会话内已加入阅读理解精讲的 section(叠加后端 inReading)
const readingAdded = ref<Set<string>>(new Set())
function isReadingAdded(sec: any): boolean { return sec.inReading || readingAdded.value.has(sec.id) }
async function addReading(sec: any) {
  if (isReadingAdded(sec)) return
  try {
    const r = await addReadingIntensive(sec.id)
    if (r.added) {
      readingAdded.value = new Set([...readingAdded.value, sec.id])
      uni.showToast({ title: '已加入阅读理解精讲', icon: 'none' })
    } else {
      uni.showToast({ title: r.reason || '加入失败', icon: 'none' })
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}
const clozeAdded = ref<Set<string>>(new Set())
function isClozeAdded(sec: any): boolean { return sec.inCloze || clozeAdded.value.has(sec.id) }
async function addCloze(sec: any) {
  if (isClozeAdded(sec)) return
  try {
    const r = await addClozeIntensive(sec.id)
    if (r.added) {
      clozeAdded.value = new Set([...clozeAdded.value, sec.id])
      uni.showToast({ title: '已加入完形填空精讲', icon: 'none' })
    } else {
      uni.showToast({ title: r.reason || '加入失败', icon: 'none' })
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}
// 本题型 全部|错题
// 完形:默认「全部」(对+错都呈现);其它:有错题→错题,无错→全部
const secWrong = ref<Record<string, boolean>>({})
function isWrongView(sec: any): boolean {
  if (sec.id in secWrong.value) return secWrong.value[sec.id]
  if (sec.isCloze) return false
  return sec.wrongCount > 0
}
function setWrong(sec: any, v: boolean) { secWrong.value = { ...secWrong.value, [sec.id]: v } }
/**
 * 错题视图只滤小题卡;原文仍挂全量空号状态(对绿/错红)
 */
function blocksFor(sec: any) {
  const all = toBlocks(sec.questions)
  if (!isWrongView(sec)) return all
  return all
    .map((b: any) => ({ ...b, questions: b.questions.filter((q: any) => q.is_wrong) }))
    .filter((b: any) => b.questions.length)
}

type PassNode = { kind: 'text'; t: string } | { kind: 'blank'; no: string; wrong: boolean }

/** 题号归一成数字串(「第 3 题」/「3」→「3」) */
function normNo(raw: any): string {
  const m = String(raw ?? '').match(/\d+/)
  return m ? m[0] : ''
}
function qidKey(q: any): string {
  return normNo(q.question_no) || String(q.id || '')
}
/** 本 block 全量空号 → 是否错(不过滤视图) */
function blankWrongMap(sec: any, grp: any): Record<string, boolean> {
  const m: Record<string, boolean> = {}
  const key = grp.key
  for (const q of sec.questions || []) {
    const bk = q.block_key || `__solo_${q.id}`
    if (bk !== key) continue
    const no = normNo(q.question_no)
    if (no) m[no] = !!q.is_wrong
  }
  return m
}
/**
 * 把语篇里的空号(下划线题号 / 括号题号 / 独立数字题号)换成对错胶囊节点
 */
function passageNodes(sec: any, grp: any): PassNode[] {
  const text = grp.passage || ''
  const map = blankWrongMap(sec, grp)
  const nos = Object.keys(map)
  if (!text || !nos.length) return [{ kind: 'text', t: text }]

  type Hit = { start: number; end: number; no: string }
  const hits: Hit[] = []
  const covered = (s: number, e: number) => hits.some(h => s < h.end && e > h.start)

  // 1) 显式空: ____3____ / __3 / （3）/ (3) / 【3】
  const explicit = /_{2,}\s*(\d{1,2})\s*_{0,}|[（(【\[]\s*(\d{1,2})\s*[）)】\]]/g
  for (const m of text.matchAll(explicit)) {
    const no = m[1] || m[2]
    if (!no || !(no in map) || m.index == null) continue
    const start = m.index
    const end = start + m[0].length
    if (!covered(start, end)) hits.push({ start, end, no })
  }
  // 2) 独立题号数字(仅本篇空号集合;避免年份等 4 位)
  for (const no of nos) {
    if (no.length > 2) continue
    const re = new RegExp(`(^|[^0-9])(${no})(?![0-9])`, 'g')
    for (const m of text.matchAll(re)) {
      if (m.index == null) continue
      const lead = m[1] || ''
      const start = m.index + lead.length
      const end = start + no.length
      if (!covered(start, end)) hits.push({ start, end, no })
    }
  }
  hits.sort((a, b) => a.start - b.start || a.end - b.end)
  const kept: Hit[] = []
  for (const h of hits) {
    if (kept.some(k => h.start < k.end && h.end > k.start)) continue
    kept.push(h)
  }

  const nodes: PassNode[] = []
  let cur = 0
  for (const h of kept) {
    if (h.start > cur) nodes.push({ kind: 'text', t: text.slice(cur, h.start) })
    nodes.push({ kind: 'blank', no: h.no, wrong: !!map[h.no] })
    cur = h.end
  }
  if (cur < text.length) nodes.push({ kind: 'text', t: text.slice(cur) })
  return nodes.length ? nodes : [{ kind: 'text', t: text }]
}

function scrollToQ(no: string) {
  if (!no) return
  uni.pageScrollTo({
    selector: `#pq-${no}`,
    duration: 280,
  })
}

function hasOpts(q: any): boolean {
  return !!(q?.options && q.options.length)
}
function stripOptLetter(op: string): string {
  return String(op || '').replace(/^[A-Da-d][.、)．]\s*/, '').trim()
}
function letterOf(i: number): string {
  return String.fromCharCode(65 + i)
}
/** 选项是否为正确答案 */
function isCorrectOpt(q: any, op: string, oi?: number): boolean {
  const ans = (q.correct_answer || '').trim()
  if (!ans) return false
  const au = ans.toUpperCase()
  if (typeof oi === 'number' && au === letterOf(oi)) return true
  const letter = (op.match(/^([A-D])/i) || [])[1]
  if (letter && au === letter.toUpperCase()) return true
  const body = stripOptLetter(op)
  return au === (op || '').trim().toUpperCase() || au === body.toUpperCase()
}
/** 选项是否为学生所选 */
function isStudentOpt(q: any, op: string, oi?: number): boolean {
  const stu = (q.student_answer || '').trim()
  if (!stu) return false
  const su = stu.toUpperCase()
  if (typeof oi === 'number' && su === letterOf(oi)) return true
  const letter = (op.match(/^([A-D])/i) || [])[1]
  if (letter && su === letter.toUpperCase()) return true
  const body = stripOptLetter(op)
  return su === (op || '').trim().toUpperCase() || su === body.toUpperCase()
}
function optCls(q: any, op: string, oi: number): string {
  const ok = isCorrectOpt(q, op, oi)
  const stu = isStudentOpt(q, op, oi)
  if (ok) return 'q-opt-ok'
  if (stu && q.is_wrong) return 'q-opt-bad'
  return ''
}
function optHint(q: any, op: string, oi: number): string {
  const ok = isCorrectOpt(q, op, oi)
  const stu = isStudentOpt(q, op, oi)
  if (ok && stu) return '正确 · 你选'
  if (ok) return '正确'
  if (stu && q.is_wrong) return '你选'
  return ''
}

// —— 底部功能(本题型级,仅有原文题型):生词 + 长难句 ——
const secVocab = ref<Record<string, PaperVocabWord[]>>({})
const secVocabOpen = ref<Record<string, boolean>>({})
const secVocabLoading = ref<Record<string, boolean>>({})
const secPicked = ref<Record<string, Set<string>>>({})
async function toggleSecVocab(sec: any) {
  const open = !secVocabOpen.value[sec.id]
  secVocabOpen.value = { ...secVocabOpen.value, [sec.id]: open }
  if (open && !(sec.id in secVocab.value)) {
    secVocabLoading.value = { ...secVocabLoading.value, [sec.id]: true }
    try { secVocab.value = { ...secVocab.value, [sec.id]: (await getPaperVocab(paperId.value, sec.id)).words } }
    catch { secVocab.value = { ...secVocab.value, [sec.id]: [] } }
    finally { secVocabLoading.value = { ...secVocabLoading.value, [sec.id]: false } }
  }
}
function secPickedHas(sec: any, w: PaperVocabWord) { return !!secPicked.value[sec.id]?.has(w.word_id) }
function secPickCount(sec: any) { return secPicked.value[sec.id]?.size || 0 }
function toggleSecWord(sec: any, w: PaperVocabWord) {
  if (w.pinned) return
  const s = new Set(secPicked.value[sec.id] || [])
  s.has(w.word_id) ? s.delete(w.word_id) : s.add(w.word_id)
  secPicked.value = { ...secPicked.value, [sec.id]: s }
}
async function addSecVocab(sec: any) {
  const ids = [...(secPicked.value[sec.id] || [])]
  if (!ids.length) return
  try {
    await addHomeworkWords(ids, paperId.value)
    secVocab.value = { ...secVocab.value, [sec.id]: (secVocab.value[sec.id] || []).map(w => ids.includes(w.word_id) ? { ...w, pinned: true } : w) }
    secPicked.value = { ...secPicked.value, [sec.id]: new Set() }
    uni.showToast({ title: `已加入作业精讲 ${ids.length} 词`, icon: 'success' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}
function openSecSentences(sec: any) {
  uni.navigateTo({ url: `/pages/user-papers/long-sentences?paperId=${paperId.value}&sectionId=${sec.id}` })
}

const similarOpen = ref(false)
const similarLoading = ref(false)
const similarKp = ref('')
const similarQid = ref('')
const similarList = ref<SimilarQuestion[]>([])

// 学生改大题的题型分类(与后端 paper_section_taxonomy.whitelist_labels 对齐)
const SECTION_LABELS = [
  '单项选择', '完形填空', '阅读理解', '任务型阅读', '选择填空',
  '词汇运用', '动词填空', '短文填空', '完成句子', '阅读填空',
  '阅读表达', '阅读回答问题', '书面表达', '听力理解', '信息还原',
  '句子翻译', '单词拼写', '句型转换', '补全对话', '其它',
]
/** 阅读理解 / 任务型阅读(整篇阅读,非完形) */
function isReadingSec(sec: any): boolean {
  return !!sec?.isReading
}
/** 完形填空:小题保留加单词(不加错题) */
function isClozeSec(sec: any): boolean {
  return !!sec?.isCloze
}
/**
 * 有语篇且非阅读/完形时,底部仍出「本题生词 / 长难句」
 * (阅读/完形改走精讲页,作业详情不再放篇级词句入口)
 */
function showPassageTools(sec: any): boolean {
  return !!sec?.hasPassage && !sec?.isReading && !sec?.isCloze
}
/**
 * 是否出小题动作栏。
 * 阅读:仅错题出栏(练同类)。完形:常驻(加单词)。其它:单选族或有考点/错题。
 */
function showActs(sec: any, q: any): boolean {
  if (isReadingSec(sec)) return !!q.is_wrong
  if (isClozeSec(sec)) return true
  const st = sec?.section_type
  if (st === 'mcq' || st === 'choice_fill' || st === 'info_restore') return true
  return !!(q.kp_kind || q.is_wrong)
}
function editSection(sec: { id: string; label: string }) {
  uni.showActionSheet({
    itemList: SECTION_LABELS,
    success: async (res) => {
      const label = SECTION_LABELS[res.tapIndex]
      if (!label || label === sec.label) return
      try {
        await updatePaperSection(sec.id, label)
        await load()
        uni.showToast({ title: `已改为「${label}」`, icon: 'none' })
      } catch (e: any) { uni.showToast({ title: e?.message || '修改失败', icon: 'none' }) }
    },
  })
}
async function practiceSimilar(qid: string) {
  if (similarLoading.value) return
  similarLoading.value = true
  try {
    const r = await practiceForQuestion(qid)
    if (!r.questions.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    similarKp.value = r.knowledge_point; similarList.value = r.questions
    similarQid.value = qid; similarOpen.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  } finally { similarLoading.value = false }
}
// 单题考点动作:加入作业精讲(语法/单词) + 手动加入我的错题(答对的兜底)
const qGrammar = ref<Set<string>>(new Set())
const qVocab = ref<Set<string>>(new Set())
const qWrong = ref<Set<string>>(new Set())
async function addGrammar(q: any) {
  if (qGrammar.value.has(q.id)) return
  try {
    const r = await addQuestionGrammar(q.id)
    qGrammar.value = new Set([...qGrammar.value, q.id])
    uni.showToast({ title: r.personal ? '已加入语法学习（自建）' : '已加入作业精讲·语法', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}
async function addVocabQ(q: any) {
  if (qVocab.value.has(q.id)) return
  try {
    const r = await addQuestionVocab(q.id)
    qVocab.value = new Set([...qVocab.value, q.id])
    uni.showToast({ title: r.added ? `已加入作业精讲·单词（${r.added}）` : '本题没识别到可加入的生词', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}
async function addToWrong(q: any) {
  if (qWrong.value.has(q.id)) return
  try {
    await addQuestionToWrong(q.id)
    qWrong.value = new Set([...qWrong.value, q.id])
    uni.showToast({ title: '已加入我的错题', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

// 结算器:回写对应错题成绩(语法推进 SM-2),返回结果文案
async function paperPracRecorder(total: number, correct: number): Promise<string> {
  const r = await recordPaperPractice(similarQid.value, total, correct)
  if (r.recorded && r.just_mastered) return '🎉 恭喜，这道错题已掌握！'
  if (r.recorded) return `已计入巩固：本轮 ${correct}/${total} 正确`
  return `本轮 ${correct}/${total} 正确`
}

const isProcessing = computed(
  () => paper.value?.ocr_status === 'pending' || paper.value?.ocr_status === 'processing',
)

const statusText = computed(() => {
  const map: Record<string, string> = {
    pending: '排队中',
    processing: '识别中',
    completed: '已完成',
    failed: '失败',
  }
  return map[paper.value?.ocr_status || ''] || '未知'
})

const statusClass = computed(() => {
  const s = paper.value?.ocr_status
  if (s === 'completed') return 'ok'
  if (s === 'failed') return 'bad'
  return 'wait'
})

async function load() {
  try {
    paper.value = await getUserPaper(paperId.value)
  } catch (e: any) {
    uni.showToast({ title: e?.message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
  // 仍在处理中 → 轮询
  if (isProcessing.value) {
    timer = setTimeout(load, 2500)
  }
}

onLoad((q: any) => {
  paperId.value = q.id || ''
  if (!paperId.value) {
    uni.showToast({ title: '缺少作业 id', icon: 'none' })
    setTimeout(() => uni.navigateBack(), 800)
    return
  }
  load()
})

onUnload(() => {
  if (timer) clearTimeout(timer)
})

function goUpload() {
  uni.redirectTo({ url: '/pages/user-papers/upload' })
}
function goList() {
  uni.navigateTo({ url: '/pages/user-papers/list' })
}
// 点标题可改名(自动命名后仍可自己修改)
function editTitle() {
  if (!paper.value) return
  uni.showModal({
    title: '作业名称', editable: true, placeholderText: '输入作业名称',
    content: paper.value.title || '',
    success: async (r) => {
      const t = (r.confirm && (r.content || '').trim()) || ''
      if (!t || !paper.value || t === paper.value.title) return
      try {
        await renamePaper(paperId.value, t)
        paper.value.title = t
        uni.showToast({ title: '已改名', icon: 'none' })
      } catch (e: any) { uni.showToast({ title: e?.message || '改名失败', icon: 'none' }) }
    },
  })
}
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 20rpx; }
.head { display: flex; flex-direction: column; gap: 12rpx; }
.head-top { display: flex; align-items: center; justify-content: space-between; }
.head-list { font-size: 24rpx; color: var(--c-primary); flex-shrink: 0; }
.title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.title-edit { font-size: 24rpx; color: var(--c-primary); font-weight: 400; margin-left: 6rpx; }
.status { align-self: flex-start; font-size: 24rpx; padding: 4rpx 16rpx; border-radius: 20rpx; }
.status.ok { background: #eafaf1; color: #2ecc71; }
.status.bad { background: var(--c-danger-bg); color: var(--c-danger); }
.status.wait { background: var(--c-primary-faint); color: #b9892e; }
.meta { font-size: 24rpx; color: var(--c-text-second); }
.processing { display: flex; flex-direction: column; gap: 10rpx; align-items: center; padding: 48rpx; }
.proc-text { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.proc-sub { font-size: 24rpx; color: var(--c-text-hint); }
.failed, .empty-q { display: flex; flex-direction: column; gap: 16rpx; align-items: center; padding: 48rpx; }
.fail-text { font-size: 30rpx; font-weight: 700; color: var(--c-danger); }
.fail-sub { font-size: 24rpx; color: var(--c-text-second); text-align: center; }
.btn-secondary { background: var(--c-bg-soft); color: var(--c-text-body); border: 2rpx solid var(--c-border); border-radius: var(--r-btn); padding: 16rpx 40rpx; font-size: 28rpx; }
.gr-card { display: flex; flex-direction: column; gap: 16rpx; }
.gr-title { font-size: 28rpx; font-weight: 800; color: var(--c-ink); }
.gr-head { display: flex; align-items: center; justify-content: space-between; }
.gr-fold { font-size: 24rpx; color: var(--c-primary); flex-shrink: 0; }
.gr-group { display: flex; flex-direction: column; gap: 10rpx; }
.gr-lbl { font-size: 24rpx; font-weight: 700; }
.gr-new { color: var(--c-danger); }
.gr-weak { color: #b9892e; }
.gr-ok { color: #2ecc71; }
.gr-chips { display: flex; flex-wrap: wrap; gap: 12rpx; }
.gr-chip { display: flex; align-items: center; gap: 8rpx; font-size: 24rpx; padding: 10rpx 18rpx; border-radius: 999rpx; }
.chip-new { background: var(--c-danger-bg); color: var(--c-danger); }
.chip-weak { background: #fdf3e2; color: #b9892e; }
.chip-ok { background: #eafaf1; color: #2ecc71; }
.chip-go { font-size: 22rpx; opacity: .8; }
.gr-plan-btn { display: flex; align-items: center; justify-content: center; gap: 10rpx; margin-top: 8rpx; padding: 20rpx; border-radius: 16rpx; background: var(--c-primary); color: #fff; font-size: 27rpx; font-weight: 700; }
.gr-plan-btn.busy { opacity: .6; }
.gr-plan-btn .ic-target, .gr-plan-btn .ic-book { width: 34rpx; height: 34rpx; filter: brightness(0) invert(1); }
.gr-hint { font-size: 23rpx; color: var(--c-text-hint); margin: -4rpx 0 4rpx; }
/* 长难句入口卡(整块单开一页) */
.entry-card { display: flex; align-items: center; gap: 12rpx; }
.entry-main { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.entry-title { font-size: 28rpx; font-weight: 800; color: var(--c-ink); }
.entry-sub { font-size: 23rpx; color: var(--c-text-hint); }
.entry-arrow { font-size: 34rpx; color: var(--c-text-hint); }
/* 先修增强 */
.gr-newitem { display: flex; flex-direction: column; gap: 6rpx; }
.gr-pre { display: flex; flex-wrap: wrap; align-items: center; gap: 10rpx; margin: 2rpx 0 4rpx 6rpx; }
.gr-pre-lbl { font-size: 21rpx; color: var(--c-danger); }
.gr-pre-chip { font-size: 21rpx; color: var(--c-danger); background: var(--c-danger-bg); border-radius: 999rpx; padding: 4rpx 14rpx; }
/* P2 生词 */
.vw-chip { background: var(--c-primary-faint); color: var(--c-ink); border: 2rpx solid transparent; }
.vw-on { border-color: var(--c-primary); background: var(--c-primary); color: #fff; }
.vw-on .chip-go { color: #fff; opacity: 1; }
/* P3 长难句 */
.ls-item { border-top: 2rpx solid var(--c-line); padding: 16rpx 0 12rpx; }
.ls-item:first-of-type { border-top: none; }
.ls-text { font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.ls-row { display: flex; justify-content: flex-end; gap: 12rpx; margin-top: 8rpx; }
.ls-btn { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 24rpx; }
.ls-add.done { color: #2ecc71; border-color: #2ecc71; }
.ls-ana { margin-top: 12rpx; padding: 14rpx; background: var(--c-primary-faint); border-radius: 12rpx; display: flex; flex-direction: column; gap: 10rpx; }
.ls-trans { font-size: 25rpx; color: var(--c-ink); line-height: 1.6; }
.ls-comps { display: flex; flex-direction: column; gap: 8rpx; }
.ls-comp { display: flex; gap: 12rpx; align-items: baseline; }
.ls-comp-t { flex-shrink: 0; font-size: 21rpx; color: var(--c-primary); background: #fff; border-radius: 8rpx; padding: 2rpx 12rpx; }
.ls-comp-x { font-size: 24rpx; color: var(--c-text-sub); line-height: 1.5; }
.section { margin-bottom: 8rpx; }
.sec-head { display: flex; align-items: center; gap: 14rpx; margin: 24rpx 4rpx 12rpx; }
.sec-bar { width: 8rpx; height: 30rpx; border-radius: 6rpx; background: var(--c-primary); }
.sec-label { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.sec-sug { font-size: 20rpx; color: #b9892e; background: var(--c-primary-faint); border-radius: 8rpx; padding: 2rpx 12rpx; }
.sec-edit { font-size: 22rpx; color: var(--c-primary); padding: 4rpx 14rpx; border: 2rpx solid var(--c-primary); border-radius: 999rpx; margin-right: 14rpx; }
.sec-cnt { font-size: 22rpx; color: var(--c-text-hint); }
.passage-card { background: var(--c-primary-faint); }
.passage-card.airy {
  background: #fff;
  border: 2rpx solid #e3e9f2;
  box-shadow: 0 4rpx 20rpx rgba(45, 80, 150, .06);
}
.passage-head { display: flex; align-items: center; justify-content: space-between; }
.passage-title { font-size: 26rpx; font-weight: 700; color: var(--c-primary); }
.passage-toggle { font-size: 22rpx; color: #93a0b3; }
.passage-text {
  display: block; font-size: 26rpx; color: var(--c-text-body);
  line-height: 1.7; margin-top: 14rpx; white-space: pre-wrap;
}
.passage-card.airy .passage-text {
  font-size: 28rpx; color: #3a4353; line-height: 2;
  letter-spacing: 0.02em; margin-top: 12rpx;
}
.p-blank {
  display: inline; font-size: 22rpx; font-weight: 800;
  padding: 2rpx 10rpx; margin: 0 4rpx; border-radius: 8rpx;
  vertical-align: baseline; line-height: 1.4;
}
.p-blank.ok { background: #e9f6f1; color: #1f8a6e; border: 1rpx solid #b7e0d0; }
.p-blank.bad { background: #fcebeb; color: #a32d2d; border: 1rpx solid #f0b6b6; }
.q-card { border-left: 6rpx solid transparent; }
.q-card.wrong { border-left-color: var(--c-danger); background: #fffbfb; }
.q-card.okborder { border-left-color: #b7e0d0; }
.q-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 12rpx; flex-wrap: wrap; }
.q-no { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.q-type { font-size: 22rpx; color: var(--c-text-hint); }
.q-type-pill {
  font-size: 20rpx; font-weight: 800; padding: 2rpx 12rpx; border-radius: 999rpx;
  background: #e8f2ff; color: var(--c-primary);
}
.q-flag { margin-left: auto; font-size: 24rpx; font-weight: 700; color: var(--c-danger); display: flex; align-items: center; gap: 4rpx; }
.q-stem { display: block; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; margin-bottom: 12rpx; white-space: pre-wrap; }
.q-opts { display: flex; flex-direction: column; gap: 8rpx; margin-bottom: 12rpx; }
.q-opt {
  display: flex; align-items: center; gap: 12rpx;
  font-size: 26rpx; color: var(--c-text-body); line-height: 1.5;
  padding: 14rpx 16rpx; background: #fafbfd; border-radius: 12rpx;
  border: 1rpx solid #e6ebf2;
}
.q-opt-t { flex: 1; }
.q-opt-h { flex-shrink: 0; font-size: 22rpx; font-weight: 800; opacity: .9; }
.q-opt-ok { background: #e9f6f1; border-color: #b7e0d0; color: #1f8a6e; font-weight: 700; }
.q-opt-bad { background: #fcebeb; border-color: #f0b6b6; color: #a32d2d; font-weight: 700; }
.q-ans { display: flex; flex-direction: column; gap: 6rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; }
.q-ans.compact { flex-direction: row; flex-wrap: wrap; gap: 16rpx; background: transparent; padding: 4rpx 0 0; }
.ans-line { font-size: 24rpx; color: var(--c-text-body); }
.q-exp { display: flex; gap: 10rpx; align-items: flex-start; font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-top: 12rpx; }
.q-exp-k { flex-shrink: 0; font-size: 22rpx; font-weight: 700; color: #2f74d6; background: #eef5ff; border-radius: 8rpx; padding: 2rpx 10rpx; margin-top: 2rpx; }
.q-exp-t { flex: 1; }
.kp-card { display: flex; flex-direction: column; gap: 10rpx; }
.kp-title { font-size: 28rpx; font-weight: 800; color: var(--c-ink); margin-bottom: 6rpx; }
.kp-row { display: flex; align-items: center; gap: 12rpx; }
.kp-name { flex: 1; font-size: 26rpx; color: var(--c-text-body); }
.kp-name.weak { color: var(--c-danger); font-weight: 700; }
.kp-cnt { font-size: 24rpx; color: var(--c-text-hint); }
.kp-weak { font-size: 20rpx; color: #fff; background: var(--c-danger); border-radius: 8rpx; padding: 2rpx 10rpx; }
.filter-row { display: flex; gap: 16rpx; margin-bottom: 16rpx; }
.fbtn { font-size: 26rpx; color: var(--c-text-second); padding: 8rpx 24rpx; border-radius: 999rpx; background: var(--c-bg-soft); }
.fbtn.on { background: var(--c-primary); color: var(--c-on-primary); font-weight: 700; }
/* 本题型 全部|错题 */
.sec-filter { display: flex; gap: 12rpx; margin: 0 4rpx 14rpx; }
/* 对/错标 */
.q-flag.q-ok { color: #18a058; }
.ans-x { color: var(--c-danger); }
.ans-ok { color: #128a4c; }
.sec-empty { text-align: center; color: var(--c-text-hint); font-size: 24rpx; padding: 24rpx 0; }
/* 阅读理解:加入精讲 */
.reading-add { display: flex; align-items: center; justify-content: center; gap: 10rpx; margin: 14rpx 4rpx 0; padding: 16rpx; border-radius: 16rpx; background: var(--c-primary); color: #fff; font-size: 27rpx; font-weight: 700; }
.reading-add .ic-book { filter: brightness(0) invert(1); }
.reading-add.done { background: var(--c-bg-soft); color: var(--c-text-second); }
.reading-add.done .ic-book { filter: none; }
/* 底部三功能 */
.sec-tools { display: flex; gap: 14rpx; margin: 14rpx 4rpx 4rpx; }
.tool-chip { flex: 1; text-align: center; font-size: 25rpx; color: var(--c-primary-deep); background: var(--c-bg-card); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 12rpx 0; font-weight: 600; }
.tool-chip.on { background: var(--c-primary); color: var(--c-on-primary); }
.tool-panel { margin-top: 12rpx; display: flex; flex-direction: column; gap: 10rpx; }
.tool-row { display: flex; align-items: center; justify-content: space-between; font-size: 26rpx; color: var(--c-ink); padding: 10rpx 0; border-bottom: 1rpx solid var(--c-border); }
.tool-row:last-child { border-bottom: none; }
.btn-similar { margin-top: 16rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-btn); font-size: 26rpx; padding: 12rpx 0; }
.q-acts { display: flex; flex-wrap: wrap; gap: 12rpx; margin-top: 16rpx; align-items: center; }
.q-act { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 8rpx 24rpx; }
.q-tag { font-size: 22rpx; padding: 6rpx 18rpx; border-radius: 999rpx; font-weight: 600; }
.q-tag-wrong { background: #fdecec; color: #c33; }
.q-act.done { color: #2ecc71; border-color: #2ecc71; }
.q-act-sim { color: var(--c-primary-deep); background: var(--c-primary-faint); border-color: transparent; }
.modal { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 100; }
.modal-card { width: 86%; max-height: 76vh; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; display: flex; flex-direction: column; gap: 16rpx; }
.modal-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.modal-body { max-height: 56vh; }
.sq { margin-bottom: 20rpx; }
.sq-stem { display: block; font-size: 27rpx; color: var(--c-text-body); line-height: 1.6; }
.sq-opts { display: flex; flex-direction: column; gap: 4rpx; margin-top: 8rpx; }
.sq-opt { font-size: 25rpx; color: var(--c-text-second); }
.muted { color: var(--c-text-hint); font-size: 24rpx; }
</style>

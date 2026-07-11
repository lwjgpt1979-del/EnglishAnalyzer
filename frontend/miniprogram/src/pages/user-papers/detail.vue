<template>
  <view class="page">
    <view v-if="loading" class="empty">加载中…</view>

    <template v-else-if="paper">
      <view class="head card">
        <text class="title">{{ paper.title || '未命名试卷' }}</text>
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

      <!-- 完成：知识点归集 + 题目列表 -->
      <template v-else-if="paper.ocr_status === 'completed'">
        <view v-if="!paper.questions.length" class="card empty-q">
          <text>未识别到题目，请重试或换更清晰的图片</text>
          <button class="btn-secondary" @tap="goUpload">重新上传</button>
        </view>

        <!-- 知识点归集卡（错题按知识点聚合，薄弱红标）-->
        <view v-if="kpItems.length" class="card kp-card">
          <text class="kp-title">本卷知识点归集</text>
          <view v-for="k in kpItems" :key="k.kp_id" class="kp-row">
            <text class="kp-name" :class="{ weak: k.weak }">{{ k.kp_name }}</text>
            <text class="kp-cnt">错 {{ k.wrong }}/{{ k.total }}</text>
            <text v-if="k.weak" class="kp-weak">薄弱</text>
          </view>
        </view>

        <!-- P1:本卷语法点 学情(已学/薄弱/未学) -->
        <view v-if="grammar && grammar.total" class="card gr-card">
          <text class="gr-title">本卷语法点 · 学情（{{ grammar.total }}）</text>
          <view v-if="grammar.new.length" class="gr-group">
            <text class="gr-lbl gr-new">未学 {{ grammar.new.length }}</text>
            <view class="gr-chips">
              <view v-for="n in grammar.new" :key="n.node_id" class="gr-newitem">
                <view class="gr-chip chip-new" @tap="goLearnNode(n)">
                  <text>{{ n.name }}</text><text class="chip-go">去学 ›</text>
                </view>
                <!-- 先修增强:该未学语法有未学先修 → 提示先补(prereq 边为空时不显示) -->
                <view v-if="unlearnedPre(n).length" class="gr-pre">
                  <text class="gr-pre-lbl">先补先修:</text>
                  <text v-for="p in unlearnedPre(n)" :key="p.node_id" class="gr-pre-chip"
                        @tap="goLearnNode({ node_id: p.node_id, name: p.name } as any)">{{ p.name }} ›</text>
                </view>
              </view>
            </view>
          </view>
          <view v-if="grammar.weak.length" class="gr-group">
            <text class="gr-lbl gr-weak">薄弱 {{ grammar.weak.length }}</text>
            <view class="gr-chips">
              <view v-for="n in grammar.weak" :key="n.node_id" class="gr-chip chip-weak" @tap="goLearnNode(n)">
                <text>{{ n.name }}</text><text class="chip-go">去练 ›</text>
              </view>
            </view>
          </view>
          <view v-if="grammar.learned.length" class="gr-group">
            <text class="gr-lbl gr-ok">已学 {{ grammar.learned.length }}</text>
            <view class="gr-chips">
              <view v-for="n in grammar.learned" :key="n.node_id" class="gr-chip chip-ok" @tap="goLearnNode(n)">
                <text>{{ n.name }}</text>
              </view>
            </view>
          </view>
          <!-- P4 闭环:未学+薄弱一键成学习计划 -->
          <view v-if="planCount" class="gr-plan-btn" :class="{ busy: planBusy }" @tap="addToPlan">
            <text class="ic ic-target" />
            <text>{{ planBusy ? '加入中…' : `一键加入学习计划（${planCount}）` }}</text>
          </view>
        </view>

        <!-- P2:本卷生词 → 加入词力通优先学 -->
        <view v-if="vocab.length" class="card gr-card">
          <text class="gr-title">本卷生词 · {{ vocab.length }}</text>
          <text class="gr-hint">从原文挑出你还没掌握的词,选中加入「词力通」优先学。</text>
          <view class="gr-chips">
            <view v-for="w in vocab" :key="w.word_id" class="gr-chip vw-chip"
                  :class="{ 'vw-on': picked.has(w.word_id) || w.pinned }" @tap="toggleWord(w)">
              <text>{{ w.word }}</text>
              <text v-if="w.pinned" class="chip-go">已加</text>
              <text v-else-if="picked.has(w.word_id)" class="chip-go">✓</text>
            </view>
          </view>
          <view v-if="pickCount" class="gr-plan-btn" :class="{ busy: vocabBusy }" @tap="addVocab">
            <text class="ic ic-book" />
            <text>{{ vocabBusy ? '加入中…' : `加入词力通（${pickCount}）` }}</text>
          </view>
        </view>

        <!-- P3:本卷长难句 → 逐句解析 -->
        <view v-if="sentences.length" class="card gr-card">
          <text class="gr-title">本卷长难句 · {{ sentences.length }}</text>
          <text class="gr-hint">原文里的长难句,点「解析」拆结构、看意思。</text>
          <view v-for="(s, i) in sentences" :key="i" class="ls-item">
            <text class="ls-text">{{ s }}</text>
            <view class="ls-row">
              <view class="ls-btn" @tap="analyzeOne(i)">
                <text>{{ lsBusy === i ? '解析中…' : (lsResult[i] ? '收起' : '解析') }}</text>
              </view>
            </view>
            <view v-if="lsResult[i]" class="ls-ana">
              <text v-if="lsResult[i].translation" class="ls-trans">{{ lsResult[i].translation }}</text>
              <view v-if="lsResult[i].segments && lsResult[i].segments.length" class="ls-comps">
                <view v-for="(c, ci) in lsResult[i].segments" :key="ci" class="ls-comp">
                  <text class="ls-comp-t">{{ c.type }}</text>
                  <text class="ls-comp-x">{{ c.text }}</text>
                </view>
              </view>
            </view>
          </view>
        </view>

        <!-- 全部/错题 筛选 -->
        <view v-if="paper.questions.length" class="filter-row">
          <text class="fbtn" :class="{ on: !onlyWrong }" @tap="onlyWrong = false">全部 {{ paper.questions.length }}</text>
          <text class="fbtn" :class="{ on: onlyWrong }" @tap="onlyWrong = true">错题 {{ wrongCount }}</text>
        </view>

        <!-- 按原卷大题分组(还原题型结构):大题头 → 语篇(完形/阅读只显示一次) → 小题 -->
        <view v-for="sec in shownSections" :key="sec.id" class="section">
          <view class="sec-head">
            <text class="sec-bar" />
            <text class="sec-label">{{ sec.label }}</text>
            <text v-if="sec.is_suggested" class="sec-sug">建议</text>
            <view style="flex:1" />
            <text v-if="sec.id !== 'all'" class="sec-edit" @tap="editSection(sec)">改题型</text>
            <text class="sec-cnt">{{ sec.questions.length }} 题</text>
          </view>
          <template v-for="grp in sec.blocks" :key="grp.key">
            <view v-if="grp.passage" class="card passage-card" @tap="toggleBlock(grp.key)">
              <view class="passage-head">
                <text class="passage-title">短文{{ grp.blockLabel }}</text>
                <text class="passage-toggle">{{ collapsed[grp.key] ? '展开 ▾' : '收起 ▴' }}</text>
              </view>
              <text v-if="!collapsed[grp.key]" class="passage-text">{{ grp.passage }}</text>
            </view>
            <view
              v-for="q in grp.questions" :key="q.id"
              class="card q-card" :class="{ wrong: q.is_wrong }"
            >
              <view class="q-head">
                <text class="q-no">{{ q.question_no ? `第 ${q.question_no} 题` : '题目' }}</text>
                <text class="q-type">{{ q.question_type || '题目' }}</text>
                <view v-if="q.is_wrong" class="q-flag"><view class="ic ic-x-circle" style="width:26rpx;height:26rpx" /><text>错</text></view>
              </view>
              <text class="q-stem">{{ q.stem || '（题干识别为空）' }}</text>
              <view class="q-ans">
                <text class="ans-line">你的答案：{{ q.student_answer || '（未识别）' }}</text>
                <text class="ans-line">正确答案：{{ q.correct_answer || '（未提供）' }}</text>
              </view>
              <text v-if="q.explanation" class="q-exp">{{ q.explanation }}</text>
              <button v-if="q.is_wrong" class="btn-similar" :disabled="similarLoading" @tap="practiceSimilar(q.id)">练同类仿真题</button>
            </view>
          </template>
        </view>
      </template>
    </template>

    <!-- 练同类结果弹层 -->
    <view v-if="similarOpen" class="modal" @tap.self="similarOpen = false">
      <view class="modal-card">
        <text class="modal-title">同类练习 · {{ similarKp }}</text>
        <scroll-view scroll-y class="modal-body">
          <view v-for="(sq, i) in similarList" :key="sq.id" class="sq">
            <text class="sq-stem">{{ i + 1 }}. {{ sq.stem }}</text>
            <view v-if="sq.options" class="sq-opts">
              <text v-for="(v, kk) in sq.options" :key="kk" class="sq-opt">{{ kk }}. {{ v }}</text>
            </view>
          </view>
          <text v-if="!similarList.length" class="muted">未生成题目</text>
        </scroll-view>
        <button class="btn-secondary" @tap="similarOpen = false">关闭</button>
      </view>
    </view>

    <view v-else class="empty">试卷不存在或无权访问</view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onUnload } from '@dcloudio/uni-app'
import { getUserPaper, updatePaperSection, getPaperKpSummary, getPaperGrammarStatus, addPaperToPlan, getPaperVocab, getPaperLongSentences, analyzePaperSentence, practiceForQuestion, type PaperKpItem, type SimilarQuestion, type PaperGrammarStatus, type GrammarNodeItem, type PaperVocabWord } from '@/api/userPapers'
import { addPins } from '@/api/vocabulary'
import type { UserPaperDetailOut } from '@/types/api'

const paper = ref<UserPaperDetailOut | null>(null)
const loading = ref(true)
const paperId = ref('')
let timer: ReturnType<typeof setTimeout> | null = null

// M4 深化：知识点归集 + 错题筛选 + 练同类
const kpItems = ref<PaperKpItem[]>([])
const onlyWrong = ref(false)
const wrongCount = computed(() => (paper.value?.questions || []).filter(q => q.is_wrong).length)

// 语篇折叠态(完形/阅读短文)
const collapsed = ref<Record<string, boolean>>({})
function toggleBlock(k: string) { collapsed.value = { ...collapsed.value, [k]: !collapsed.value[k] } }

// 按原卷大题分组 → 大题内按 block_key 归「短文+多小问」组;支持 全部/错题 过滤;
// 兼容后端未返回 sections 的旧数据(退回单个「全部题目」组)
const shownSections = computed(() => {
  const filt = (qs: any[]) => onlyWrong.value ? qs.filter(q => q.is_wrong) : qs
  const toBlocks = (qs: any[]) => {
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
  const secs = paper.value?.sections || []
  const out: any[] = []
  for (const sec of secs) {
    const qs = filt(sec.questions || [])
    if (!qs.length) continue
    out.push({ id: sec.id, label: sec.label, is_suggested: !!sec.is_suggested, questions: qs, blocks: toBlocks(qs) })
  }
  if (!out.length) {                          // 旧后端/旧数据:无 sections → 扁平兜底
    const qs = filt(paper.value?.questions || [])
    if (qs.length) out.push({ id: 'all', label: '全部题目', is_suggested: false, questions: qs, blocks: toBlocks(qs) })
  }
  return out
})
const similarOpen = ref(false)
const similarLoading = ref(false)
const similarKp = ref('')
const similarList = ref<SimilarQuestion[]>([])

async function loadKpSummary() {
  try { kpItems.value = (await getPaperKpSummary(paperId.value)).items } catch { /* ignore */ }
}

// P1:本卷语法点 已学/薄弱/未学
const grammar = ref<PaperGrammarStatus | null>(null)
async function loadGrammar() {
  try { grammar.value = await getPaperGrammarStatus(paperId.value) } catch { /* ignore */ }
}
function goLearnNode(n: GrammarNodeItem) {
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${n.node_id}&name=${encodeURIComponent(n.name)}&cat=grammar` })
}

// P4 闭环:未学+薄弱语法一键加入学习计划
const planBusy = ref(false)
const planCount = computed(() => (grammar.value ? grammar.value.new.length + grammar.value.weak.length : 0))
async function addToPlan() {
  if (planBusy.value || !planCount.value) return
  planBusy.value = true
  try {
    const r = await addPaperToPlan(paperId.value)
    uni.showModal({
      title: '已加入学习计划',
      content: `本卷未学 ${r.new} + 薄弱 ${r.weak} 个语法点已加入,今日计划会带你去学去练。`,
      confirmText: '去看计划', cancelText: '知道了',
      success: (m) => { if (m.confirm) uni.switchTab({ url: '/pages/index/index' }) },
    })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
  finally { planBusy.value = false }
}

// 先修增强:某未学语法点里「还没学的先修」
function unlearnedPre(n: GrammarNodeItem) {
  return (n.prereq || []).filter(p => !p.learned)
}

// P2:本卷生词 → 加入词力通优先学
const vocab = ref<PaperVocabWord[]>([])
const picked = ref<Set<string>>(new Set())
const vocabBusy = ref(false)
const pickCount = computed(() => picked.value.size)
async function loadVocab() {
  try { vocab.value = (await getPaperVocab(paperId.value)).words } catch { /* ignore */ }
}
function toggleWord(w: PaperVocabWord) {
  if (w.pinned) return
  const s = new Set(picked.value)
  s.has(w.word_id) ? s.delete(w.word_id) : s.add(w.word_id)
  picked.value = s
}
async function addVocab() {
  if (vocabBusy.value || !picked.value.size) return
  vocabBusy.value = true
  try {
    const ids = [...picked.value]
    await addPins(ids, 1)
    // 本地标记已加,清空选择
    vocab.value = vocab.value.map(w => ids.includes(w.word_id) ? { ...w, pinned: true } : w)
    picked.value = new Set()
    uni.showToast({ title: `已加入 ${ids.length} 个词`, icon: 'success' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
  finally { vocabBusy.value = false }
}

// P3:本卷长难句 → 逐句解析
const sentences = ref<string[]>([])
const lsResult = ref<Record<number, any>>({})
const lsBusy = ref<number>(-1)
async function loadSentences() {
  try { sentences.value = (await getPaperLongSentences(paperId.value)).sentences } catch { /* ignore */ }
}
async function analyzeOne(i: number) {
  if (lsBusy.value >= 0) return
  if (lsResult.value[i]) { const r = { ...lsResult.value }; delete r[i]; lsResult.value = r; return }  // 收起
  lsBusy.value = i
  try {
    const r = await analyzePaperSentence(sentences.value[i])
    lsResult.value = { ...lsResult.value, [i]: r }
  } catch (e: any) { uni.showToast({ title: e?.message || '解析失败', icon: 'none' }) }
  finally { lsBusy.value = -1 }
}

// 学生改大题的题型分类(AI 建议不准时)
const SECTION_LABELS = ['单项选择', '完形填空', '阅读理解', '任务型阅读', '词汇运用', '短文填空', '书面表达', '听力理解', '其它']
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
    similarKp.value = r.knowledge_point; similarList.value = r.questions; similarOpen.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  } finally { similarLoading.value = false }
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
  } else if (paper.value?.ocr_status === 'completed') {
    loadKpSummary()
    loadGrammar()
    loadVocab()
    loadSentences()
  }
}

onLoad((q: any) => {
  paperId.value = q.id || ''
  if (!paperId.value) {
    uni.showToast({ title: '缺少试卷 id', icon: 'none' })
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
</script>

<style scoped>
.page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.empty { text-align: center; padding: 80rpx 0; color: var(--c-text-hint); }
.card { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 28rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); margin-bottom: 20rpx; }
.head { display: flex; flex-direction: column; gap: 12rpx; }
.title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
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
.ls-row { display: flex; justify-content: flex-end; margin-top: 8rpx; }
.ls-btn { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 24rpx; }
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
.passage-head { display: flex; align-items: center; justify-content: space-between; }
.passage-title { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); }
.passage-toggle { font-size: 22rpx; color: var(--c-primary); }
.passage-text { display: block; font-size: 26rpx; color: var(--c-text-body); line-height: 1.7; margin-top: 14rpx; white-space: pre-wrap; }
.q-card { border-left: 6rpx solid transparent; }
.q-card.wrong { border-left-color: var(--c-danger); }
.q-head { display: flex; align-items: center; gap: 16rpx; margin-bottom: 12rpx; }
.q-no { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.q-type { font-size: 22rpx; color: var(--c-text-hint); }
.q-flag { margin-left: auto; font-size: 24rpx; font-weight: 700; color: var(--c-danger); display: flex; align-items: center; gap: 4rpx; }
.q-stem { display: block; font-size: 28rpx; color: var(--c-text-body); line-height: 1.6; margin-bottom: 16rpx; white-space: pre-wrap; }
.q-ans { display: flex; flex-direction: column; gap: 6rpx; background: var(--c-bg-soft); border-radius: var(--r-md); padding: 16rpx; }
.ans-line { font-size: 24rpx; color: var(--c-text-body); }
.q-exp { display: block; font-size: 24rpx; color: var(--c-text-second); line-height: 1.6; margin-top: 12rpx; }
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
.btn-similar { margin-top: 16rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-btn); font-size: 26rpx; padding: 12rpx 0; }
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

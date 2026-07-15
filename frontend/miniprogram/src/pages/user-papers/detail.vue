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
            <text v-if="sec.is_suggested" class="sec-sug">建议</text>
            <view style="flex:1" />
            <text v-if="sec.id !== 'all'" class="sec-edit" @tap="editSection(sec)">改题型</text>
          </view>
          <!-- 本题型 全部|错题(默认错题;无错题默认全部) -->
          <view class="sec-filter">
            <text class="fbtn" :class="{ on: !isWrongView(sec) }" @tap="setWrong(sec, false)">全部 {{ sec.total }}</text>
            <text class="fbtn" :class="{ on: isWrongView(sec) }" @tap="setWrong(sec, true)">错题 {{ sec.wrongCount }}</text>
          </view>

          <template v-for="grp in blocksFor(sec)" :key="grp.key">
            <!-- 原文(阅读/完形语篇) -->
            <view v-if="grp.passage" class="card passage-card" @tap="toggleBlock(grp.key)">
              <view class="passage-head">
                <text class="passage-title">原文{{ grp.blockLabel }}</text>
                <text class="passage-toggle">{{ collapsed[grp.key] ? '展开 ▾' : '收起 ▴' }}</text>
              </view>
              <text v-if="!collapsed[grp.key]" class="passage-text">{{ grp.passage }}</text>
            </view>

            <view v-for="q in grp.questions" :key="q.id" class="card q-card" :class="{ wrong: q.is_wrong }">
              <view class="q-head">
                <text class="q-no">{{ q.question_no ? `第 ${q.question_no} 题` : '题目' }}</text>
                <view v-if="q.is_wrong" class="q-flag"><view class="ic ic-x-circle" style="width:26rpx;height:26rpx" /><text>错</text></view>
                <view v-else class="q-flag q-ok"><view class="ic ic-check-circle" style="width:26rpx;height:26rpx" /><text>对</text></view>
              </view>
              <text class="q-stem">{{ q.stem || '（题干识别为空）' }}</text>
              <view class="q-ans">
                <text class="ans-line" :class="{ 'ans-x': q.is_wrong }">你的答案：{{ q.student_answer || '（未识别）' }}</text>
                <text class="ans-line ans-ok">正确答案：{{ q.correct_answer || '（未提供）' }}</text>
              </view>
              <text v-if="q.explanation" class="q-exp">{{ q.explanation }}</text>
              <!-- 错题练同类(单题级);语法/词汇动作收到底部三功能 -->
              <view v-if="q.is_wrong" class="q-acts">
                <view class="q-act q-act-sim" @tap="practiceSimilar(q.id)">
                  <text>{{ similarLoading ? '生成中…' : '练同类仿真题' }}</text>
                </view>
              </view>
            </view>
          </template>
          <view v-if="!blocksFor(sec).length" class="sec-empty">本题型该筛选下暂无题目</view>

          <!-- 底部功能:仅有原文的题型(阅读/完形)有 本题生词 + 长难句 -->
          <view v-if="sec.hasPassage" class="sec-tools">
            <text class="tool-chip" :class="{ on: secVocabOpen[sec.id] }" @tap="toggleSecVocab(sec)">本题生词</text>
            <text class="tool-chip" @tap="openSecSentences(sec)">长难句</text>
          </view>

          <!-- 本题生词:懒加载该题型生词 -->
          <view v-if="sec.hasPassage && secVocabOpen[sec.id]" class="card tool-panel">
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
import { getUserPaper, updatePaperSection, getPaperVocab, practiceForQuestion, recordPaperPractice, renamePaper, type SimilarQuestion, type PaperVocabWord } from '@/api/userPapers'
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
const paperSections = computed(() => {
  const build = (id: string, label: string, is_suggested: boolean, qs: any[]) =>
    ({ id, label, is_suggested, questions: qs, total: qs.length,
       wrongCount: qs.filter((q: any) => q.is_wrong).length,
       hasPassage: qs.some((q: any) => q.passage || q.block_key) })
  const out: any[] = []
  for (const sec of (paper.value?.sections || [])) {
    if ((sec.questions || []).length) out.push(build(sec.id, sec.label, !!sec.is_suggested, sec.questions))
  }
  if (!out.length && (paper.value?.questions || []).length) out.push(build('all', '全部题目', false, paper.value!.questions))
  return out
})
// 本题型 全部|错题(默认:有错题→错题,无错题→全部)
const secWrong = ref<Record<string, boolean>>({})
function isWrongView(sec: any): boolean {
  return sec.id in secWrong.value ? secWrong.value[sec.id] : sec.wrongCount > 0
}
function setWrong(sec: any, v: boolean) { secWrong.value = { ...secWrong.value, [sec.id]: v } }
function blocksFor(sec: any) {
  return toBlocks(isWrongView(sec) ? sec.questions.filter((q: any) => q.is_wrong) : sec.questions)
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
    if (!r.questions.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    similarKp.value = r.knowledge_point; similarList.value = r.questions
    similarQid.value = qid; similarOpen.value = true
  } catch (e: any) {
    uni.showToast({ title: e?.message || '生成失败', icon: 'none' })
  } finally { similarLoading.value = false }
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
/* 本题型 全部|错题 */
.sec-filter { display: flex; gap: 12rpx; margin: 0 4rpx 14rpx; }
/* 对/错标 */
.q-flag.q-ok { color: #18a058; }
.ans-x { color: var(--c-danger); }
.ans-ok { color: #128a4c; }
.sec-empty { text-align: center; color: var(--c-text-hint); font-size: 24rpx; padding: 24rpx 0; }
/* 底部三功能 */
.sec-tools { display: flex; gap: 14rpx; margin: 14rpx 4rpx 4rpx; }
.tool-chip { flex: 1; text-align: center; font-size: 25rpx; color: var(--c-primary-deep); background: var(--c-bg-card); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 12rpx 0; font-weight: 600; }
.tool-chip.on { background: var(--c-primary); color: var(--c-on-primary); }
.tool-panel { margin-top: 12rpx; display: flex; flex-direction: column; gap: 10rpx; }
.tool-row { display: flex; align-items: center; justify-content: space-between; font-size: 26rpx; color: var(--c-ink); padding: 10rpx 0; border-bottom: 1rpx solid var(--c-border); }
.tool-row:last-child { border-bottom: none; }
.btn-similar { margin-top: 16rpx; background: var(--c-primary-faint); color: var(--c-primary-deep); border-radius: var(--r-btn); font-size: 26rpx; padding: 12rpx 0; }
.q-acts { display: flex; flex-wrap: wrap; gap: 12rpx; margin-top: 16rpx; }
.q-act { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 8rpx 24rpx; }
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

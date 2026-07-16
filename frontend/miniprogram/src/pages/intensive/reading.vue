<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">作业精讲 · 阅读理解</text>
      <text class="hd-sub">来自你上传作业里的阅读理解,按卷复习:读短文、看题、对答案。</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>
    <view v-else-if="!batches.length" class="tip">还没有阅读理解——上传含阅读理解的作业即可在此复习。</view>

    <!-- 批次列表 -->
    <template v-else>
      <view v-for="b in batches" :key="b.paper_id" class="card batch" @tap="openBatch(b)">
        <view class="batch-main">
          <text class="batch-title">{{ b.title }}</text>
          <text class="batch-sub">{{ b.date }} · {{ b.count }} 题</text>
        </view>
        <text class="batch-arrow">{{ openId === b.paper_id ? '▾' : '›' }}</text>
      </view>
      <!-- 展开:该卷的短文 + 小题 -->
      <view v-if="openId" class="wrap">
        <view v-if="itemsLoading" class="tip">加载中…</view>
        <view v-else-if="!blocks.length" class="tip">该卷没有阅读理解内容</view>
        <template v-else>
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
                <text v-for="(seg, si) in passageSegs(bi, bk.passage)" :key="si" :class="{ 'ev-hl': seg.hl }">{{ seg.t }}</text>
              </view>
            </view>

            <!-- 本篇短文:本地生词 + 长难句(懒加载,展开才请求) -->
            <view v-if="bk.passage" class="study-tools">
              <text class="tool-chip" :class="{ on: studyOpen[bi] }" @tap="toggleStudy(bi, bk)">本地生词 · 长难句</text>
            </view>
            <template v-if="bk.passage && studyOpen[bi]">
              <view v-if="studyLoading[bi]" class="tip">加载中…</view>
              <template v-else-if="study[bi]">
                <KeyWordsList :words="study[bi].words" :paper-id="openId" title="本地生词" />
                <view v-if="study[bi].sentences.length" class="card">
                  <text class="sec-t">长难句</text>
                  <text class="sec-sub">点句子看逐句解析(结构·语法·重点词)。</text>
                  <view v-for="(s, si) in study[bi].sentences" :key="si" class="ls-row" @tap="openSentence(s)">
                    <text class="ls-text">{{ s }}</text>
                    <text class="ls-go">解析 ›</text>
                  </view>
                </view>
                <view v-if="!study[bi].words.length && !study[bi].sentences.length" class="tip">本篇没有生词或长难句</view>
              </template>
            </template>

            <!-- 讲义卡片:题型大标签 + 四件套 -->
            <view v-for="(q, qi) in bk.questions" :key="qi" class="q-card">
              <view class="q-head">
                <text class="q-type" :class="typeCls(q)">{{ typeLabel(q) }}</text>
                <text v-if="q.is_wrong" class="st-chip st-bad">答错</text>
                <text v-else class="st-chip st-ok">答对</text>
                <text class="q-no">{{ q.no ? `第 ${q.no} 题` : '' }}</text>
              </view>
              <text class="q-stem">{{ q.stem || '（题干为空）' }}</text>
              <view class="q-ans">
                <text class="ans-chip" :class="q.is_wrong ? 'ac-bad' : 'ac-ok'">你选 {{ q.student_answer || '未识别' }} {{ q.is_wrong ? '✗' : '✓' }}</text>
                <text class="ans-chip ac-ok">正确 {{ q.correct_answer || '未提供' }} ✓</text>
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
        </template>
      </view>
    </template>

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
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { rdHwBatches, rdHwPassages, type IntensiveBatch, type ReadingBlock } from '@/api/curriculum'
import { getReadingAnalysis, readingPractice, recordPaperPractice, getPassageStudy,
         type ReadingAnalysis, type SimilarQuestion, type StudyWord } from '@/api/userPapers'
import PracticeQuiz from '@/components/PracticeQuiz.vue'
import KeyWordsList from '@/components/KeyWordsList.vue'

const batches = ref<IntensiveBatch[]>([])
const loading = ref(true)
const openId = ref('')
const blocks = ref<ReadingBlock[]>([])
const itemsLoading = ref(false)
const collapsed = ref<Record<number, boolean>>({})

function toggle(i: number) { collapsed.value = { ...collapsed.value, [i]: !collapsed.value[i] } }

// 题型大标签:中文题型名(优先解析出的 skill)+ 同系配色
function typeLabel(q: any): string {
  return ana.value[q.id]?.skill || q.type || '阅读理解'
}
function typeCls(q: any): string {
  const s = typeLabel(q)
  if (s.includes('细节')) return 'tt-detail'
  if (s.includes('推')) return 'tt-infer'
  if (s.includes('主旨') || s.includes('大意') || s.includes('标题')) return 'tt-main'
  if (s.includes('词义') || s.includes('猜')) return 'tt-word'
  if (s.includes('态度') || s.includes('观点') || s.includes('情感')) return 'tt-att'
  return 'tt-detail'
}

// 证据句在原文里高亮(按当前展开解析的题定位;匹配不到则不高亮)
const activeEv = ref<Record<number, string>>({})
function passageSegs(bi: number, passage: string): { t: string; hl: boolean }[] {
  const ev = (activeEv.value[bi] || '').trim()
  if (!ev || !passage) return [{ t: passage, hl: false }]
  const idx = passage.toLowerCase().indexOf(ev.toLowerCase())
  if (idx < 0) return [{ t: passage, hl: false }]
  return [
    { t: passage.slice(0, idx), hl: false },
    { t: passage.slice(idx, idx + ev.length), hl: true },
    { t: passage.slice(idx + ev.length), hl: false },
  ].filter(s => s.t)
}

// 本篇短文:本地生词 + 长难句(懒加载,按 block 缓存)
const studyOpen = ref<Record<number, boolean>>({})
const studyLoading = ref<Record<number, boolean>>({})
const study = ref<Record<number, { words: StudyWord[]; sentences: string[] }>>({})
async function toggleStudy(bi: number, bk: ReadingBlock) {
  const open = !studyOpen.value[bi]
  studyOpen.value = { ...studyOpen.value, [bi]: open }
  if (open && !study.value[bi]) {
    studyLoading.value = { ...studyLoading.value, [bi]: true }
    try { study.value = { ...study.value, [bi]: await getPassageStudy(bk.passage, openId.value || undefined) } }
    catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }); studyOpen.value = { ...studyOpen.value, [bi]: false } }
    finally { studyLoading.value = { ...studyLoading.value, [bi]: false } }
  }
}
function openSentence(s: string) {
  uni.navigateTo({ url: `/pages/user-papers/sentence?text=${encodeURIComponent(s)}&paperId=${openId.value}` })
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
  // 展开后把证据句在原文里高亮(自动滚回原文吸顶处对照)
  activeEv.value = { ...activeEv.value, [bi]: ana.value[q.id]?.evidence || '' }
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
    const r = await readingPractice(qid)   // 阅读理解练同类:本篇短文的理解新题(非语法题)
    if (r.error) { uni.showToast({ title: r.error, icon: 'none' }); return }
    if (!r.questions.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    pracKp.value = '阅读理解'; pracList.value = r.questions; pracQid.value = qid; pracOpen.value = true
  } catch (e: any) { uni.showToast({ title: e?.message || '出题失败', icon: 'none' }) }
  finally { pracLoading.value = '' }
}
async function pracRecorder(total: number, correct: number): Promise<string> {
  const r = await recordPaperPractice(pracQid.value, total, correct)
  if (r.recorded && r.just_mastered) return '🎉 恭喜，这道错题已掌握！'
  if (r.recorded) return `已计入巩固：本轮 ${correct}/${total} 正确`
  return `本轮 ${correct}/${total} 正确`
}

async function openBatch(b: IntensiveBatch) {
  if (openId.value === b.paper_id) { openId.value = ''; return }   // 再点收起
  openId.value = b.paper_id
  itemsLoading.value = true
  blocks.value = []
  collapsed.value = {}
  activeEv.value = {}
  studyOpen.value = {}; studyLoading.value = {}; study.value = {}
  try {
    blocks.value = (await rdHwPassages(b.paper_id)).blocks
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { itemsLoading.value = false }
}

onLoad(async () => {
  try { batches.value = (await rdHwBatches()).batches } catch { /* ignore */ }
  finally { loading.value = false }
})
</script>

<style scoped>
/* 冷静蓝白:纯白卡 + 蓝灰分层 */
.page { min-height: 100vh; background: #f4f6fa; padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: #1f2733; display: block; }
.hd-sub { font-size: 24rpx; color: #93a0b3; margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: #93a0b3; padding: 60rpx 0; }
.card { background: #fff; border: 2rpx solid #eaeef4; border-radius: 20rpx; padding: 24rpx; margin-bottom: 16rpx; }
.batch { display: flex; align-items: center; box-shadow: 0 4rpx 20rpx rgba(45, 80, 150, .05); }
.batch-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6rpx; }
.batch-title { font-size: 30rpx; font-weight: 700; color: #1f2733; }
.batch-sub { font-size: 23rpx; color: #93a0b3; }
.batch-arrow { font-size: 30rpx; color: #3d8bf5; }
.wrap { margin-top: 6rpx; }
.block { margin-bottom: 8rpx; }

/* 原文:吸顶常驻 */
.passage { position: sticky; top: 0; z-index: 5; background: #fff; border: 2rpx solid #e3e9f2; border-radius: 18rpx; padding: 20rpx 22rpx; margin-bottom: 16rpx; box-shadow: 0 6rpx 22rpx rgba(45, 80, 150, .08); }
.passage-head { display: flex; align-items: center; justify-content: space-between; }
.passage-brand { display: flex; align-items: center; gap: 10rpx; }
.ic-book { width: 30rpx; height: 30rpx; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='%233d8bf5' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M4 19.5A2.5 2.5 0 0 1 6.5 17H20'/%3E%3Cpath d='M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z'/%3E%3C/svg%3E"); background-size: contain; background-repeat: no-repeat; }
.passage-title { font-size: 24rpx; font-weight: 700; color: #3d8bf5; letter-spacing: .5rpx; }
.passage-toggle { font-size: 22rpx; color: #93a0b3; }
.passage-text { display: block; font-size: 26rpx; color: #3a4353; line-height: 1.8; margin-top: 14rpx; max-height: 40vh; overflow-y: auto; white-space: pre-wrap; }
.ev-hl { background: #e4eeff; color: #1f4c8f; border-radius: 4rpx; padding: 0 2rpx; box-shadow: inset 0 -4rpx 0 #7ca9f5; }

/* 本地生词 · 长难句 */
.study-tools { display: flex; gap: 12rpx; margin: 2rpx 0 12rpx; }
.tool-chip { font-size: 22rpx; color: #3d8bf5; border: 2rpx solid #3d8bf5; border-radius: 999rpx; padding: 6rpx 22rpx; }
.tool-chip.on { background: #3d8bf5; color: #fff; }
.sec-t { display: block; font-size: 24rpx; font-weight: 700; color: #46506a; margin-bottom: 6rpx; }
.sec-sub { display: block; font-size: 21rpx; color: #93a0b3; margin-bottom: 16rpx; line-height: 1.5; }
.ls-row { display: flex; align-items: center; gap: 14rpx; padding: 14rpx 0; border-top: 2rpx solid #eef1f5; }
.ls-row:first-of-type { border-top: none; }
.ls-text { flex: 1; min-width: 0; font-size: 25rpx; line-height: 1.6; color: #1f2733; }
.ls-go { flex-shrink: 0; font-size: 22rpx; color: #3d8bf5; }

/* 讲义卡片 */
.q-card { background: #fff; border: 2rpx solid #eaeef4; border-radius: 18rpx; padding: 22rpx; margin-bottom: 16rpx; box-shadow: 0 4rpx 18rpx rgba(45, 80, 150, .05); }
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
.q-ans { margin-top: 14rpx; display: flex; flex-wrap: wrap; gap: 10rpx; }
.ans-chip { font-size: 23rpx; border-radius: 10rpx; padding: 6rpx 16rpx; }
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
</style>

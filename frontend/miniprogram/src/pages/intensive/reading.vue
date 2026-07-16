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
            <view v-if="bk.passage" class="card passage" @tap="toggle(bi)">
              <view class="passage-head">
                <text class="passage-title">短文{{ bk.block_label }}</text>
                <text class="passage-toggle">{{ collapsed[bi] ? '展开 ▾' : '收起 ▴' }}</text>
              </view>
              <text v-if="!collapsed[bi]" class="passage-text">{{ bk.passage }}</text>
            </view>
            <view v-for="(q, qi) in bk.questions" :key="qi" class="card q-card" :class="{ wrong: q.is_wrong }">
              <view class="q-head">
                <text class="q-no">{{ q.no ? `第 ${q.no} 题` : '题目' }}</text>
                <text class="q-type">{{ q.type || '题目' }}</text>
                <text v-if="q.is_wrong" class="q-flag">错</text>
              </view>
              <text class="q-stem">{{ q.stem || '（题干为空）' }}</text>
              <view class="q-ans">
                <text class="ans-line" :class="{ 'ans-x': q.is_wrong }">你的答案：{{ q.student_answer || '（未识别）' }}</text>
                <text class="ans-line ans-ok">正确答案：{{ q.correct_answer || '（未提供）' }}</text>
              </view>
              <text v-if="q.explanation" class="q-exp">{{ q.explanation }}</text>

              <!-- 解题精讲 + 练同类 -->
              <view class="q-acts">
                <view class="q-act" :class="{ on: anaOpen[q.id] }" @tap="toggleAna(q)">
                  <text>{{ anaLoading[q.id] ? '解析中…' : (anaOpen[q.id] ? '收起解析' : '看解析') }}</text>
                </view>
                <view class="q-act q-act-sim" @tap="practice(q.id)">
                  <text>{{ pracLoading === q.id ? '出题中…' : '练同类' }}</text>
                </view>
              </view>

              <!-- 解析面板:题型 + 定位句 + 为何对 + 干扰项 -->
              <view v-if="anaOpen[q.id] && ana[q.id]" class="ana">
                <text v-if="ana[q.id].error" class="ana-err">{{ ana[q.id].error }}</text>
                <template v-else>
                  <view v-if="ana[q.id].skill || ana[q.id].rc_code" class="ana-row"><text class="ana-k">题型</text><text class="ana-v">{{ ana[q.id].skill || ana[q.id].rc_code }}</text></view>
                  <view v-if="ana[q.id].evidence" class="ana-ev"><text class="ana-k">① 回原文定位</text><text class="ana-quote">“{{ ana[q.id].evidence }}”</text></view>
                  <view v-if="ana[q.id].answer_reason" class="ana-row2"><text class="ana-k">② 为什么对</text><text class="ana-t">{{ ana[q.id].answer_reason }}</text></view>
                  <view v-if="hasDistractors(q.id)" class="ana-dis">
                    <text class="ana-k">③ 干扰项为什么错</text>
                    <view v-for="(d, key) in ana[q.id].distractors" :key="key" class="dis-row">
                      <text class="dis-key">{{ key }}</text>
                      <text class="dis-why">{{ d.why_wrong }}</text>
                    </view>
                  </view>
                  <view v-if="ana[q.id].skill_tip" class="ana-tip"><text class="ana-k tip-k">④ 解题技巧</text><text class="ana-t">{{ ana[q.id].skill_tip }}</text></view>
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
import { getReadingAnalysis, practiceForQuestion, recordPaperPractice, type ReadingAnalysis, type SimilarQuestion } from '@/api/userPapers'
import PracticeQuiz from '@/components/PracticeQuiz.vue'

const batches = ref<IntensiveBatch[]>([])
const loading = ref(true)
const openId = ref('')
const blocks = ref<ReadingBlock[]>([])
const itemsLoading = ref(false)
const collapsed = ref<Record<number, boolean>>({})

function toggle(i: number) { collapsed.value = { ...collapsed.value, [i]: !collapsed.value[i] } }

// 解题精讲(缓存·懒加载)
const ana = ref<Record<string, ReadingAnalysis>>({})
const anaOpen = ref<Record<string, boolean>>({})
const anaLoading = ref<Record<string, boolean>>({})
function hasDistractors(id: string): boolean {
  const d = ana.value[id]?.distractors
  return !!d && Object.keys(d).length > 0
}
async function toggleAna(q: any) {
  const open = !anaOpen.value[q.id]
  anaOpen.value = { ...anaOpen.value, [q.id]: open }
  if (open && !ana.value[q.id]) {
    anaLoading.value = { ...anaLoading.value, [q.id]: true }
    try { ana.value = { ...ana.value, [q.id]: await getReadingAnalysis(q.id) } }
    catch (e: any) { ana.value = { ...ana.value, [q.id]: { error: e?.message || '解析失败' } } }
    finally { anaLoading.value = { ...anaLoading.value, [q.id]: false } }
  }
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
    const r = await practiceForQuestion(qid)
    if (!r.questions.length) { uni.showToast({ title: '未生成题目', icon: 'none' }); return }
    pracKp.value = r.knowledge_point; pracList.value = r.questions; pracQid.value = qid; pracOpen.value = true
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
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 20rpx; }
.hd-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; display: block; line-height: 1.5; }
.tip { text-align: center; color: var(--c-text-hint); padding: 60rpx 0; }
.card { background: #fff; border-radius: 20rpx; padding: 24rpx; margin-bottom: 16rpx; }
.batch { display: flex; align-items: center; }
.batch-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6rpx; }
.batch-title { font-size: 30rpx; font-weight: 700; color: var(--c-ink); }
.batch-sub { font-size: 23rpx; color: var(--c-text-hint); }
.batch-arrow { font-size: 30rpx; color: var(--c-primary); }
.wrap { margin-top: 6rpx; }
.block { margin-bottom: 8rpx; }
.passage { background: var(--c-primary-faint); }
.passage-head { display: flex; align-items: center; justify-content: space-between; }
.passage-title { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep, var(--c-primary)); }
.passage-toggle { font-size: 22rpx; color: var(--c-primary); }
.passage-text { display: block; font-size: 26rpx; color: var(--c-text-body, var(--c-ink)); line-height: 1.7; margin-top: 14rpx; white-space: pre-wrap; }
.q-card.wrong { border: 2rpx solid #f5c2c7; }
.q-head { display: flex; align-items: center; gap: 12rpx; margin-bottom: 10rpx; }
.q-no { font-size: 24rpx; font-weight: 700; color: var(--c-ink); }
.q-type { font-size: 21rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 8rpx; padding: 2rpx 12rpx; }
.q-flag { font-size: 20rpx; color: #fff; background: #e5484d; border-radius: 6rpx; padding: 2rpx 10rpx; }
.q-stem { display: block; font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.q-ans { margin-top: 12rpx; display: flex; flex-direction: column; gap: 4rpx; }
.ans-line { font-size: 24rpx; color: var(--c-text-sub); }
.q-exp { display: block; font-size: 24rpx; color: var(--c-text-sub); line-height: 1.6; margin-top: 10rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 10rpx; padding: 12rpx 14rpx; }
.ans-x { color: #e5484d; }
.ans-ok { color: #128a4c; }
/* 单题动作 */
.q-acts { display: flex; gap: 12rpx; margin-top: 14rpx; }
.q-act { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 8rpx 24rpx; }
.q-act.on { background: var(--c-primary); color: #fff; }
.q-act-sim { color: var(--c-primary-deep, var(--c-primary)); background: var(--c-primary-faint); border-color: transparent; }
/* 解析面板 */
.ana { margin-top: 12rpx; background: #f6f8fb; border-radius: 14rpx; padding: 16rpx 18rpx; display: flex; flex-direction: column; gap: 12rpx; }
.ana-err { font-size: 24rpx; color: var(--c-text-hint); }
.ana-k { font-size: 22rpx; font-weight: 700; color: var(--c-primary-deep, var(--c-primary)); background: #e8f1ff; border-radius: 8rpx; padding: 2rpx 12rpx; align-self: flex-start; }
.ana-row { display: flex; align-items: center; gap: 12rpx; }
.ana-v { font-size: 24rpx; color: var(--c-ink); }
.ana-ev { display: flex; flex-direction: column; gap: 8rpx; }
.ana-quote { font-size: 25rpx; color: var(--c-ink); line-height: 1.6; border-left: 6rpx solid #3d8bf5; padding-left: 14rpx; background: #eef4fb; border-radius: 0 8rpx 8rpx 0; padding: 10rpx 14rpx; }
.ana-row2 { display: flex; flex-direction: column; gap: 8rpx; }
.ana-t { font-size: 24rpx; color: var(--c-text-body, var(--c-ink)); line-height: 1.6; }
.ana-dis { display: flex; flex-direction: column; gap: 8rpx; }
.dis-row { display: flex; gap: 12rpx; align-items: flex-start; }
.dis-key { flex-shrink: 0; width: 40rpx; height: 40rpx; border-radius: 50%; background: #fdecec; color: #c33; font-size: 22rpx; font-weight: 700; display: flex; align-items: center; justify-content: center; }
.dis-why { flex: 1; font-size: 23rpx; color: var(--c-text-second, var(--c-text-sub)); line-height: 1.55; }
.ana-tip { display: flex; flex-direction: column; gap: 8rpx; background: #fff8ec; border-radius: 10rpx; padding: 12rpx 14rpx; }
.tip-k { background: #ffe6bf; color: #92600d; }
</style>

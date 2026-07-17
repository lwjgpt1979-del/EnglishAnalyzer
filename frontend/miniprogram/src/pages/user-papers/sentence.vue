<template>
  <view class="page">
    <view class="card src-card">
      <text class="src-label">长难句</text>
      <text class="src-text">{{ text }}</text>
      <view class="src-add" :class="{ done: saved }" @tap="save">
        <text>{{ saved ? '已加入待学习' : '加入待学习' }}</text>
      </view>
    </view>

    <view v-if="loading" class="tip">解析中…</view>

    <template v-else-if="a">
      <view v-if="a.translation" class="card">
        <text class="sec-t">意思</text>
        <text class="trans">{{ a.translation }}</text>
        <text v-if="a.sentence_type" class="stype">{{ a.sentence_type }}</text>
      </view>

      <!-- 结构一览:先看句子骨架(主干 + 各修饰成分)-->
      <view v-if="a.segments && a.segments.length" class="card">
        <text class="sec-t">结构一览</text>
        <text class="sec-sub">先看句子骨架:主干 + 各修饰成分,读长句先抓主干。</text>
        <view v-for="(s, i) in a.segments" :key="'s'+i" class="tree-row" :class="{ sub: isSub(s.type) }">
          <view class="tree-bar" :style="{ background: s.color || 'var(--c-primary)' }"></view>
          <view class="tree-body">
            <text class="tree-type" :style="{ color: s.color || 'var(--c-primary)' }">{{ s.type }}</text>
            <text class="tree-text">{{ s.text }}</text>
          </view>
        </view>
        <view v-if="a.explanations && a.explanations.length" class="ref-hd" @tap="refOpen = !refOpen">
          <text class="ref-more">{{ refOpen ? '收起结构讲解 ▴' : '看结构讲解 ▾' }}</text>
        </view>
        <template v-if="refOpen">
          <view v-for="(e, i) in a.explanations" :key="'e'+i" class="expl">
            <text class="expl-idx">{{ e.idx }}</text>
            <text class="expl-text">{{ e.text }}</text>
          </view>
        </template>
      </view>

      <!-- 三 Tab:认成分 / 认语法 / 重点词 -->
      <view class="card">
        <view class="tabbar">
          <text class="tab-i" :class="{ on: tab === 'component' }" @tap="tab = 'component'">认成分</text>
          <text class="tab-i" :class="{ on: tab === 'grammar' }" @tap="tab = 'grammar'">认语法</text>
          <text class="tab-i" :class="{ on: tab === 'word' }" @tap="tab = 'word'">重点词</text>
        </view>

        <!-- 认成分 / 认语法:提问式选择(答对答错都能看讲解)-->
        <template v-if="tab !== 'word'">
          <text class="sec-sub">选一下,答对答错都能看讲解;历史正确率累计。</text>
          <view v-if="!curQuiz.length" class="tip sm">暂无{{ tab === 'component' ? '成分' : '语法点' }}题</view>
          <view v-for="x in curQuiz" :key="x.i" class="quiz">
            <view class="q-stem-row">
              <text class="q-tag" :class="x.q.kind">{{ x.q.tag }}</text>
              <text class="q-stem">{{ x.q.clause || text }}</text>
              <text v-if="x.q.answered_before && picked[x.i] == null" class="q-done">已练 {{ x.q.stat_correct }}/{{ x.q.stat_total }}</text>
            </view>
            <text class="q-ask">{{ x.q.question }}</text>
            <view class="q-opts">
              <view v-for="(o, oi) in x.q.options" :key="oi" class="q-opt"
                :class="optClass(x.i, oi)" @tap="pick(x.i, oi)">
                <text>{{ o }}</text>
              </view>
            </view>
            <view v-if="picked[x.i] != null" class="q-feed-wrap">
              <view class="q-feed">
                <text class="q-res" :class="{ ok: picked[x.i] === x.q.answer }">
                  {{ picked[x.i] === x.q.answer ? '✓ 答对了' : '✗ 答错了' }}
                </text>
                <view v-if="x.q.node_id" class="q-view" :class="{ done: grammarAdded.has(x.q.node_id) }" @tap="viewGrammar(x.q)">
                  <text>{{ grammarAdded.has(x.q.node_id) ? '已加入 · 看讲解 →' : '查看讲解 →' }}</text>
                </view>
              </view>
              <text class="q-ans">正确答案：{{ x.q.options[x.q.answer] }}</text>
              <text v-if="x.q.explanation" class="q-exp">{{ x.q.explanation }}</text>
              <text v-if="x.q.stat_total" class="q-rate">历史正确率 {{ rate(x.q) }}%（{{ x.q.stat_correct }}/{{ x.q.stat_total }}）</text>
            </view>
          </view>
        </template>

        <!-- 重点词:复用 KeyWordsList(点词看卡片/加入)-->
        <template v-else>
          <view v-if="!words.length" class="tip sm">本句暂无重点词</view>
          <KeyWordsList v-else :words="words" :paper-id="paperId" title="重点词汇" />
        </template>
      </view>
    </template>

    <view v-else class="tip">解析失败,返回重试</view>
  </view>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  savePaperSentence,
  getSentenceStudyAids, addGrammarTarget, recordGrammarAnswer,
  type GrammarQuizItem, type StudyWord,
} from '@/api/userPapers'
import KeyWordsList from '@/components/KeyWordsList.vue'

const text = ref('')
const a = ref<any>(null)
const loading = ref(true)
const saved = ref(false)
const paperId = ref('')
const refOpen = ref(false)

const quiz = ref<GrammarQuizItem[]>([])
const words = ref<StudyWord[]>([])
const picked = ref<Record<number, number | null>>({})
const grammarAdded = ref<Set<string>>(new Set())

function rate(q: GrammarQuizItem) { return q.stat_total ? Math.round(q.stat_correct / q.stat_total * 100) : 0 }

// F+B 三 tab:认成分 / 认语法 / 重点词;quiz 按 kind 拆两 tab,保留原 index 供判分/正确率
const tab = ref<'component' | 'grammar' | 'word'>('component')
const compQuiz = computed(() => quiz.value.map((q, i) => ({ q, i })).filter(x => x.q.kind === 'component'))
const gramQuiz = computed(() => quiz.value.map((q, i) => ({ q, i })).filter(x => x.q.kind === 'grammar'))
const curQuiz = computed(() => (tab.value === 'component' ? compQuiz.value : gramQuiz.value))
function isSub(type: string): boolean { return /从句|状语|定语|插入|补语|同位|不定式|分词|介词|表语/.test(type || '') }

async function pick(qi: number, oi: number) {
  if (picked.value[qi] != null) return   // 已答不改
  picked.value = { ...picked.value, [qi]: oi }
  const q = quiz.value[qi]
  const ok = oi === q.answer
  try {   // 记录作答 → 累计正确率(以往至今)
    const st = await recordGrammarAnswer(q.gp_key, q.options[q.answer], ok, q.node_id)
    q.stat_correct = st.correct; q.stat_total = st.total
  } catch { /* 记录失败不影响答题 */ }
}
function optClass(qi: number, oi: number) {
  const p = picked.value[qi]
  if (p == null) return ''
  const ans = quiz.value[qi].answer
  if (oi === ans) return 'right'
  if (oi === p) return 'wrong'
  return 'dim'
}

async function viewGrammar(q: GrammarQuizItem) {
  if (!q.node_id) return
  // 答对答错都能看讲解:加入作业精讲·语法(按卷归组)+ 跳讲解页(无讲解会即时生成)
  if (!grammarAdded.value.has(q.node_id)) {
    try {
      await addGrammarTarget(q.node_id, paperId.value || undefined)
      grammarAdded.value = new Set([...grammarAdded.value, q.node_id])
    } catch { /* 加入失败不挡看讲解 */ }
  }
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${q.node_id}&name=${encodeURIComponent(q.node_name || '')}&cat=grammar` })
}

async function save() {
  if (saved.value || !text.value) return
  try {
    await savePaperSentence(text.value, paperId.value || undefined)
    saved.value = true
    uni.showToast({ title: '已加入作业精讲·长难句', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

onLoad(async (q: any) => {
  text.value = decodeURIComponent(q.text || '')
  paperId.value = q.paperId || ''
  if (!text.value) { loading.value = false; return }
  try {
    // 一次请求全给(解析 + 选择题 + 词 + 各项已加入/已练回显),避免二次解析、更快更稳
    const aids = await getSentenceStudyAids(text.value, paperId.value || undefined)
    a.value = aids.analysis
    quiz.value = aids.grammar_quiz || []
    words.value = aids.words || []
    saved.value = aids.sentence_added                                      // 已加入待学习回显
    grammarAdded.value = new Set(quiz.value.filter(x => x.grammar_added && x.node_id).map(x => x.node_id as string))
  } catch { /* 解析失败:a 为空,页面提示重试 */ }
  finally { loading.value = false }
})
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx 24rpx 60rpx; box-sizing: border-box; }
.card { background: #fff; border-radius: 20rpx; padding: 26rpx 24rpx; margin-bottom: 20rpx; }
.tip { text-align: center; color: var(--c-text-hint); padding: 60rpx 0; }
.src-card { display: flex; flex-direction: column; gap: 14rpx; }
.src-label { font-size: 22rpx; color: var(--c-primary); }
.src-text { font-size: 30rpx; line-height: 1.7; color: var(--c-ink); }
.src-add { align-self: flex-start; font-size: 24rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 8rpx 28rpx; }
.src-add.done { color: #2ecc71; border-color: #2ecc71; }
.sec-t { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-text-second); margin-bottom: 6rpx; }
.sec-sub { display: block; font-size: 21rpx; color: var(--c-text-hint); margin-bottom: 16rpx; line-height: 1.5; }
.trans { font-size: 28rpx; line-height: 1.7; color: var(--c-ink); }
.stype { display: inline-block; margin-top: 12rpx; font-size: 22rpx; color: var(--c-primary); background: var(--c-primary-faint); border-radius: 8rpx; padding: 4rpx 16rpx; }

/* 语法选择题 */
.quiz { padding: 16rpx 0; border-top: 2rpx solid var(--c-line, #eef1f5); }
.quiz:first-of-type { border-top: none; }
.q-group { font-size: 24rpx; font-weight: 800; color: var(--c-primary); margin: 6rpx 0 12rpx; }
.q-stem-row { display: flex; align-items: flex-start; gap: 10rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 12rpx; padding: 14rpx 16rpx; }
.q-tag { flex-shrink: 0; font-size: 19rpx; color: #fff; background: var(--c-primary); border-radius: 6rpx; padding: 3rpx 10rpx; margin-top: 4rpx; }
.q-tag.component { background: #12a150; }
.q-done { flex-shrink: 0; font-size: 19rpx; color: #ff8a3d; margin-top: 4rpx; }
.q-stem { flex: 1; font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.q-ask { display: block; font-size: 23rpx; color: var(--c-text-sub); margin: 14rpx 0 10rpx; }
.q-opts { display: flex; flex-direction: column; gap: 12rpx; }
.q-opt { font-size: 25rpx; color: var(--c-ink); border: 2rpx solid var(--c-line, #e6eaf0); border-radius: 12rpx; padding: 14rpx 18rpx; }
.q-opt.right { color: #12a150; border-color: #12a150; background: rgba(46,204,113,.08); }
.q-opt.wrong { color: #e5484d; border-color: #e5484d; background: rgba(229,72,77,.08); }
.q-opt.dim { color: var(--c-text-hint); }
.q-feed-wrap { margin-top: 14rpx; }
.q-feed { display: flex; align-items: center; justify-content: space-between; }
.q-res { font-size: 23rpx; color: #e5484d; }
.q-res.ok { color: #12a150; }
.q-view { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.q-view.done { color: #2ecc71; border-color: #2ecc71; }
.q-ans { display: block; font-size: 24rpx; font-weight: 600; color: var(--c-ink); margin-top: 12rpx; }
.q-exp { display: block; font-size: 23rpx; color: var(--c-text-sub); line-height: 1.6; margin-top: 6rpx; }

/* 正确率汇总 */
.sm-row { display: flex; align-items: center; gap: 14rpx; padding: 12rpx 0; border-top: 2rpx solid var(--c-line, #eef1f5); }
.sm-row:first-of-type { border-top: none; }
.sm-tag { flex-shrink: 0; font-size: 18rpx; color: #fff; background: var(--c-primary); border-radius: 5rpx; padding: 2rpx 8rpx; }
.sm-tag.component { background: #12a150; }
.sm-name { flex: 1; min-width: 0; font-size: 24rpx; color: var(--c-ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sm-bar { width: 140rpx; height: 12rpx; background: #eef1f5; border-radius: 999rpx; overflow: hidden; flex-shrink: 0; }
.sm-fill { height: 100%; background: var(--c-primary); border-radius: 999rpx; }
.sm-rate { font-size: 23rpx; font-weight: 700; color: var(--c-primary); width: 72rpx; text-align: right; flex-shrink: 0; }
.sm-cnt { font-size: 21rpx; color: var(--c-text-hint); width: 70rpx; text-align: right; flex-shrink: 0; }

/* 重点词 */
.kw-list { display: flex; flex-direction: column; gap: 12rpx; }
.kw-row { display: flex; align-items: center; gap: 16rpx; padding: 12rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 14rpx; }
.kw-img { width: 84rpx; height: 84rpx; border-radius: 10rpx; flex-shrink: 0; background: #eef1f5; }
.kw-gen { display: flex; align-items: center; justify-content: center; background: var(--c-primary-faint, #eaf2ff); }
.kw-gen-t { font-size: 19rpx; color: var(--c-primary); }
.kw-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.kw-w { font-size: 27rpx; font-weight: 700; color: var(--c-primary); }
.kw-def { font-size: 23rpx; color: var(--c-text-sub); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-add { flex-shrink: 0; font-size: 22rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.kw-add.done { color: #2ecc71; border-color: #2ecc71; }

/* 结构参考 */
.ref-hd { display: flex; align-items: center; justify-content: space-between; }
.ref-caret { font-size: 22rpx; color: var(--c-text-hint); }
.seg { display: flex; align-items: baseline; gap: 14rpx; padding: 14rpx 16rpx; border-radius: 12rpx; margin-top: 10rpx; }
.seg-type { flex-shrink: 0; font-size: 22rpx; font-weight: 700; }
.seg-text { font-size: 26rpx; line-height: 1.5; color: var(--c-ink); }
.expl { display: flex; gap: 12rpx; padding: 8rpx 0; }
.expl-idx { flex-shrink: 0; width: 34rpx; height: 34rpx; text-align: center; line-height: 34rpx; font-size: 20rpx; color: #fff; background: var(--c-primary); border-radius: 50%; }
.expl-text { flex: 1; font-size: 25rpx; line-height: 1.6; color: var(--c-text-sub); }

/* 结构一览:层级缩进(修饰成分缩进 + 左色条)*/
.tree-row { display: flex; gap: 14rpx; padding: 12rpx 0; }
.tree-row.sub { padding-left: 40rpx; }
.tree-bar { width: 6rpx; border-radius: 3rpx; flex: none; align-self: stretch; }
.tree-body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.tree-type { font-size: 21rpx; font-weight: 700; }
.tree-text { font-size: 26rpx; line-height: 1.6; color: var(--c-ink); }
.ref-more { display: inline-block; margin-top: 10rpx; font-size: 22rpx; color: var(--c-primary); }

/* 三 Tab */
.tabbar { display: flex; gap: 10rpx; background: #eef2f7; border-radius: 16rpx; padding: 6rpx; margin-bottom: 16rpx; }
.tab-i { flex: 1; text-align: center; font-size: 26rpx; color: #6b7688; padding: 14rpx 0; border-radius: 12rpx; }
.tab-i.on { color: var(--c-primary); font-weight: 700; background: #fff; box-shadow: 0 3rpx 10rpx rgba(45, 80, 150, .12); }
.tip.sm { padding: 40rpx 0; font-size: 24rpx; }
.q-rate { display: block; font-size: 21rpx; color: var(--c-text-hint); margin-top: 8rpx; }

/* 单词卡片弹窗 */
.card-mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; }
.cp-img { width: 100%; height: 300rpx; border-radius: 16rpx; background: #eef1f5; }
.cp-head { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; }
.cp-word { font-size: 40rpx; font-weight: 800; color: var(--c-ink); }
.cp-play { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.cp-play.on { color: #2ecc71; border-color: #2ecc71; }
.cp-ph { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.cp-def { display: block; font-size: 27rpx; color: var(--c-ink); margin-top: 14rpx; line-height: 1.6; }
.cp-en { display: block; font-size: 24rpx; color: var(--c-text-sub); margin-top: 12rpx; line-height: 1.6; }
.cp-ex { margin-top: 14rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 12rpx; padding: 14rpx 16rpx; }
.cp-ex-en { display: block; font-size: 25rpx; color: var(--c-ink); line-height: 1.5; }
.cp-ex-zh { display: block; font-size: 23rpx; color: var(--c-text-sub); margin-top: 4rpx; }
.cp-add { margin-top: 20rpx; text-align: center; font-size: 26rpx; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 16rpx; }
.cp-add.done { background: #2ecc71; }
</style>

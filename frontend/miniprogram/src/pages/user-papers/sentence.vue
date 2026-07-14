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

      <!-- 语法结构 · 提问式选择 -->
      <view v-if="quiz.length" class="card">
        <text class="sec-t">语法结构 · 选一选</text>
        <text class="sec-sub">句子结构拆分就是语法。选一下，答对答错都能点进讲解。</text>
        <view v-for="(q, qi) in quiz" :key="qi" class="quiz">
          <text class="q-stem">{{ q.clause || text }}</text>
          <text class="q-ask">这属于哪种语法结构？</text>
          <view class="q-opts">
            <view v-for="(o, oi) in q.options" :key="oi" class="q-opt"
              :class="optClass(qi, oi)" @tap="pick(qi, oi)">
              <text>{{ o }}</text>
            </view>
          </view>
          <view v-if="picked[qi] != null" class="q-feed">
            <text class="q-res" :class="{ ok: picked[qi] === q.answer }">
              {{ picked[qi] === q.answer ? '✓ 答对了' : '✗ 正确答案：' + q.options[q.answer] }}
            </text>
            <view class="q-view" :class="{ done: grammarAdded.has(q.node_id) }" @tap="viewGrammar(q)">
              <text>{{ grammarAdded.has(q.node_id) ? '已加入 · 看讲解 →' : '查看讲解 →' }}</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 重点词汇:点词看卡片 / 加入作业精讲 -->
      <view v-if="words.length" class="card">
        <text class="sec-t">重点词汇</text>
        <text class="sec-sub">点单词看卡片；「加入」进作业精讲·单词。</text>
        <view class="kw-list">
          <view v-for="(w, wi) in words" :key="wi" class="kw-row" @tap="openCard(w)">
            <image v-if="w.image_url" :src="w.image_url" class="kw-img" mode="aspectFill" />
            <view class="kw-main">
              <text class="kw-w">{{ w.word }}</text>
              <text class="kw-def">{{ defText(w.definitions) }}</text>
            </view>
            <view v-if="w.in_vocab" class="kw-add" :class="{ done: wordAdded.has(w.word_id) }"
              @tap.stop="addWord(w)">
              <text>{{ wordAdded.has(w.word_id) ? '已加入' : '加入' }}</text>
            </view>
          </view>
        </view>
      </view>

      <!-- 结构参考(可折叠) -->
      <view v-if="(a.segments && a.segments.length) || (a.explanations && a.explanations.length)" class="card">
        <view class="ref-hd" @tap="refOpen = !refOpen">
          <text class="sec-t" style="margin:0">结构拆分（参考）</text>
          <text class="ref-caret">{{ refOpen ? '收起' : '展开' }}</text>
        </view>
        <template v-if="refOpen">
          <view v-for="(s, i) in a.segments" :key="'s'+i" class="seg" :style="{ background: s.tint || 'var(--c-bg-soft)' }">
            <text class="seg-type" :style="{ color: s.color || 'var(--c-primary)' }">{{ s.type }}</text>
            <text class="seg-text">{{ s.text }}</text>
          </view>
          <view v-for="(e, i) in a.explanations" :key="'e'+i" class="expl">
            <text class="expl-idx">{{ e.idx }}</text>
            <text class="expl-text">{{ e.text }}</text>
          </view>
        </template>
      </view>
    </template>

    <view v-else class="tip">解析失败,返回重试</view>

    <!-- 单词卡片弹窗 -->
    <view v-if="cardWord" class="card-mask" @tap="cardWord = null">
      <view class="card-pop" @tap.stop>
        <image v-if="cardWord.image_url" :src="cardWord.image_url" class="cp-img" mode="aspectFill" />
        <view class="cp-head">
          <text class="cp-word">{{ cardWord.word }}</text>
          <view class="cp-play" :class="{ on: playingId === cardWord.word_id }" @tap="playWord(cardWord)">
            <text>{{ playingId === cardWord.word_id ? '♪ 播放中' : '🔊 发音' }}</text>
          </view>
        </view>
        <text v-if="cardWord.phonetic" class="cp-ph">/{{ cardWord.phonetic }}/</text>
        <text class="cp-def">{{ defText(cardWord.definitions) }}</text>
        <text v-if="cardWord.en_description" class="cp-en">{{ cardWord.en_description }}</text>
        <view v-if="cardWord.example && cardWord.example.en" class="cp-ex">
          <text class="cp-ex-en">{{ cardWord.example.en }}</text>
          <text v-if="cardWord.example.zh" class="cp-ex-zh">{{ cardWord.example.zh }}</text>
        </view>
        <view v-if="cardWord.in_vocab" class="cp-add" :class="{ done: wordAdded.has(cardWord.word_id) }" @tap="addWord(cardWord)">
          <text>{{ wordAdded.has(cardWord.word_id) ? '已加入作业精讲' : '加入作业精讲·单词' }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import {
  analyzePaperSentence, savePaperSentence,
  getSentenceStudyAids, addGrammarTarget,
  type GrammarQuizItem, type StudyWord,
} from '@/api/userPapers'
import { addHomeworkWords } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'

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
const wordAdded = ref<Set<string>>(new Set())
const cardWord = ref<StudyWord | null>(null)

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

function pick(qi: number, oi: number) {
  if (picked.value[qi] != null) return   // 已答不改
  picked.value = { ...picked.value, [qi]: oi }
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
  // 答对答错都能看讲解:加入作业精讲·语法(按卷归组)+ 跳讲解页(无讲解会即时生成)
  if (!grammarAdded.value.has(q.node_id)) {
    try {
      await addGrammarTarget(q.node_id, paperId.value || undefined)
      grammarAdded.value = new Set([...grammarAdded.value, q.node_id])
    } catch { /* 加入失败不挡看讲解 */ }
  }
  uni.navigateTo({ url: `/pages/curriculum/kp-content?id=${q.node_id}&name=${encodeURIComponent(q.node_name)}&cat=grammar` })
}

async function addWord(w: StudyWord) {
  if (!w.word_id || wordAdded.value.has(w.word_id)) return
  if (!paperId.value) { uni.showToast({ title: '请从作业里进入以归入批次', icon: 'none' }); return }
  try {
    await addHomeworkWords([w.word_id], paperId.value)
    wordAdded.value = new Set([...wordAdded.value, w.word_id])
    uni.showToast({ title: '已加入作业精讲·单词', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

function openCard(w: StudyWord) { cardWord.value = w }

const playingId = ref('')
let _audio: UniApp.InnerAudioContext | null = null
async function playWord(w: StudyWord) {
  if (!w.word) return
  try {
    const url = w.word_audio_url || (await resolveSpeakUrl(w.word))
    if (_audio) { _audio.stop(); _audio.destroy() }
    _audio = uni.createInnerAudioContext()
    _audio.src = url
    playingId.value = w.word_id || w.word
    _audio.onEnded(() => { playingId.value = '' })
    _audio.onError(() => { playingId.value = ''; uni.showToast({ title: '发音播放失败', icon: 'none' }) })
    _audio.play()
  } catch { playingId.value = ''; uni.showToast({ title: '发音获取失败', icon: 'none' }) }
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
  saved.value = q.saved === '1'
  paperId.value = q.paperId || ''
  if (!text.value) { loading.value = false; return }
  try {
    a.value = await analyzePaperSentence(text.value)
    const aids = await getSentenceStudyAids(text.value)
    quiz.value = aids.grammar_quiz || []
    words.value = aids.words || []
  } catch { /* ignore */ }
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
.q-stem { display: block; font-size: 26rpx; line-height: 1.6; color: var(--c-ink); background: var(--c-bg-soft, #f6f8fb); border-radius: 12rpx; padding: 14rpx 16rpx; }
.q-ask { display: block; font-size: 23rpx; color: var(--c-text-sub); margin: 14rpx 0 10rpx; }
.q-opts { display: flex; flex-direction: column; gap: 12rpx; }
.q-opt { font-size: 25rpx; color: var(--c-ink); border: 2rpx solid var(--c-line, #e6eaf0); border-radius: 12rpx; padding: 14rpx 18rpx; }
.q-opt.right { color: #12a150; border-color: #12a150; background: rgba(46,204,113,.08); }
.q-opt.wrong { color: #e5484d; border-color: #e5484d; background: rgba(229,72,77,.08); }
.q-opt.dim { color: var(--c-text-hint); }
.q-feed { display: flex; align-items: center; justify-content: space-between; margin-top: 14rpx; }
.q-res { font-size: 23rpx; color: #e5484d; }
.q-res.ok { color: #12a150; }
.q-view { font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.q-view.done { color: #2ecc71; border-color: #2ecc71; }

/* 重点词 */
.kw-list { display: flex; flex-direction: column; gap: 12rpx; }
.kw-row { display: flex; align-items: center; gap: 16rpx; padding: 12rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 14rpx; }
.kw-img { width: 84rpx; height: 84rpx; border-radius: 10rpx; flex-shrink: 0; background: #eef1f5; }
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

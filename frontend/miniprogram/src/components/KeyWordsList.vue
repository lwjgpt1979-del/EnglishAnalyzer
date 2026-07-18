<template>
  <view v-if="words.length" class="card">
    <text class="sec-t">{{ title }}</text>
    <text class="sec-sub">点单词看卡片；「加入」进作业精讲·单词。</text>
    <view class="kw-list">
      <view v-for="(w, wi) in words" :key="wi" class="kw-row"
        @tap="w.pending_create ? learnMissing(w) : openCard(w)">
        <image v-if="w.image_url" :src="w.image_url" class="kw-img" mode="aspectFill" />
        <view v-else-if="genWords.has(w.word_id || '') || learningWord === w.word" class="kw-img kw-gen">
          <text class="kw-gen-t">{{ learningWord === w.word ? '收录中' : '生成中' }}</text>
        </view>
        <view class="kw-main">
          <text class="kw-w">{{ w.word }}</text>
          <text class="kw-def">{{ kwSub(w) }}</text>
        </view>
        <!-- 缺词占位:学这个词(触发有效性闸门→即时入库) -->
        <view v-if="w.pending_create" class="kw-add kw-new" @tap.stop="learnMissing(w)">
          <text>{{ learningWord === w.word ? '收录中…' : '学这个词' }}</text>
        </view>
        <view v-else-if="w.in_vocab" class="kw-add" :class="{ done: wordAdded.has(w.word_id || '') }"
          @tap.stop="addWord(w)">
          <text>{{ wordAdded.has(w.word_id || '') ? '已加入' : '加入' }}</text>
        </view>
      </view>
    </view>

    <!-- 单词卡片弹窗(noCard 时不渲染,交父级根层弹) -->
    <view v-if="!noCard && cardWord" class="card-mask" @tap="cardWord = null">
      <view class="card-pop" @tap.stop>
        <image v-if="cardWord.image_url" :src="cardWord.image_url" class="cp-img" mode="aspectFill" />
        <!-- P3 图不对/换一张:撤图重刷(全学生共享) -->
        <view v-if="cardWord.image_url && !genWords.has(cardWord.word_id || '')" class="cp-report"
              :class="{ busy: regenId === (cardWord.word_id || '') }" @tap.stop="reportImage(cardWord)">
          <view class="ic ic-refresh cp-report-ic"></view>
          <text>{{ regenId === (cardWord.word_id || '') ? '重新生成中…' : '图不对 · 换一张' }}</text>
        </view>
        <view class="cp-head">
          <text class="cp-word">{{ cardWord.word }}</text>
          <view class="cp-play" :class="{ on: playingId === (cardWord.word_id || cardWord.word) }" @tap="playWord(cardWord)">
            <view class="ic ic-volume cp-play-ic"></view>
            <text>{{ playingId === (cardWord.word_id || cardWord.word) ? '播放中' : '发音' }}</text>
          </view>
        </view>
        <text v-if="cardWord.phonetic" class="cp-ph">/{{ cardWord.phonetic }}/</text>
        <text class="cp-def">{{ defText(cardWord.definitions) }}</text>
        <text v-if="cardWord.en_description" class="cp-en">{{ cardWord.en_description }}</text>
        <view v-if="cardWord.example && cardWord.example.en" class="cp-ex">
          <text class="cp-ex-en">{{ cardWord.example.en }}</text>
          <text v-if="cardWord.example.zh" class="cp-ex-zh">{{ cardWord.example.zh }}</text>
        </view>
        <view v-if="cardWord.in_vocab" class="cp-add" :class="{ done: wordAdded.has(cardWord.word_id || '') }" @tap="addWord(cardWord)">
          <text>{{ wordAdded.has(cardWord.word_id || '') ? '已加入作业精讲' : '加入作业精讲·单词' }}</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { StudyWord } from '@/api/userPapers'
import { addHomeworkWords, ensureWordMedia, reportWordImage, ensureMissingWord } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'

const props = withDefaults(defineProps<{
  words: StudyWord[]
  paperId?: string
  title?: string
  noCard?: boolean          // true=不渲染内置卡片,只 emit('pick') 由父级在根层渲染(避免困在 scroll-view)
}>(), { title: '重点词汇', noCard: false })
const emit = defineEmits<{ (e: 'pick', word: StudyWord): void }>()

const cardWord = ref<StudyWord | null>(null)
const wordAdded = ref<Set<string>>(new Set())
const genWords = ref<Set<string>>(new Set())

// 已加入回显:随 words 变化重建(阅读精讲每篇短文各一份 words)
watch(() => props.words, (ws) => {
  wordAdded.value = new Set((ws || []).filter(x => x.word_added && x.word_id).map(x => x.word_id as string))
}, { immediate: true })

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

function openCard(w: StudyWord) {
  // C 查看即生成:在库但无图的词,点开即补媒体(触发点=消费点,不必等「加入」)
  if (!w.image_url && w.word_id) genWordMedia(w)
  if (props.noCard) { emit('pick', w); return }   // 交给父级在根层弹卡
  cardWord.value = w
}

// 列表行副标题:收录中 / 缺词占位 / 媒体生成中 / 释义
function kwSub(w: StudyWord): string {
  if (learningWord.value === w.word) return '收录中…'
  if (w.pending_create) return '词库暂无 · 点「学这个词」即时收录'
  if (genWords.value.has(w.word_id || '')) return '配图/发音生成中…'
  return defText(w.definitions)
}

// 缺词「查看即生成」:点开占位词 → 有效性闸门 → 通过即时入库,原地替换为真词卡;不通过提示人工收录
const learningWord = ref('')
async function learnMissing(w: StudyWord) {
  if (learningWord.value || !w.word) return
  learningWord.value = w.word
  try {
    const r = await ensureMissingWord(w.word, props.paperId)
    if (r.status === 'queued' || !r.word) {
      uni.showToast({ title: '该词已提交人工收录', icon: 'none' }); return
    }
    Object.assign(w, r.word, { pending_create: false })   // 原地变真词卡
    if (w.word_id && w.word_added) wordAdded.value = new Set([...wordAdded.value, w.word_id])
    uni.showToast({ title: r.status === 'created' ? '已收录,可以学啦' : '已加入', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '收录失败', icon: 'none' }) }
  finally { learningWord.value = '' }
}

async function addWord(w: StudyWord) {
  if (!w.word_id || wordAdded.value.has(w.word_id)) return
  if (!props.paperId) { uni.showToast({ title: '请从作业里进入以归入批次', icon: 'none' }); return }
  try {
    await addHomeworkWords([w.word_id], props.paperId)
    wordAdded.value = new Set([...wordAdded.value, w.word_id])
    uni.showToast({ title: '已加入作业精讲·单词', icon: 'none' })
    if (!w.image_url) genWordMedia(w)   // 无媒体 → 立即生成配图/发音/信息
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

// 无媒体的词即时生成媒体+信息,回来原地更新卡片
async function genWordMedia(w: StudyWord) {
  if (!w.word_id || genWords.value.has(w.word_id)) return
  genWords.value = new Set([...genWords.value, w.word_id])
  try {
    const m = await ensureWordMedia(w.word_id)
    w.image_url = m.image_url ?? null
    w.word_audio_url = m.word_audio_url ?? null
    w.en_description = m.en_description ?? null
    w.example = (m.example as any) ?? null
    if (m.definitions) w.definitions = m.definitions
  } catch { /* 生成失败静默,不影响已加入 */ }
  finally {
    const s = new Set(genWords.value); s.delete(w.word_id); genWords.value = s
  }
}

// P3 图不对/换一张:撤下当前图并按新管线重生成(全学生共享),原地更新卡片
const regenId = ref('')
async function reportImage(w: StudyWord) {
  if (!w.word_id || regenId.value) return
  regenId.value = w.word_id
  try {
    const m = await reportWordImage(w.word_id)
    const r = m.report
    if (r?.limited) { uni.showToast({ title: '今日反馈已达上限', icon: 'none' }); return }
    if (r && !r.regenerated) {   // ② 仅记票,图不动,等更多同学确认
      uni.showToast({ title: `已反馈,还需 ${Math.max(0, r.need - r.votes)} 人确认`, icon: 'none' }); return
    }
    w.image_url = m.image_url ?? null
    w.word_audio_url = m.word_audio_url ?? null
    w.en_description = m.en_description ?? null
    w.example = (m.example as any) ?? null
    if (m.definitions) w.definitions = m.definitions
    uni.showToast({ title: m.image_url ? '已换新图' : '暂无合适配图,已用词义卡', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '重刷失败', icon: 'none' }) }
  finally { regenId.value = '' }
}

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
</script>

<style scoped>
.card { background: #fff; border-radius: 20rpx; padding: 26rpx 24rpx; margin-bottom: 20rpx; }
.sec-t { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-text-second); margin-bottom: 6rpx; }
.sec-sub { display: block; font-size: 21rpx; color: var(--c-text-hint); margin-bottom: 16rpx; line-height: 1.5; }
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
.kw-add.kw-new { color: #ff8a3d; border-color: #ffd8bd; }
/* 单词卡片弹窗 */
.card-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 200; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; }
.cp-img { width: 100%; height: 300rpx; border-radius: 16rpx; background: #eef1f5; }
.cp-head { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; }
.cp-word { font-size: 40rpx; font-weight: 800; color: var(--c-ink); }
.cp-play { display: flex; align-items: center; gap: 8rpx; font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.cp-play.on { color: #2ecc71; border-color: #2ecc71; }
.cp-play-ic { width: 26rpx; height: 26rpx; }
/* P3 图不对/换一张 */
.cp-report { display: flex; align-items: center; justify-content: center; gap: 8rpx; margin-top: 12rpx; font-size: 22rpx; color: #93a0b3; }
.cp-report.busy { color: var(--c-primary); }
.cp-report-ic { width: 26rpx; height: 26rpx; opacity: .75; }
.cp-ph { display: block; font-size: 24rpx; color: var(--c-text-hint); margin-top: 8rpx; }
.cp-def { display: block; font-size: 27rpx; color: var(--c-ink); margin-top: 14rpx; line-height: 1.6; }
.cp-en { display: block; font-size: 24rpx; color: var(--c-text-sub); margin-top: 12rpx; line-height: 1.6; }
.cp-ex { margin-top: 14rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 12rpx; padding: 14rpx 16rpx; }
.cp-ex-en { display: block; font-size: 25rpx; color: var(--c-ink); line-height: 1.5; }
.cp-ex-zh { display: block; font-size: 23rpx; color: var(--c-text-sub); margin-top: 4rpx; }
.cp-add { margin-top: 20rpx; text-align: center; font-size: 26rpx; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 16rpx; }
.cp-add.done { background: #2ecc71; }
</style>

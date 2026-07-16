<template>
  <view v-if="words.length" class="card">
    <text class="sec-t">{{ title }}</text>
    <text class="sec-sub">点单词看卡片；「加入」进作业精讲·单词。</text>
    <view class="kw-list">
      <view v-for="(w, wi) in words" :key="wi" class="kw-row" @tap="openCard(w)">
        <image v-if="w.image_url" :src="w.image_url" class="kw-img" mode="aspectFill" />
        <view v-else-if="genWords.has(w.word_id || '')" class="kw-img kw-gen"><text class="kw-gen-t">生成中</text></view>
        <view class="kw-main">
          <text class="kw-w">{{ w.word }}</text>
          <text class="kw-def">{{ genWords.has(w.word_id || '') ? '配图/发音生成中…' : defText(w.definitions) }}</text>
        </view>
        <view v-if="w.in_vocab" class="kw-add" :class="{ done: wordAdded.has(w.word_id || '') }"
          @tap.stop="addWord(w)">
          <text>{{ wordAdded.has(w.word_id || '') ? '已加入' : '加入' }}</text>
        </view>
      </view>
    </view>

    <!-- 单词卡片弹窗 -->
    <view v-if="cardWord" class="card-mask" @tap="cardWord = null">
      <view class="card-pop" @tap.stop>
        <image v-if="cardWord.image_url" :src="cardWord.image_url" class="cp-img" mode="aspectFill" />
        <view class="cp-head">
          <text class="cp-word">{{ cardWord.word }}</text>
          <view class="cp-play" :class="{ on: playingId === (cardWord.word_id || cardWord.word) }" @tap="playWord(cardWord)">
            <text>{{ playingId === (cardWord.word_id || cardWord.word) ? '♪ 播放中' : '🔊 发音' }}</text>
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
import { addHomeworkWords, ensureWordMedia } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'

const props = withDefaults(defineProps<{
  words: StudyWord[]
  paperId?: string
  title?: string
}>(), { title: '重点词汇' })

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

function openCard(w: StudyWord) { cardWord.value = w }

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

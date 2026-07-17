<template>
  <view v-if="word" class="card-mask" @tap="emit('close')">
    <view class="card-pop" @tap.stop>
      <image v-if="word.image_url" :src="word.image_url" class="cp-img" mode="aspectFill" />
      <!-- P3 图不对/换一张:撤图重刷(全学生共享) -->
      <view v-if="word.image_url && !genning" class="cp-report" :class="{ busy: regen }" @tap.stop="reportImage">
        <view class="ic ic-refresh cp-report-ic"></view>
        <text>{{ regen ? '重新生成中…' : '图不对 · 换一张' }}</text>
      </view>
      <view class="cp-head">
        <text class="cp-word">{{ word.word }}</text>
        <view class="cp-play" :class="{ on: playing }" @tap="playWord">
          <view class="ic ic-volume cp-play-ic"></view>
          <text>{{ playing ? '播放中' : '发音' }}</text>
        </view>
      </view>
      <text v-if="word.phonetic" class="cp-ph">/{{ word.phonetic }}/</text>
      <text class="cp-def">{{ defText(word.definitions) }}</text>
      <text v-if="word.en_description" class="cp-en">{{ word.en_description }}</text>
      <view v-if="word.example && word.example.en" class="cp-ex">
        <text class="cp-ex-en">{{ word.example.en }}</text>
        <text v-if="word.example.zh" class="cp-ex-zh">{{ word.example.zh }}</text>
      </view>
      <view v-if="word.in_vocab" class="cp-add" :class="{ done: added }" @tap="addWord">
        <text>{{ added ? '已加入作业精讲' : '加入作业精讲·单词' }}</text>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { StudyWord } from '@/api/userPapers'
import { addHomeworkWords, ensureWordMedia, reportWordImage } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'

const props = defineProps<{ word: StudyWord | null; paperId?: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const added = ref(false)
const genning = ref(false)
const regen = ref(false)
const playing = ref(false)
watch(() => props.word, (w) => {
  added.value = !!(w && w.word_added)
  genning.value = false; regen.value = false; playing.value = false
}, { immediate: true })

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

async function addWord() {
  const w = props.word
  if (!w || !w.word_id || added.value) return
  if (!props.paperId) { uni.showToast({ title: '请从作业里进入以归入批次', icon: 'none' }); return }
  try {
    await addHomeworkWords([w.word_id], props.paperId)
    added.value = true
    ;(w as any).word_added = true
    uni.showToast({ title: '已加入作业精讲·单词', icon: 'none' })
    if (!w.image_url) genMedia()
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}
async function genMedia() {
  const w = props.word
  if (!w || !w.word_id || genning.value) return
  genning.value = true
  try {
    const m = await ensureWordMedia(w.word_id)
    w.image_url = m.image_url ?? null; w.word_audio_url = m.word_audio_url ?? null
    w.en_description = m.en_description ?? null; w.example = (m.example as any) ?? null
    if (m.definitions) w.definitions = m.definitions
  } catch { /* 生成失败静默 */ } finally { genning.value = false }
}
async function reportImage() {
  const w = props.word
  if (!w || !w.word_id || regen.value) return
  regen.value = true
  try {
    const m = await reportWordImage(w.word_id)
    const r = (m as any).report
    if (r?.limited) { uni.showToast({ title: '今日反馈已达上限', icon: 'none' }); return }
    if (r && !r.regenerated) { uni.showToast({ title: `已反馈,还需 ${Math.max(0, r.need - r.votes)} 人确认`, icon: 'none' }); return }
    w.image_url = m.image_url ?? null; w.word_audio_url = m.word_audio_url ?? null
    w.en_description = m.en_description ?? null; w.example = (m.example as any) ?? null
    if (m.definitions) w.definitions = m.definitions
    uni.showToast({ title: m.image_url ? '已换新图' : '暂无合适配图,已用词义卡', icon: 'none' })
  } catch (e: any) { uni.showToast({ title: e?.message || '重刷失败', icon: 'none' }) }
  finally { regen.value = false }
}
let _audio: UniApp.InnerAudioContext | null = null
async function playWord() {
  const w = props.word
  if (!w || !w.word) return
  try {
    const url = w.word_audio_url || (await resolveSpeakUrl(w.word))
    if (_audio) { _audio.stop(); _audio.destroy() }
    _audio = uni.createInnerAudioContext()
    _audio.src = url; playing.value = true
    _audio.onEnded(() => { playing.value = false })
    _audio.onError(() => { playing.value = false; uni.showToast({ title: '发音播放失败', icon: 'none' }) })
    _audio.play()
  } catch { playing.value = false; uni.showToast({ title: '发音获取失败', icon: 'none' }) }
}
</script>

<style scoped>
.card-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 300; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; }
.cp-img { width: 100%; height: 300rpx; border-radius: 16rpx; background: #eef1f5; }
.cp-head { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; }
.cp-word { font-size: 40rpx; font-weight: 800; color: var(--c-ink); }
.cp-play { display: flex; align-items: center; gap: 8rpx; font-size: 23rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.cp-play.on { color: #2ecc71; border-color: #2ecc71; }
.cp-play-ic { width: 26rpx; height: 26rpx; }
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

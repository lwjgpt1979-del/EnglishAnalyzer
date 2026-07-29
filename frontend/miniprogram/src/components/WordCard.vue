<template>
  <view v-if="word" class="card-mask" @tap="onMaskTap">
    <view class="card-pop" @tap.stop>
      <!-- 方案 B:卡顶设置齿轮 -->
      <view class="cp-gear" @tap.stop="setOpen = !setOpen">
        <view class="ic ic-settings cp-gear-ic"></view>
      </view>

      <image v-if="word.image_url" :src="word.image_url" class="cp-img" mode="aspectFill" />
      <view v-else-if="genning" class="cp-img cp-gen"><text>配图生成中…</text></view>
      <!-- P3 图不对/换一张:撤图重刷(全学生共享) -->
      <view v-if="word.image_url && !genning" class="cp-report" :class="{ busy: regen }" @tap.stop="reportImage">
        <view class="ic ic-refresh cp-report-ic"></view>
        <text>{{ regen ? '重新生成中…' : '图不对 · 换一张' }}</text>
      </view>
      <view class="cp-head">
        <text class="cp-word">{{ word.word }}</text>
        <view class="cp-play" :class="{ on: playing }" @tap="playWord('tap')">
          <view class="ic ic-volume cp-play-ic"></view>
          <text>{{ playing ? '播放中' : '发音' }}</text>
        </view>
      </view>
      <text v-if="word.phonetic" class="cp-ph">/{{ word.phonetic }}/</text>
      <text class="cp-def">{{ defText(word.definitions) }}</text>
      <text v-if="word.en_description" class="cp-en">{{ word.en_description }}</text>
      <view v-if="word.example && word.example.en" class="cp-ex" :class="{ speaking: playingEx }">
        <text class="cp-ex-en">{{ word.example.en }}</text>
        <text v-if="word.example.zh" class="cp-ex-zh">{{ word.example.zh }}</text>
      </view>
      <view v-if="word.in_vocab" class="cp-add" :class="{ done: added }" @tap="addWord">
        <text>{{ added ? '已加入作业精讲' : '加入作业精讲·单词' }}</text>
      </view>

      <!-- 播放设置底栏 -->
      <view v-if="setOpen" class="cp-sheet" @tap.stop>
        <view class="cp-sheet-hd">
          <text class="cp-sheet-t">播放设置</text>
          <view class="ic ic-close cp-sheet-x" @tap="setOpen = false"></view>
        </view>
        <view class="cp-row">
          <view class="cp-row-main">
            <text class="cp-row-t">例句连读</text>
            <text class="cp-row-s">点「发音」时：单词播完 → 接播例句</text>
          </view>
          <view class="cp-sw" :class="{ on: readSeq }" @tap="toggleSeq"></view>
        </view>
        <view class="cp-row">
          <view class="cp-row-main">
            <text class="cp-row-t">打开词卡自动播</text>
            <text class="cp-row-s">打开即执行一次「发音」（尊重例句连读）</text>
          </view>
          <view class="cp-sw" :class="{ on: autoPlay }" @tap="toggleAuto"></view>
        </view>
        <view class="cp-sheet-done" @tap="setOpen = false">完成</view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import type { StudyWord } from '@/api/userPapers'
import { addHomeworkWords, ensureWordMedia, reportWordImage } from '@/api/vocabulary'
import {
  playWordMedia, stopWordPlay,
  getReadSeq, setReadSeq, getCardAutoPlay, setCardAutoPlay,
} from '@/utils/wordPlay'

const props = defineProps<{ word: StudyWord | null; paperId?: string }>()
const emit = defineEmits<{ (e: 'close'): void }>()

const added = ref(false)
const genning = ref(false)
const regen = ref(false)
const playing = ref(false)
const playingEx = ref(false)
const setOpen = ref(false)
const readSeq = ref(getReadSeq())
const autoPlay = ref(getCardAutoPlay())

watch(() => props.word, (w) => {
  added.value = !!(w && w.word_added)
  genning.value = false; regen.value = false
  playing.value = false; playingEx.value = false
  setOpen.value = false
  readSeq.value = getReadSeq()
  autoPlay.value = getCardAutoPlay()
  stopWordPlay()
  if (w?.word) {
    // 查看即生成:无图且非 text_only → 补媒体
    if (w.word_id && !w.image_url && w.image_status !== 'text_only') genMedia()
    nextTick(() => { playWord('open') })
  }
}, { immediate: true })

/**
 * 遮罩点击:设置开着则先关设置,否则关词卡。
 */
function onMaskTap() {
  if (setOpen.value) { setOpen.value = false; return }
  stopWordPlay()
  emit('close')
}

function toggleSeq() {
  readSeq.value = !readSeq.value
  setReadSeq(readSeq.value)
}

function toggleAuto() {
  autoPlay.value = !autoPlay.value
  setCardAutoPlay(autoPlay.value)
}

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
  if (w.image_status === 'text_only') return
  genning.value = true
  try {
    const m = await ensureWordMedia(w.word_id)
    w.image_url = m.image_url ?? null
    w.image_status = m.image_status ?? w.image_status
    w.word_audio_url = m.word_audio_url ?? null
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

/**
 * @param mode tap=点发音;open=打开自动播闸门
 */
function playWord(mode: 'tap' | 'open' = 'tap') {
  const w = props.word
  if (!w?.word) return
  playWordMedia(
    { word: w.word, wordAudio: w.word_audio_url, example: w.example },
    {
      mode,
      onStart: () => { playing.value = true; playingEx.value = false },
      onSegment: (kind) => { playingEx.value = kind === 'example' },
      onEnd: () => { playing.value = false; playingEx.value = false },
      onError: () => { playing.value = false; playingEx.value = false },
    },
  )
}
</script>

<style scoped>
.card-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 300; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 28rpx; box-sizing: border-box; position: relative; }
.cp-gear {
  position: absolute; right: 20rpx; top: 20rpx; z-index: 2;
  width: 56rpx; height: 56rpx; border-radius: 14rpx;
  background: rgba(255,255,255,.92); border: 2rpx solid #e6ebf2;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 4rpx 12rpx rgba(45, 80, 150, .1);
}
.cp-gear-ic { width: 30rpx; height: 30rpx; }
.cp-img { width: 100%; height: 300rpx; border-radius: 16rpx; background: #eef1f5; }
.cp-gen { display: flex; align-items: center; justify-content: center; background: #eaf2ff; color: var(--c-primary); font-size: 24rpx; }
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
.cp-ex.speaking { outline: 3rpx solid #85B7EB; background: #eef5ff; }
.cp-ex-en { display: block; font-size: 25rpx; color: var(--c-ink); line-height: 1.5; }
.cp-ex-zh { display: block; font-size: 23rpx; color: var(--c-text-sub); margin-top: 4rpx; }
.cp-add { margin-top: 20rpx; text-align: center; font-size: 26rpx; color: #fff; background: var(--c-primary); border-radius: 999rpx; padding: 16rpx; }
.cp-add.done { background: #2ecc71; }

.cp-sheet {
  margin-top: 20rpx; background: #f8fafc; border: 2rpx solid #e6ebf2;
  border-radius: 16rpx; padding: 20rpx 22rpx;
}
.cp-sheet-hd { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8rpx; }
.cp-sheet-t { font-size: 28rpx; font-weight: 800; color: var(--c-ink); }
.cp-sheet-x { width: 32rpx; height: 32rpx; }
.cp-row { display: flex; align-items: center; justify-content: space-between; gap: 16rpx; padding: 12rpx 0; }
.cp-row-t { display: block; font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.cp-row-s { display: block; font-size: 20rpx; color: #93a0b3; margin-top: 4rpx; line-height: 1.4; }
.cp-sw {
  flex: none; width: 84rpx; height: 48rpx; border-radius: 999rpx; background: #d5dde8;
  position: relative; transition: background .2s;
}
.cp-sw::after {
  content: ''; position: absolute; top: 4rpx; left: 4rpx;
  width: 40rpx; height: 40rpx; border-radius: 50%; background: #fff;
  box-shadow: 0 2rpx 6rpx rgba(0,0,0,.15); transition: left .2s;
}
.cp-sw.on { background: var(--c-primary); }
.cp-sw.on::after { left: 40rpx; }
.cp-sheet-done {
  margin-top: 8rpx; text-align: center; font-size: 26rpx; font-weight: 800;
  color: var(--c-primary); padding: 12rpx;
}
</style>

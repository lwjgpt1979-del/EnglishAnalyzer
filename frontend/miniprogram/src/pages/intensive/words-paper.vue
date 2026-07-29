<template>
  <view class="page">
    <view v-if="loading" class="tip">加载中…</view>
    <PaperChecklist v-else :items="words" :date="sub" unit="词" flat
        @open="openCard" @start="startStudy">
      <template #item="{ item }">
        <view class="wrow">
          <image v-if="item.image_url" :src="item.image_url" class="w-img" mode="aspectFill" />
          <view v-else class="w-img w-img-ph"><view class="ic ic-image w-img-ic"></view></view>
          <view class="wrow-main">
            <view class="word-top"><text class="word-w">{{ item.word }}</text><text v-if="item.phonetic" class="word-ph">/{{ item.phonetic }}/</text></view>
            <text class="word-def">{{ defText(item.definitions) }}</text>
          </view>
          <view class="w-play" :class="{ on: playingId === item.word_id }" @tap.stop="playListWord(item)"><view class="ic ic-volume w-play-ic"></view></view>
        </view>
      </template>
      <template #empty>该{{ mode === 'homework' ? '批次' : '单元' }}没有单词</template>
    </PaperChecklist>

    <!-- U1:弹层统一 WordCard(齿轮/连读/自动播) -->
    <WordCard :word="sheetCard" :paper-id="paperIdForCard" @close="sheetCard = null" />
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { getHwWords, getCourseWords, type IntensiveWord } from '@/api/vocabulary'
import type { StudyWord } from '@/api/userPapers'
import PaperChecklist from '@/components/PaperChecklist.vue'
import WordCard from '@/components/WordCard.vue'
import { playWordMedia } from '@/utils/wordPlay'

const mode = ref('homework')
const groupId = ref('')
const sub = ref('')
const words = ref<IntensiveWord[]>([])
const loading = ref(true)
const sheetCard = ref<StudyWord | null>(null)
const playingId = ref('')

/** 作业精讲批次可带 paperId;课程单元不传 */
const paperIdForCard = computed(() => (mode.value === 'homework' ? groupId.value : undefined))

/**
 * 打开弹层:直接把清单行交给 WordCard(同一引用,ensure/换图回写列表)。
 * @param w 清单词
 */
function openCard(w: IntensiveWord) {
  sheetCard.value = w as unknown as StudyWord
}

/** 列表行喇叭:只播(尊重连读),不打开弹层 */
function playListWord(w: IntensiveWord) {
  if (!w.word) return
  playWordMedia(
    { word: w.word, wordAudio: w.word_audio_url, example: w.example },
    {
      mode: 'tap',
      onStart: () => { playingId.value = w.word_id },
      onEnd: () => { if (playingId.value === w.word_id) playingId.value = '' },
      onError: () => { if (playingId.value === w.word_id) playingId.value = '' },
    },
  )
}

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

function startStudy() {
  const src = mode.value === 'homework' ? 'homework' : 'course'
  const key = mode.value === 'homework' ? 'paper_id' : 'unit_id'
  uni.navigateTo({ url: `/pages/vocabulary/index?source=${src}&${key}=${groupId.value}` })
}

async function load() {
  loading.value = true
  words.value = []
  try {
    words.value = mode.value === 'homework'
      ? (await getHwWords(groupId.value)).words
      : (await getCourseWords(groupId.value)).words
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => {
  mode.value = q.mode || 'homework'
  groupId.value = q.id || ''
  sub.value = q.sub ? decodeURIComponent(q.sub) : ''
  if (q.title) uni.setNavigationBarTitle({ title: decodeURIComponent(q.title) })
  load()
})
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
.word-top { display: flex; align-items: baseline; gap: 16rpx; }
.word-w { font-size: 34rpx; font-weight: 700; color: var(--c-ink); }
.word-ph { font-size: 24rpx; color: var(--c-text-hint); }
.word-def { display: block; font-size: 26rpx; color: var(--c-text-sub); margin-top: 8rpx; line-height: 1.6; }
.wrow { display: flex; align-items: center; gap: 18rpx; }
.wrow-main { flex: 1; min-width: 0; }
.w-img { width: 104rpx; height: 104rpx; border-radius: 16rpx; flex-shrink: 0; background: var(--c-bg-page, #eef3fa); }
.w-img-ph { display: flex; align-items: center; justify-content: center; color: var(--c-text-hint); }
.w-img-ic { width: 40rpx; height: 40rpx; opacity: .55; }
.w-play {
  flex: none; width: 64rpx; height: 64rpx; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #e8f2ff; border: 2rpx solid #bcd8ff;
}
.w-play.on { background: #e9f6f1; border-color: #b7e0d0; }
.w-play-ic { width: 32rpx; height: 32rpx; }
</style>

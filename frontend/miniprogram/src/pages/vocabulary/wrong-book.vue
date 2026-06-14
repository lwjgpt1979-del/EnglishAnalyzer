<!-- src/pages/vocabulary/wrong-book.vue 词力通错词本 -->
<template>
  <view class="wb-page">
    <view v-if="loading" class="center-tip">加载中…</view>
    <view v-else-if="!items.length" class="center-tip">还没有错词，继续加油 🎉</view>
    <view v-else>
      <view class="wb-top">
        <text class="wb-hint">共 {{ items.length }} 个错词 · 错得多的在前</text>
        <view class="wb-filters">
          <text class="wb-chip" :class="{ on: filter === 'all' }" @tap="filter = 'all'">全部</text>
          <text class="wb-chip" :class="{ on: filter === 'unmastered' }" @tap="filter = 'unmastered'">未掌握</text>
        </view>
      </view>

      <button class="btn-primary wb-coach" @tap="goCoach">🎤 去口语陪练纠音</button>

      <view v-for="it in shown" :key="it.word_id" class="wb-item">
        <view class="wb-row">
          <image v-if="firstImg(it)" class="wb-img" :src="firstImg(it)!" mode="aspectFit" />
          <view v-else class="wb-img wb-img-empty"><text>📕</text></view>
          <view class="wb-info">
            <view class="wb-head">
              <text class="wb-word">{{ it.word }}</text>
              <text class="wb-badge">错 {{ it.wrong_count }} 次</text>
            </view>
            <text v-if="it.phonetic" class="wb-ph">/{{ cleanPhon(it.phonetic) }}/</text>
            <text class="wb-def">{{ defText(it) }}</text>
            <text class="wb-level" :class="it.level">{{ levelLabel(it.level) }}</text>
          </view>
        </view>
        <view v-if="firstEx(it)" class="wb-ex"><text class="wb-ex-en">{{ firstEx(it)!.en }}</text><text v-if="firstEx(it)!.zh" class="wb-ex-zh">{{ firstEx(it)!.zh }}</text></view>
        <view class="wb-btns">
          <text class="wb-btn" @tap="playWord(it)">🔊 发音</text>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { getWrongWords } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'
import { useAuthStore } from '@/stores/auth'
import type { VocabWrongItem } from '@/types/api'

const auth = useAuthStore()
const loading = ref(true)
const items = ref<VocabWrongItem[]>([])
const filter = ref<'all' | 'unmastered'>('all')

const shown = computed(() =>
  filter.value === 'unmastered' ? items.value.filter(i => i.level !== 'mastered') : items.value)

function defText(it: VocabWrongItem): string {
  const d = it.definitions
  if (Array.isArray(d)) return d.map((x: any) => `${x.pos ? x.pos + ' ' : ''}${x.meaning}`).join('；')
  return ''
}
function firstImg(it: VocabWrongItem): string | null {
  return it.image_urls && it.image_urls.length ? it.image_urls[0] : null
}
function firstEx(it: VocabWrongItem) {
  const e = it.examples
  if (Array.isArray(e) && e.length && e[0]?.en) return e[0]
  return null
}
function cleanPhon(p?: string | null): string {
  return (p || '').trim().replace(/^\/+|\/+$/g, '')
}
function levelLabel(lv: string): string {
  return lv === 'mastered' ? '已掌握' : lv === 'review' ? '待复习' : lv === 'learning' ? '在学' : '新学'
}

let _ctx: UniApp.InnerAudioContext | null = null
async function playWord(it: VocabWrongItem) {
  const url = it.word_audio_url || await resolveSpeakUrl(it.word)
  if (!url) return
  if (!_ctx) _ctx = uni.createInnerAudioContext()
  _ctx.src = url
  _ctx.play()
}
function goCoach() { uni.navigateTo({ url: '/pages/speaking/index' }) }

async function load() {
  if (!auth.isLoggedIn()) await auth.login()
  loading.value = true
  try {
    items.value = (await getWrongWords()).items
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  } finally {
    loading.value = false
  }
}
onMounted(load)
</script>

<style scoped>
.wb-page { padding: 24rpx; background: var(--c-bg-page); min-height: 100vh; }
.center-tip { text-align: center; padding: 160rpx 40rpx; color: var(--c-text-hint); line-height: 1.8; }
.wb-top { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.wb-hint { font-size: 24rpx; color: var(--c-text-hint); }
.wb-filters { display: flex; gap: 12rpx; }
.wb-chip { font-size: 24rpx; color: var(--c-text-second); background: var(--c-bg-card); border-radius: var(--r-pill); padding: 6rpx 22rpx; }
.wb-chip.on { color: #fff; background: var(--c-primary); font-weight: 700; }
.wb-coach { margin-bottom: 20rpx; }
.wb-item { background: var(--c-bg-card); border-radius: var(--r-lg); padding: 22rpx; margin-bottom: 18rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); }
.wb-row { display: flex; gap: 18rpx; }
.wb-img { width: 180rpx; height: 170rpx; border-radius: 12rpx; flex-shrink: 0; background: var(--c-bg-soft); }
.wb-img-empty { display: flex; align-items: center; justify-content: center; font-size: 56rpx; opacity: .5; }
.wb-info { flex: 1; display: flex; flex-direction: column; gap: 6rpx; min-width: 0; }
.wb-head { display: flex; align-items: center; gap: 12rpx; }
.wb-word { font-size: 40rpx; font-weight: 900; color: var(--c-ink); }
.wb-badge { font-size: 20rpx; font-weight: 700; color: #fff; background: #ff6b6b; border-radius: var(--r-pill); padding: 3rpx 14rpx; }
.wb-ph { font-size: 24rpx; color: var(--c-text-second); }
.wb-def { font-size: 26rpx; color: var(--c-text-body); }
.wb-level { font-size: 20rpx; align-self: flex-start; color: var(--c-text-hint); background: var(--c-bg-soft); border-radius: var(--r-pill); padding: 2rpx 14rpx; }
.wb-level.mastered { color: #1b7a3d; background: #d8f3dc; }
.wb-level.review { color: #b06a2a; background: #fff3e0; }
.wb-ex { margin-top: 14rpx; padding-top: 14rpx; border-top: 1rpx solid var(--c-bg-soft); display: flex; flex-direction: column; gap: 4rpx; }
.wb-ex-en { font-size: 26rpx; color: var(--c-text-body); }
.wb-ex-zh { font-size: 22rpx; color: var(--c-text-hint); }
.wb-btns { display: flex; gap: 16rpx; margin-top: 14rpx; }
.wb-btn { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 8rpx 26rpx; border-radius: var(--r-pill); }
</style>

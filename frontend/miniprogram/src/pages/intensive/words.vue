<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 单词</text>
      <text class="hd-sub">{{ groupOpen ? groupTitle : (mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元') }}</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>

    <!-- 一级:批次 / 单元 -->
    <template v-else-if="!groupOpen">
      <view v-if="!groups.length" class="tip">{{ mode === 'homework' ? '还没有加入待学习的单词——去上传的试卷里挑生词加入' : '未设教材或该教材暂无单元词' }}</view>
      <template v-for="sec in sections" :key="sec.key">
        <text v-if="sec.header" class="sec-h">{{ sec.header }}</text>
        <view v-for="g in sec.items" :key="g.id" class="card grp" @tap="openGroup(g)">
          <view class="grp-main">
            <text class="grp-title">{{ g.title }}</text>
            <text class="grp-sub">{{ g.sub }}</text>
          </view>
          <text class="grp-cnt">{{ g.count }} 词 ›</text>
        </view>
      </template>
    </template>

    <!-- 二级:词表 -->
    <template v-else>
      <view class="back" @tap="groupOpen = null"><text>‹ 返回{{ mode === 'homework' ? '批次' : '单元' }}</text></view>
      <view v-if="!wordsLoading && words.length" class="start-btn" @tap="startStudy">
        <text>▶ 开始学习(配图·发音·例句·检测)</text>
      </view>
      <view v-if="wordsLoading" class="tip">加载中…</view>
      <view v-else-if="!words.length" class="tip">该{{ mode === 'homework' ? '批次' : '单元' }}没有单词</view>
      <text v-else class="list-hint">共 {{ words.length }} 词 · 下方为词表预览,点上方按钮进入卡片学习</text>
      <view v-for="w in words" :key="w.word_id" class="card word-row" @tap="openCard(w)">
        <image v-if="w.image_url" :src="w.image_url" class="w-img" mode="aspectFill" />
        <view v-else class="w-img w-img-ph"><text>词</text></view>
        <view class="w-main">
          <view class="word-top">
            <text class="word-w">{{ w.word }}</text>
            <text v-if="w.phonetic" class="word-ph">/{{ w.phonetic }}/</text>
          </view>
          <text class="word-def">{{ defText(w.definitions) }}</text>
        </view>
        <view class="w-play" :class="{ on: playingId === w.word_id }" @tap.stop="playWord(w)">
          <text>{{ playingId === w.word_id ? '♪' : '🔊' }}</text>
        </view>
      </view>
    </template>

    <!-- 单词卡片弹层:点单个词展开 -->
    <view v-if="cardWord" class="card-mask" @tap="cardWord = null">
      <view class="card-pop" @tap.stop>
        <image v-if="cardWord.image_url" :src="cardWord.image_url" class="cp-img" mode="aspectFill" />
        <view v-else-if="genWords.has(cardWord.word_id)" class="cp-img cp-img-ph"><text>配图/发音生成中…</text></view>
        <view v-else class="cp-img cp-img-ph"><text>暂无配图</text></view>
        <view class="cp-head">
          <text class="cp-word">{{ cardWord.word }}</text>
          <view class="cp-play" :class="{ on: playingId === cardWord.word_id }" @tap="playWord(cardWord)">
            <text>{{ playingId === cardWord.word_id ? '♪ 播放中' : '🔊 发音' }}</text>
          </view>
        </view>
        <text v-if="cardWord.phonetic" class="cp-ph">/{{ cardWord.phonetic }}/</text>
        <text class="cp-def">{{ defText(cardWord.definitions) }}</text>
        <view v-if="cardWord.example && cardWord.example.en" class="cp-ex">
          <text class="cp-ex-en">{{ cardWord.example.en }}</text>
          <text v-if="cardWord.example.zh" class="cp-ex-zh">{{ cardWord.example.zh }}</text>
        </view>
        <text v-if="cardWord.en_description" class="cp-desc">{{ cardWord.en_description }}</text>
        <view class="cp-close" @tap="cardWord = null"><text>关闭</text></view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { onLoad } from '@dcloudio/uni-app'
import { getHwWordBatches, getHwWords, getCourseWordUnits, getCourseWords, ensureWordMedia,
         type IntensiveWord, type HwWordBatch, type CourseWordUnit } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'

const mode = ref('homework')
// 点单个词 → 展开单词卡片弹层;无媒体的词点开即时生成配图/发音/信息(规则:见 CLAUDE.md)
const cardWord = ref<IntensiveWord | null>(null)
const genWords = ref<Set<string>>(new Set())
function openCard(w: IntensiveWord) {
  cardWord.value = w
  if (!w.image_url) genWordMedia(w)
}
async function genWordMedia(w: IntensiveWord) {
  if (!w.word_id || genWords.value.has(w.word_id)) return
  genWords.value = new Set([...genWords.value, w.word_id])
  try {
    const m = await ensureWordMedia(w.word_id)
    w.image_url = m.image_url ?? null
    w.word_audio_url = m.word_audio_url ?? null
    w.en_description = m.en_description ?? null
    w.example = (m.example as any) ?? null
    if (m.definitions) w.definitions = m.definitions
  } catch { /* 生成失败静默 */ }
  finally {
    const s = new Set(genWords.value); s.delete(w.word_id); genWords.value = s
  }
}
// 单词发音:优先用已生成的 word_audio_url,否则走 TTS
const playingId = ref('')
let _audio: UniApp.InnerAudioContext | null = null
async function playWord(w: IntensiveWord) {
  try {
    const url = w.word_audio_url || (await resolveSpeakUrl(w.word))
    if (_audio) { _audio.stop(); _audio.destroy() }
    _audio = uni.createInnerAudioContext()
    _audio.src = url
    playingId.value = w.word_id
    _audio.onEnded(() => { playingId.value = '' })
    _audio.onError(() => { playingId.value = ''; uni.showToast({ title: '发音播放失败', icon: 'none' }) })
    _audio.play()
  } catch { playingId.value = ''; uni.showToast({ title: '发音获取失败', icon: 'none' }) }
}
const loading = ref(true)
const groups = ref<any[]>([])          // {id, title, sub, count}
const groupOpen = ref<any>(null)
const groupTitle = computed(() => groupOpen.value?.title || '')
const words = ref<IntensiveWord[]>([])
const wordsLoading = ref(false)
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))

// 课程侧按「年级 学期」分节;作业侧不分节
const sections = computed(() => {
  if (mode.value === 'homework') return [{ key: 'all', header: '', items: groups.value }]
  const map: Record<string, any[]> = {}
  for (const g of groups.value) {
    const k = g.header || ''
    ;(map[k] = map[k] || []).push(g)
  }
  return Object.keys(map).map(k => ({ key: k, header: k, items: map[k] }))
})

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

async function openGroup(g: any) {
  groupOpen.value = g
  wordsLoading.value = true
  words.value = []
  try {
    words.value = mode.value === 'homework'
      ? (await getHwWords(g.id)).words
      : (await getCourseWords(g.id)).words
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { wordsLoading.value = false }
}

// 进入完整词力通学习流(限定在该单元/批次词范围)
function startStudy() {
  const g = groupOpen.value
  if (!g) return
  const src = mode.value === 'homework' ? 'homework' : 'course'
  const key = mode.value === 'homework' ? 'paper_id' : 'unit_id'
  uni.navigateTo({ url: `/pages/vocabulary/index?source=${src}&${key}=${g.id}` })
}

async function load() {
  loading.value = true
  try {
    if (mode.value === 'homework') {
      const bs: HwWordBatch[] = (await getHwWordBatches()).batches
      groups.value = bs.map(b => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.word_count }))
    } else {
      const r = await getCourseWordUnits()
      groups.value = (r.units as CourseWordUnit[]).map(u => ({
        id: u.unit_id, title: `${u.unit_title}`, sub: `第${u.unit_no}单元`, count: u.word_count,
        header: `${u.grade} ${u.semester}册`,
      }))
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => { mode.value = q.mode || 'homework'; load() })
</script>

<style scoped>
.page { min-height: 100vh; background: var(--c-bg, #f5f7fa); padding: 24rpx; box-sizing: border-box; }
.hd { padding: 8rpx 4rpx 16rpx; }
.hd-title { font-size: 38rpx; font-weight: 800; color: var(--c-ink); display: block; }
.hd-sub { font-size: 23rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }
.tip { text-align: center; color: var(--c-text-hint); padding: 70rpx 24rpx; line-height: 1.6; }
.sec-h { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-text-second); margin: 18rpx 6rpx 10rpx; }
.card { background: #fff; border-radius: 18rpx; padding: 24rpx; margin-bottom: 16rpx; }
.grp { display: flex; align-items: center; gap: 14rpx; }
.grp-main { flex: 1; display: flex; flex-direction: column; gap: 6rpx; }
.grp-title { font-size: 28rpx; font-weight: 700; color: var(--c-ink); }
.grp-sub { font-size: 22rpx; color: var(--c-text-hint); }
.grp-cnt { font-size: 24rpx; color: var(--c-primary); flex-shrink: 0; }
.back { padding: 8rpx 4rpx 16rpx; font-size: 26rpx; color: var(--c-primary); }
.start-btn { background: var(--c-primary); color: #fff; text-align: center; padding: 24rpx; border-radius: 16rpx; font-size: 30rpx; font-weight: 600; margin-bottom: 16rpx; }
.list-hint { display: block; color: var(--c-text-hint, #999); font-size: 24rpx; margin-bottom: 12rpx; }
.word-top { display: flex; align-items: baseline; gap: 16rpx; }
.word-w { font-size: 32rpx; font-weight: 700; color: var(--c-ink); }
.word-ph { font-size: 24rpx; color: var(--c-text-hint); }
.word-def { display: block; font-size: 26rpx; color: var(--c-text-sub); margin-top: 8rpx; line-height: 1.6; }
.word-row { display: flex; align-items: center; gap: 18rpx; }
.w-img { width: 96rpx; height: 96rpx; border-radius: 12rpx; flex-shrink: 0; background: var(--c-bg-page, #f5f6f8); }
.w-img-ph { display: flex; align-items: center; justify-content: center; color: var(--c-text-hint); font-size: 24rpx; }
.w-main { flex: 1; min-width: 0; }
.w-play { width: 64rpx; height: 64rpx; border-radius: 50%; background: var(--c-bg-page, #f2f4f7); display: flex; align-items: center; justify-content: center; font-size: 30rpx; flex-shrink: 0; }
.w-play.on { background: var(--c-primary); color: #fff; }
.card-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 24rpx; max-height: 84vh; overflow-y: auto; }
.cp-img { width: 100%; height: 300rpx; border-radius: 16rpx; background: var(--c-bg-page, #f5f6f8); }
.cp-img-ph { display: flex; align-items: center; justify-content: center; color: var(--c-text-hint); font-size: 26rpx; }
.cp-head { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; }
.cp-word { font-size: 44rpx; font-weight: 800; color: var(--c-ink); }
.cp-play { background: var(--c-primary); color: #fff; padding: 10rpx 22rpx; border-radius: 999rpx; font-size: 26rpx; }
.cp-play.on { opacity: 0.7; }
.cp-ph { display: block; font-size: 26rpx; color: var(--c-text-hint); margin-top: 6rpx; }
.cp-def { display: block; font-size: 30rpx; color: var(--c-ink); margin-top: 14rpx; line-height: 1.6; }
.cp-ex { margin-top: 16rpx; padding: 16rpx; background: var(--c-bg-page, #f5f6f8); border-radius: 12rpx; }
.cp-ex-en { display: block; font-size: 28rpx; color: var(--c-ink); line-height: 1.6; }
.cp-ex-zh { display: block; font-size: 24rpx; color: var(--c-text-sub); margin-top: 6rpx; }
.cp-desc { display: block; font-size: 24rpx; color: var(--c-text-sub); margin-top: 14rpx; line-height: 1.6; }
.cp-close { text-align: center; margin-top: 20rpx; padding: 20rpx; color: var(--c-primary); font-size: 28rpx; }
</style>

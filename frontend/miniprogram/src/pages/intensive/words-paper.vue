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
          <view class="w-play" :class="{ on: playingId === item.word_id }" @tap.stop="playWord(item)"><view class="ic ic-volume w-play-ic"></view></view>
        </view>
      </template>
      <template #empty>该{{ mode === 'homework' ? '批次' : '单元' }}没有单词</template>
    </PaperChecklist>

    <!-- 单词卡片弹层:点单个词展开 -->
    <view v-if="cardWord" class="card-mask" @tap="cardWord = null">
      <view class="card-pop" @tap.stop>
        <image v-if="cardWord.image_url" :src="cardWord.image_url" class="cp-img" mode="aspectFill" />
        <view v-else-if="genWords.has(cardWord.word_id)" class="cp-img cp-img-ph"><text>配图生成中…</text></view>
        <!-- ⑦E 无好图降级词义卡:不出误导图,以词义为主(线性图标占位) -->
        <view v-else class="cp-img cp-card-ph">
          <view class="ic ic-book cp-card-ic"></view>
          <text class="cp-card-w">{{ cardWord.word }}</text>
          <text class="cp-card-m">{{ defText(cardWord.definitions) }}</text>
        </view>
        <!-- P3 图不对/换一张:撤图重刷(全学生共享),重生成中禁用 -->
        <view v-if="cardWord.image_url && !genWords.has(cardWord.word_id)" class="cp-report"
              :class="{ busy: regenId === cardWord.word_id }" @tap.stop="reportImage(cardWord)">
          <view class="ic ic-refresh cp-report-ic"></view>
          <text>{{ regenId === cardWord.word_id ? '重新生成中…' : '图不对 · 换一张' }}</text>
        </view>
        <view class="cp-head">
          <text class="cp-word">{{ cardWord.word }}</text>
          <view class="cp-play" :class="{ on: playingId === cardWord.word_id }" @tap="playWord(cardWord)">
            <view class="ic ic-volume-w cp-play-ic"></view>
            <text>{{ playingId === cardWord.word_id ? '播放中' : '发音' }}</text>
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
import { ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { getHwWords, getCourseWords, ensureWordMedia, reportWordImage, type IntensiveWord } from '@/api/vocabulary'
import PaperChecklist from '@/components/PaperChecklist.vue'
import { resolveSpeakUrl } from '@/utils/tts'

const mode = ref('homework')
const groupId = ref('')
const sub = ref('')
const words = ref<IntensiveWord[]>([])
const loading = ref(true)

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
// P3 图不对/换一张:撤下当前图并按新管线重生成(全学生共享),原地更新卡片(可能换新图,也可能降级词义卡)
const regenId = ref('')
async function reportImage(w: IntensiveWord) {
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

function defText(d: any): string {
  if (!d) return ''
  if (Array.isArray(d)) return d.map((x: any) => typeof x === 'string' ? x
    : [x.pos || x.part_of_speech, x.meaning || x.zh || x.definition].filter(Boolean).join(' ')).join('；')
  if (typeof d === 'string') return d
  return ''
}

// 进入完整词力通学习流(限定在该单元/批次词范围)
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
// 从词力通学习流返回 → 刷新当前卷词表的已学打勾(跳过 onLoad 后的首次)
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
.w-img-ic { width: 44rpx; height: 44rpx; opacity: .55; }
.w-play { width: 64rpx; height: 64rpx; border-radius: 50%; background: var(--c-bg-page, #f2f4f7); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.w-play.on { background: #eaf2fe; }
.w-play-ic { width: 34rpx; height: 34rpx; }
.card-mask { position: fixed; left: 0; right: 0; top: 0; bottom: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 40rpx; }
.card-pop { width: 100%; max-width: 620rpx; background: #fff; border-radius: 24rpx; padding: 24rpx; max-height: 84vh; overflow-y: auto; }
.cp-img { width: 100%; height: 300rpx; border-radius: 16rpx; background: var(--c-bg-page, #f5f6f8); }
.cp-img-ph { display: flex; align-items: center; justify-content: center; color: var(--c-text-hint); font-size: 26rpx; }
/* ⑦E 无好图降级词义卡 */
.cp-card-ph { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 10rpx; background: linear-gradient(135deg, #f3f8ff, #eef4fb); }
.cp-card-ic { width: 64rpx; height: 64rpx; opacity: .7; }
.cp-card-w { font-size: 36rpx; font-weight: 800; color: #2f74d6; }
.cp-card-m { font-size: 24rpx; color: #6b7688; max-width: 84%; text-align: center; }
/* P3 图不对/换一张 */
.cp-report { display: flex; align-items: center; justify-content: center; gap: 8rpx; margin-top: 12rpx; font-size: 22rpx; color: #93a0b3; }
.cp-report.busy { color: #3d8bf5; }
.cp-report-ic { width: 26rpx; height: 26rpx; opacity: .75; }
.cp-head { display: flex; align-items: center; justify-content: space-between; margin-top: 18rpx; }
.cp-word { font-size: 44rpx; font-weight: 800; color: var(--c-ink); }
.cp-play { background: var(--c-primary); color: #fff; display: flex; align-items: center; gap: 8rpx; padding: 10rpx 22rpx; border-radius: 999rpx; font-size: 26rpx; }
.cp-play.on { opacity: 0.7; }
.cp-play-ic { width: 28rpx; height: 28rpx; }
.cp-ph { display: block; font-size: 26rpx; color: var(--c-text-hint); margin-top: 6rpx; }
.cp-def { display: block; font-size: 30rpx; color: var(--c-ink); margin-top: 14rpx; line-height: 1.6; }
.cp-ex { margin-top: 16rpx; padding: 16rpx; background: var(--c-bg-page, #f5f6f8); border-radius: 12rpx; }
.cp-ex-en { display: block; font-size: 28rpx; color: var(--c-ink); line-height: 1.6; }
.cp-ex-zh { display: block; font-size: 24rpx; color: var(--c-text-sub); margin-top: 6rpx; }
.cp-desc { display: block; font-size: 24rpx; color: var(--c-text-sub); margin-top: 14rpx; line-height: 1.6; }
.cp-close { text-align: center; margin-top: 20rpx; padding: 20rpx; color: var(--c-primary); font-size: 28rpx; }
</style>

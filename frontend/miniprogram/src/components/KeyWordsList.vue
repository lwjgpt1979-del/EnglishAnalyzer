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
          <view class="kw-wrow">
            <text class="kw-w">{{ w.word }}</text>
            <text v-if="w.exam_tag" class="kw-exam">{{ w.exam_tag }}</text>
          </view>
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

    <!-- U1:内置弹层统一 WordCard;noCard 时由父级根层 WordCard 承接 -->
    <WordCard v-if="!noCard" :word="cardWord" :paper-id="paperId" @close="cardWord = null" />
  </view>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import type { StudyWord } from '@/api/userPapers'
import { addHomeworkWords, ensureWordMedia, ensureMissingWord } from '@/api/vocabulary'
import WordCard from '@/components/WordCard.vue'

const props = withDefaults(defineProps<{
  words: StudyWord[]
  paperId?: string
  title?: string
  /** true=不渲染内置 WordCard,只 emit('pick') 由父级在根层渲染(避免困在 scroll-view) */
  noCard?: boolean
}>(), { title: '重点词汇', noCard: false })
const emit = defineEmits<{ (e: 'pick', word: StudyWord): void }>()

const cardWord = ref<StudyWord | null>(null)
const wordAdded = ref<Set<string>>(new Set())
const genWords = ref<Set<string>>(new Set())

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
  // 列表「生成中」角标仍由本组件轮询/ensure;弹层 WordCard 也会 ensure
  if (!w.image_url && w.word_id) genWordMedia(w)
  if (props.noCard) { emit('pick', w); return }
  cardWord.value = w
}

function kwSub(w: StudyWord): string {
  if (learningWord.value === w.word) return '收录中…'
  if (w.pending_create) return '词库暂无 · 点「学这个词」即时收录'
  if (genWords.value.has(w.word_id || '')) return '配图/发音生成中…'
  return defText(w.definitions)
}

const learningWord = ref('')
async function learnMissing(w: StudyWord) {
  if (learningWord.value || !w.word) return
  learningWord.value = w.word
  try {
    const r = await ensureMissingWord(w.word, props.paperId)
    if (r.status === 'queued' || !r.word) {
      uni.showToast({ title: '该词已提交人工收录', icon: 'none' }); return
    }
    Object.assign(w, r.word, { pending_create: false })
    if (w.word_id && w.word_added) wordAdded.value = new Set([...wordAdded.value, w.word_id])
    uni.showToast({ title: r.status === 'created' ? '已收录,可以学啦' : '已加入', icon: 'none' })
    if (r.status === 'created' && w.word_id && !w.image_url) pollMissingMedia(w)
  } catch (e: any) { uni.showToast({ title: e?.message || '收录失败', icon: 'none' }) }
  finally { learningWord.value = '' }
}

async function pollMissingMedia(w: StudyWord) {
  const id = w.word_id
  if (!id) return
  genWords.value = new Set([...genWords.value, id])
  try {
    for (let i = 0; i < 6; i++) {
      await new Promise(res => setTimeout(res, 3000))
      const m = await ensureWordMedia(id)
      if (m.image_url) {
        w.image_url = m.image_url
        w.word_audio_url = m.word_audio_url ?? w.word_audio_url
        w.en_description = m.en_description ?? w.en_description
        w.example = (m.example as any) ?? w.example
        break
      }
    }
  } catch { /* 静默 */ }
  finally { const s = new Set(genWords.value); s.delete(id); genWords.value = s }
}

async function addWord(w: StudyWord) {
  if (!w.word_id || wordAdded.value.has(w.word_id)) return
  if (!props.paperId) { uni.showToast({ title: '请从作业里进入以归入批次', icon: 'none' }); return }
  try {
    await addHomeworkWords([w.word_id], props.paperId)
    wordAdded.value = new Set([...wordAdded.value, w.word_id])
    uni.showToast({ title: '已加入作业精讲·单词', icon: 'none' })
    if (!w.image_url) genWordMedia(w)
  } catch (e: any) { uni.showToast({ title: e?.message || '加入失败', icon: 'none' }) }
}

async function genWordMedia(w: StudyWord) {
  if (!w.word_id || w.image_status === 'text_only' || genWords.value.has(w.word_id)) return
  genWords.value = new Set([...genWords.value, w.word_id])
  try {
    const m = await ensureWordMedia(w.word_id)
    w.image_url = m.image_url ?? null
    w.image_status = m.image_status ?? w.image_status
    w.word_audio_url = m.word_audio_url ?? null
    w.en_description = m.en_description ?? null
    w.example = (m.example as any) ?? null
    if (m.definitions) w.definitions = m.definitions
  } catch { /* 静默 */ }
  finally {
    const s = new Set(genWords.value); s.delete(w.word_id); genWords.value = s
  }
}
</script>

<style scoped>
.card { background: #fff; border-radius: 20rpx; padding: 26rpx 24rpx; margin-bottom: 20rpx; }
.sec-t { display: block; font-size: 24rpx; font-weight: 700; color: var(--c-text-second); margin-bottom: 6rpx; }
.sec-sub { display: block; font-size: 21rpx; color: var(--c-text-hint); margin-bottom: 16rpx; line-height: 1.5; }
.kw-list { display: flex; flex-direction: column; gap: 12rpx; }
.kw-row { display: flex; align-items: center; gap: 16rpx; padding: 12rpx; background: var(--c-bg-soft, #f6f8fb); border-radius: 14rpx; }
.kw-img { width: 84rpx; height: 84rpx; border-radius: 10rpx; flex-shrink: 0; background: #eef1f5; }
.kw-gen { display: flex; align-items: center; justify-content: center; background: var(--c-primary-faint, #eaf2ff); }
.kw-gen-t { font-size: 19rpx; color: var(--c-primary); }
.kw-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4rpx; }
.kw-wrow { display: flex; align-items: center; gap: 8rpx; }
.kw-w { font-size: 27rpx; font-weight: 700; color: var(--c-primary); }
.kw-exam { flex: none; font-size: 18rpx; color: #c2670c; background: #fff3e0; border-radius: 6rpx; padding: 1rpx 8rpx; }
.kw-def { font-size: 23rpx; color: var(--c-text-sub); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kw-add { flex-shrink: 0; font-size: 22rpx; color: var(--c-primary); border: 2rpx solid var(--c-primary); border-radius: 999rpx; padding: 6rpx 22rpx; }
.kw-add.done { color: #2ecc71; border-color: #2ecc71; }
.kw-add.kw-new { color: #ff8a3d; border-color: #ffd8bd; }
</style>

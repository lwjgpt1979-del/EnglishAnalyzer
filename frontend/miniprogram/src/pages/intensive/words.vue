<template>
  <view class="page">
    <view class="hd">
      <text class="hd-title">{{ modeLabel }} · 单词</text>
      <text class="hd-sub">{{ groupOpen ? groupTitle : (mode === 'homework' ? '按批次(卷/日期)' : '按 年级 → 册 → 单元') }}</text>
    </view>

    <view v-if="loading" class="tip">加载中…</view>

    <!-- 一级:作业=批次列表 / 课程=闯关地图 -->
    <template v-else-if="!groupOpen">
      <template v-if="mode === 'homework'">
        <view v-if="!groups.length" class="tip">还没有加入待学习的单词——去上传的试卷里挑生词加入</view>
        <IntensiveBatchList v-else :batches="hwItems" unit="词" @open="openById" />
      </template>
      <UnitLevelMap v-else :units="courseUnits" unit="词" :title="semLabel" :next-hint="nextHint" @open="openCourseUnit" />
    </template>

    <!-- 二级:单元/批次词清单(卷头进度即底色 + 勾选圈),作业/课程同一套 -->
    <template v-else>
      <view class="back" @tap="groupOpen = null"><text>‹ 返回{{ mode === 'homework' ? '批次' : '单元' }}</text></view>
      <view v-if="wordsLoading" class="tip">加载中…</view>
      <PaperChecklist v-else :items="words" :date="groupOpen && groupOpen.sub" unit="词"
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
    </template>

    <!-- 学完当前学期:庆祝弹层(测验 / 预习下册 / 复习)-->
    <SemesterDoneModal :visible="showDone" :semester-label="semLabel" unit-label="单词"
      :unit-total="courseUnits.length" :content-total="courseWordTotal" :next-semester="nextSemester"
      @quiz="onSemesterQuiz" @preview="onPreviewNext" @review="showDone = false" @close="showDone = false" />

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
import { computed, ref } from 'vue'
import { onLoad, onShow } from '@dcloudio/uni-app'
import { getHwWordBatches, getHwWords, getCourseWordUnits, getCourseWords, ensureWordMedia,
         reportWordImage, type IntensiveWord, type HwWordBatch, type CourseWordUnit } from '@/api/vocabulary'
import PaperChecklist from '@/components/PaperChecklist.vue'
import { resolveSpeakUrl } from '@/utils/tts'
import IntensiveBatchList, { type BatchItem } from '@/components/IntensiveBatchList.vue'
import UnitLevelMap from '@/components/UnitLevelMap.vue'
import SemesterDoneModal from '@/components/SemesterDoneModal.vue'

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
const loading = ref(true)
const groups = ref<any[]>([])          // {id, title, sub, count}
const groupOpen = ref<any>(null)
const groupTitle = computed(() => groupOpen.value?.title || '')
// 作业批次 → 统一批次组件(状态/时间轴/进度);sub 即日期
const hwItems = computed<BatchItem[]>(() => groups.value.map(g => ({
  id: g.id, title: g.title, date: g.sub, count: g.count, studied: g.studied,
})))
function openById(id: string) { const g = groups.value.find(x => x.id === id); if (g) openGroup(g) }
const words = ref<IntensiveWord[]>([])
const wordsLoading = ref(false)
const modeLabel = computed(() => (mode.value === 'homework' ? '作业精讲' : '课程精讲'))

// 课程精讲·闯关地图 + 学完庆祝弹层
const courseUnits = ref<CourseWordUnit[]>([])
const courseGrade = ref<string | undefined>(undefined)   // 空=后端默认当前学期;切学期时赋值
const courseSem = ref<string | undefined>(undefined)
const semLabel = ref('课程')
const nextSemester = ref<{ grade: string; semester: string } | null>(null)
const showDone = ref(false)
const courseWordTotal = computed(() => courseUnits.value.reduce((a, u) => a + (u.word_count || 0), 0))
const nextHint = computed(() => nextSemester.value
  ? `闯完本册接入 ${nextSemester.value.grade}${nextSemester.value.semester}册` : '')
function openCourseUnit(unitId: string) {
  const u = courseUnits.value.find(x => x.unit_id === unitId)
  if (u) openGroup({ id: u.unit_id, title: u.unit_title, sub: `第${u.unit_no}单元`, count: u.word_count })
}
function onPreviewNext() {   // 预习下学期:切 grade/semester 重新加载
  if (!nextSemester.value) return
  courseGrade.value = nextSemester.value.grade
  courseSem.value = nextSemester.value.semester
  showDone.value = false
  load()
}
function onSemesterQuiz() { uni.showToast({ title: '学期测验即将上线', icon: 'none' }) }

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
      groups.value = bs.map(b => ({ id: b.paper_id, title: b.title, sub: b.date, count: b.word_count, studied: b.studied }))
    } else {
      const r = await getCourseWordUnits(courseGrade.value, courseSem.value)
      courseUnits.value = r.units
      semLabel.value = r.grade && r.semester ? `${r.grade}${r.semester}册` : '课程'
      nextSemester.value = r.next_semester
      showDone.value = r.semester_done
    }
  } catch (e: any) { uni.showToast({ title: e?.message || '加载失败', icon: 'none' }) }
  finally { loading.value = false }
}

onLoad((q: any) => { mode.value = q.mode || 'homework'; load() })
// 从词力通学习流返回 → 刷新批次进度与当前卷词表的已学打勾(跳过 onLoad 后的首次)
let _shown = false
onShow(() => { if (!_shown) { _shown = true; return } load(); if (groupOpen.value) openGroup(groupOpen.value) })
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
.start-btn { background: var(--c-primary); color: #fff; display: flex; align-items: center; justify-content: center; gap: 12rpx; padding: 24rpx; border-radius: 16rpx; font-size: 30rpx; font-weight: 600; margin-bottom: 16rpx; }
.start-ic { width: 30rpx; height: 30rpx; }
.list-hint { display: block; color: var(--c-text-hint, #999); font-size: 24rpx; margin-bottom: 12rpx; }
.word-top { display: flex; align-items: baseline; gap: 16rpx; }
.word-w { font-size: 34rpx; font-weight: 700; color: var(--c-ink); }
.word-ph { font-size: 24rpx; color: var(--c-text-hint); }
.word-def { display: block; font-size: 26rpx; color: var(--c-text-sub); margin-top: 8rpx; line-height: 1.6; }
.word-row { display: flex; align-items: center; gap: 18rpx; }
.wrow { display: flex; align-items: center; gap: 18rpx; }
.wrow-main { flex: 1; min-width: 0; }
.w-img { width: 104rpx; height: 104rpx; border-radius: 16rpx; flex-shrink: 0; background: var(--c-bg-page, #eef3fa); }
.w-img-ph { display: flex; align-items: center; justify-content: center; color: var(--c-text-hint); }
.w-img-ic { width: 44rpx; height: 44rpx; opacity: .55; }
.w-main { flex: 1; min-width: 0; }
.w-play { width: 64rpx; height: 64rpx; border-radius: 50%; background: var(--c-bg-page, #f2f4f7); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.w-play.on { background: #eaf2fe; }
.w-play-ic { width: 34rpx; height: 34rpx; }
.card-mask { position: fixed; inset: 0; background: rgba(0,0,0,0.45); display: flex; align-items: center; justify-content: center; z-index: 100; padding: 40rpx; }
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

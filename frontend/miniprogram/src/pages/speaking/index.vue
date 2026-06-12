<template>
  <view class="sp-page">
    <!-- 场景选择 -->
    <view v-if="phase === 'pick'">
      <view class="head">
        <text class="h-title">🗣️ AI 口语对话</text>
        <text class="h-sub">选个场景，开口说英语 · AI 实时回应并纠错</text>
      </view>

      <!-- 为你定制（因材施教）-->
      <view v-if="custom.length" class="sec-head">
        <text class="sec-name">✨ 为你定制</text>
        <text class="sec-desc">按你的学期内容 / 在练单词 / 错题薄弱点生成</text>
      </view>
      <view v-if="custom.length" class="grid">
        <view
          v-for="s in custom" :key="s.key"
          class="sc-card custom" @tap="start(s.key)"
        >
          <view class="sc-top">
            <text class="sc-emoji">{{ s.emoji }}</text>
            <text v-if="s.source" class="sc-tag">{{ s.source }}</text>
          </view>
          <text class="sc-title">{{ s.title }}</text>
          <text class="sc-open">{{ s.opening }}</text>
        </view>
      </view>

      <!-- 通用场景 -->
      <view class="sec-head"><text class="sec-name">🌐 通用场景</text></view>
      <view class="grid">
        <view
          v-for="s in preset" :key="s.key"
          class="sc-card" @tap="start(s.key)"
        >
          <text class="sc-emoji">{{ s.emoji }}</text>
          <text class="sc-title">{{ s.title }}</text>
          <text class="sc-open">{{ s.opening }}</text>
        </view>
      </view>
    </view>

    <!-- 对话 -->
    <view v-else class="chat-wrap">
      <view class="chat-top">
        <text class="ct-leave" @tap="leave">← 换场景</text>
        <text class="ct-end" @tap="endAndRate">结束并评价</text>
      </view>
      <scroll-view scroll-y class="chat" :scroll-top="scrollTop" :scroll-with-animation="true">
        <view class="chat-inner">
          <view v-for="(m, i) in messages" :key="i" :class="['row', m.role]">
            <view v-if="m.role === 'assistant'" class="bubble ai">
              <text class="b-text">{{ m.text }}</text>
              <view class="b-tools">
                <text class="b-play" @tap="playAudio(m)">{{ m.playing ? '⏸' : '▶' }} 听</text>
                <text v-if="m.translation" class="b-tr-btn" @tap="m.showTr = !m.showTr">
                  {{ m.showTr ? '隐藏翻译' : '中文' }}
                </text>
              </view>
              <text v-if="m.showTr && m.translation" class="b-tr">{{ m.translation }}</text>
              <view v-if="m.correction" class="b-fix">
                <text class="b-fix-tag">✍️ 纠错</text>
                <text class="b-fix-text">{{ m.correction }}</text>
              </view>
            </view>
            <view v-else class="bubble me">
              <text class="b-text">{{ m.text }}</text>
            </view>
          </view>
          <view v-if="thinking" class="row assistant">
            <view class="bubble ai thinking"><text>AI 正在回应…</text></view>
          </view>
        </view>
      </scroll-view>

      <!-- 输入条 -->
      <view class="input-bar">
        <!-- #ifdef MP-WEIXIN -->
        <view class="mic" :class="{ rec: recording }" @touchstart="micStart" @touchend="micEnd">
          <text>{{ recording ? '松开发送' : '🎤' }}</text>
        </view>
        <!-- #endif -->
        <input
          class="ti" v-model="draft" type="text" confirm-type="send"
          placeholder="打字或按住🎤说英语…" @confirm="send"
        />
        <button class="send" :disabled="!draft.trim() || thinking" @tap="send">发送</button>
      </view>
    </view>

    <!-- 结束评价 -->
    <view v-if="summary" class="mask" @tap="summary = null">
      <view class="sheet" @tap.stop>
        <text class="sh-title">🎉 本次口语评价</text>
        <view class="score-ring">
          <text class="sr-num">{{ summary.overall }}</text>
          <text class="sr-unit">分</text>
        </view>
        <view class="dims">
          <view class="dim"><text class="dim-l">流利度</text><text class="dim-v">{{ summary.fluency }}</text></view>
          <view class="dim"><text class="dim-l">语法</text><text class="dim-v">{{ summary.grammar }}</text></view>
          <view class="dim"><text class="dim-l">词汇</text><text class="dim-v">{{ summary.vocabulary }}</text></view>
        </view>
        <view class="sec">
          <text class="sec-t">✨ 亮点</text>
          <text v-for="(h, i) in summary.highlights" :key="i" class="sec-li">· {{ h }}</text>
        </view>
        <view class="sec">
          <text class="sec-t">📈 可提升</text>
          <text v-for="(im, i) in summary.improvements" :key="i" class="sec-li">· {{ im }}</text>
        </view>
        <!-- 本次专项（因材施教）-->
        <view v-if="summary.focus_review" class="focus-box">
          <text class="focus-t">🎯 本次专项 · {{ summary.focus_source }}</text>
          <text class="focus-review">{{ summary.focus_review }}</text>
          <view v-if="(summary.focus_used && summary.focus_used.length) || (summary.focus_missed && summary.focus_missed.length)" class="chips">
            <text v-for="(w, i) in summary.focus_used" :key="'u'+i" class="chip used">✓ {{ w }}</text>
            <text v-for="(w, i) in summary.focus_missed" :key="'m'+i" class="chip miss">{{ w }}</text>
          </view>
        </view>
        <text class="encour">{{ summary.encouragement }}</text>
        <view class="sheet-btns">
          <button class="btn-ghost" @tap="summary = null">继续聊</button>
          <button class="btn-fill" @tap="() => { summary = null; leave() }">换个场景</button>
        </view>
      </view>
    </view>
  </view>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import {
  getSpeakScenarios, startSpeak, replySpeak, summarizeSpeak,
  type SpeakScenario, type SpeakTurn, type SpeakSummary,
} from '@/api/speaking'

interface Msg {
  role: 'user' | 'assistant'
  text: string
  audio?: string
  translation?: string
  correction?: string
  showTr?: boolean
  playing?: boolean
}

const phase = ref<'pick' | 'chat'>('pick')
const custom = ref<SpeakScenario[]>([])
const preset = ref<SpeakScenario[]>([])
const scenarioKey = ref('')
const messages = ref<Msg[]>([])
const draft = ref('')
const thinking = ref(false)
const scrollTop = ref(0)
const recording = ref(false)
const summary = ref<SpeakSummary | null>(null)
const rating = ref(false)

async function endAndRate() {
  const userTurns = messages.value.filter(m => m.role === 'user').length
  if (userTurns === 0) { uni.showToast({ title: '先聊几句再评价吧', icon: 'none' }); return }
  if (rating.value) return
  rating.value = true
  uni.showLoading({ title: '正在评价…' })
  try {
    const history: SpeakTurn[] = messages.value
      .map(m => ({ role: m.role, text: m.text }))
    summary.value = await summarizeSpeak(scenarioKey.value, history)
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '评价失败', icon: 'none' })
  } finally {
    uni.hideLoading()
    rating.value = false
  }
}

onMounted(async () => {
  try {
    const list = await getSpeakScenarios()
    custom.value = list.custom || []
    preset.value = list.preset || []
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '加载失败', icon: 'none' })
  }
})

async function start(key: string) {
  scenarioKey.value = key
  messages.value = []
  phase.value = 'chat'
  thinking.value = true
  try {
    const o = await startSpeak(key)
    pushAi(o.ai_text, o.ai_audio_url)
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '开始失败', icon: 'none' })
  } finally {
    thinking.value = false
  }
}

function pushAi(text: string, audio: string, translation = '', correction = '') {
  messages.value.push({ role: 'assistant', text, audio, translation, correction, showTr: false })
  scrollToEnd()
}

async function send() {
  const t = draft.value.trim()
  if (!t || thinking.value) return
  draft.value = ''
  messages.value.push({ role: 'user', text: t })
  scrollToEnd()
  thinking.value = true
  try {
    const history: SpeakTurn[] = messages.value
      .filter(m => m.role === 'user' || m.role === 'assistant')
      .slice(-8)
      .map(m => ({ role: m.role, text: m.text }))
    const r = await replySpeak(scenarioKey.value, t, history)
    pushAi(r.ai_text, r.ai_audio_url, r.translation, r.correction)
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '回应失败', icon: 'none' })
  } finally {
    thinking.value = false
  }
}

function scrollToEnd() {
  nextTick(() => { scrollTop.value = 999999 + Math.random() })
}

// ── 音频 ──
let _ctx: UniApp.InnerAudioContext | null = null
let _cur: Msg | null = null
function playAudio(m: Msg) {
  if (!m.audio) { uni.showToast({ title: '暂无语音', icon: 'none' }); return }
  if (!_ctx) {
    _ctx = uni.createInnerAudioContext()
    _ctx.onEnded(() => { if (_cur) _cur.playing = false })
    _ctx.onStop(() => { if (_cur) _cur.playing = false })
    _ctx.onError(() => { if (_cur) _cur.playing = false })
  }
  if (_cur && _cur.playing) { _cur.playing = false; try { _ctx.stop() } catch { /* ignore */ } }
  _cur = m
  m.playing = true
  _ctx.src = m.audio
  _ctx.play()
}

function leave() {
  if (_cur && _ctx) { try { _ctx.stop() } catch { /* ignore */ } }
  phase.value = 'pick'
}

// ── 语音输入（微信同声传译插件，仅微信端） ──
/* #ifdef MP-WEIXIN */
let _mgr: any = null
function getMgr() {
  if (_mgr) return _mgr
  try {
    const plugin: any = requirePlugin('WechatSI')
    _mgr = plugin.getRecordRecognitionManager()
    _mgr.onRecognize = () => { /* 中间结果忽略 */ }
    _mgr.onStop = (res: any) => {
      recording.value = false
      const text = (res && res.result || '').trim()
      if (text) { draft.value = text; send() }
      else uni.showToast({ title: '没听清，再说一次或打字', icon: 'none' })
    }
    _mgr.onError = () => {
      recording.value = false
      uni.showToast({ title: '语音识别不可用，请打字', icon: 'none' })
    }
    return _mgr
  } catch {
    return null
  }
}
function micStart() {
  const mgr = getMgr()
  if (!mgr) { uni.showToast({ title: '未启用语音插件，请打字', icon: 'none' }); return }
  recording.value = true
  mgr.start({ lang: 'en_US' })
}
function micEnd() {
  if (!recording.value) return
  const mgr = getMgr()
  if (mgr) mgr.stop()
}
/* #endif */
</script>

<style scoped>
.sp-page { min-height: 100vh; background: var(--c-bg-page); }

.head { padding: 28rpx 24rpx 8rpx; }
.h-title { font-size: 40rpx; font-weight: 800; color: var(--c-ink); display: block; }
.h-sub { font-size: 24rpx; color: var(--c-text-hint); margin-top: 6rpx; display: block; }

.sec-head { padding: 14rpx 24rpx 0; display: flex; align-items: baseline; gap: 14rpx; flex-wrap: wrap; }
.sec-name { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.sec-desc { font-size: 22rpx; color: var(--c-text-hint); }
.grid { display: flex; flex-wrap: wrap; gap: 20rpx; padding: 16rpx 24rpx; }
.sc-card { width: calc(50% - 10rpx); box-sizing: border-box; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 26rpx 22rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); display: flex; flex-direction: column; gap: 10rpx; }
.sc-card.custom { background: linear-gradient(160deg, var(--c-primary-faint), var(--c-bg-card)); border: 2rpx solid var(--c-primary-soft); }
.sc-top { display: flex; align-items: center; justify-content: space-between; }
.sc-tag { font-size: 18rpx; font-weight: 700; color: var(--c-primary-deep); background: #fff; padding: 4rpx 12rpx; border-radius: var(--r-pill); }
.sc-emoji { font-size: 48rpx; }
.sc-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.sc-open { font-size: 22rpx; color: var(--c-text-hint); line-height: 1.5; }

.chat-wrap { display: flex; flex-direction: column; height: 100vh; }
.chat { flex: 1; min-height: 0; }
.chat-inner { padding: 24rpx 24rpx 12rpx; display: flex; flex-direction: column; gap: 18rpx; }
.row { display: flex; }
.row.assistant { justify-content: flex-start; }
.row.user { justify-content: flex-end; }
.bubble { max-width: 78%; border-radius: 22rpx; padding: 18rpx 22rpx; box-shadow: 0 3rpx 16rpx rgba(0,0,0,.05); }
.bubble.ai { background: var(--c-bg-card); border-top-left-radius: 6rpx; }
.bubble.me { background: var(--c-primary); border-top-right-radius: 6rpx; }
.bubble.me .b-text { color: var(--c-on-primary); }
.b-text { font-size: 30rpx; line-height: 1.55; color: var(--c-text-body); display: block; }
.b-tools { display: flex; gap: 24rpx; margin-top: 12rpx; }
.b-play, .b-tr-btn { font-size: 24rpx; font-weight: 700; color: var(--c-primary-deep); }
.b-tr { display: block; margin-top: 8rpx; font-size: 24rpx; color: var(--c-text-hint); line-height: 1.5; }
.b-fix { margin-top: 12rpx; background: #fff7e8; border-radius: 12rpx; padding: 12rpx 14rpx; display: flex; flex-direction: column; gap: 4rpx; }
.b-fix-tag { font-size: 22rpx; font-weight: 800; color: #c98314; }
.b-fix-text { font-size: 24rpx; color: #8a6516; line-height: 1.5; }
.bubble.thinking { color: var(--c-text-hint); font-size: 26rpx; }

.input-bar { display: flex; align-items: center; gap: 14rpx; padding: 16rpx 20rpx; background: var(--c-bg-card); box-shadow: 0 -4rpx 20rpx rgba(0,0,0,.05); }
.mic { flex-shrink: 0; width: 76rpx; height: 76rpx; border-radius: 50%; background: var(--c-primary-faint); color: var(--c-primary-deep); display: flex; align-items: center; justify-content: center; font-size: 26rpx; font-weight: 700; }
.mic.rec { background: var(--c-primary); color: var(--c-on-primary); transform: scale(1.06); }
.ti { flex: 1; background: var(--c-bg-soft); border-radius: var(--r-pill); padding: 18rpx 24rpx; font-size: 28rpx; color: var(--c-text-body); }
.send { flex-shrink: 0; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 28rpx; font-weight: 700; padding: 0 30rpx; height: 72rpx; line-height: 72rpx; }
.send[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }

.chat-top { display: flex; align-items: center; justify-content: space-between; padding: 14rpx 24rpx; background: var(--c-bg-card); box-shadow: 0 2rpx 12rpx rgba(0,0,0,.04); }
.ct-leave { font-size: 26rpx; color: var(--c-text-hint); }
.ct-end { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 8rpx 22rpx; border-radius: var(--r-pill); }

.mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 40rpx; }
.sheet { width: 100%; max-width: 620rpx; background: var(--c-bg-card); border-radius: 28rpx; padding: 36rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; max-height: 86vh; overflow-y: auto; }
.sh-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.score-ring { width: 160rpx; height: 160rpx; border-radius: 50%; background: var(--c-primary-faint); border: 8rpx solid var(--c-primary); display: flex; align-items: baseline; justify-content: center; gap: 4rpx; }
.sr-num { font-size: 64rpx; font-weight: 900; color: var(--c-primary-deep); }
.sr-unit { font-size: 24rpx; color: var(--c-primary-deep); }
.dims { display: flex; gap: 28rpx; }
.dim { display: flex; flex-direction: column; align-items: center; gap: 4rpx; }
.dim-l { font-size: 22rpx; color: var(--c-text-hint); }
.dim-v { font-size: 36rpx; font-weight: 800; color: var(--c-ink); }
.sec { width: 100%; display: flex; flex-direction: column; gap: 6rpx; }
.sec-t { font-size: 26rpx; font-weight: 700; color: var(--c-ink); }
.sec-li { font-size: 25rpx; color: var(--c-text-second); line-height: 1.6; }
.focus-box { width: 100%; background: var(--c-primary-faint); border-radius: 16rpx; padding: 18rpx 20rpx; display: flex; flex-direction: column; gap: 8rpx; }
.focus-t { font-size: 25rpx; font-weight: 800; color: var(--c-primary-deep); }
.focus-review { font-size: 25rpx; color: var(--c-text-second); line-height: 1.6; }
.chips { display: flex; flex-wrap: wrap; gap: 10rpx; margin-top: 4rpx; }
.chip { font-size: 22rpx; padding: 4rpx 16rpx; border-radius: var(--r-pill); }
.chip.used { background: #e6f8ee; color: #18a058; }
.chip.miss { background: #fff; color: var(--c-text-hint); border: 2rpx solid var(--c-border); }
.encour { font-size: 26rpx; color: var(--c-primary-deep); text-align: center; line-height: 1.6; margin-top: 4rpx; }
.sheet-btns { display: flex; gap: 16rpx; width: 100%; margin-top: 12rpx; }
.btn-ghost { flex: 1; background: var(--c-bg-soft); color: var(--c-text-body); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; }
.btn-fill { flex: 1; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; font-weight: 700; }
</style>

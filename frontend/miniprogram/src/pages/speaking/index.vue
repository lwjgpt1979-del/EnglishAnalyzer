<template>
  <view class="sp-page">
    <!-- 场景选择 -->
    <view v-if="phase === 'pick'">
      <view class="head">
        <text class="h-title">🗣️ AI 口语对话</text>
        <text class="h-sub">选个场景，开口说英语 · AI 实时回应并纠错</text>
      </view>
      <view class="grid">
        <view
          v-for="s in scenarios" :key="s.key"
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
      <text class="leave" @tap="leave">← 换个场景</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'
import {
  getSpeakScenarios, startSpeak, replySpeak,
  type SpeakScenario, type SpeakTurn,
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
const scenarios = ref<SpeakScenario[]>([])
const scenarioKey = ref('')
const messages = ref<Msg[]>([])
const draft = ref('')
const thinking = ref(false)
const scrollTop = ref(0)
const recording = ref(false)

onMounted(async () => {
  try {
    scenarios.value = await getSpeakScenarios()
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

.grid { display: flex; flex-wrap: wrap; gap: 20rpx; padding: 20rpx 24rpx; }
.sc-card { width: calc(50% - 10rpx); box-sizing: border-box; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 26rpx 22rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); display: flex; flex-direction: column; gap: 10rpx; }
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
.leave { text-align: center; padding: 16rpx; font-size: 24rpx; color: var(--c-text-hint); }
</style>

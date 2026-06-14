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
        <view class="ct-right">
          <text class="ct-auto" :class="{ on: autoPlay }" @tap="autoPlay = !autoPlay">
            {{ autoPlay ? '🔊 自动播放' : '🔇 自动播放' }}
          </text>
          <text v-if="vocabMode" class="ct-auto" :class="{ on: readSentences }" @tap="readSentences = !readSentences">
            {{ readSentences ? '🔉 读例句/短语' : '🔈 读例句/短语' }}
          </text>
          <text class="ct-end" @tap="endAndRate">结束并评价</text>
        </view>
      </view>
      <scroll-view scroll-y class="chat" :scroll-top="scrollTop" :scroll-with-animation="true">
        <view class="chat-inner">
          <view v-for="(m, i) in messages" :key="i" :class="['row', m.role]">
            <view v-if="m.role === 'system'" class="sys-banner">
              <text>{{ m.text }}</text>
            </view>
            <view v-else-if="m.role === 'assistant'" class="bubble ai">
              <text v-if="m.text" class="b-text">{{ m.text }}</text>
              <!-- 词卡：图左 + 词/音标/释义右；下方 例句 / 短语 / 发音·测发音 -->
              <view v-if="m.card" class="wcard">
                <view class="wcard-top">
                  <image v-if="m.card.image_urls && m.card.image_urls.length"
                    class="wcard-img" :src="m.card.image_urls[0]" mode="aspectFit" />
                  <view v-else class="wcard-img wcard-img-empty"><text>🖼️</text></view>
                  <view class="wcard-info">
                    <text class="wcard-word">{{ m.card.word }}</text>
                    <text v-if="m.card.phonetic" class="wcard-phon">{{ m.card.phonetic }}</text>
                    <text v-if="m.card.meaning" class="wcard-mean">{{ m.card.meaning }}</text>
                  </view>
                </view>
                <view v-if="m.card.example && m.card.example.en" class="wcard-row">
                  <text class="wcard-tag">例句</text>
                  <view class="wcard-rowtext">
                    <text class="wcard-en">{{ m.card.example.en }}</text>
                    <text v-if="m.card.example.zh" class="wcard-zh">{{ m.card.example.zh }}</text>
                  </view>
                </view>
                <view v-if="m.card.phrase && m.card.phrase.en" class="wcard-row">
                  <text class="wcard-tag">短语</text>
                  <view class="wcard-rowtext">
                    <text class="wcard-en">{{ m.card.phrase.en }}</text>
                    <text v-if="m.card.phrase.zh" class="wcard-zh">{{ m.card.phrase.zh }}</text>
                  </view>
                </view>
                <view class="wcard-btns">
                  <text class="wcard-btn" @tap="playWord(m.card)">🔊 发音</text>
                  <text class="wcard-btn primary" @tap="openPron(m.card.word)">🎤 测发音</text>
                </view>
              </view>
              <view v-if="m.text" class="b-tools">
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

      <!-- 输入条（微信式：默认语音，可切键盘）-->
      <view class="input-bar">
        <!-- #ifdef MP-WEIXIN -->
        <view class="mode-toggle" @tap="toggleMode">
          <text class="mt-ico">{{ inputMode === 'voice' ? '⌨' : '🎙' }}</text>
        </view>
        <view
          v-if="inputMode === 'voice'"
          class="hold-btn" :class="{ holding: recording }"
          @touchstart="micStart" @touchmove="micMove"
          @touchend="micEnd" @touchcancel="micEnd"
        >{{ recording ? '松开 发送' : '按住 说话' }}</view>
        <!-- #endif -->
        <input
          v-if="inputMode === 'text'"
          class="ti" v-model="draft" type="text" confirm-type="send"
          placeholder="说点什么…" @confirm="send"
        />
        <button
          v-if="inputMode === 'text'"
          class="send" :disabled="!draft.trim() || thinking" @tap="send"
        >发送</button>
      </view>
    </view>

    <!-- #ifdef MP-WEIXIN -->
    <!-- 微信式「按住说话」录音浮层 -->
    <view v-if="recording" class="rec-mask">
      <view class="rec-panel" :class="{ cancel: cancelZone }">
        <view v-if="!cancelZone" class="rec-wave">
          <view v-for="i in 5" :key="i" class="wbar" :style="{ animationDelay: (i * 0.12) + 's' }" />
        </view>
        <text v-else class="rec-cancel-ico">✕</text>
      </view>
      <text class="rec-tip" :class="{ cancel: cancelZone }">
        {{ cancelZone ? '松开手指，取消发送' : '正在聆听… 上滑取消' }}
      </text>
    </view>
    <!-- #endif -->

    <!-- 测发音弹窗（SOE 真实评测） -->
    <view v-if="pron.open" class="mask" @tap.self="closePron">
      <view class="pron-card" @tap.stop>
        <text class="pron-title">🎤 测发音</text>
        <text class="pron-word">{{ pron.word }}</text>
        <view v-if="!pron.result">
          <button
            class="pron-rec" :class="{ on: pron.recording }" :disabled="pron.scoring"
            @tap="pron.recording ? pronStop() : pronStart()"
          >{{ pron.scoring ? '评分中…' : (pron.recording ? '● 录音中，点击结束' : '开始朗读') }}</button>
          <text class="pron-hint">清楚地读出上面的单词</text>
        </view>
        <view v-else class="pron-result">
          <view class="pron-score" :class="`lv-${pron.result.level}`">
            <text class="pr-num">{{ pron.result.overall }}</text><text class="pr-unit">分</text>
          </view>
          <view v-if="pron.result.accuracy != null" class="pron-dims">
            <text class="pd">准确 {{ pron.result.accuracy }}</text>
            <text class="pd">流利 {{ pron.result.fluency }}</text>
            <text class="pd">完整 {{ pron.result.completion }}</text>
          </view>
          <text class="pron-tip">💡 {{ pron.result.tip }}</text>
          <button class="pron-rec" @tap="openPron(pron.word)">🔁 再测</button>
        </view>
        <text class="pron-close" @tap="closePron">关闭</text>
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
        <view v-if="summary.checkin" class="checkin-line">
          ✅ 已计入今日打卡 · 连续 <text class="cl-num">{{ summary.checkin.current_streak }}</text> 天 🔥
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
          <button
            v-if="summary.focus_missed && summary.focus_missed.length"
            class="repractice" @tap="repracticeMissed"
          >🔁 再练这 {{ summary.focus_missed.length }} 个没用到的词</button>
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
import { nextTick, onMounted, reactive, ref } from 'vue'
import {
  getSpeakScenarios, startSpeak, replySpeak, summarizeSpeak, getVocabCards,
  type SpeakScenario, type SpeakTurn, type SpeakSummary, type VocabCard,
} from '@/api/speaking'
import { shadowScore, type ShadowScoreResult } from '@/api/vocabulary'
import { resolveSpeakUrl } from '@/utils/tts'

interface Msg {
  role: 'user' | 'assistant' | 'system'
  text: string
  audio?: string
  translation?: string
  correction?: string
  showTr?: boolean
  playing?: boolean
  card?: VocabCard | null   // 词力通：随气泡一起出的词卡（文字+音标+图片）
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
const cancelZone = ref(false)
const autoPlay = ref(true)   // AI 回复自动播放语音
const readSentences = ref(true)  // 词力通：词卡同时连播例句/短语
const targetWords = ref<string[]>([])   // 词力通场景的目标词（供测发音）
// 词卡学习模式（词力通场景）
const vocabMode = ref(false)
const cards = ref<VocabCard[]>([])
const cardIdx = ref(0)
// 测发音弹窗（复用词力通跟读的 SOE 评测）
const pron = reactive<{
  open: boolean; word: string; recording: boolean; scoring: boolean
  result: ShadowScoreResult | null
}>({ open: false, word: '', recording: false, scoring: false, result: null })
// 输入模式：微信端默认语音，H5 只用文字
const inputMode = ref<'voice' | 'text'>('text')
// #ifdef MP-WEIXIN
inputMode.value = 'voice'
// #endif
function toggleMode() {
  if (recording.value) return
  inputMode.value = inputMode.value === 'voice' ? 'text' : 'voice'
}
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

function repracticeMissed() {
  const missed = summary.value?.focus_missed || []
  if (!missed.length) return
  summary.value = null
  start('words:' + missed.join('|'))
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
  targetWords.value = []
  vocabMode.value = key === 'vocab' || key.startsWith('words:')
  cards.value = []
  cardIdx.value = 0
  phase.value = 'chat'
  thinking.value = true
  try {
    if (vocabMode.value) {
      cards.value = await getVocabCards()
      if (!cards.value.length) vocabMode.value = false
    }
    const o = await startSpeak(key)
    targetWords.value = o.target_words || []
    if (vocabMode.value) {
      cardIdx.value = 0
      pushAi('', '', '', '', cards.value[0])
    } else {
      pushAi(o.ai_text, o.ai_audio_url)
    }
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '开始失败', icon: 'none' })
  } finally {
    thinking.value = false
  }
}

// 顺序播放队列（词 →可选 例句 → 短语）
function _playUrls(urls: string[]) {
  _queue = urls.filter(Boolean)
  ensureAudioCtx()
  _cur = null
  if (_queue.length && _ctx) { _ctx.src = _queue[0]; _ctx.play() }
}
async function playWord(c?: VocabCard | null) {
  if (!c) return
  const u = c.audio_url || await resolveSpeakUrl(c.word)
  _playUrls([u])
}
async function playCard(c?: VocabCard | null) {
  if (!c) return
  const urls: string[] = [c.audio_url || await resolveSpeakUrl(c.word)]
  if (readSentences.value) {
    if (c.example && c.example.en) urls.push(await resolveSpeakUrl(c.example.en))
    if (c.phrase && c.phrase.en) urls.push(await resolveSpeakUrl(c.phrase.en))
  }
  _playUrls(urls)
}

function pushAi(text: string, audio: string, translation = '', correction = '', card: VocabCard | null = null) {
  const msg: Msg = { role: 'assistant', text, audio, translation, correction, showTr: false, card }
  messages.value.push(msg)
  scrollToEnd()
  if (card && autoPlay.value) playCard(card)        // 词卡：自动播单词(+开关:例句/短语)
  else if (audio && autoPlay.value) playAudio(msg)  // 普通回复：自动播 AI 语音
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
    // 词力通：AI 点评后带出下一个词卡（文字+音标+图片一起出）
    let nextCard: VocabCard | null = null
    if (vocabMode.value && cardIdx.value < cards.value.length - 1) {
      cardIdx.value += 1
      nextCard = cards.value[cardIdx.value]
    }
    pushAi(r.ai_text, nextCard ? '' : r.ai_audio_url, r.translation, r.correction, nextCard)
    if (r.mastered_wrong) {
      messages.value.push({
        role: 'system',
        text: `🎉 答对了！「${r.mastered_wrong.kp}」这道错题已通过复习，待复习剩 ${r.mastered_wrong.due_left} 道`,
      })
      scrollToEnd()
      uni.showToast({ title: '错题复习 +1 ✅', icon: 'success' })
    }
    if (r.vocab_practiced && r.vocab_practiced.length) {
      const ws = r.vocab_practiced.map(v => v.word).join('、')
      messages.value.push({ role: 'system', text: `🔤 用对了「${ws}」，熟练度 +1` })
      scrollToEnd()
    }
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
let _queue: string[] = []
function ensureAudioCtx() {
  if (!_ctx) {
    _ctx = uni.createInnerAudioContext()
    const next = () => {
      _queue.shift()
      if (_queue.length && _ctx) { _ctx.src = _queue[0]; _ctx.play() }
      else if (_cur) _cur.playing = false
    }
    _ctx.onEnded(next)
    _ctx.onStop(() => { _queue = []; if (_cur) _cur.playing = false })
    _ctx.onError(() => { _queue = []; if (_cur) _cur.playing = false })
  }
  return _ctx
}
function playAudio(m: Msg) {
  if (!m.audio) { uni.showToast({ title: '暂无语音', icon: 'none' }); return }
  ensureAudioCtx()
  if (_cur && _cur !== m) _cur.playing = false   // 切换播放对象：重设 src 自动中断上一段
  _cur = m
  m.playing = true
  _queue = [m.audio]
  if (_ctx) { _ctx.src = m.audio; _ctx.play() }
}

function leave() {
  if (_cur && _ctx) { try { _ctx.stop() } catch { /* ignore */ } }
  phase.value = 'pick'
}

// ── 测发音（录音 → 复用词力通 SOE 评测）──
let _pronRec: UniApp.RecorderManager | null = null
let _pronBound = false
function ensurePronRecorder(): UniApp.RecorderManager {
  if (!_pronRec) _pronRec = uni.getRecorderManager()
  if (!_pronBound) {
    _pronRec.onStop((res) => { pronReadAndScore((res as { tempFilePath?: string }).tempFilePath || '') })
    _pronBound = true
  }
  return _pronRec
}
function openPron(word: string) {
  pron.word = word; pron.result = null; pron.recording = false; pron.scoring = false; pron.open = true
}
function closePron() { pron.open = false }
function pronStart() {
  pron.result = null
  // #ifdef MP-WEIXIN
  try {
    ensurePronRecorder().start({ format: 'mp3', sampleRate: 16000, numberOfChannels: 1, encodeBitRate: 48000, duration: 15000 })
    pron.recording = true
    return
  } catch { /* fallthrough */ }
  // #endif
  pron.recording = true
}
function pronStop() {
  pron.recording = false
  pron.scoring = true
  // #ifdef MP-WEIXIN
  try { _pronRec?.stop(); return } catch { /* ignore */ }
  // #endif
  pronReadAndScore('')
}
async function pronReadAndScore(path: string) {
  let audio = ''
  if (path) {
    audio = await new Promise<string>((resolve) => {
      try {
        uni.getFileSystemManager().readFile({
          filePath: path, encoding: 'base64',
          success: (r) => resolve((r.data as string) || ''), fail: () => resolve(''),
        })
      } catch { resolve('') }
    })
  }
  try {
    pron.result = await shadowScore(pron.word, audio, 'mp3')
  } catch (e) {
    uni.showToast({ title: (e as Error).message || '评分失败', icon: 'none' })
  } finally {
    pron.scoring = false
  }
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
      _busy = false
      if (_canceled) { _canceled = false; return }   // 上滑取消：丢弃结果
      const text = (res && res.result || '').trim()
      if (text) { draft.value = text; send() }
      else uni.showToast({ title: '没听清，再说一次或打字', icon: 'none' })
    }
    _mgr.onError = (res: any) => {
      recording.value = false
      _busy = false
      if (_canceled) { _canceled = false; return }
      // eslint-disable-next-line no-console
      console.warn('[WechatSI onError]', JSON.stringify(res))
      const raw = res && (res.msg || res.errMsg) || ''
      const friendly = /finish|忙|wait/i.test(raw) ? '识别还在处理，请稍候再说' : '语音识别失败，请打字'
      uni.showToast({ title: friendly, icon: 'none', duration: 2000 })
    }
    return _mgr
  } catch (e) {
    // eslint-disable-next-line no-console
    console.warn('[WechatSI requirePlugin 失败]', e)
    return null
  }
}
let _recStartAt = 0
let _startY = 0
let _busy = false       // 上一句识别处理中（stop 后等 onStop/onError）
let _canceled = false   // 本次上滑取消
const CANCEL_DY = 80    // 上滑超过此距离(px)进入取消区

function micStart(e: any) {
  if (_busy) { uni.showToast({ title: '上一句还在识别，请稍候', icon: 'none' }); return }
  const mgr = getMgr()
  if (!mgr) { uni.showToast({ title: '未启用语音插件，请打字', icon: 'none' }); return }
  _startY = e?.touches?.[0]?.clientY ?? e?.changedTouches?.[0]?.clientY ?? 0
  cancelZone.value = false
  _canceled = false
  recording.value = true
  _recStartAt = Date.now()
  try { mgr.start({ lang: 'en_US', duration: 30000 }) } catch (e2) {
    recording.value = false
    // eslint-disable-next-line no-console
    console.warn('[WechatSI start 失败]', e2)
    uni.showToast({ title: '无法开始录音，请打字', icon: 'none' })
  }
}
function micMove(e: any) {
  if (!recording.value) return
  const y = e?.touches?.[0]?.clientY ?? 0
  cancelZone.value = (_startY - y) > CANCEL_DY
}
function micEnd() {
  if (!recording.value) return
  recording.value = false
  const wasCancel = cancelZone.value
  cancelZone.value = false
  if (Date.now() - _recStartAt < 400) {
    _canceled = true
    try { getMgr()?.stop() } catch { /* ignore */ }
    uni.showToast({ title: '按住说话时间太短', icon: 'none' })
    return
  }
  if (wasCancel) {
    _canceled = true
    try { getMgr()?.stop() } catch { /* ignore */ }
    uni.showToast({ title: '已取消', icon: 'none' })
    return
  }
  _busy = true   // 进入识别处理，结果回来前不允许再次开始
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
.grid { display: flex; flex-wrap: wrap; justify-content: space-between; padding: 12rpx 24rpx; }
.sc-card { width: 48%; box-sizing: border-box; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 22rpx 20rpx; margin-bottom: 18rpx; box-shadow: 0 4rpx 24rpx rgba(0,0,0,.04); display: flex; flex-direction: column; gap: 8rpx; }
.sc-card.custom { background: linear-gradient(160deg, var(--c-primary-faint), var(--c-bg-card)); border: 2rpx solid var(--c-primary-soft); }
.sc-top { display: flex; align-items: center; justify-content: space-between; }
.sc-tag { font-size: 18rpx; font-weight: 700; color: var(--c-primary-deep); background: #fff; padding: 3rpx 12rpx; border-radius: var(--r-pill); }
.sc-emoji { font-size: 40rpx; }
.sc-title { font-size: 28rpx; font-weight: 800; color: var(--c-ink); }
.sc-open { font-size: 21rpx; color: var(--c-text-hint); line-height: 1.45; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.chat-wrap { display: flex; flex-direction: column; height: 100vh; }

/* 气泡内词卡：图左+词右，例句/短语/按钮分行（按布局2）*/
.wcard { margin-top: 14rpx; background: var(--c-bg-card); border-radius: 16rpx; padding: 18rpx; display: flex; flex-direction: column; }
.wcard-top { display: flex; gap: 18rpx; padding-bottom: 16rpx; border-bottom: 1rpx solid var(--c-border); }
.wcard-img { width: 320rpx; height: 300rpx; border-radius: 12rpx; flex-shrink: 0; background: var(--c-bg-soft); }
.wcard-img-empty { display: flex; align-items: center; justify-content: center; font-size: 72rpx; opacity: .5; }
.wcard-info { flex: 1; display: flex; flex-direction: column; justify-content: center; gap: 8rpx; min-width: 0; }
.wcard-word { font-size: 46rpx; font-weight: 900; color: var(--c-ink); }
.wcard-phon { font-size: 26rpx; color: var(--c-text-second); }
.wcard-mean { font-size: 30rpx; color: var(--c-text-body); font-weight: 600; }
.wcard-row { display: flex; gap: 14rpx; padding: 14rpx 0; border-bottom: 1rpx solid var(--c-border); }
.wcard-tag { flex-shrink: 0; font-size: 22rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 4rpx 14rpx; border-radius: var(--r-pill); height: 32rpx; line-height: 32rpx; }
.wcard-rowtext { flex: 1; display: flex; flex-direction: column; gap: 4rpx; min-width: 0; }
.wcard-en { font-size: 28rpx; color: var(--c-text-body); line-height: 1.45; }
.wcard-zh { font-size: 24rpx; color: var(--c-text-hint); line-height: 1.4; }
.wcard-btns { display: flex; gap: 14rpx; padding-top: 16rpx; }
.wcard-btn { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 10rpx 30rpx; border-radius: var(--r-pill); }
.wcard-btn.primary { background: var(--c-primary); color: var(--c-on-primary); }
.chat { flex: 1; min-height: 0; }
.chat-inner { padding: 24rpx 24rpx 12rpx; display: flex; flex-direction: column; gap: 18rpx; }
.row { display: flex; }
.row.assistant { justify-content: flex-start; }
.row.user { justify-content: flex-end; }
.row.system { justify-content: center; }
.sys-banner { max-width: 88%; background: #e6f8ee; color: #18a058; border-radius: 16rpx; padding: 14rpx 22rpx; font-size: 24rpx; font-weight: 600; line-height: 1.5; text-align: center; }
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
.mode-toggle { flex-shrink: 0; width: 76rpx; height: 76rpx; border-radius: 50%; background: var(--c-bg-soft); display: flex; align-items: center; justify-content: center; }
.mt-ico { font-size: 40rpx; color: var(--c-text-body); line-height: 1; }
.hold-btn { flex: 1; height: 76rpx; line-height: 76rpx; text-align: center; border-radius: var(--r-pill); background: #fff; border: 2rpx solid var(--c-border); font-size: 30rpx; font-weight: 700; color: var(--c-text-body); }
.hold-btn.holding { background: var(--c-primary-faint); border-color: var(--c-primary); color: var(--c-primary-deep); }

/* 微信式录音浮层 */
.rec-mask { position: fixed; inset: 0; background: rgba(0,0,0,.35); display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 28rpx; z-index: 60; }
.rec-panel { width: 240rpx; height: 240rpx; border-radius: 36rpx; background: rgba(40,44,52,.92); display: flex; align-items: center; justify-content: center; box-shadow: 0 12rpx 48rpx rgba(0,0,0,.3); }
.rec-panel.cancel { background: rgba(214,69,69,.95); }
.rec-wave { display: flex; align-items: center; gap: 10rpx; height: 90rpx; }
.wbar { width: 12rpx; height: 28rpx; border-radius: 6rpx; background: #7ee0a8; animation: wave .8s ease-in-out infinite; }
@keyframes wave { 0%,100% { height: 24rpx; opacity:.6 } 50% { height: 84rpx; opacity:1 } }
.rec-cancel-ico { color: #fff; font-size: 96rpx; font-weight: 800; }
.rec-tip { font-size: 26rpx; color: #fff; background: rgba(0,0,0,.4); padding: 10rpx 28rpx; border-radius: var(--r-pill); }
.rec-tip.cancel { background: rgba(214,69,69,.9); }
.ti { flex: 1; background: var(--c-bg-soft); border-radius: var(--r-pill); padding: 18rpx 24rpx; font-size: 28rpx; color: var(--c-text-body); }
.send { flex-shrink: 0; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 28rpx; font-weight: 700; padding: 0 30rpx; height: 72rpx; line-height: 72rpx; }
.send[disabled] { background: var(--c-primary-soft); color: #9aa7b8; }

.chat-top { display: flex; align-items: center; justify-content: space-between; padding: 14rpx 24rpx; background: var(--c-bg-card); box-shadow: 0 2rpx 12rpx rgba(0,0,0,.04); }
.ct-leave { font-size: 26rpx; color: var(--c-text-hint); }
.ct-right { display: flex; align-items: center; gap: 14rpx; }
.ct-auto { font-size: 24rpx; color: var(--c-text-hint); }
.ct-auto.on { color: var(--c-primary-deep); }
.ct-end { font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 8rpx 22rpx; border-radius: var(--r-pill); }

/* 测发音 chips 条 */
.pron-bar { white-space: nowrap; padding: 12rpx 20rpx; background: var(--c-bg-card); border-top: 1rpx solid var(--c-border); }
.pron-lead { font-size: 22rpx; color: var(--c-text-hint); margin-right: 10rpx; }
.pron-chip { display: inline-block; font-size: 26rpx; font-weight: 700; color: var(--c-primary-deep); background: var(--c-primary-faint); padding: 8rpx 22rpx; border-radius: var(--r-pill); margin-right: 12rpx; }
/* 测发音弹窗 */
.pron-card { width: 100%; max-width: 560rpx; background: var(--c-bg-card); border-radius: 28rpx; padding: 36rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; }
.pron-title { font-size: 30rpx; font-weight: 800; color: var(--c-ink); }
.pron-word { font-size: 48rpx; font-weight: 900; color: var(--c-primary-deep); }
.pron-rec { width: 100%; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 22rpx; font-size: 30rpx; font-weight: 700; }
.pron-rec.on { background: var(--c-danger, #e64f4f); }
.pron-hint { font-size: 22rpx; color: var(--c-text-hint); margin-top: 10rpx; text-align: center; display: block; }
.pron-result { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 12rpx; }
.pron-score { display: flex; align-items: baseline; gap: 4rpx; }
.pr-num { font-size: 72rpx; font-weight: 900; color: var(--c-primary); }
.pron-score.lv-excellent .pr-num, .pron-score.lv-good .pr-num { color: #18a058; }
.pron-score.lv-poor .pr-num { color: var(--c-danger, #e64f4f); }
.pr-unit { font-size: 26rpx; color: var(--c-text-hint); }
.pron-dims { display: flex; gap: 16rpx; }
.pd { font-size: 22rpx; color: var(--c-text-second); background: var(--c-bg-soft); padding: 4rpx 16rpx; border-radius: var(--r-pill); }
.pron-tip { font-size: 25rpx; color: var(--c-text-second); text-align: center; line-height: 1.5; }
.pron-close { font-size: 24rpx; color: var(--c-text-hint); margin-top: 6rpx; }
.mask { position: fixed; inset: 0; background: rgba(0,0,0,.45); display: flex; align-items: center; justify-content: center; z-index: 50; padding: 40rpx; }
.sheet { width: 100%; max-width: 620rpx; background: var(--c-bg-card); border-radius: 28rpx; padding: 36rpx 32rpx; display: flex; flex-direction: column; align-items: center; gap: 16rpx; max-height: 86vh; overflow-y: auto; }
.sh-title { font-size: 34rpx; font-weight: 800; color: var(--c-ink); }
.score-ring { width: 160rpx; height: 160rpx; border-radius: 50%; background: var(--c-primary-faint); border: 8rpx solid var(--c-primary); display: flex; align-items: baseline; justify-content: center; gap: 4rpx; }
.sr-num { font-size: 64rpx; font-weight: 900; color: var(--c-primary-deep); }
.sr-unit { font-size: 24rpx; color: var(--c-primary-deep); }
.checkin-line { font-size: 24rpx; color: #18a058; background: #e6f8ee; border-radius: var(--r-pill); padding: 8rpx 24rpx; font-weight: 600; }
.cl-num { font-size: 30rpx; font-weight: 900; color: #18a058; }
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
.repractice { margin-top: 12rpx; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); font-size: 25rpx; font-weight: 700; padding: 14rpx 0; }
.encour { font-size: 26rpx; color: var(--c-primary-deep); text-align: center; line-height: 1.6; margin-top: 4rpx; }
.sheet-btns { display: flex; gap: 16rpx; width: 100%; margin-top: 12rpx; }
.btn-ghost { flex: 1; background: var(--c-bg-soft); color: var(--c-text-body); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; }
.btn-fill { flex: 1; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-btn); padding: 20rpx; font-size: 28rpx; font-weight: 700; }
</style>

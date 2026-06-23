<!-- 通用跟读评测弹窗（录音→SOE评分→逐词反馈）。scorer 解耦：词力通/听力等复用 -->
<template>
  <view v-if="open" class="shadow-modal" @tap.self="close">
    <view class="shadow-card">
      <view class="shadow-title" style="display:flex;align-items:center;gap:10rpx"><view class="ic ic-mic" style="width:34rpx;height:34rpx" /><text>跟读练习</text></view>
      <text class="shadow-sentence">{{ text }}</text>

      <view class="shadow-tools">
        <view class="shadow-demo" @tap="playDemo" style="display:flex;align-items:center;gap:8rpx"><view class="ic ic-volume" style="width:30rpx;height:30rpx" /><text>示范</text></view>
      </view>

      <view v-if="!result" class="shadow-rec-area">
        <button class="shadow-rec-btn" :class="{ recording }" :disabled="scoring"
          @tap="recording ? stopAndScore() : startRecord()">
          {{ scoring ? '评分中…' : (recording ? '● 录音中，点击结束' : '开始跟读') }}
        </button>
        <text class="shadow-hint">点击开始，朗读上面的句子</text>
      </view>

      <view v-else class="shadow-result">
        <view class="shadow-score" :class="`lv-${result.level}`">
          <text class="ss-num">{{ result.overall }}</text>
          <text class="ss-unit">分 · {{ levelLabel(result.level) }}</text>
        </view>
        <view v-if="result.accuracy != null" class="shadow-dims">
          <text class="sd">准确度 {{ result.accuracy }}</text>
          <text class="sd">流利度 {{ result.fluency }}</text>
          <text class="sd">完整度 {{ result.completion }}</text>
        </view>
        <view class="shadow-words">
          <text v-for="(w, i) in (result.words || [])" :key="i" class="sw-chip" :class="{ weak: w.score < 80 }">
            {{ w.word }} <text class="sw-score">{{ w.score }}</text>
          </text>
        </view>
        <view v-if="result.tip" class="shadow-tip" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-idea" style="width:30rpx;height:30rpx;flex:none" /><text>{{ result.tip }}</text></view>
        <view class="shadow-actions">
          <button class="btn-primary half" @tap="retry" style="display:flex;align-items:center;justify-content:center;gap:8rpx"><view class="ic ic-refresh" style="width:30rpx;height:30rpx;filter:brightness(0) invert(1)" /><text>重跟</text></button>
        </view>
      </view>

      <text class="shadow-close" @tap="close">关闭</text>
    </view>
  </view>
</template>

<script setup lang="ts">
import { reactive, ref, toRefs, watch } from 'vue'
import { resolveSpeakUrl, gradeToStage } from '@/utils/tts'
import { useAuthStore } from '@/stores/auth'

interface ShadowResult {
  overall: number; level: string; accuracy?: number | null; fluency?: number | null
  completion?: number | null; words?: { word: string; score: number }[]; tip?: string
}
const props = defineProps<{
  open: boolean
  text: string
  scorer: (text: string, audioB64: string, fmt: string) => Promise<ShadowResult>
}>()
const emit = defineEmits<{ (e: 'close'): void; (e: 'paywall'): void; (e: 'scored', r: ShadowResult): void }>()
const { open, text } = toRefs(props)

const auth = useAuthStore()
const recording = ref(false)
const scoring = ref(false)
const result = ref<ShadowResult | null>(null)

watch(open, (v) => { if (v) { recording.value = false; scoring.value = false; result.value = null } })

function levelLabel(lv: string) {
  return ({ excellent: '优秀', good: '良好', fair: '一般', poor: '加油' } as Record<string, string>)[lv] || ''
}

function close() {
  // #ifdef MP-WEIXIN
  if (recording.value) { try { _recorder?.stop() } catch { /* ignore */ } }
  // #endif
  recording.value = false
  emit('close')
}

let _ctx: UniApp.InnerAudioContext | null = null
async function playDemo() {
  if (!_ctx) _ctx = uni.createInnerAudioContext()
  _ctx.src = await resolveSpeakUrl(text.value, gradeToStage((auth.user as any)?.preferred_grade))
  _ctx.play()
}

let _recorder: UniApp.RecorderManager | null = null
let _bound = false
function ensureRecorder(): UniApp.RecorderManager {
  if (!_recorder) _recorder = uni.getRecorderManager()
  if (!_bound) {
    _recorder.onStop((res) => { readAndScore((res as { tempFilePath?: string }).tempFilePath || '') })
    _bound = true
  }
  return _recorder
}

function startRecord() {
  result.value = null
  // #ifdef MP-WEIXIN
  try {
    ensureRecorder().start({ format: 'mp3', sampleRate: 16000, numberOfChannels: 1, encodeBitRate: 48000, duration: 60000 })
    recording.value = true
    return
  } catch { /* 退回直接评分 */ }
  // #endif
  recording.value = true
}

function stopAndScore() {
  recording.value = false
  scoring.value = true
  // #ifdef MP-WEIXIN
  try { _recorder?.stop(); return } catch { /* ignore */ }
  // #endif
  readAndScore('')
}

async function readAndScore(path: string) {
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
    result.value = await props.scorer(text.value, audio, 'mp3')
    if (result.value) emit('scored', result.value)
  } catch (e) {
    if ((e as { code?: number }).code === 402) { emit('close'); emit('paywall') }
    else uni.showToast({ title: (e as Error).message || '评分失败', icon: 'none' })
  } finally {
    scoring.value = false
  }
}

function retry() { result.value = null }
</script>

<style scoped>
.shadow-modal { position: fixed; inset: 0; background: rgba(0,0,0,.5); display: flex; align-items: center; justify-content: center; z-index: 1100; }
.shadow-card { width: 600rpx; background: var(--c-bg-card); border-radius: var(--r-lg); padding: 36rpx 30rpx; display: flex; flex-direction: column; align-items: center; gap: 18rpx; }
.shadow-title { font-size: 32rpx; font-weight: 800; color: var(--c-ink); }
.shadow-sentence { font-size: 30rpx; color: var(--c-text-body); text-align: center; line-height: 1.6; }
.shadow-tools { display: flex; gap: 24rpx; }
.shadow-demo { font-size: 26rpx; color: var(--c-primary-deep); }
.shadow-rec-area { display: flex; flex-direction: column; align-items: center; gap: 12rpx; width: 100%; }
.shadow-rec-btn { width: 100%; background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); height: 84rpx; line-height: 84rpx; font-size: 30rpx; font-weight: 700; }
.shadow-rec-btn.recording { background: var(--c-danger); }
.shadow-hint { font-size: 22rpx; color: var(--c-text-hint); }
.shadow-result { width: 100%; display: flex; flex-direction: column; align-items: center; gap: 14rpx; }
.shadow-score { display: flex; align-items: baseline; gap: 8rpx; }
.ss-num { font-size: 72rpx; font-weight: 900; color: var(--c-primary); }
.ss-unit { font-size: 26rpx; color: var(--c-text-second); }
.lv-poor .ss-num { color: var(--c-danger); }
.lv-fair .ss-num { color: #ffb020; }
.shadow-dims { display: flex; gap: 20rpx; }
.sd { font-size: 24rpx; color: var(--c-text-second); }
.shadow-words { display: flex; flex-wrap: wrap; gap: 10rpx; justify-content: center; }
.sw-chip { font-size: 26rpx; color: var(--c-text-body); background: var(--c-bg-soft); border-radius: 8rpx; padding: 6rpx 12rpx; }
.sw-chip.weak { background: var(--c-danger-bg); color: var(--c-danger); }
.sw-score { font-size: 20rpx; opacity: .7; }
.shadow-tip { font-size: 24rpx; color: var(--c-text-second); text-align: center; }
.shadow-actions { display: flex; gap: 16rpx; width: 100%; }
.btn-primary { background: var(--c-primary); color: var(--c-on-primary); border-radius: var(--r-pill); height: 80rpx; line-height: 80rpx; font-size: 28rpx; font-weight: 700; }
.btn-primary.half { flex: 1; }
.shadow-close { font-size: 26rpx; color: var(--c-text-hint); padding: 4rpx; }
</style>

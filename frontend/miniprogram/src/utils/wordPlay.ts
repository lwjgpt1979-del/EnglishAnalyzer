/**
 * 词卡式发音公共播放器(方案 P1)。
 * - 统一偏好:例句连读 / 打开自动播(见 readSeq.ts)
 * - 词卡入口一律走 playWordMedia;听力/长难句/跟读示范等勿用
 */
import { resolveSpeakUrl } from '@/utils/tts'
import { getReadSeq, getCardAutoPlay } from '@/utils/readSeq'

export type WordPlayLine = { en?: string | null; audio?: string | null } | null | undefined

/** 词卡可播媒体 */
export type WordPlayMedia = {
  word: string
  /** 单词预生成音频;缺则 TTS */
  wordAudio?: string | null
  example?: WordPlayLine
  phrase?: WordPlayLine
}

/** tap=点发音;open=打开词卡(受 autoPlay 闸门);word=强制只播单词 */
export type WordPlayMode = 'tap' | 'open' | 'word'

export type WordPlaySegment = 'word' | 'example' | 'phrase'

export type WordPlayOptions = {
  mode?: WordPlayMode
  onStart?: () => void
  /** 每段开始(index 从 0) */
  onSegment?: (kind: WordPlaySegment, index: number) => void
  onEnd?: () => void
  onError?: (msg: string) => void
}

type QueueItem = { url: string; kind: WordPlaySegment }

let _audio: UniApp.InnerAudioContext | null = null
let _queue: QueueItem[] = []
let _qi = 0
let _opts: WordPlayOptions | null = null
let _playing = false

function destroyAudio() {
  if (!_audio) return
  try { _audio.stop(); _audio.destroy() } catch { /* ignore */ }
  _audio = null
}

/** 停止当前词卡播放队列 */
export function stopWordPlay() {
  _queue = []
  _qi = 0
  _playing = false
  const cb = _opts
  _opts = null
  destroyAudio()
  cb?.onEnd?.()
}

/** @returns 是否正在播词卡队列 */
export function isWordPlaying(): boolean {
  return _playing
}

/**
 * 顺序播放 URL 队列(底层;词卡外偶发复用也可)。
 * @param items 带 kind 的地址
 * @param opts 回调
 */
export function playWordQueue(items: QueueItem[], opts?: WordPlayOptions) {
  // 换曲打断:停旧音频;旧 onEnd 仍触发以清 UI「播放中」
  stopWordPlay()

  const list = items.filter(x => !!x.url)
  if (!list.length) return
  _queue = list
  _qi = 0
  _opts = opts || null
  _playing = true
  opts?.onStart?.()

  const playNext = () => {
    if (_qi >= _queue.length) {
      _playing = false
      const cb = _opts
      _opts = null
      destroyAudio()
      cb?.onEnd?.()
      return
    }
    const item = _queue[_qi]
    _opts?.onSegment?.(item.kind, _qi)
    const ctx = uni.createInnerAudioContext()
    _audio = ctx
    ctx.src = item.url
    ctx.onEnded(() => {
      _qi += 1
      try { ctx.destroy() } catch { /* ignore */ }
      if (_audio === ctx) _audio = null
      playNext()
    })
    ctx.onError(() => {
      _playing = false
      destroyAudio()
      const msg = '发音播放失败'
      _opts?.onError?.(msg)
      uni.showToast({ title: msg, icon: 'none' })
    })
    ctx.play()
  }
  playNext()
}

/**
 * 只播一条 URL(如测验题干单字、TTS 文本)。
 * @param url 音频地址
 * @param opts 回调
 */
export function playAudioUrl(url: string | null | undefined, opts?: WordPlayOptions) {
  if (!url) return
  playWordQueue([{ url, kind: 'word' }], opts)
}

/**
 * 解析文本 → 可播 URL(优先调用方已给 audio)。
 * @param text 英文
 * @param audio 预生成
 */
async function resolveLine(text: string | null | undefined, audio?: string | null): Promise<string | null> {
  const t = (text || '').trim()
  if (!t && !audio) return null
  if (audio) return audio
  if (!t) return null
  try {
    return await resolveSpeakUrl(t)
  } catch {
    return null
  }
}

/**
 * 词卡式播放入口。
 * - mode=tap: 尊重例句连读(词 → 例句 → 短语)
 * - mode=open: 自动播关则 no-op;开则等同 tap
 * - mode=word: 只播单词(测验/列表点音标等)
 */
export async function playWordMedia(media: WordPlayMedia, opts?: WordPlayOptions): Promise<void> {
  const mode: WordPlayMode = opts?.mode || 'tap'
  const word = (media.word || '').trim()
  if (!word) return

  if (mode === 'open' && !getCardAutoPlay()) {
    return
  }

  try {
    const items: QueueItem[] = []
    const wordUrl = await resolveLine(word, media.wordAudio)
    if (!wordUrl) {
      opts?.onError?.('发音获取失败')
      uni.showToast({ title: '发音获取失败', icon: 'none' })
      return
    }
    items.push({ url: wordUrl, kind: 'word' })

    const seq = mode !== 'word' && getReadSeq()
    if (seq) {
      const ex = media.example
      if (ex?.en) {
        const u = await resolveLine(ex.en, ex.audio)
        if (u) items.push({ url: u, kind: 'example' })
      }
      const ph = media.phrase
      if (ph?.en) {
        const u = await resolveLine(ph.en, ph.audio)
        if (u) items.push({ url: u, kind: 'phrase' })
      }
    }

    playWordQueue(items, opts)
  } catch {
    opts?.onError?.('发音获取失败')
    uni.showToast({ title: '发音获取失败', icon: 'none' })
  }
}

// 偏好 re-export,调用方可只引 wordPlay
export {
  getReadSeq, setReadSeq, getCardAutoPlay, setCardAutoPlay,
} from '@/utils/readSeq'

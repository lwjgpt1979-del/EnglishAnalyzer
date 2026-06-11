// src/utils/tts.ts —— 解析一段文本的可播放音频 URL
import { request } from '@/utils/request'

const BASE = (import.meta.env.VITE_API_BASE_URL as string) || 'http://localhost:8000'

/** 学段：控制听力语速（小学慢 / 初中标准 / 高中略快）。单词统一用 junior。 */
export type Stage = 'primary' | 'junior' | 'senior'

/** 由年级字符串（如「小学5年级」「初中7年级」「高中2年级」）推断学段，默认初中。 */
export function gradeToStage(grade?: string | null): Stage {
  const g = grade || ''
  if (g.includes('小学')) return 'primary'
  if (g.includes('高中')) return 'senior'
  return 'junior'
}

/**
 * 返回可播放的音频 URL：
 * - 后端配置了 COS → 返回 COS 直链（已持久化，命中即复用，不重复合成）
 * - 未配 COS → 回退到 /tts/speak 流式接口
 * stage 控制语速；不传默认 junior（初中），词力通单词即用此默认。
 */
export async function resolveSpeakUrl(text: string, stage: Stage = 'junior'): Promise<string> {
  const fallback = `${BASE}/api/v1/tts/speak?text=${encodeURIComponent(text)}&stage=${stage}`
  try {
    const r = await request<{ url: string }>(
      `/api/v1/tts/url?text=${encodeURIComponent(text)}&stage=${stage}`, { method: 'GET' },
    )
    return r?.url || fallback
  } catch {
    return fallback
  }
}
